"""Pure message -> watch routing, independent of discord.py objects so it can
be unit-tested with plain values."""

from dataclasses import dataclass
from typing import Literal

ChannelType = Literal["dm", "group", "guild"]


@dataclass(frozen=True)
class WatchRef:
    id: int
    kind: str
    channel_id: str | None
    enabled: bool
    always_catch_up: bool = False


@dataclass(frozen=True)
class Route:
    watch_id: int
    item_kind: str  # "message" | "message_request"


@dataclass(frozen=True)
class IncomingMessage:
    channel_type: ChannelType
    channel_id: str
    # For threads/forum posts: the channel they live under, so watching a
    # channel also covers its threads.
    parent_channel_id: str | None
    author_is_me: bool
    is_pending_request: bool


def route_message(msg: IncomingMessage, watches: list[WatchRef]) -> Route | None:
    """Returns where a message should be stored, or None to drop it. Anything
    not explicitly watched is never stored."""
    if msg.author_is_me:
        return None
    enabled = [w for w in watches if w.enabled]

    if msg.channel_type in ("dm", "group"):
        if msg.is_pending_request:
            requests = next((w for w in enabled if w.kind == "requests"), None)
            return Route(requests.id, "message_request") if requests else None
        dms = next((w for w in enabled if w.kind == "all_dms"), None)
        return Route(dms.id, "message") if dms else None

    by_channel = {w.channel_id: w for w in enabled if w.kind == "channel"}
    watch = by_channel.get(msg.channel_id) or (by_channel.get(msg.parent_channel_id) if msg.parent_channel_id else None)
    return Route(watch.id, "message") if watch else None


def needs_backfill(
    last_message_id: str | None,
    acked_message_id: str | None,
    last_stored_id: str | None,
    *,
    always: bool = False,
    offline_since: int | None = None,
) -> int | None:
    """Decides whether a channel has messages we haven't stored yet, and if so
    returns the snowflake to fetch history *after* (0 = no known floor, just
    take the most recent few). None means skip the channel. Snowflakes are
    time-ordered, so integer comparison is chronological.

    Default: only channels Discord reports as unread (last message newer than
    the user's read marker) -- keeps startup REST calls to the handful of
    channels that actually changed while offline.

    `always` (a per-watch opt-in) ignores the read marker, for channels that
    never *look* unread: muted ones, or ones read on another device while this
    listener was down. Its floor is instead `offline_since`, the snowflake of
    when the listener last ran, so it fetches exactly the downtime gap. With no
    `offline_since` (first ever run) there is no gap to fill, so it falls
    back to the unread-only rule."""
    if not last_message_id:
        return None
    last = int(last_message_id)
    stored = int(last_stored_id or 0)
    if always and offline_since is not None:
        floor = max(stored, offline_since)
    else:
        floor = max(int(acked_message_id or 0), stored)
    return floor if last > floor else None
