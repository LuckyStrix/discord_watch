"""Classifier service: every `batch_interval_s`, judge pending items with the
local model. A plain async loop instead of notes_app's RQ worker -- there is
exactly one periodic job, so a status column + SKIP LOCKED is all the queue
this needs."""

import asyncio
import logging
import time
from datetime import datetime, timezone

from app.classifier.runner import get_settings, process_pending, purge_old
from app.db import async_session
from app.models import ListenerStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("classifier")

PURGE_EVERY_S = 3600


async def heartbeat(error: str | None) -> None:
    async with async_session() as db:
        row = await db.get(ListenerStatus, 1) or ListenerStatus(id=1)
        row.classifier_heartbeat_at = datetime.now(timezone.utc)
        row.classifier_last_error = error
        db.add(row)
        await db.commit()


async def main() -> None:
    last_purge = 0.0
    while True:
        error = None
        interval = 45
        try:
            async with async_session() as db:
                interval = (await get_settings(db)).batch_interval_s
                done = await process_pending(db)
                if done:
                    log.info("classified %d items", done)
                if time.monotonic() - last_purge > PURGE_EVERY_S:
                    purged = await purge_old(db)
                    last_purge = time.monotonic()
                    if purged:
                        log.info("purged %d old items", purged)
        except Exception as exc:  # noqa: BLE001 -- keep the loop alive through DB/Ollama blips
            log.exception("classifier pass failed")
            error = str(exc)[:500]
        try:
            await heartbeat(error)
        except Exception:  # noqa: BLE001
            log.exception("heartbeat failed")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
