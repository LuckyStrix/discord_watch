from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import DiscordChannel, Watch
from app.schemas import ChannelRead, GuildRead

router = APIRouter(prefix="/discord", tags=["discord"])


@router.get("/channels", response_model=list[GuildRead])
async def list_channels(db: AsyncSession = Depends(get_db)):
    """The listener-maintained channel directory, grouped by server, for the
    'add a channel' picker."""
    channels = (await db.execute(select(DiscordChannel))).scalars().all()
    watched = dict((await db.execute(select(Watch.channel_id, Watch.id).where(Watch.kind == "channel"))).all())
    watched_guilds = dict((await db.execute(select(Watch.guild_id, Watch.id).where(Watch.kind == "guild"))).all())

    guilds: dict[str, GuildRead] = {}
    # Discord's own order: categories by position (uncategorized first), then
    # channels by position within each.
    for c in sorted(channels, key=lambda c: (c.guild_name.lower(), c.guild_id, c.category_position, c.position)):
        if c.guild_id not in guilds:
            guilds[c.guild_id] = GuildRead(
                guild_id=c.guild_id, guild_name=c.guild_name, watch_id=watched_guilds.get(c.guild_id), channels=[]
            )
        guild = guilds[c.guild_id]
        guild.channels.append(
            ChannelRead(
                channel_id=c.channel_id,
                name=c.name,
                category=c.category,
                category_id=c.category_id,
                watch_id=watched.get(c.channel_id),
            )
        )
    return list(guilds.values())
