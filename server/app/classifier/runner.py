"""DB + Ollama I/O around the pure logic in prompt.py."""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.classifier.prompt import (
    BatchResult,
    ContextLine,
    Decision,
    PromptItem,
    apply_results,
    build_system_prompt,
    build_user_prompt,
)
from app.llm.ollama_provider import OllamaProvider
from app.models import AppSettings, Item, Watch

log = logging.getLogger(__name__)

BATCH_SIZE = 20
CONTEXT_MESSAGES = 8
MAX_ATTEMPTS = 3


async def get_settings(db: AsyncSession) -> AppSettings:
    row = await db.get(AppSettings, 1)
    if not row:
        row = AppSettings(id=1)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def provider_for(s: AppSettings) -> OllamaProvider:
    return OllamaProvider(s.ollama_model, num_thread=s.num_thread, keep_alive=s.keep_alive)


def to_prompt_item(local_id: int, item: Item, watch: Watch) -> PromptItem:
    return PromptItem(
        id=local_id,
        kind=item.kind,
        author_name=item.author_name,
        content=item.content,
        mentions_me=item.mentions_me,
        reply_to_me=item.reply_to_me,
        has_attachments=bool(item.attachments),
        is_dm=watch.kind == "all_dms",
        is_spam_request=item.is_spam,
    )


async def load_context(db: AsyncSession, channel_id: str | None, before: datetime) -> list[ContextLine]:
    if channel_id is None:
        return []
    rows = (
        await db.execute(
            select(Item.author_name, Item.content)
            .where(Item.channel_id == channel_id, Item.created_at < before)
            .order_by(Item.created_at.desc())
            .limit(CONTEXT_MESSAGES)
        )
    ).all()
    return [ContextLine(author_name=a, content=c) for a, c in reversed(rows)]


async def classify(
    provider: OllamaProvider, s: AppSettings, watch: Watch, items: list[Item], context: list[ContextLine]
) -> dict[int, Decision]:
    """Classifies one channel's worth of items. Returns decisions keyed by
    Item.id. Prompt ids are small 1-based indices rather than DB ids --
    a 3B model copies "3" back far more reliably than "48213"."""
    prompt_items = [to_prompt_item(n, item, watch) for n, item in enumerate(items, start=1)]
    first = items[0]
    note = None
    if watch.kind == "guild" and watch.channel_notes:
        # Threads/forum posts use their parent's note (keyed by the forum).
        note = watch.channel_notes.get(first.parent_channel_id or "") or watch.channel_notes.get(first.channel_id or "")
    # Every item in a call shares one channel (see process_pending's grouping).
    # Server channels get a "#" so they match how criteria name them ("#memes").
    where = f"#{first.channel_name}" if first.guild_id and first.channel_name else first.channel_name
    system = build_system_prompt(s.about_me, watch.label, watch.criteria, note, where)
    user = build_user_prompt(prompt_items, context, where)
    result = await provider.structured_extract(system, user, BatchResult)
    decisions = apply_results(prompt_items, result)
    return {items[n - 1].id: d for n, d in decisions.items()}


async def process_pending(db: AsyncSession) -> int:
    """One classifier pass. Items are grouped per (watch, channel) so each
    Ollama call judges a single conversation with that channel's context --
    mixing channels in one prompt confuses a small model.

    No row locks: there is exactly one classifier, and holding FOR UPDATE
    across minutes of CPU inference made the inbox's "Done"/"Mark all seen"
    hang on still-pending rows. Each batch commits as soon as it's judged."""
    s = await get_settings(db)
    rows = (
        await db.execute(
            select(Item, Watch)
            .join(Watch, Item.watch_id == Watch.id)
            .where(Item.status == "pending", Watch.enabled.is_(True))
            # Newest first, so a live DM isn't stuck behind a startup
            # catch-up's worth of older messages.
            .order_by(Item.created_at.desc())
            .limit(BATCH_SIZE * 10)
        )
    ).all()
    await db.commit()
    if not rows:
        return 0

    groups: dict[tuple[int, str | None], list[Item]] = defaultdict(list)
    watches: dict[int, Watch] = {}
    for item, watch in rows:
        groups[(watch.id, item.channel_id)].append(item)
        watches[watch.id] = watch

    provider = provider_for(s)
    done = 0
    for (watch_id, channel_id), group in groups.items():
        group.sort(key=lambda i: i.created_at)  # chronological within a conversation
        for start in range(0, len(group), BATCH_SIZE):
            batch = group[start : start + BATCH_SIZE]
            context = await load_context(db, channel_id, batch[0].created_at)
            try:
                decisions = await classify(provider, s, watches[watch_id], batch, context)
            except ValueError as exc:
                # The model answered but its output was unusable: a per-item
                # failure worth counting toward MAX_ATTEMPTS.
                log.warning("unusable model output for watch %s: %s", watch_id, exc)
                decisions = {}
            # Anything else (Ollama unreachable, model not pulled, timeout)
            # propagates: items stay pending with attempts untouched, and the
            # main loop records the error. Counting those as attempts would
            # mark every pending message "error" after a few minutes of
            # Ollama being down.
            now = datetime.now(timezone.utc)
            for item in batch:
                decision = decisions.get(item.id)
                if decision is None:
                    item.attempts += 1
                    if item.attempts >= MAX_ATTEMPTS:
                        item.status = "error"
                    continue
                item.importance = decision.importance
                item.needs_reply = decision.needs_reply
                item.reason = decision.reason
                item.status = "done"
                item.classified_at = now
                done += 1
            await db.commit()
    return done


async def purge_old(db: AsyncSession) -> int:
    s = await get_settings(db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=s.retention_days)
    # Past retention, keep only what's still asking for attention (undismissed
    # important/urgent/needs-reply). Everything else goes -- including items
    # stranded as pending because their section was disabled.
    keep = and_(
        Item.dismissed_at.is_(None),
        or_(Item.needs_reply.is_(True), Item.importance.in_(("important", "urgent"))),
    )
    result = await db.execute(delete(Item).where(Item.created_at < cutoff, not_(keep)))
    await db.commit()
    return result.rowcount or 0
