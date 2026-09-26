from fastapi import APIRouter, Depends, HTTPException
from ollama import AsyncClient
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.items import attention_clause
from app.classifier.runner import get_settings
from app.config import settings as app_config
from app.db import get_db
from app.models import Item, ListenerStatus
from app.schemas import SettingsRead, SettingsUpdate, StatusRead

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsRead)
async def read_settings(db: AsyncSession = Depends(get_db)):
    return SettingsRead.model_validate(await get_settings(db))


@router.patch("/settings", response_model=SettingsRead)
async def update_settings(payload: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    row = await get_settings(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return SettingsRead.model_validate(row)


@router.get("/settings/ollama-models")
async def list_ollama_models():
    client = AsyncClient(host=app_config.ollama_base_url)
    try:
        response = await client.list()
    except Exception as exc:  # noqa: BLE001 -- surface any connectivity issue to the UI
        raise HTTPException(status_code=502, detail=f"Could not reach Ollama at {app_config.ollama_base_url}: {exc}")
    return [
        {
            "name": m.model,
            "parameter_size": m.details.parameter_size if m.details else None,
            "size_bytes": m.size,
        }
        for m in response.models
    ]


@router.get("/status", response_model=StatusRead)
async def read_status(db: AsyncSession = Depends(get_db)):
    row = await db.get(ListenerStatus, 1) or ListenerStatus(id=1, connected=False)
    pending, unseen = (
        await db.execute(
            select(
                func.count().filter(Item.status == "pending"),
                func.count().filter(and_(attention_clause(), Item.seen_at.is_(None), Item.dismissed_at.is_(None))),
            )
        )
    ).one()
    return StatusRead(
        connected=bool(row.connected),
        user_tag=row.user_tag,
        heartbeat_at=row.heartbeat_at,
        last_event_at=row.last_event_at,
        last_error=row.last_error,
        classifier_heartbeat_at=row.classifier_heartbeat_at,
        classifier_last_error=row.classifier_last_error,
        pending_count=pending,
        attention_unseen=unseen,
    )
