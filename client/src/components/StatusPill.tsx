import { Link } from "react-router-dom";

import type { Status } from "../api/types";

// Heartbeats are written every 30s (listener) / every batch interval
// (classifier); anything older than this means the service isn't running.
const STALE_MS = 3 * 60_000;

function fresh(ts: string | null) {
  return !!ts && Date.now() - new Date(ts).getTime() < STALE_MS;
}

export function describeStatus(status: Status | undefined) {
  if (!status) return { ok: false, label: "…" };
  const listenerUp = status.connected && fresh(status.heartbeat_at);
  const classifierUp = fresh(status.classifier_heartbeat_at) && !status.classifier_last_error;
  if (listenerUp && classifierUp) return { ok: true, label: "Live" };
  if (!listenerUp) return { ok: false, label: status.last_error ? "Discord error" : "Discord offline" };
  return { ok: false, label: "Model error" };
}

export default function StatusPill({ status }: { status: Status | undefined }) {
  const { ok, label } = describeStatus(status);
  return (
    <Link to="/settings" className={`status-pill ${ok ? "ok" : "bad"}`} title={status?.last_error ?? status?.classifier_last_error ?? ""}>
      <span className="dot" />
      {label}
    </Link>
  );
}
