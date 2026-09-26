from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.items import attention_clause
from app.classifier.runner import classify, get_settings, load_context, provider_for
from app.db import get_db
from app.models import DiscordChannel, Item, Watch
from app.schemas import TestResult, WatchCreate, WatchRead, WatchUpdate

router = APIRouter(prefix="/watches", tags=["watches"])

TEST_SAMPLE = 20
# Built-ins sort first, in this order, then channels by server/name.
KIND_ORDER = {"all_dms": 0, "requests": 1, "guild": 2, "channel": 3}


async def _counts(db: AsyncSession) -> dict[int, tuple[int, int]]:
    rows = (
        await db.execute(
            select(
                Item.watch_id,
                func.count().filter(Item.status == "pending"),
                func.count().filter(and_(attention_clause(), Item.dismissed_at.is_(None), Item.seen_at.is_(None))),
            ).group_by(Item.watch_id)
        )
    ).all()
    return {w: (p, a) for w, p, a in rows}


def _to_read(w: Watch, counts: dict[int, tuple[int, int]]) -> WatchRead:
    read = WatchRead.model_validate(w)
    read.pending_count, read.attention_count = counts.get(w.id, (0, 0))
    return read


async def _directory_names(db: AsyncSession, watches: list[Watch]) -> dict[str, tuple[str, str, str]]:
    """channel_id -> (guild_id, guild_name, channel_name) for every channel in
    a server that has any watch, so both channel and whole-server watches can
    be labelled from the live directory (names follow renames)."""
    guild_ids = {w.guild_id for w in watches if w.guild_id}
    if not guild_ids:
        return {}
    rows = (
        await db.execute(
            select(DiscordChannel.channel_id, DiscordChannel.guild_id, DiscordChannel.guild_name, DiscordChannel.name)
            .where(DiscordChannel.guild_id.in_(guild_ids))
        )
    ).all()
    return {cid: (gid, gname, cname) for cid, gid, gname, cname in rows}


@router.get("", response_model=list[WatchRead])
async def list_watches(db: AsyncSession = Depends(get_db)):
    watches = (await db.execute(select(Watch))).scalars().all()
    counts = await _counts(db)
    directory = await _directory_names(db, watches)
    guild_names = {gid: gname for gid, gname, _ in directory.values()}
    watches = sorted(watches, key=lambda w: (KIND_ORDER.get(w.kind, 9), w.label.lower()))
    result = []
    for w in watches:
        read = _to_read(w, counts)
        if w.guild_id:
            read.guild_name = guild_names.get(w.guild_id)
        if w.channel_id and w.channel_id in directory:
            read.channel_name = directory[w.channel_id][2]
        result.append(read)
    return result


