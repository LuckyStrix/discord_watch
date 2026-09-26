from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Item, Watch
from app.schemas import BulkItemUpdate, ItemRead, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])


def attention_clause():
    """Mirrors app.classifier.prompt.is_attention in SQL."""
    return or_(Item.needs_reply.is_(True), Item.importance.in_(("important", "urgent")))


def _to_read(item: Item, label: str | None) -> ItemRead:
    read = ItemRead.model_validate(item)
    read.watch_label = label
    return read


@router.get("", response_model=list[ItemRead])
async def list_items(
    filter: Literal["attention", "all"] = "attention",
    watch_id: int | None = None,
    include_dismissed: bool = False,
    before_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Item, Watch.label).join(Watch, Item.watch_id == Watch.id)
    if filter == "attention":
        stmt = stmt.where(attention_clause())
    if watch_id is not None:
        stmt = stmt.where(Item.watch_id == watch_id)
    if not include_dismissed:
        stmt = stmt.where(Item.dismissed_at.is_(None))
    if before_id is not None:
        stmt = stmt.where(Item.id < before_id)
    rows = (await db.execute(stmt.order_by(Item.id.desc()).limit(limit))).all()
    return [_to_read(item, label) for item, label in rows]


def _apply(values: ItemUpdate) -> dict:
    now = datetime.now(timezone.utc)
    changes: dict = {}
    if values.seen is not None:
        changes["seen_at"] = now if values.seen else None
    if values.dismissed is not None:
        changes["dismissed_at"] = now if values.dismissed else None
        if values.dismissed:
            changes.setdefault("seen_at", now)
    return changes


@router.patch("/{item_id}", response_model=ItemRead)
async def update_item(item_id: int, payload: ItemUpdate, db: AsyncSession = Depends(get_db)):
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for field, value in _apply(payload).items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    watch = await db.get(Watch, item.watch_id)
    return _to_read(item, watch.label if watch else None)


@router.post("/bulk")
async def bulk_update(payload: BulkItemUpdate, db: AsyncSession = Depends(get_db)):
    changes = _apply(payload)
    if not payload.ids or not changes:
        return {"updated": 0}
    # Only stamp items that don't already have a timestamp, so "mark all seen"
    # doesn't rewrite when earlier items were actually seen.
    stmt = update(Item).where(Item.id.in_(payload.ids))
    if "seen_at" in changes and changes["seen_at"] is not None and "dismissed_at" not in changes:
        stmt = stmt.where(Item.seen_at.is_(None))
    result = await db.execute(stmt.values(**changes))
    await db.commit()
    return {"updated": result.rowcount}


@router.post("/{item_id}/reclassify", response_model=ItemRead)
async def reclassify(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.status = "pending"
    item.attempts = 0
    await db.commit()
    await db.refresh(item)
    watch = await db.get(Watch, item.watch_id)
    return _to_read(item, watch.label if watch else None)
