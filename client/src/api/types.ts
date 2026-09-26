export type Importance = "ignore" | "fyi" | "important" | "urgent";

export interface Item {
  id: number;
  watch_id: number;
  watch_label: string | null;
  kind: "message" | "friend_request" | "message_request";
  guild_name: string | null;
  channel_name: string | null;
  author_name: string | null;
  content: string;
  attachments: { filename: string; url: string; content_type: string | null }[];
  mentions_me: boolean;
  reply_to_me: boolean;
  is_spam: boolean;
  jump_url: string | null;
  created_at: string;
  status: "pending" | "done" | "error";
  importance: Importance | null;
  needs_reply: boolean;
  reason: string | null;
  seen_at: string | null;
  dismissed_at: string | null;
}

export interface Watch {
  id: number;
  kind: "channel" | "guild" | "all_dms" | "requests";
  guild_id: string | null;
  channel_id: string | null;
  label: string;
  criteria: string;
  enabled: boolean;
  always_catch_up: boolean;
  excluded_channel_ids: string[];
  excluded_category_ids: string[];
  channel_notes: Record<string, string>;
  created_at: string;
  pending_count: number;
  attention_count: number;
  guild_name: string | null;
  channel_name: string | null;
}

export interface TestResult {
  item_id: number;
  author_name: string | null;
  content: string;
  importance: Importance | null;
  needs_reply: boolean;
  reason: string | null;
  previous_importance: Importance | null;
}

export interface Guild {
  guild_id: string;
  guild_name: string;
  watch_id: number | null;
  channels: {
    channel_id: string;
    name: string;
    category: string | null;
    category_id: string | null;
    watch_id: number | null;
  }[];
}

export interface AppSettings {
  ollama_model: string;
  num_thread: number;
  keep_alive: string;
  batch_interval_s: number;
  retention_days: number;
  about_me: string;
  backfill_enabled: boolean;
}

export interface OllamaModel {
  name: string;
  parameter_size: string | null;
  size_bytes: number;
}

export interface Status {
  connected: boolean;
  user_tag: string | null;
  heartbeat_at: string | null;
  last_event_at: string | null;
  last_error: string | null;
  classifier_heartbeat_at: string | null;
  classifier_last_error: string | null;
  pending_count: number;
  attention_unseen: number;
}
