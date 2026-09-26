from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# "guild" watches a whole server (every channel the account can read, plus
# channels created later); a channel watch inside it takes precedence.
# The all_dms/requests kinds are singletons seeded by the initial migration --
# they exist so DMs and requests get their own editable criteria just like a
# channel does, and can't be deleted (only disabled).
WATCH_KINDS = ("channel", "guild", "all_dms", "requests")


class Watch(Base):
    __tablename__ = "watches"
    __table_args__ = (
        CheckConstraint(f"kind IN {WATCH_KINDS}", name="ck_watches_kind"),
        CheckConstraint("kind <> 'channel' OR channel_id IS NOT NULL", name="ck_watches_channel_has_id"),
        CheckConstraint("kind <> 'guild' OR guild_id IS NOT NULL", name="ck_watches_guild_has_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # Discord snowflakes are kept as strings everywhere: they exceed 2**53, so
    # as JSON numbers they'd silently lose precision in the browser.
    guild_id: Mapped[str | None] = mapped_column(String(32))
    channel_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    criteria: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Startup catch-up normally only fetches channels Discord marks unread.
    # This opts a section into fetching the whole downtime gap regardless --
    # for muted channels, or ones read on another device while the PC was off.
    always_catch_up: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Whole-server watches only: channel / category ids carved out of the
    # server. Excluding a category also covers channels added to it later.
    # An explicit channel watch still wins over either.
    excluded_channel_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    excluded_category_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
