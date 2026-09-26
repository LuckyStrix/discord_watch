from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    watch_id: int
    watch_label: str | None = None
    kind: str
    guild_name: str | None
    channel_name: str | None
    author_name: str | None
    content: str
    attachments: list
    mentions_me: bool
    reply_to_me: bool
    is_spam: bool
    jump_url: str | None
    created_at: datetime
    status: str
    importance: str | None
    needs_reply: bool
    reason: str | None
    seen_at: datetime | None
    dismissed_at: datetime | None


class ItemUpdate(BaseModel):
    seen: bool | None = None
    dismissed: bool | None = None


class WatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    guild_id: str | None
    channel_id: str | None
    label: str
    criteria: str
    enabled: bool
    always_catch_up: bool
    excluded_channel_ids: list[str]
    excluded_category_ids: list[str]
    created_at: datetime
    pending_count: int = 0
    attention_count: int = 0
    # From the channel directory, for grouping the Watching page by server.
    guild_name: str | None = None
    channel_name: str | None = None


class WatchCreate(BaseModel):
    """Exactly one of channel_id (one channel) or guild_id (a whole server)."""

    channel_id: str | None = None
    guild_id: str | None = None
    criteria: str = ""


class WatchUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    criteria: str | None = None
    enabled: bool | None = None
    always_catch_up: bool | None = None
    excluded_channel_ids: list[str] | None = None
    excluded_category_ids: list[str] | None = None


class TestResult(BaseModel):
    item_id: int
    author_name: str | None
    content: str
    importance: str | None
    needs_reply: bool
    reason: str | None
    previous_importance: str | None


class ChannelRead(BaseModel):
    channel_id: str
    name: str
    category: str | None
    category_id: str | None
    watch_id: int | None  # None = not watched


class GuildRead(BaseModel):
    guild_id: str
    guild_name: str
    watch_id: int | None  # the whole-server watch, if any
    channels: list[ChannelRead]


class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ollama_model: str
    num_thread: int
    keep_alive: str
    batch_interval_s: int
    retention_days: int
    about_me: str
    backfill_enabled: bool


class SettingsUpdate(BaseModel):
    ollama_model: str | None = Field(default=None, min_length=1)
    num_thread: int | None = Field(default=None, ge=1, le=64)
    keep_alive: str | None = Field(default=None, pattern=r"^\d+[smh]?$")
    batch_interval_s: int | None = Field(default=None, ge=10, le=3600)
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    about_me: str | None = None
    backfill_enabled: bool | None = None


class StatusRead(BaseModel):
    connected: bool
    user_tag: str | None
    heartbeat_at: datetime | None
    last_event_at: datetime | None
    last_error: str | None
    classifier_heartbeat_at: datetime | None
    classifier_last_error: str | None
    pending_count: int
    attention_unseen: int
