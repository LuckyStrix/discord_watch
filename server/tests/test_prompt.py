from app.classifier.prompt import (
    BatchResult,
    ContextLine,
    ItemResult,
    PromptItem,
    apply_results,
    build_system_prompt,
    build_user_prompt,
    floor_importance,
    is_attention,
)


def item(id: int, **kw) -> PromptItem:
    return PromptItem(id=id, kind=kw.pop("kind", "message"), author_name=kw.pop("author", "alice"), content=kw.pop("content", "hi"), **kw)


def test_system_prompt_includes_criteria_and_about_me():
    s = build_system_prompt("I run the raid team.", "Guild › #raids", "Schedule changes for Friday raids")
    assert "I run the raid team." in s
    assert "Guild › #raids" in s
    assert "Schedule changes for Friday raids" in s


def test_system_prompt_without_criteria_falls_back_to_general_judgement():
    s = build_system_prompt("", "All DMs", "   ")
    assert "no specific criteria" in s
    assert "About the user" not in s


def test_user_prompt_marks_flags_and_separates_context():
    p = build_user_prompt(
        [item(1, mentions_me=True, content="can you review this?"), item(2, kind="friend_request", content="req")],
        [ContextLine("bob", "earlier stuff")],
    )
    context_part, items_part = p.split("Items to judge:")
    assert "earlier stuff" in context_part
    assert "#1 alice [@mentions the user]: can you review this?" in items_part
    assert "FRIEND REQUEST" in items_part


def test_user_prompt_clips_long_content_and_collapses_whitespace():
    p = build_user_prompt([item(1, content="word\n\n" * 1000)], [])
    line = p.splitlines()[-1]
    assert "\n" not in line
    assert line.endswith("…")


def test_floor_lifts_direct_items_to_fyi():
    assert floor_importance(item(1, is_dm=True), "ignore") == "fyi"
    assert floor_importance(item(1, mentions_me=True), "ignore") == "fyi"
    assert floor_importance(item(1, reply_to_me=True), "ignore") == "fyi"
    assert floor_importance(item(1, kind="friend_request"), "ignore") == "fyi"
    assert floor_importance(item(1, kind="message_request"), "ignore") == "fyi"


def test_floor_leaves_channel_chatter_and_spam_alone():
    assert floor_importance(item(1), "ignore") == "ignore"
    assert floor_importance(item(1, kind="message_request", is_spam_request=True), "ignore") == "ignore"
    assert floor_importance(item(1, is_dm=True), "urgent") == "urgent"


def test_apply_results_drops_unknown_and_duplicate_ids_and_leaves_missing_absent():
    items = [item(1), item(2, is_dm=True), item(3)]
    result = BatchResult(
        results=[
            ItemResult(id=1, importance="important", needs_reply=True, reason=" Asks you to review. "),
            ItemResult(id=1, importance="ignore", needs_reply=False, reason="dup"),
            ItemResult(id=2, importance="ignore", needs_reply=False, reason="chatter"),
            ItemResult(id=99, importance="urgent", needs_reply=True, reason="hallucinated"),
        ]
    )
    d = apply_results(items, result)
    assert set(d) == {1, 2}
    assert d[1].importance == "important" and d[1].needs_reply and d[1].reason == "Asks you to review."
    assert d[2].importance == "fyi"  # DM floor applied
    assert "Model said ignore" in d[2].reason


def test_attention_rule():
    assert is_attention("important", False)
    assert is_attention("urgent", False)
    assert is_attention("fyi", True)
    assert not is_attention("fyi", False)
    assert not is_attention(None, False)


def test_long_reasons_are_clipped_not_rejected():
    result = BatchResult(results=[ItemResult(id=1, importance="fyi", needs_reply=False, reason="word " * 200)])
    d = apply_results([item(1)], result)
    assert len(d[1].reason) <= 300 and d[1].reason.endswith("…")


def test_user_prompt_names_the_channel_so_per_channel_criteria_can_work():
    p = build_user_prompt([item(1)], [], "general › memes")
    assert p.startswith("Channel: general › memes")
    assert "Channel:" not in build_user_prompt([item(1)], [])


def test_channel_note_is_added_after_the_section_criteria():
    s = build_system_prompt("", "Market (whole server)", "Anything addressed to me.", "Also flag cameras under $50.", "#want-to-sell")
    assert s.index("Anything addressed to me.") < s.index("Also flag cameras under $50.")
    assert "Extra criteria for #want-to-sell specifically (in addition to the above)" in s


def test_blank_or_missing_channel_note_adds_nothing():
    base = build_system_prompt("", "Market", "Anything addressed to me.")
    assert build_system_prompt("", "Market", "Anything addressed to me.", "   ", "#x") == base
    assert "Extra criteria" not in base
