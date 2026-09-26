import { useEffect, useState } from "react";

import { useOllamaModels, useSettings, useStatus, useUpdateSettings } from "../api/hooks";
import type { AppSettings } from "../api/types";
import { timeAgo } from "../components/ItemCard";
import { describeStatus } from "../components/StatusPill";

function StatusPanel() {
  const { data: status } = useStatus();
  const { ok, label } = describeStatus(status);
  if (!status) return null;
  return (
    <section className="watch-card">
      <h3>Status</h3>
      <dl className="status-grid">
        <dt>Overall</dt>
        <dd className={ok ? "ok-text" : "error"}>{label}</dd>
        <dt>Discord</dt>
        <dd>
          {status.connected ? `Connected as ${status.user_tag}` : "Not connected"}
          {status.heartbeat_at && <span className="muted small"> · heartbeat {timeAgo(status.heartbeat_at)}</span>}
        </dd>
        <dt>Last stored event</dt>
        <dd>{status.last_event_at ? timeAgo(status.last_event_at) : "—"}</dd>
        <dt>Classifier</dt>
        <dd>
          {status.classifier_heartbeat_at ? `last ran ${timeAgo(status.classifier_heartbeat_at)}` : "never ran"}
          {status.pending_count > 0 && <span className="muted small"> · {status.pending_count} waiting</span>}
        </dd>
      </dl>
      {status.last_error && <p className="error">Listener: {status.last_error}</p>}
      {status.classifier_last_error && <p className="error">Classifier: {status.classifier_last_error}</p>}
    </section>
  );
}

export default function SettingsPage() {
  const { data: settings } = useSettings();
  const { data: models, error: modelsError } = useOllamaModels();
  const update = useUpdateSettings();
  const [draft, setDraft] = useState<AppSettings | null>(null);

  useEffect(() => {
    if (settings && !draft) setDraft(settings);
  }, [settings, draft]);

  if (!draft || !settings) return <p className="muted">Loading…</p>;

  const dirty = JSON.stringify(draft) !== JSON.stringify(settings);
  const set = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => setDraft({ ...draft, [key]: value });
  const modelNames = models?.map((m) => m.name) ?? [];

  return (
    <div className="page">
      <h1>Settings</h1>
      <StatusPanel />

      <section className="watch-card form">
        <h3>About me</h3>
        <p className="muted small">
          Sent with every judgement. Who you are, what you're involved in, and who matters to you.
        </p>
        <textarea
          rows={4}
          value={draft.about_me}
          placeholder="I'm Carter. I lead a raid team in X and organize game nights with friends. Anything from my close friends (A, B) matters more than acquaintances."
          onChange={(e) => set("about_me", e.target.value)}
        />
      </section>

      <section className="watch-card form">
        <h3>Model</h3>
        <label>
          Ollama model
          <select value={draft.ollama_model} onChange={(e) => set("ollama_model", e.target.value)}>
            {!modelNames.includes(draft.ollama_model) && <option value={draft.ollama_model}>{draft.ollama_model}</option>}
            {models?.map((m) => (
              <option key={m.name} value={m.name}>
                {m.name} {m.parameter_size ? `(${m.parameter_size})` : ""}
              </option>
            ))}
          </select>
        </label>
        {modelsError && <p className="error small">{String(modelsError)}</p>}
        <p className="muted small">
          Always runs on the CPU (no VRAM used). Small models (3–4B) are the sweet spot, and bigger ones will be slow on CPU.
        </p>
        <label>
          CPU threads
          <input type="number" min={1} max={64} value={draft.num_thread} onChange={(e) => set("num_thread", Number(e.target.value))} />
        </label>
        <label>
          Keep model loaded for
          <input value={draft.keep_alive} onChange={(e) => set("keep_alive", e.target.value)} />
        </label>
        <label>
          Judge new messages every (seconds)
          <input
            type="number"
            min={10}
            max={3600}
            value={draft.batch_interval_s}
            onChange={(e) => set("batch_interval_s", Number(e.target.value))}
          />
        </label>
      </section>

      <section className="watch-card form">
        <h3>Data</h3>
        <label>
          Keep unimportant items for (days)
          <input
            type="number"
            min={1}
            value={draft.retention_days}
            onChange={(e) => set("retention_days", Number(e.target.value))}
          />
        </label>
        <label className="toggle">
          <input type="checkbox" checked={draft.backfill_enabled} onChange={(e) => set("backfill_enabled", e.target.checked)} />
          On startup, catch up on unread messages missed while offline
        </label>
        <p className="muted small">
          Only fetches watched channels that Discord reports as unread (plus sections set to "always catch up"), one
          at a time. Turn off for zero extra API calls.
        </p>
      </section>

      <div className="toolbar">
        <button className="btn primary" disabled={!dirty || update.isPending} onClick={() => update.mutate(draft, { onSuccess: setDraft })}>
          {update.isPending ? "Saving…" : "Save"}
        </button>
        {dirty && (
          <button className="btn ghost" onClick={() => setDraft(settings)}>
            Discard
          </button>
        )}
        {update.error && <span className="error">{String(update.error)}</span>}
      </div>
    </div>
  );
}
