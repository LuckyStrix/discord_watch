import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import {
  useChannels,
  useCreateWatch,
  useDeleteWatch,
  useReclassifyWatch,
  useTestWatch,
  useUpdateWatch,
  useWatches,
} from "../api/hooks";
import type { Guild, Watch } from "../api/types";

// Same two-layer save as notes_app's NoteViewerPage: debounce while typing,
// plus an immediate flush on blur so clicking away never loses an edit.
const AUTOSAVE_DELAY_MS = 800;

const BUILTIN_HINT: Record<string, string> = {
  guild:
    "Every readable channel here, including threads and channels added later. Channels listed below use their own criteria instead. Busy servers mean more to judge, so watch the waiting count.",
  all_dms: "Every direct message and group DM from people you've accepted.",
  requests: "Incoming friend requests and message requests from people who aren't friends yet.",
};

function CriteriaEditor({ watch }: { watch: Watch }) {
  const update = useUpdateWatch();
  const [draft, setDraft] = useState(watch.criteria);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const saved = useRef(watch.criteria);

  // Reset only when switching to a different watch -- not on every background
  // refetch, which would clobber in-progress typing.
  useEffect(() => {
    setDraft(watch.criteria);
    saved.current = watch.criteria;
  }, [watch.id]);

  const flush = (value: string) => {
    clearTimeout(timer.current);
    if (value === saved.current) return;
    saved.current = value;
    update.mutate({ id: watch.id, criteria: value });
  };

  return (
    <div className="criteria">
      <label htmlFor={`criteria-${watch.id}`}>What's important here?</label>
      <textarea
        id={`criteria-${watch.id}`}
        rows={3}
        value={draft}
        placeholder="e.g. Anyone asking me to fill a raid spot, schedule changes, or messages from officers. Memes and loot chatter aren't important."
        onChange={(e) => {
          const value = e.target.value;
          setDraft(value);
          clearTimeout(timer.current);
          timer.current = setTimeout(() => flush(value), AUTOSAVE_DELAY_MS);
        }}
        onBlur={() => flush(draft)}
      />
      <span className="muted small">{update.isPending ? "Saving…" : draft === saved.current ? "Saved" : ""}</span>
    </div>
  );
}

