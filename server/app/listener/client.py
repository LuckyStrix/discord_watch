"""The Discord side: a passive, read-only gateway session.

Hard rules (keep them if you edit this file):
  * never send, react, type, change presence, join/leave anything;
  * never ack (mark read) -- the user's unread badges must stay untouched;
  * no polling. The gateway pushes every event to a logged-in session, the
    same as it does to the desktop app -- including muted channels, since
    muting is only a notification preference. The only REST calls are the
    startup backfill (watched channels only; unread ones unless a section
    opts into "always catch up"; capped, sequential and jittered) and one
    profile lookup per live friend request.
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta, timezone

import discord
from sqlalchemy import BigInteger, cast, func, select
from sqlalchemy.dialects.postgresql import insert

from app.classifier.runner import get_settings
from app.db import async_session
from app.listener.routing import IncomingMessage, WatchRef, needs_backfill, route_message
from app.models import DiscordChannel, Item, ListenerStatus, Watch

log = logging.getLogger("listener")

WATCH_REFRESH_S = 30
HEARTBEAT_S = 30
BACKFILL_LIMIT = 25
BACKFILL_MAX_CHANNELS = 30
# How far back any catch-up may reach -- "always catch up" after a long
# outage, and unread channels that were never opened (which have no read
# marker, so would otherwise count as unread back to the channel's creation).
MAX_CATCH_UP_DAYS = 3
BACKFILL_DELAY_S = (2.0, 4.0)
CONTENT_MAX = 4000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _channel_type(channel) -> str:
    if isinstance(channel, discord.DMChannel):
        return "dm"
    if isinstance(channel, discord.GroupChannel):
        return "group"
    return "guild"


def _channel_label(channel) -> str | None:
    if isinstance(channel, discord.DMChannel):
        return f"DM with {channel.recipient.display_name}" if channel.recipient else "DM"
    if isinstance(channel, discord.GroupChannel):
        return channel.name or ", ".join(r.display_name for r in channel.recipients) or "Group DM"
    if isinstance(channel, discord.Thread) and channel.parent:
        return f"{channel.parent.name} › {channel.name}"
    return getattr(channel, "name", None)


def _category_id(channel) -> str | None:
    """A channel's category; for a thread or forum post, its parent's."""
    if isinstance(channel, discord.Thread):
        channel = channel.parent
    category_id = getattr(channel, "category_id", None)
    return str(category_id) if category_id else None


def _is_pending_request(channel) -> bool:
    if isinstance(channel, discord.DMChannel):
        return channel.is_message_request() and not channel.is_accepted()
    return False


def _message_text(message: discord.Message) -> str:
    # Bots often post only embeds; fold their text in so the model can judge them.
    parts = [message.content or ""]
    for embed in message.embeds:
        parts.extend(p for p in (embed.title, embed.description) if p)
        parts.extend(f"{f.name}: {f.value}" for f in embed.fields)
    if message.poll:
        parts.append(f"Poll: {message.poll.question}")
    return "\n".join(p for p in parts if p).strip()[:CONTENT_MAX]


class WatchClient(discord.Client):
    def __init__(self) -> None:
        super().__init__(
            # Member chunking at startup is something the official client
            # doesn't do and isn't needed here.
            chunk_guilds_at_startup=False,
            max_messages=200,
        )
        self._watches: list[WatchRef] = []
        self._watches_loaded_at = 0.0
        self._last_event_at: datetime | None = None
        self._background: set[asyncio.Task] = set()
        self._ready_once = False
        self._previous_heartbeat: datetime | None = None

    # -- helpers ----------------------------------------------------------

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _load_watches(self, force: bool = False) -> list[WatchRef]:
        if force or time.monotonic() - self._watches_loaded_at > WATCH_REFRESH_S:
            async with async_session() as db:
                rows = (await db.execute(select(Watch))).scalars().all()
            self._watches = [
                WatchRef(
                    w.id, w.kind, w.channel_id, w.enabled, w.always_catch_up, w.guild_id,
                    frozenset(w.excluded_channel_ids or []), frozenset(w.excluded_category_ids or []),
                )
                for w in rows
            ]
            self._watches_loaded_at = time.monotonic()
        return self._watches

    def _is_me(self, user) -> bool:
        return self.user is not None and user.id == self.user.id

    def _mentions_me(self, message: discord.Message) -> bool:
        if self.user is None:
            return False
        if any(u.id == self.user.id for u in message.mentions):
            return True
        guild = message.guild
        me = guild.me if guild else None
        if me is not None and message.role_mentions:
            my_roles = {r.id for r in me.roles}
            return any(r.id in my_roles for r in message.role_mentions)
        return False

    def _reply_to_me(self, message: discord.Message) -> bool:
        ref = message.reference
        resolved = ref.resolved if ref else None
        return isinstance(resolved, discord.Message) and self._is_me(resolved.author)

    async def _store(self, values: dict) -> bool:
        async with async_session() as db:
            stmt = insert(Item).values(**values).on_conflict_do_nothing(index_elements=["discord_message_id"])
            result = await db.execute(stmt)
            await db.commit()
        self._last_event_at = _now()
        return bool(result.rowcount)

    # -- messages ---------------------------------------------------------

    async def handle_message(self, message: discord.Message) -> bool:
        channel = message.channel
        incoming = IncomingMessage(
            channel_type=_channel_type(channel),
            channel_id=str(channel.id),
            parent_channel_id=str(channel.parent_id) if isinstance(channel, discord.Thread) else None,
            author_is_me=self._is_me(message.author),
            is_pending_request=_is_pending_request(channel),
            guild_id=str(message.guild.id) if message.guild else None,
            category_id=_category_id(channel),
        )
        route = route_message(incoming, await self._load_watches())
        if route is None:
            return False
        return await self._store(
            dict(
                watch_id=route.watch_id,
                kind=route.item_kind,
                discord_message_id=str(message.id),
                guild_id=str(message.guild.id) if message.guild else None,
                guild_name=message.guild.name if message.guild else None,
                channel_id=str(channel.id),
                channel_name=_channel_label(channel),
                parent_channel_id=str(channel.parent_id) if isinstance(channel, discord.Thread) else None,
                author_id=str(message.author.id),
                author_name=message.author.display_name,
                content=_message_text(message),
                attachments=[
                    {"filename": a.filename, "url": a.url, "content_type": a.content_type} for a in message.attachments
                ],
                mentions_me=self._mentions_me(message),
                reply_to_me=self._reply_to_me(message),
                is_spam=isinstance(channel, discord.DMChannel) and channel.is_spam(),
                jump_url=message.jump_url,
                created_at=message.created_at,
            )
        )

    async def on_message(self, message: discord.Message) -> None:
        try:
            await self.handle_message(message)
        except Exception:  # noqa: BLE001 -- one bad message must not kill the session
            log.exception("failed to store message %s", message.id)

    # -- friend requests --------------------------------------------------

    async def _mutual_guilds(self, user: discord.User, live: bool) -> list[str] | None:
        """Mutual servers for a friend request. For a live request this makes
        one profile fetch -- the same call the desktop app makes when you open
        a request, and requests are rare. The startup rescan must not fan out
        REST calls, so it only uses the local member cache (incomplete without
        member chunking; None means "unknown" rather than "none")."""
        if live:
            try:
                profile = await user.profile(with_mutual_guilds=True, with_mutual_friends=False)
                return [g.guild.name for g in profile.mutual_guilds or [] if g.guild and g.guild.name]
            except discord.HTTPException as exc:
                log.warning("profile fetch failed for %s: %s", user.id, exc)
        cached = [g.name for g in self.guilds if g.get_member(user.id) is not None]
        return cached or None

    async def handle_friend_request(self, relationship: discord.Relationship, live: bool = False) -> None:
        if relationship.type != discord.RelationshipType.incoming_request:
            return
        requests = next((w for w in await self._load_watches() if w.kind == "requests" and w.enabled), None)
        if requests is None:
            return
        user = relationship.user
        mutual = await self._mutual_guilds(user, live)
        if mutual is None:
            mutual_text = "Mutual servers unknown."
        else:
            mutual_text = f"Mutual servers: {', '.join(mutual)}." if mutual else "No mutual servers."
        stored = await self._store(
            dict(
                watch_id=requests.id,
                kind="friend_request",
                # Friend requests have no message id; this synthetic key keeps
                # the startup re-scan from re-inserting pending requests.
                discord_message_id=f"friend_request:{user.id}:{relationship.since.timestamp() if relationship.since else 0:.0f}",
                author_id=str(user.id),
                author_name=f"{user.display_name} (@{user.name})",
                content=f"Friend request from {user.display_name} (@{user.name}). {mutual_text}",
                created_at=relationship.since or _now(),
            )
        )
        if stored:
            log.info("stored friend request from %s", user.name)

    async def on_relationship_add(self, relationship: discord.Relationship) -> None:
        try:
            await self.handle_friend_request(relationship, live=True)
        except Exception:  # noqa: BLE001
            log.exception("failed to store friend request")

    # -- channel directory -----------------------------------------------

    async def sync_channel_directory(self) -> None:
        rows = []
        for guild in self.guilds:
            me = guild.me
            # Forums aren't TextChannels; their posts are threads whose
            # parent_id is the forum, which routing already handles.
            for channel in [*guild.text_channels, *guild.forums]:
                if me is not None and not channel.permissions_for(me).read_messages:
                    continue
                rows.append(
                    dict(
                        channel_id=str(channel.id),
                        guild_id=str(guild.id),
                        guild_name=guild.name,
                        category=channel.category.name if channel.category else None,
                        category_id=str(channel.category.id) if channel.category else None,
                        category_position=channel.category.position if channel.category else -1,
                        name=channel.name,
                        position=channel.position,
                    )
                )
        async with async_session() as db:
            await db.execute(DiscordChannel.__table__.delete())
            if rows:
                await db.execute(insert(DiscordChannel).values(rows))
            await db.commit()
        log.info("channel directory synced: %d channels in %d servers", len(rows), len(self.guilds))

    def _schedule_directory_sync(self) -> None:
        # Channel events can arrive in bursts (e.g. a server reorganizing);
        # coalesce them into one resync a few seconds later.
        if getattr(self, "_sync_pending", False):
            return
        self._sync_pending = True

        async def later() -> None:
            await asyncio.sleep(5)
            self._sync_pending = False
            await self.sync_channel_directory()

        self._spawn(later())

    async def on_guild_channel_create(self, _channel) -> None:
        self._schedule_directory_sync()

    async def on_guild_channel_delete(self, _channel) -> None:
        self._schedule_directory_sync()

    async def on_guild_channel_update(self, _before, _after) -> None:
        self._schedule_directory_sync()

    async def on_guild_join(self, _guild) -> None:
        self._schedule_directory_sync()

    async def on_guild_remove(self, _guild) -> None:
        self._schedule_directory_sync()

    # -- startup ----------------------------------------------------------

    def _offline_since(self) -> int | None:
        """Snowflake for when this listener last ran (its previous heartbeat),
        clamped to MAX_CATCH_UP_DAYS. None on the very first run."""
        if self._previous_heartbeat is None:
            return None
        since = max(self._previous_heartbeat, _now() - timedelta(days=MAX_CATCH_UP_DAYS))
        return discord.utils.time_snowflake(since)

    async def backfill(self) -> None:
        """Fetch messages missed while offline, for watched channels only.

        Per channel, a watch's `always_catch_up` decides the rule (see
        routing.needs_backfill): unread-only by default, or the whole downtime
        gap for sections that opt in. Either way: at most BACKFILL_LIMIT
        newest messages per channel in one request, at most
        BACKFILL_MAX_CHANNELS channels (most recently active first), one at a
        time with jitter."""
        watches = await self._load_watches(force=True)
        by_kind = {w.kind: w for w in watches if w.enabled and w.kind in ("all_dms", "requests")}
        # channel id -> always_catch_up. Channel watches go in first so a
        # channel's own setting beats its whole-server watch's.
        chosen: dict[int, tuple[object, bool]] = {}
        for w in watches:
            if w.kind == "channel" and w.enabled:
                channel = self.get_channel(int(w.channel_id))
                # A watched forum has no history() (see the guild loop below);
                # routing still catches its live posts.
                if channel is not None and not isinstance(channel, discord.ForumChannel):
                    chosen[channel.id] = (channel, w.always_catch_up)
        for w in watches:
            if w.kind == "guild" and w.enabled:
                guild = self.get_guild(int(w.guild_id))
                if guild is None:
                    continue
                me = guild.me
                # Text channels only: forums have no history of their own
                # (their posts are threads), and fetching every thread of a
                # server would be exactly the REST fan-out to avoid.
                for channel in guild.text_channels:
                    if me is not None and not channel.permissions_for(me).read_messages:
                        continue
                    if w.excludes(str(channel.id), None, _category_id(channel)):
                        continue
                    chosen.setdefault(channel.id, (channel, w.always_catch_up))
        candidates: list[tuple[object, bool]] = list(chosen.values())
        for channel in self.private_channels:
            watch = by_kind.get("requests" if _is_pending_request(channel) else "all_dms")
            if watch is not None:
                candidates.append((channel, watch.always_catch_up))
        offline_since = self._offline_since()
        oldest_allowed = discord.utils.time_snowflake(_now() - timedelta(days=MAX_CATCH_UP_DAYS))

        async with async_session() as db:
            # Cast: snowflakes are stored as strings, and string max() is wrong
            # across digit-count boundaries.
            last_ids = dict(
                (
                    await db.execute(
                        select(Item.channel_id, func.max(cast(Item.discord_message_id, BigInteger)))
                        .where(Item.kind != "friend_request")
                        .group_by(Item.channel_id)
                    )
                ).all()
            )

        todo: list[tuple[object, int]] = []
        for channel, always in candidates:
            last_stored = last_ids.get(str(channel.id))
            after = needs_backfill(
                str(channel.last_message_id) if channel.last_message_id else None,
                str(channel.acked_message_id) if getattr(channel, "acked_message_id", None) else None,
                str(last_stored) if last_stored else None,
                always=always,
                offline_since=offline_since,
                oldest_allowed=oldest_allowed,
            )
            if after is not None:
                todo.append((channel, after))
        # Most recently active first, so the cap drops the stalest channels.
        todo.sort(key=lambda t: t[0].last_message_id or 0, reverse=True)
        skipped = max(0, len(todo) - BACKFILL_MAX_CHANNELS)

        fetched = 0
        for channel, after in todo[:BACKFILL_MAX_CHANNELS]:
            await asyncio.sleep(random.uniform(*BACKFILL_DELAY_S))
            try:
                # oldest_first=False matters: with `after` alone the library
                # walks forward from `after` and returns the *oldest* messages
                # past it -- weeks-old ones for a channel you rarely read.
                # This way it's the newest BACKFILL_LIMIT after the floor, in
                # a single request.
                kwargs = {"limit": BACKFILL_LIMIT, "oldest_first": False}
                if after:
                    kwargs["after"] = discord.Object(id=after)
                async for message in channel.history(**kwargs):
                    if await self.handle_message(message):
                        fetched += 1
            except discord.HTTPException as exc:
                log.warning("backfill skipped %s: %s", channel.id, exc)
        log.info(
            "backfill done: %d new messages from %d channels%s",
            fetched,
            min(len(todo), BACKFILL_MAX_CHANNELS),
            f" ({skipped} older channels skipped by the cap)" if skipped else "",
        )

    async def rescan_friend_requests(self) -> None:
        for relationship in self.relationships:
            await self.handle_friend_request(relationship)

    async def on_ready(self) -> None:
        log.info("connected as %s", self.user)
        await self.sync_channel_directory()
        # Every READY, not just the first: requests sent while a reconnect was
        # in progress arrive only in the READY relationship list, never as a
        # RELATIONSHIP_ADD event. Cache-only and deduped, so it costs nothing.
        await self.rescan_friend_requests()
        if self._ready_once:
            # READY fires again after a full reconnect; backfill once per process.
            return
        self._ready_once = True
        async with async_session() as db:
            backfill_enabled = (await get_settings(db)).backfill_enabled
        if backfill_enabled:
            self._spawn(self.backfill())

    # -- heartbeat --------------------------------------------------------

    async def write_status(self, error: str | None = None) -> None:
        async with async_session() as db:
            row = await db.get(ListenerStatus, 1) or ListenerStatus(id=1)
            row.connected = self.is_ready() and not self.is_closed()
            if self.user:
                row.user_id = str(self.user.id)
                row.user_tag = str(self.user)
            row.heartbeat_at = _now()
            if self._last_event_at:
                row.last_event_at = self._last_event_at
            row.last_error = error
            db.add(row)
            await db.commit()

    async def heartbeat_loop(self) -> None:
        while not self.is_closed():
            try:
                await self.write_status()
            except Exception:  # noqa: BLE001
                log.exception("status write failed")
            await asyncio.sleep(HEARTBEAT_S)

    async def setup_hook(self) -> None:
        # Capture when the previous run last heartbeated *before* the new
        # heartbeat loop overwrites it -- that's where the downtime gap starts.
        async with async_session() as db:
            row = await db.get(ListenerStatus, 1)
            self._previous_heartbeat = row.heartbeat_at if row else None
        self._spawn(self.heartbeat_loop())
