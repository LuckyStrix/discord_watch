import { useEffect, useRef, useState } from "react";

import { useItems } from "../api/hooks";

const LAST_NOTIFIED_KEY = "discord_watch_last_notified_id";

function readLastNotified(): number | null {
  try {
    const raw = localStorage.getItem(LAST_NOTIFIED_KEY);
    return raw ? Number(raw) : null;
  } catch {
    return null;
  }
}

function writeLastNotified(id: number) {
  try {
    localStorage.setItem(LAST_NOTIFIED_KEY, String(id));
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

/** Raises a desktop/phone notification for each newly-arrived attention item.
 * The first load only records a baseline, so opening the page never replays
 * a burst of old notifications. */
export function useAttentionNotifications() {
  const { data: items } = useItems("attention", null);
  const baseline = useRef<number | null>(readLastNotified());

  useEffect(() => {
    if (!items || items.length === 0) return;
    const maxId = Math.max(...items.map((i) => i.id));
    if (baseline.current === null) {
      baseline.current = maxId;
      writeLastNotified(maxId);
      return;
    }
    const fresh = items.filter((i) => i.id > baseline.current! && !i.seen_at).sort((a, b) => a.id - b.id);
    if (fresh.length === 0) return;
    baseline.current = maxId;
    writeLastNotified(maxId);

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
