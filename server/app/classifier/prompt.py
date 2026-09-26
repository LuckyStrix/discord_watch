"""Pure prompt-building and result-applying logic for classification -- no DB,
no network, so it's unit-testable. `runner.py` owns the I/O around it."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

Importance = Literal["ignore", "fyi", "important", "urgent"]
IMPORTANCE_ORDER: list[str] = ["ignore", "fyi", "important", "urgent"]

CONTENT_LIMIT = 800
REASON_LIMIT = 300

RUBRIC = """You triage Discord activity for one person (called "the user" below) so they only look at what matters.
For EACH numbered item, decide:
- reason: first, one short plain sentence on whether and how the item relates to the user's criteria.
- importance:
  - "urgent": a time-sensitive direct request or question to the user, or something that clearly needs them soon.
  - "important": matches the user's criteria for this section, or is personally addressed to them and substantive.
  - "fyi": mildly relevant; worth a glance later, no action needed.
  - "ignore": chatter, memes, bots, spam, or anything not matching the criteria.
- needs_reply: true only if someone is waiting on the user to respond.
Judge only the numbered items. Earlier messages are context only.
Return one result per numbered item, using its number as "id"."""


class ItemResult(BaseModel):
    # Field order matters: with schema-constrained decoding the model writes
    # fields in this order, so putting `reason` before `importance` makes it
    # reason first and label second. A 3B model otherwise picks a label and
    # then writes a reason that contradicts it.
    id: int
    # No max_length: a schema limit turns one long-winded answer into a
    # validation failure (and eventually a lost item). Clipped in
    # apply_results instead.
    reason: str
    importance: Importance
    needs_reply: bool


class BatchResult(BaseModel):
    results: list[ItemResult]


@dataclass
class PromptItem:
    """The fields of an Item the prompt needs -- decoupled from the ORM model
    so tests (and the criteria dry-run) can build them directly."""

    id: int
    kind: str
    author_name: str | None
    content: str
    mentions_me: bool = False
    reply_to_me: bool = False
    has_attachments: bool = False
    is_dm: bool = False
    is_spam_request: bool = False


@dataclass
class ContextLine:
    author_name: str | None
    content: str


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= CONTENT_LIMIT else text[:CONTENT_LIMIT] + "…"


def build_system_prompt(about_me: str, section_label: str, criteria: str) -> str:
    parts = [RUBRIC]
    if about_me.strip():
        parts.append(f"About the user:\n{about_me.strip()}")
    parts.append(f'Section being reviewed: "{section_label}"')
    parts.append(
        f"The user's criteria for what is important here:\n{criteria.strip()}"
        if criteria.strip()
        else "The user gave no specific criteria for this section; use general judgement about what a busy person would want to see."
    )
    return "\n\n".join(parts)


def _describe(item: PromptItem) -> str:
    flags = []
    if item.kind == "friend_request":
        flags.append("FRIEND REQUEST")
    elif item.kind == "message_request":
        flags.append("MESSAGE REQUEST from someone who isn't a friend")
    elif item.is_dm:
        flags.append("direct message to the user")
    if item.is_spam_request:
        flags.append("Discord flagged as likely spam")
    if item.mentions_me:
        flags.append("@mentions the user")
    if item.reply_to_me:
        flags.append("replies to the user")
    if item.has_attachments:
        flags.append("has attachments")
    flag_text = f" [{'; '.join(flags)}]" if flags else ""
    return f"#{item.id} {item.author_name or 'unknown'}{flag_text}: {_clip(item.content) or '(no text)'}"


def build_user_prompt(items: list[PromptItem], context: list[ContextLine]) -> str:
    parts = []
    if context:
        lines = "\n".join(f"- {c.author_name or 'unknown'}: {_clip(c.content)}" for c in context)
        parts.append(f"Earlier messages (context only, do not judge):\n{lines}")
    parts.append("Items to judge:\n" + "\n".join(_describe(i) for i in items))
    return "\n\n".join(parts)


def floor_importance(item: PromptItem, importance: str) -> str:
    """Deterministic guardrails a 3B model can't override: anything
    addressed directly to the user (DMs, @mentions, replies, requests) is at
    least "fyi", so it never silently vanishes -- except requests Discord
    itself marked as spam."""
    if item.is_spam_request:
        return importance
    direct = item.is_dm or item.mentions_me or item.reply_to_me or item.kind in ("friend_request", "message_request")
    if direct and IMPORTANCE_ORDER.index(importance) < IMPORTANCE_ORDER.index("fyi"):
        return "fyi"
    return importance


@dataclass
class Decision:
    importance: str
    needs_reply: bool
    reason: str


def apply_results(items: list[PromptItem], result: BatchResult) -> dict[int, Decision]:
    """Maps model output back onto the batch. Results for ids that weren't in
    the batch are dropped; items the model skipped are simply absent from the
    returned dict (the caller leaves them pending for a retry)."""
    by_id = {i.id: i for i in items}
    decisions: dict[int, Decision] = {}
    for r in result.results:
        item = by_id.get(r.id)
        if item is None or r.id in decisions:
            continue
        importance = floor_importance(item, r.importance)
        reason = " ".join(r.reason.split())
        if len(reason) > REASON_LIMIT:
            reason = reason[: REASON_LIMIT - 1] + "…"
        if importance != r.importance:
            reason = f"{reason} (Model said {r.importance}; kept visible because it was sent to you directly.)"
        decisions[r.id] = Decision(importance=importance, needs_reply=r.needs_reply, reason=reason)
    return decisions


def is_attention(importance: str | None, needs_reply: bool) -> bool:
    return needs_reply or importance in ("important", "urgent")
