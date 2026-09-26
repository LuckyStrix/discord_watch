import { useState } from "react";
import { Link } from "react-router-dom";

import { type ItemFilter, useBulkUpdateItems, useItems, useWatches } from "../api/hooks";
import ItemCard from "../components/ItemCard";
import { notificationsSupported, useNotificationPermission } from "../components/useNotifications";

function NotificationBanner() {
  const { permission, request } = useNotificationPermission();
  if (permission === "granted") return null;
  if (permission === "unsupported") {
    return (
      <div className="banner">
        Browser notifications need HTTPS. Open this page through <code>tailscale serve</code> (see README) to enable
        them. The unread count in the tab title still works.
      </div>
    );
  }
  if (permission === "denied") {
    return <div className="banner">Notifications are blocked for this site in your browser settings.</div>;
  }
  return (
    <div className="banner">
      Get a notification when something needs your attention.{" "}
      <button className="btn primary" onClick={request} disabled={!notificationsSupported()}>
        Enable notifications
      </button>
    </div>
  );
}

export default function InboxPage() {
  const [filter, setFilter] = useState<ItemFilter>("attention");
  const [watchId, setWatchId] = useState<number | null>(null);
  const { data: items, isLoading, error } = useItems(filter, watchId);
  const { data: watches } = useWatches();
  const bulk = useBulkUpdateItems();

  const unseenIds = (items ?? []).filter((i) => !i.seen_at).map((i) => i.id);

  return (
    <div className="page">
      <NotificationBanner />
      <div className="toolbar">
        <div className="tabs">
          <button className={filter === "attention" ? "active" : ""} onClick={() => setFilter("attention")}>
            Needs attention
          </button>
          <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
            Everything
          </button>
        </div>
        <select value={watchId ?? ""} onChange={(e) => setWatchId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">All sections</option>
          {watches?.map((w) => (
            <option key={w.id} value={w.id}>
              {w.label}
            </option>
          ))}
        </select>
        <button
          className="btn"
          disabled={unseenIds.length === 0 || bulk.isPending}
          onClick={() => bulk.mutate({ ids: unseenIds, seen: true })}
        >
          Mark all seen
        </button>
      </div>

      {error && <p className="error">Failed to load: {String(error)}</p>}
      {isLoading && <p className="muted">Loading…</p>}
      {items && items.length === 0 && (
        <div className="empty">
          {filter === "attention" ? (
            <>
              <p>Nothing needs your attention.</p>
              <p className="muted">
                Tune what counts as important on the <Link to="/watches">Watching</Link> page.
              </p>
            </>
          ) : (
            <p>Nothing stored yet. Messages appear here as the listener sees them.</p>
          )}
        </div>
      )}
      <div className="item-list">{items?.map((item) => <ItemCard key={item.id} item={item} />)}</div>
    </div>
  );
}
