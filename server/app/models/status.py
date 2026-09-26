from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ListenerStatus(Base):
    """Singleton heartbeat row the listener/classifier write so the UI can
    show whether the Discord session and the model loop are alive."""

    __tablename__ = "listener_status"
    __table_args__ = (CheckConstraint("id = 1", name="ck_listener_status_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    connected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    user_id: Mapped[str | None] = mapped_column(String(32))
    user_tag: Mapped[str | None] = mapped_column(String(255))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    classifier_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    classifier_last_error: Mapped[str | None] = mapped_column(Text)
