"""Listener service entrypoint: one passive Discord gateway session."""

import asyncio
import logging

import discord

from app.config import settings
from app.db import async_session
from app.listener.client import WatchClient
from app.models import ListenerStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("listener")

# After a fatal login problem, wait this long before exiting (and being
# restarted by compose) so a bad token never turns into a tight login loop.
FATAL_BACKOFF_S = 600


async def record_error(message: str) -> None:
    async with async_session() as db:
        row = await db.get(ListenerStatus, 1) or ListenerStatus(id=1)
        row.connected = False
        row.last_error = message
        db.add(row)
        await db.commit()


async def main() -> None:
    if not settings.discord_token:
        msg = "DISCORD_TOKEN is not set in .env"
        log.error(msg)
        await record_error(msg)
        await asyncio.sleep(FATAL_BACKOFF_S)
        return

    client = WatchClient()
    try:
        async with client:
            await client.start(settings.discord_token)
    except discord.LoginFailure as exc:
        log.error("login failed: %s", exc)
        await record_error(f"Login failed (token invalid or expired): {exc}")
        await asyncio.sleep(FATAL_BACKOFF_S)
    except Exception as exc:  # noqa: BLE001
        log.exception("listener crashed")
        await record_error(f"Listener crashed: {exc}")
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