@router.post("", response_model=WatchRead, status_code=201)
async def create_watch(payload: WatchCreate, db: AsyncSession = Depends(get_db)):
    if (payload.channel_id is None) == (payload.guild_id is None):
        raise HTTPException(status_code=422, detail="Give exactly one of channel_id or guild_id")
    if payload.guild_id is not None:
        return await _create_guild_watch(payload.guild_id, payload.criteria, db)
    channel = await db.get(DiscordChannel, payload.channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Unknown channel -- is the listener connected?")
    existing = (await db.execute(select(Watch).where(Watch.channel_id == payload.channel_id))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="That channel is already watched")
    watch = Watch(
        kind="channel",
        guild_id=channel.guild_id,
        channel_id=channel.channel_id,
        label=f"{channel.guild_name} › #{channel.name}",
        criteria=payload.criteria,
    )
    db.add(watch)
    await db.commit()
    await db.refresh(watch)
    return _to_read(watch, {})


async def _create_guild_watch(guild_id: str, criteria: str, db: AsyncSession) -> WatchRead:
    known = (
        await db.execute(select(DiscordChannel.guild_name).where(DiscordChannel.guild_id == guild_id).limit(1))
    ).scalar_one_or_none()
    if known is None:
        raise HTTPException(status_code=404, detail="Unknown server -- is the listener connected?")
    existing = (
        await db.execute(select(Watch).where(Watch.kind == "guild", Watch.guild_id == guild_id))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="That server is already watched")
    watch = Watch(kind="guild", guild_id=guild_id, label=f"{known} (whole server)", criteria=criteria)
    db.add(watch)
    await db.commit()
    await db.refresh(watch)
    return _to_read(watch, {})


async def _get(db: AsyncSession, watch_id: int) -> Watch:
    watch = await db.get(Watch, watch_id)
    if not watch:
        raise HTTPException(status_code=404, detail="Watch not found")
    return watch


@router.patch("/{watch_id}", response_model=WatchRead)
async def update_watch(watch_id: int, payload: WatchUpdate, db: AsyncSession = Depends(get_db)):
    watch = await _get(db, watch_id)
    changes = payload.model_dump(exclude_unset=True)
    if watch.kind != "guild" and ({"excluded_channel_ids", "excluded_category_ids"} & changes.keys()):
        raise HTTPException(status_code=400, detail="Only whole-server sections have exclusions")
    for key in ("excluded_channel_ids", "excluded_category_ids"):
        if key in changes:
            changes[key] = sorted(set(changes[key]))
    for field, value in changes.items():
        setattr(watch, field, value)
    await db.commit()
    await db.refresh(watch)
    return _to_read(watch, await _counts(db))


@router.delete("/{watch_id}", status_code=204)
async def delete_watch(watch_id: int, db: AsyncSession = Depends(get_db)):
    watch = await _get(db, watch_id)
    if watch.kind in ("all_dms", "requests"):
        raise HTTPException(status_code=400, detail="Built-in sections can be disabled, not deleted")
    await db.delete(watch)
    await db.commit()


@router.post("/{watch_id}/test", response_model=list[TestResult])
async def test_criteria(watch_id: int, db: AsyncSession = Depends(get_db)):
    """Dry-runs the watch's *current* criteria over its most recent items and
    returns what the model would decide now, next to what it decided before --
    nothing is saved. For tuning criteria without waiting for new messages."""
    watch = await _get(db, watch_id)
    s = await get_settings(db)
    items = (
        (await db.execute(select(Item).where(Item.watch_id == watch_id).order_by(Item.created_at.desc()).limit(TEST_SAMPLE)))
        .scalars()
        .all()
    )
    items = list(reversed(items))
    if not items:
        return []

    by_channel: dict[str | None, list[Item]] = {}
    for item in items:
        by_channel.setdefault(item.channel_id, []).append(item)

    provider = provider_for(s)
    decisions = {}
    try:
        for channel_id, group in by_channel.items():
            context = await load_context(db, channel_id, group[0].created_at)
            decisions.update(await classify(provider, s, watch, group, context))
    except Exception as exc:  # noqa: BLE001 -- surface Ollama problems to the UI
        raise HTTPException(status_code=502, detail=f"Model call failed: {exc}")

    results = []
    for item in items:
        d = decisions.get(item.id)
        results.append(
            TestResult(
                item_id=item.id,
                author_name=item.author_name,
                content=item.content,
                importance=d.importance if d else None,
                needs_reply=d.needs_reply if d else False,
                reason=d.reason if d else "Model returned no result for this item",
                previous_importance=item.importance,
            )
        )
    return results


@router.post("/{watch_id}/reclassify")
async def reclassify_watch(watch_id: int, db: AsyncSession = Depends(get_db)):
    """Re-queues the watch's undismissed items so new criteria apply to them."""
    await _get(db, watch_id)
    items = (
        (await db.execute(select(Item).where(Item.watch_id == watch_id, Item.dismissed_at.is_(None)))).scalars().all()
    )
    for item in items:
        item.status = "pending"
        item.attempts = 0
    await db.commit()
    return {"queued": len(items)}
