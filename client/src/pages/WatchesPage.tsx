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
    "Every channel you can read in this server, including threads, forum posts and channels added later. Channels you also watch on their own use their own criteria instead. Busy servers mean more for the model to judge, so keep an eye on the waiting count.",
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

function WatchCard({ watch }: { watch: Watch }) {
  const update = useUpdateWatch();
  const del = useDeleteWatch();
  const test = useTestWatch();
  const reclassify = useReclassifyWatch();

  return (
    <section className={`watch-card${watch.enabled ? "" : " disabled"}`}>
      <header className="watch-head">
        <h3>{watch.label}</h3>
        {watch.attention_count > 0 && <span className="count-badge">{watch.attention_count}</span>}
        {watch.pending_count > 0 && <span className="muted small">{watch.pending_count} waiting to be judged</span>}
        <label className="toggle">
          <input
            type="checkbox"
            checked={watch.enabled}
            onChange={(e) => update.mutate({ id: watch.id, enabled: e.target.checked })}
          />
          {watch.enabled ? "On" : "Off"}
        </label>
      </header>
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
    </section>
  );
}

function AddChannel({ onDone }: { onDone: () => void }) {
  const { data: guilds, isLoading } = useChannels(true);
  const create = useCreateWatch();
  const [query, setQuery] = useState("");

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

  return (
    <section className="watch-card picker">
      <header className="watch-head">
        <h3>Add a channel or server</h3>
        <button className="btn ghost" onClick={onDone}>
          Close
        </button>
      </header>
      <input autoFocus placeholder="Filter servers and channels…" value={query} onChange={(e) => setQuery(e.target.value)} />
      {isLoading && <p className="muted">Loading…</p>}
      {guilds && guilds.length === 0 && (
        <p className="muted">No channels yet. The list fills in once the listener has connected to Discord.</p>
      )}
      {create.error && <p className="error">{String(create.error)}</p>}
      <div className="picker-list">
        {filtered.map((g) => (
          <details key={g.guild_id} open={!!query}>
            <summary>
              {g.guild_name}
              {g.watched ? (
                <span className="muted small"> · whole server watched</span>
              ) : (
                <button
                  className="btn small guild-watch"
                  disabled={create.isPending}
                  onClick={(e) => {
                    e.preventDefault(); // don't toggle the <details>
                    create.mutate({ guild_id: g.guild_id }, { onSuccess: onDone });
                  }}
                >
                  Watch whole server
                </button>
              )}
            </summary>
            <ul>
              {g.channels.map((c) => (
                <li key={c.channel_id}>
                  <span>
                    {c.category && <span className="muted small">{c.category} / </span>}#{c.name}
                  </span>
                  {c.watched ? (
                    <span className="muted small">watching</span>
                  ) : (
                    <button
                      className="btn small"
                      disabled={create.isPending}
                      onClick={() => create.mutate({ channel_id: c.channel_id }, { onSuccess: onDone })}
                    >
                      Watch
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </details>
        ))}
      </div>
    </section>
  );
}

export default function WatchesPage() {
  const { data: watches, isLoading } = useWatches();
  const [adding, setAdding] = useState(false);

  return (
    <div className="page">
      <div className="toolbar">
        <h1>Watching</h1>
        {!adding && (
          <button className="btn primary" onClick={() => setAdding(true)}>
            + Add channel or server
          </button>
        )}
      </div>
      <p className="muted">
        Each section has its own idea of "important". Describe it in plain words; the local model uses this, plus your
        About me in Settings, to decide what reaches your inbox.
      </p>
      {adding && <AddChannel onDone={() => setAdding(false)} />}
      {isLoading && <p className="muted">Loading…</p>}
      {watches?.map((w) => <WatchCard key={w.id} watch={w} />)}
    </div>
  );
}
