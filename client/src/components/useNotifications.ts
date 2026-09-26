import { useEffect, useRef, useState } from "react";

import { useItems } from "../api/hooks";

// Ids of attention items this browser has already seen in the list (and so
// notified about, or deliberately skipped on first load). A set rather than a
// "highest id so far" baseline: items are judged out of order (a failed
// batch retries later, "Re-judge" can promote an old item), so an older id
// can become attention after a newer one and must still notify.
const KNOWN_KEY = "discord_watch_known_attention_ids";
const KNOWN_CAP = 1000;

function readKnown(): Set<number> | null {
  try {
    const raw = localStorage.getItem(KNOWN_KEY);
    return raw ? new Set(JSON.parse(raw) as number[]) : null;
  } catch {
    return null;
  }
}

function writeKnown(known: Set<number>) {
  try {
    // Keep the newest ids; anything older has long left the attention list.
    const ids = [...known].sort((a, b) => b - a).slice(0, KNOWN_CAP);
    localStorage.setItem(KNOWN_KEY, JSON.stringify(ids));
  } catch {
    // Storage unavailable (private window etc.) -- worst case we re-notify.
  }
}

/** Browser notifications need a secure context (HTTPS or localhost). Over a
 * plain http://100.x Tailscale address the API simply doesn't exist, which is
 * why the README recommends `tailscale serve`. */
export function notificationsSupported() {
  return typeof window !== "undefined" && "Notification" in window && window.isSecureContext;
}

export function useNotificationPermission() {
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">(
    notificationsSupported() ? Notification.permission : "unsupported",
  );
  const request = async () => {
    if (!notificationsSupported()) return;
    setPermission(await Notification.requestPermission());
  };
  return { permission, request };
}

/** Raises a desktop/phone notification for each attention item this browser
 * hasn't seen in the list before. The very first load only records what's
 * already there, so opening the page never replays a burst of old items. */
export function useAttentionNotifications() {
  const { data: items } = useItems("attention", null);
  const known = useRef<Set<number> | null>(readKnown());

  useEffect(() => {
    if (!items) return;
    if (known.current === null) {
      known.current = new Set(items.map((i) => i.id));
      writeKnown(known.current);
      return;
    }
    const seenBefore = known.current;
    const fresh = items.filter((i) => !seenBefore.has(i.id) && !i.seen_at).sort((a, b) => a.id - b.id);
    if (fresh.length === 0) return;
    for (const i of fresh) seenBefore.add(i.id);
    writeKnown(seenBefore);

    if (!notificationsSupported() || Notification.permission !== "granted") return;
    // Collapse bursts into one summary notification.
    if (fresh.length > 3) {
      new Notification(`${fresh.length} Discord items need attention`, {
        body: fresh.slice(0, 3).map((i) => `${i.author_name}: ${i.reason ?? i.content}`).join("\n"),
        tag: "discord_watch_batch",
      });
      return;
    }
    for (const item of fresh) {
      const where = item.kind === "message" ? item.channel_name ?? item.watch_label : item.watch_label;
      const n = new Notification(`${item.importance === "urgent" ? "Urgent: " : ""}${item.author_name ?? "Discord"} · ${where}`, {
        body: item.reason ?? item.content.slice(0, 180),
        tag: `discord_watch_${item.id}`,
      });
      n.onclick = () => {
        window.focus();
        n.close();
      };
    }
  }, [items]);
}

/** Unseen-count in the tab title and as a badge on the favicon -- the
 * fallback signal that works even where notifications can't. */
export function useTabBadge(count: number) {
  useEffect(() => {
    document.title = count > 0 ? `(${count}) discord_watch` : "discord_watch";

    const link = document.getElementById("favicon") as HTMLLinkElement | null;
    if (!link) return;
    if (count === 0) {
      link.href = "/favicon.svg";
      return;
    }
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 64;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(img, 0, 0, 64, 64);
      ctx.fillStyle = "#ed4245";
      ctx.beginPath();
      ctx.arc(46, 18, 18, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#fff";
      ctx.font = "bold 24px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(count > 9 ? "9+" : String(count), 46, 19);
      link.href = canvas.toDataURL("image/png");
    };
    img.src = "/favicon.svg";
  }, [count]);
}
