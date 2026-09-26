from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DiscordChannel(Base):
    """Directory of the guild text channels the account can read, written by
    the listener so the server (which has no Discord session) can offer a
    channel picker."""

    __tablename__ = "discord_channels"

    channel_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    guild_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    guild_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
