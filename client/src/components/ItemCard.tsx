import { useReclassifyItem, useUpdateItem } from "../api/hooks";
import type { Item } from "../api/types";

const KIND_LABEL: Record<Item["kind"], string> = {
  message: "",
  friend_request: "Friend request",
  message_request: "Message request",
};

export function timeAgo(iso: string) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// Friend requests have no message to jump to; the friends list is where
// they're accepted.
function discordLink(item: Item) {
  return item.jump_url ?? "https://discord.com/channels/@me";
}

export default function ItemCard({ item }: { item: Item }) {
  const update = useUpdateItem();
  const reclassify = useReclassifyItem();
  const unseen = !item.seen_at && !item.dismissed_at;
  const where = [item.guild_name, item.channel_name].filter(Boolean).join(" › ") || item.watch_label;

  return (
    <article className={`item-card importance-${item.importance ?? "pending"}${unseen ? " unseen" : ""}`}>
      <div className="item-main">
        <header className="item-head">
          <span className={`importance-tag tag-${item.importance ?? "pending"}`}>
            {item.status === "pending" ? "judging…" : item.status === "error" ? "error" : item.importance}
          </span>
          {item.needs_reply && <span className="tag tag-reply">needs reply</span>}
          {KIND_LABEL[item.kind] && <span className="tag">{KIND_LABEL[item.kind]}</span>}
          {item.is_spam && <span className="tag tag-spam">spam?</span>}
          <span className="item-author">{item.author_name}</span>
          <span className="item-where">{where}</span>
          <span className="item-time" title={new Date(item.created_at).toLocaleString()}>
            {timeAgo(item.created_at)}
          </span>
        </header>
        {item.reason && <p className="item-reason">{item.reason}</p>}
        <p className="item-content">{item.content || <em>(no text)</em>}</p>
        {item.attachments.length > 0 && (
          <ul className="item-attachments">
            {item.attachments.map((a) => (
              <li key={a.url}>
                <a href={a.url} target="_blank" rel="noreferrer">
                  {a.filename}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
      {/* A fixed right-hand column pinned to the top of the tile, every button
          in a fixed slot (Mark seen is disabled rather than removed): when
          Done removes a tile, the next one slides up and puts its Done under
          the same mouse position, whatever each tile's height. */}
      <footer className="item-actions">
        {item.dismissed_at ? (
          <button className="btn" onClick={() => update.mutate({ id: item.id, dismissed: false })}>
            Restore
          </button>
        ) : (
          <button className="btn primary" onClick={() => update.mutate({ id: item.id, dismissed: true })}>
            Done
          </button>
        )}
        <a
          className="btn"
          href={discordLink(item)}
          target="_blank"
          rel="noreferrer"
          onClick={() => unseen && update.mutate({ id: item.id, seen: true })}
        >
          Open in Discord
        </a>
        <button className="btn" disabled={!unseen} onClick={() => update.mutate({ id: item.id, seen: true })}>
          {unseen ? "Mark seen" : "Seen"}
        </button>
        <button
          className="btn ghost"
          disabled={reclassify.isPending || item.status === "pending"}
          onClick={() => reclassify.mutate(item.id)}
          title="Judge this again with the current criteria"
        >
          Re-judge
        </button>
      </footer>
    </article>
  );
}
