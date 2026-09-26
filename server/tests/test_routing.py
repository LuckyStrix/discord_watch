from app.listener.routing import IncomingMessage, Route, WatchRef, needs_backfill, route_message

DMS = WatchRef(1, "all_dms", None, True)
REQUESTS = WatchRef(2, "requests", None, True)
RAIDS = WatchRef(3, "channel", "100", True)
OFF = WatchRef(4, "channel", "200", False)
ALL = [DMS, REQUESTS, RAIDS, OFF]


def msg(channel_type="guild", channel_id="100", parent=None, me=False, request=False) -> IncomingMessage:
    return IncomingMessage(channel_type, channel_id, parent, me, request)


def test_own_messages_are_dropped():
    assert route_message(msg(me=True), ALL) is None
    assert route_message(msg("dm", "9", me=True), ALL) is None


def test_dms_and_group_dms_go_to_all_dms():
    assert route_message(msg("dm", "9"), ALL) == Route(1, "message")
    assert route_message(msg("group", "9"), ALL) == Route(1, "message")


def test_pending_message_request_goes_to_requests():
    assert route_message(msg("dm", "9", request=True), ALL) == Route(2, "message_request")


def test_watched_channel_and_its_threads():
    assert route_message(msg(channel_id="100"), ALL) == Route(3, "message")
    assert route_message(msg(channel_id="555", parent="100"), ALL) == Route(3, "message")


def test_unwatched_and_disabled_channels_are_dropped():
    assert route_message(msg(channel_id="999"), ALL) is None
    assert route_message(msg(channel_id="200"), ALL) is None


def test_disabled_builtin_sections_drop_their_messages():
    watches = [WatchRef(1, "all_dms", None, False), WatchRef(2, "requests", None, False)]
    assert route_message(msg("dm", "9"), watches) is None
    assert route_message(msg("dm", "9", request=True), watches) is None


def test_backfill_only_for_unread_channels():
    # Nothing new since the user last read it.
    assert needs_backfill("500", "500", None) is None
    # Unread, nothing stored yet: fetch after the read marker.
    assert needs_backfill("500", "400", None) == 400
    # Unread, but we already stored past the read marker.
    assert needs_backfill("500", "400", "450") == 450
    assert needs_backfill("500", "400", "500") is None
    # Never read and nothing stored: fetch the most recent few.
    assert needs_backfill("500", None, None) == 0
    # Empty channel.
    assert needs_backfill(None, None, None) is None


def test_backfill_compares_snowflakes_numerically():
    # Lexically "99" > "100"; numerically it isn't.
    assert needs_backfill("100", "99", None) == 99
