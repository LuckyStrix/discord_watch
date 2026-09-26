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
    watched = set((await db.execute(select(Watch.channel_id).where(Watch.channel_id.is_not(None)))).scalars().all())

    guilds: dict[str, GuildRead] = {}
    for c in sorted(channels, key=lambda c: (c.guild_name.lower(), c.category or "", c.position)):
        guild = guilds.setdefault(c.guild_id, GuildRead(guild_id=c.guild_id, guild_name=c.guild_name, channels=[]))
        guild.channels.append(
            ChannelRead(channel_id=c.channel_id, name=c.name, category=c.category, watched=c.channel_id in watched)
        )
    return list(guilds.values())