function WatchDetails({ watch, children }: { watch: Watch; children?: ReactNode }) {
  const update = useUpdateWatch();
  const del = useDeleteWatch();
  const test = useTestWatch();
  const reclassify = useReclassifyWatch();

  return (
    <>
      {BUILTIN_HINT[watch.kind] && <p className="muted small">{BUILTIN_HINT[watch.kind]}</p>}
      <CriteriaEditor watch={watch} />
      {children}
      <label
        className="toggle catch-up"
        title="Normally the startup catch-up only fetches channels Discord shows as unread."
      >
        <input
          type="checkbox"
          checked={watch.always_catch_up}
          onChange={(e) => update.mutate({ id: watch.id, always_catch_up: e.target.checked })}
        />
        Always catch up after downtime, even if Discord doesn't show it as unread (muted, or read on another
        device)
      </label>
      <div className="watch-actions">
        <button className="btn" disabled={test.isPending} onClick={() => test.mutate(watch.id)}>
          {test.isPending ? "Testing… (runs on CPU, may take a bit)" : "Test criteria on recent messages"}
        </button>
        <button
          className="btn ghost"
          disabled={reclassify.isPending}
          onClick={() => reclassify.mutate(watch.id)}
          title="Re-queue this section's items so they're judged again with the current criteria"
        >
          {reclassify.data ? `Re-judging ${reclassify.data.queued}` : "Re-judge all"}
        </button>
        {(watch.kind === "channel" || watch.kind === "guild") && (
          <button
            className="btn danger ghost"
            onClick={() => confirm(`Stop watching ${watch.label}? Its stored items are deleted.`) && del.mutate(watch.id)}
          >
            Remove
          </button>
        )}
      </div>
      {test.error && <p className="error">{String(test.error)}</p>}
      {test.data && (
        <div className="test-results">
          {test.data.length === 0 ? (
            <p className="muted">No stored messages for this section yet, so there's nothing to test against.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Message</th>
                  <th>Now</th>
                  <th>Before</th>
                  <th>Why</th>
                </tr>
              </thead>
              <tbody>
                {test.data.map((r) => (
                  <tr key={r.item_id}>
                    <td>
                      <strong>{r.author_name}</strong>: {r.content.slice(0, 160)}
                    </td>
                    <td>
                      <span className={`importance-tag tag-${r.importance ?? "pending"}`}>{r.importance ?? "?"}</span>
                      {r.needs_reply && <span className="tag tag-reply">reply</span>}
                    </td>
                    <td className="muted">{r.previous_importance ?? "—"}</td>
                    <td className="small">{r.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted small">Dry run: nothing was saved. Use "Re-judge all" to apply the new criteria.</p>
        </div>
      )}
    </>
  );
}

function Counts({ attention, pending }: { attention: number; pending: number }) {
  return (
    <>
      {attention > 0 && <span className="count-badge">{attention}</span>}
      {pending > 0 && <span className="muted small">{pending} waiting to be judged</span>}
    </>
  );
}

function EnabledToggle({ watch }: { watch: Watch }) {
  const update = useUpdateWatch();
  return (
    <label className="toggle">
      <input
        type="checkbox"
        checked={watch.enabled}
        onChange={(e) => update.mutate({ id: watch.id, enabled: e.target.checked })}
      />
      {watch.enabled ? "On" : "Off"}
    </label>
  );
}

/** DMs and requests: always-open cards, as before. */
function BuiltinCard({ watch }: { watch: Watch }) {
  return (
    <section className={`watch-card${watch.enabled ? "" : " disabled"}`}>
      <header className="watch-head">
        <h3>{watch.label}</h3>
        <Counts attention={watch.attention_count} pending={watch.pending_count} />
        <EnabledToggle watch={watch} />
      </header>
      <WatchDetails watch={watch} />
    </section>
  );
}

/** Channels and categories carved out of a whole-server watch, each with a
 * button to put it back. Names come from the live channel directory. */
function Exclusions({ watch, guild }: { watch: Watch; guild: Guild | undefined }) {
  const update = useUpdateWatch();
  const channelName = new Map(guild?.channels.map((c) => [c.channel_id, c.name]) ?? []);
  const categoryName = new Map(
    guild?.channels.filter((c) => c.category_id).map((c) => [c.category_id!, c.category ?? "category"]) ?? [],
  );
  const chips = [
    ...watch.excluded_category_ids.map((id) => ({
      key: `cat:${id}`,
      label: `${categoryName.get(id) ?? "unknown category"} (category)`,
      remove: () => update.mutate({ id: watch.id, excluded_category_ids: watch.excluded_category_ids.filter((x) => x !== id) }),
    })),
    ...watch.excluded_channel_ids.map((id) => ({
      key: `ch:${id}`,
      label: `#${channelName.get(id) ?? "deleted channel"}`,
      remove: () => update.mutate({ id: watch.id, excluded_channel_ids: watch.excluded_channel_ids.filter((x) => x !== id) }),
    })),
  ];
  if (chips.length === 0) return null;
  return (
    <div className="exclusions">
      <span className="muted small">Not watching:</span>
      {chips.map((c) => (
        <span key={c.key} className="chip">
          {c.label}
          <button title="Watch this again" disabled={update.isPending} onClick={c.remove}>
            ✕
          </button>
        </span>
      ))}
    </div>
  );
}

/** One channel's note, with the same debounce + flush-on-blur autosave as
 * CriteriaEditor. Saving sends only this channel's entry (the server merges),
 * so editing two notes back to back can't clobber either. */
function ChannelNoteEditor({
  watch,
  channelId,
  name,
  initial,
  onRemoved,
}: {
  watch: Watch;
  channelId: string;
  name: string;
  initial: string;
  onRemoved: () => void;
}) {
  const update = useUpdateWatch();
  const [draft, setDraft] = useState(initial);
  const saved = useRef(initial);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const flush = (value: string) => {
    clearTimeout(timer.current);
    if (value === saved.current || !value.trim()) return; // blank = not saved yet; use ✕ to remove
    saved.current = value;
    update.mutate({ id: watch.id, channel_notes: { [channelId]: value } });
  };

  const remove = () => {
    clearTimeout(timer.current);
    if (saved.current) update.mutate({ id: watch.id, channel_notes: { [channelId]: "" } });
    onRemoved();
  };

  return (
    <div className="channel-note">
      <div className="channel-note-head">
        <strong>#{name}</strong>
        <span className="muted small">{update.isPending ? "Saving…" : draft.trim() && draft === saved.current ? "Saved" : ""}</span>
        <button className="btn small ghost" title="Remove this note" onClick={remove}>
          ✕
        </button>
      </div>
      <textarea
        rows={2}
        value={draft}
        autoFocus={!initial}
        placeholder="Added to the server's criteria for this channel only, e.g. Also flag cameras or lenses under $50."
        onChange={(e) => {
          const value = e.target.value;
          setDraft(value);
          clearTimeout(timer.current);
          timer.current = setTimeout(() => flush(value), AUTOSAVE_DELAY_MS);
        }}
        onBlur={() => flush(draft)}
      />
    </div>
  );
}

/** Per-channel additions to a whole-server section's criteria. */
function ChannelNotes({ watch, guild }: { watch: Watch; guild: Guild | undefined }) {
  // Notes being written but not saved yet (a blank note isn't stored).
  const [adding, setAdding] = useState<string[]>([]);
  const channelName = new Map(guild?.channels.map((c) => [c.channel_id, c.name]) ?? []);
  const ids = [...Object.keys(watch.channel_notes), ...adding.filter((id) => !(id in watch.channel_notes))];
  const available = (guild?.channels ?? []).filter((c) => !ids.includes(c.channel_id));

  return (
    <div className="channel-notes">
      <div className="channel-notes-head">
        <span className="small">
          <strong>Channel notes</strong>{" "}
          <span className="muted">extra criteria for one channel, added to the server's</span>
        </span>
        <select
          value=""
          disabled={available.length === 0}
          onChange={(e) => e.target.value && setAdding((a) => [...a, e.target.value])}
        >
          <option value="">+ Add a note for…</option>
          {available.map((c) => (
            <option key={c.channel_id} value={c.channel_id}>
              {c.category ? `${c.category} / ` : ""}#{c.name}
            </option>
          ))}
        </select>
      </div>
      {ids.map((id) => (
        <ChannelNoteEditor
          key={id}
          watch={watch}
          channelId={id}
          name={channelName.get(id) ?? "deleted channel"}
          initial={watch.channel_notes[id] ?? ""}
          onRemoved={() => setAdding((a) => a.filter((x) => x !== id))}
        />
      ))}
    </div>
  );
}

/** One watch inside a server group, collapsed by default (a server can have
 * many); rows without criteria say so instead of auto-expanding, which made
 * the page very long. A plain button rather than <details>, because clicks
 * on the On/Off checkbox inside a <summary> toggle it too. */
function WatchRow({ watch, guild }: { watch: Watch; guild: Guild | undefined }) {
  const [open, setOpen] = useState(false);
  const name = watch.kind === "guild" ? "Whole server" : `#${watch.channel_name ?? watch.label.split(" › #").pop()}`;
  const excludedCount = watch.excluded_channel_ids.length + watch.excluded_category_ids.length;
  const noteCount = Object.keys(watch.channel_notes).length;
  return (
    <div className={`watch-row${watch.enabled ? "" : " disabled"}`}>
      <div className="watch-row-head">
        <button className="row-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
          <span className="chevron">{open ? "▾" : "▸"}</span>
          <span className={watch.kind === "guild" ? "row-name whole" : "row-name"}>{name}</span>
          {excludedCount > 0 && <span className="tag">{excludedCount} excluded</span>}
          {noteCount > 0 && <span className="tag">{noteCount} channel note{noteCount === 1 ? "" : "s"}</span>}
          {!open &&
            (watch.criteria.trim() ? (
              <span className="row-criteria muted small">{watch.criteria}</span>
            ) : (
              <span className="tag">needs criteria</span>
            ))}
        </button>
        <Counts attention={watch.attention_count} pending={watch.pending_count} />
        <EnabledToggle watch={watch} />
      </div>
      {open && (
        <div className="watch-row-body">
          {watch.kind === "guild" && <Exclusions watch={watch} guild={guild} />}
          <WatchDetails watch={watch}>
            {watch.kind === "guild" && <ChannelNotes watch={watch} guild={guild} />}
          </WatchDetails>
        </div>
      )}
    </div>
  );
}

interface ServerGroupData {
  guildId: string;
  name: string;
  // Set only when another watched server has the same name -- two servers
  // can both be called "Lucky's server" -- so the groups are tellable apart.
  disambiguator?: string;
  watches: Watch[];
}

function groupByServer(watches: Watch[]): ServerGroupData[] {
  const groups = new Map<string, ServerGroupData>();
  for (const w of watches) {
    if (w.kind !== "channel" && w.kind !== "guild") continue;
    const guildId = w.guild_id ?? `unknown-${w.id}`;
    const fallbackName = w.kind === "guild" ? w.label.replace(/ \(whole server\)$/, "") : w.label.split(" › ")[0];
    const group = groups.get(guildId) ?? { guildId, name: w.guild_name ?? fallbackName, watches: [] };
    group.watches.push(w);
    groups.set(guildId, group);
  }
  for (const g of groups.values()) {
    // Whole-server entry first, then channels alphabetically.
    g.watches.sort((a, b) =>
      a.kind !== b.kind ? (a.kind === "guild" ? -1 : 1) : (a.channel_name ?? a.label).localeCompare(b.channel_name ?? b.label),
    );
  }
  const all = [...groups.values()];
  const nameCounts = new Map<string, number>();
  for (const g of all) nameCounts.set(g.name, (nameCounts.get(g.name) ?? 0) + 1);
  for (const g of all) if ((nameCounts.get(g.name) ?? 0) > 1) g.disambiguator = `id …${g.guildId.slice(-4)}`;
  return all.sort((a, b) => a.name.localeCompare(b.name));
}

function ServerGroup({ group, guild }: { group: ServerGroupData; guild: Guild | undefined }) {
  const attention = group.watches.reduce((n, w) => n + w.attention_count, 0);
  const pending = group.watches.reduce((n, w) => n + w.pending_count, 0);
  return (
    <section className="watch-card server-group">
      <header className="watch-head">
        <h3>
          {group.name}
          {group.disambiguator && <span className="muted small"> · {group.disambiguator}</span>}
        </h3>
        <Counts attention={attention} pending={pending} />
      </header>
      {group.watches.map((w) => (
        <WatchRow key={w.id} watch={w} guild={guild} />
      ))}
    </section>
  );
}

type Channel = Guild["channels"][number];

/** A server's channels in Discord's order, split into category groups. */
function byCategory(channels: Channel[]) {
  const groups: { id: string | null; name: string | null; channels: Channel[] }[] = [];
  for (const c of channels) {
    const last = groups[groups.length - 1];
    if (last && last.id === c.category_id) last.channels.push(c);
    else groups.push({ id: c.category_id, name: c.category, channels: [c] });
  }
  return groups;
}

/** Checkbox picker that stays open until Done.
 *
 * Server NOT watched as a whole: a channel checkbox = watch that channel.
 * Server watched as a whole: every checkbox means "included in the server
 * watch" -- untick a channel or a whole category to exclude it. A channel
 * can still get its own section ("own criteria"), which always wins. */
function ChannelPicker({ onDone }: { onDone: () => void }) {
  const { data: guilds, isLoading } = useChannels(true);
  const { data: watches } = useWatches();
  const create = useCreateWatch();
  const del = useDeleteWatch();
  const update = useUpdateWatch();
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [inFlight, setInFlight] = useState<Set<string>>(new Set());
  // Watches ticked during this picker session can be unticked without a
  // confirm -- they can't have collected anything worth warning about yet.
  const [addedHere, setAddedHere] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const watchById = useMemo(() => new Map((watches ?? []).map((w) => [w.id, w])), [watches]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (guilds ?? [])
      .map((g) => ({
        ...g,
        channels: g.channels.filter(
          (c) =>
            !q ||
            c.name.toLowerCase().includes(q) ||
            (c.category ?? "").toLowerCase().includes(q) ||
            g.guild_name.toLowerCase().includes(q),
        ),
      }))
      .filter((g) => g.channels.length > 0);
  }, [guilds, query]);

  const dupNames = useMemo(() => {
    const seen = new Set<string>();
    const dups = new Set<string>();
    for (const g of guilds ?? []) (seen.has(g.guild_name) ? dups : seen).add(g.guild_name);
    return dups;
  }, [guilds]);

  const setIn = (setter: typeof setInFlight, key: string, on: boolean) =>
    setter((prev) => {
      const next = new Set(prev);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });

  /** Runs one change with the row disabled until both lists have refetched,
   * so the checkbox can't flip back mid-way and invite a duplicate click. */
  const run = async (key: string, action: () => Promise<unknown>) => {
    if (inFlight.has(key)) return;
    setError(null);
    setIn(setInFlight, key, true);
    try {
      await action();
      await Promise.all([
        qc.refetchQueries({ queryKey: ["channels"] }),
        qc.refetchQueries({ queryKey: ["watches"] }),
      ]);
    } catch (e) {
      setError(String(e));
    } finally {
      setIn(setInFlight, key, false);
    }
  };

  const toggleWatch = (key: string, label: string, watchId: number | null, payload: { channel_id?: string; guild_id?: string }) => {
    if (watchId !== null && !addedHere.has(key) && !confirm(`Stop watching ${label}? Its stored items are deleted.`)) return;
    return run(key, async () => {
      if (watchId === null) {
        await create.mutateAsync(payload);
        setIn(setAddedHere, key, true);
      } else {
        await del.mutateAsync(watchId);
      }
    });
  };

  const setExcluded = (server: Watch, field: "excluded_channel_ids" | "excluded_category_ids", id: string, excluded: boolean) =>
    run(`x:${id}`, () => {
      const current = server[field];
      const next = excluded ? [...current, id] : current.filter((x) => x !== id);
      return update.mutateAsync({ id: server.id, [field]: next });
    });

  const watchedCount = (guilds ?? []).reduce(
    (n, g) => n + (g.watch_id !== null ? 1 : 0) + g.channels.filter((c) => c.watch_id !== null).length,
    0,
  );

  return (
    <section className="watch-card picker">
      <header className="watch-head">
        <h3>Choose what to watch</h3>
        <span className="muted small">{watchedCount} watched</span>
        <button className="btn primary" onClick={onDone}>
          Done
        </button>
      </header>
      <input autoFocus placeholder="Filter servers, categories and channels…" value={query} onChange={(e) => setQuery(e.target.value)} />
      {isLoading && <p className="muted">Loading…</p>}
      {guilds && guilds.length === 0 && (
        <p className="muted">No channels yet. The list fills in once the listener has connected to Discord.</p>
      )}
      {error && <p className="error">{error}</p>}
      <div className="picker-list">
        {filtered.map((g) => {
          const open = !!query || expanded.has(g.guild_id);
          const gKey = `g:${g.guild_id}`;
          const server = g.watch_id !== null ? watchById.get(g.watch_id) : undefined;
          const channelsWatched = g.channels.filter((c) => c.watch_id !== null).length;
          const excludedCount = server ? server.excluded_channel_ids.length + server.excluded_category_ids.length : 0;
          return (
            <div key={g.guild_id} className="picker-guild">
              <div className="picker-guild-head">
                <button className="row-toggle" onClick={() => setIn(setExpanded, g.guild_id, !expanded.has(g.guild_id))}>
                  <span className="chevron">{open ? "▾" : "▸"}</span>
                  <span className="row-name">{g.guild_name}</span>
                  {dupNames.has(g.guild_name) && <span className="muted small">id …{g.guild_id.slice(-4)}</span>}
                  {channelsWatched > 0 && (
                    <span className="muted small">
                      {channelsWatched} with own criteria
                    </span>
                  )}
                  {excludedCount > 0 && <span className="muted small">{excludedCount} excluded</span>}
                </button>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={g.watch_id !== null}
                    disabled={inFlight.has(gKey)}
                    onChange={() => toggleWatch(gKey, `${g.guild_name} (whole server)`, g.watch_id, { guild_id: g.guild_id })}
                  />
                  Whole server
                </label>
              </div>
              {open &&
                byCategory(g.channels).map((cat) => {
                  const catExcluded = !!(server && cat.id && server.excluded_category_ids.includes(cat.id));
                  return (
                    <div key={cat.id ?? "none"} className="picker-category">
                      {cat.name && (
                        <div className="picker-category-head">
                          {server && cat.id ? (
                            <label className="toggle" title="Untick to leave this whole category out, including channels added to it later">
                              <input
                                type="checkbox"
                                checked={!catExcluded}
                                disabled={inFlight.has(`x:${cat.id}`)}
                                onChange={(e) => setExcluded(server, "excluded_category_ids", cat.id!, !e.target.checked)}
                              />
                              {cat.name}
                            </label>
                          ) : (
                            <span>{cat.name}</span>
                          )}
                        </div>
                      )}
                      <ul>
                        {cat.channels.map((c) => {
                          const cKey = `c:${c.channel_id}`;
                          if (!server || c.watch_id !== null) {
                            // Own watch (or no server watch): checkbox = that channel's own section.
                            return (
                              <li key={c.channel_id}>
                                <label className="toggle">
                                  <input
                                    type="checkbox"
                                    checked={c.watch_id !== null}
                                    disabled={inFlight.has(cKey)}
                                    onChange={() => toggleWatch(cKey, `#${c.name}`, c.watch_id, { channel_id: c.channel_id })}
                                  />
                                  #{c.name}
                                </label>
                                {server && <span className="tag">own criteria</span>}
                              </li>
                            );
                          }
                          // Covered by the server watch: checkbox = included.
                          const chExcluded = server.excluded_channel_ids.includes(c.channel_id);
                          return (
                            <li key={c.channel_id} className={catExcluded ? "muted" : undefined}>
                              <label className="toggle" title={catExcluded ? "Its category is excluded" : undefined}>
                                <input
                                  type="checkbox"
                                  checked={!chExcluded && !catExcluded}
                                  disabled={catExcluded || inFlight.has(`x:${c.channel_id}`)}
                                  onChange={(e) => setExcluded(server, "excluded_channel_ids", c.channel_id, !e.target.checked)}
                                />
                                #{c.name}
                              </label>
                              <button
                                className="btn small ghost own-btn"
                                title="Give this channel its own section and criteria (overrides the server's, even if excluded)"
                                disabled={inFlight.has(cKey)}
                                onClick={() => toggleWatch(cKey, `#${c.name}`, null, { channel_id: c.channel_id })}
                              >
                                own criteria
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  );
                })}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function WatchesPage() {
  const { data: watches, isLoading } = useWatches();
  const [adding, setAdding] = useState(false);
  const builtins = (watches ?? []).filter((w) => w.kind === "all_dms" || w.kind === "requests");
  const servers = groupByServer(watches ?? []);
  // The directory is only needed to name excluded channels/categories.
  const hasServerWatch = (watches ?? []).some((w) => w.kind === "guild");
  const { data: directory } = useChannels(hasServerWatch);
  const guildById = new Map((directory ?? []).map((g) => [g.guild_id, g]));

  return (
    <div className="page">
      <div className="toolbar">
        <h1>Watching</h1>
        {!adding && (
          <button className="btn primary" onClick={() => setAdding(true)}>
            + Add channels or servers
          </button>
        )}
      </div>
      <p className="muted">
        Each section has its own idea of "important". Describe it in plain words; the local model uses this, plus your
        About me in Settings, to decide what reaches your inbox.
      </p>
      {adding && <ChannelPicker onDone={() => setAdding(false)} />}
      {isLoading && <p className="muted">Loading…</p>}
      {builtins.map((w) => (
        <BuiltinCard key={w.id} watch={w} />
      ))}
      {servers.map((g) => (
        <ServerGroup key={g.guildId} group={g} guild={guildById.get(g.guildId)} />
      ))}
    </div>
  );
}
