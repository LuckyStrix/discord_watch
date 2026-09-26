from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AppSettings(Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_app_settings_singleton"),
        CheckConstraint("num_thread > 0", name="ck_app_settings_num_thread"),
        CheckConstraint("batch_interval_s >= 10", name="ck_app_settings_batch_interval"),
        CheckConstraint("retention_days > 0", name="ck_app_settings_retention"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    ollama_model: Mapped[str] = mapped_column(String(128), nullable=False, server_default="qwen2.5:3b-instruct-q4_K_M")
    # Classification always runs CPU-only (num_gpu=0, see OllamaProvider) so it
    # never competes with games/other GPU work for VRAM. num_thread caps how
    # many cores a batch can take -- the knob for "don't notice it".
    num_thread: Mapped[int] = mapped_column(Integer, nullable=False, server_default="4")
    # Ollama duration string; how long the model stays in RAM after a batch.
    keep_alive: Mapped[str] = mapped_column(String(16), nullable=False, server_default="2m")
    batch_interval_s: Mapped[int] = mapped_column(Integer, nullable=False, server_default="45")
    # ignore/fyi items (and anything dismissed) older than this are purged.
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="14")
    # Global context prepended to every classification prompt.
    about_me: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # On listener startup, fetch messages missed while offline -- only for
    # watched channels that Discord reports as having unread messages.
    backfill_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
