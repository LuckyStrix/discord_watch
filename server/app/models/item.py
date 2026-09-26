from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ITEM_KINDS = ("message", "friend_request", "message_request")
ITEM_STATUSES = ("pending", "done", "error")
IMPORTANCE_LEVELS = ("ignore", "fyi", "important", "urgent")


class Item(Base):
    """One thing the listener saw that the classifier should judge: a message
    in a watched channel/DM, or a friend/message request."""

    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint(f"kind IN {ITEM_KINDS}", name="ck_items_kind"),
        CheckConstraint(f"status IN {ITEM_STATUSES}", name="ck_items_status"),
        CheckConstraint(f"importance IS NULL OR importance IN {IMPORTANCE_LEVELS}", name="ck_items_importance"),
        Index("ix_items_status_watch", "status", "watch_id"),
        Index("ix_items_channel_created", "channel_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("watches.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # Unique so a backfill overlapping a live event can't double-insert;
    # NULL for friend requests, which aren't messages.
    discord_message_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    guild_id: Mapped[str | None] = mapped_column(String(32))
    guild_name: Mapped[str | None] = mapped_column(String(255))
    channel_id: Mapped[str | None] = mapped_column(String(32))
    channel_name: Mapped[str | None] = mapped_column(String(255))
    # For thread / forum-post messages: the channel they live under, so
    # per-channel notes (keyed by the forum/channel) apply to them too.
    parent_channel_id: Mapped[str | None] = mapped_column(String(32))
    author_id: Mapped[str | None] = mapped_column(String(32))
    author_name: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    attachments: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    mentions_me: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    reply_to_me: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Discord's own spam flag on message requests.
    is_spam: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    jump_url: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    importance: Mapped[str | None] = mapped_column(String(16))
    needs_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    reason: Mapped[str | None] = mapped_column(Text)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
