import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  useChannels,
  useCreateWatch,
  useDeleteWatch,
  useReclassifyWatch,
  useTestWatch,
  useUpdateWatch,
  useWatches,
} from "../api/hooks";
import type { Watch } from "../api/types";

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

function WatchDetails({ watch }: { watch: Watch }) {
  const update = useUpdateWatch();
  const del = useDeleteWatch();
  const test = useTestWatch();
  const reclassify = useReclassifyWatch();

  return (
    <>
      {BUILTIN_HINT[watch.kind] && <p className="muted small">{BUILTIN_HINT[watch.kind]}</p>}
      <CriteriaEditor watch={watch} />
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

/** One watch inside a server group, collapsed by default (a server can have
 * many); rows without criteria say so instead of auto-expanding, which made
 * the page very long. A plain button rather than <details>, because clicks
 * on the On/Off checkbox inside a <summary> toggle it too. */
function WatchRow({ watch }: { watch: Watch }) {
  const [open, setOpen] = useState(false);
  const name = watch.kind === "guild" ? "Whole server" : `#${watch.channel_name ?? watch.label.split(" › #").pop()}`;
  return (
    <div className={`watch-row${watch.enabled ? "" : " disabled"}`}>
      <div className="watch-row-head">
        <button className="row-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
          <span className="chevron">{open ? "▾" : "▸"}</span>
          <span className={watch.kind === "guild" ? "row-name whole" : "row-name"}>{name}</span>
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
          <WatchDetails watch={watch} />
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

function ServerGroup({ group }: { group: ServerGroupData }) {
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
        <WatchRow key={w.id} watch={w} />
      ))}
    </section>
  );
}

/** Checkbox picker that stays open: tick to watch, untick to stop. */
function ChannelPicker({ onDone }: { onDone: () => void }) {
  const { data: guilds, isLoading } = useChannels(true);
  const create = useCreateWatch();
  const del = useDeleteWatch();
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [inFlight, setInFlight] = useState<Set<string>>(new Set());
  // Watches ticked during this picker session can be unticked without a
  // confirm -- they can't have collected anything worth warning about yet.
  const [addedHere, setAddedHere] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (guilds ?? [])
      .map((g) => ({
        ...g,
        channels: g.channels.filter(
          (c) => !q || c.name.toLowerCase().includes(q) || g.guild_name.toLowerCase().includes(q),
        ),
      }))
      .filter((g) => g.channels.length > 0);
  }, [guilds, query]);

  const setIn = (setter: typeof setInFlight, key: string, on: boolean) =>
    setter((prev) => {
      const next = new Set(prev);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });

  const toggle = async (key: string, label: string, watchId: number | null, payload: { channel_id?: string; guild_id?: string }) => {
    if (inFlight.has(key)) return;
    if (watchId !== null && !addedHere.has(key) && !confirm(`Stop watching ${label}? Its stored items are deleted.`)) return;
    setError(null);
    setIn(setInFlight, key, true);
    try {
      if (watchId === null) {
        await create.mutateAsync(payload);
        setIn(setAddedHere, key, true);
      } else {
        await del.mutateAsync(watchId);
      }
      // Keep the row disabled until the directory reflects the change, or the
      // checkbox briefly flips back and a second click would 409.
      await qc.refetchQueries({ queryKey: ["channels"] });
    } catch (e) {
      setError(String(e));
    } finally {
      setIn(setInFlight, key, false);
    }
  };

  const dupNames = useMemo(() => {
    const seen = new Set<string>();
    const dups = new Set<string>();
    for (const g of guilds ?? []) (seen.has(g.guild_name) ? dups : seen).add(g.guild_name);
    return dups;
  }, [guilds]);

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
      <input autoFocus placeholder="Filter servers and channels…" value={query} onChange={(e) => setQuery(e.target.value)} />
      {isLoading && <p className="muted">Loading…</p>}
      {guilds && guilds.length === 0 && (
        <p className="muted">No channels yet. The list fills in once the listener has connected to Discord.</p>
      )}
      {error && <p className="error">{error}</p>}
      <div className="picker-list">
        {filtered.map((g) => {
          const open = !!query || expanded.has(g.guild_id);
          const gKey = `g:${g.guild_id}`;
          const channelsWatched = g.channels.filter((c) => c.watch_id !== null).length;
          return (
            <div key={g.guild_id} className="picker-guild">
              <div className="picker-guild-head">
                <button className="row-toggle" onClick={() => setIn(setExpanded, g.guild_id, !expanded.has(g.guild_id))}>
                  <span className="chevron">{open ? "▾" : "▸"}</span>
                  <span className="row-name">{g.guild_name}</span>
                  {dupNames.has(g.guild_name) && <span className="muted small">id …{g.guild_id.slice(-4)}</span>}
                  {channelsWatched > 0 && <span className="muted small">{channelsWatched} channel{channelsWatched === 1 ? "" : "s"}</span>}
                </button>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={g.watch_id !== null}
                    disabled={inFlight.has(gKey)}
                    onChange={() => toggle(gKey, `${g.guild_name} (whole server)`, g.watch_id, { guild_id: g.guild_id })}
                  />
                  Whole server
                </label>
              </div>
              {open && (
                <ul>
                  {g.channels.map((c) => {
                    const cKey = `c:${c.channel_id}`;
                    return (
                      <li key={c.channel_id}>
                        <label className="toggle">
                          <input
                            type="checkbox"
                            checked={c.watch_id !== null}
                            disabled={inFlight.has(cKey)}
                            onChange={() => toggle(cKey, `#${c.name}`, c.watch_id, { channel_id: c.channel_id })}
                          />
                          {c.category && <span className="muted small">{c.category} /</span>}#{c.name}
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
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
        <ServerGroup key={g.guildId} group={g} />
      ))}
    </div>
  );
}
