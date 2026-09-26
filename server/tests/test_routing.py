from app.listener.routing import IncomingMessage, Route, WatchRef, needs_backfill, route_message

DMS = WatchRef(1, "all_dms", None, True)
REQUESTS = WatchRef(2, "requests", None, True)
RAIDS = WatchRef(3, "channel", "100", True)
OFF = WatchRef(4, "channel", "200", False)
ALL = [DMS, REQUESTS, RAIDS, OFF]


def msg(channel_type="guild", channel_id="100", parent=None, me=False, request=False, guild=None, category=None) -> IncomingMessage:
    return IncomingMessage(channel_type, channel_id, parent, me, request, guild, category)


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


GUILD = WatchRef(5, "guild", None, True, guild_id="77")


def test_whole_server_watch_covers_every_channel_and_thread_in_it():
    watches = ALL + [GUILD]
    assert route_message(msg(channel_id="555", guild="77"), watches) == Route(5, "message")
    assert route_message(msg(channel_id="556", parent="555", guild="77"), watches) == Route(5, "message")
    # Other servers are untouched.
    assert route_message(msg(channel_id="555", guild="88"), watches) is None


def test_channel_watch_beats_its_servers_watch():
    watches = ALL + [GUILD]
    assert route_message(msg(channel_id="100", guild="77"), watches) == Route(3, "message")
    assert route_message(msg(channel_id="101", parent="100", guild="77"), watches) == Route(3, "message")


def test_disabled_server_watch_drops_its_messages():
    watches = ALL + [WatchRef(5, "guild", None, False, guild_id="77")]
    assert route_message(msg(channel_id="555", guild="77"), watches) is None


def test_server_watch_exclusions_drop_channels_their_threads_and_categories():
    guild = WatchRef(
        5, "guild", None, True, guild_id="77",
        excluded_channel_ids=frozenset({"600"}), excluded_category_ids=frozenset({"900"}),
    )
    watches = ALL + [guild]
    assert route_message(msg(channel_id="600", guild="77"), watches) is None
    assert route_message(msg(channel_id="601", parent="600", guild="77"), watches) is None  # thread in it
    assert route_message(msg(channel_id="700", guild="77", category="900"), watches) is None
    assert route_message(msg(channel_id="701", guild="77", category="901"), watches) == Route(5, "message")


def test_explicit_channel_watch_survives_its_servers_exclusions():
    guild = WatchRef(5, "guild", None, True, guild_id="77", excluded_category_ids=frozenset({"900"}))
    assert route_message(msg(channel_id="100", guild="77", category="900"), ALL + [guild]) == Route(3, "message")


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


def test_always_catch_up_ignores_read_marker_and_fills_the_downtime_gap():
    # Read on another device (acked == last), but the listener was down since 300.
    assert needs_backfill("500", "500", None) is None
    assert needs_backfill("500", "500", None, always=True, offline_since=300) == 300
    # Already stored past the downtime start: only fetch after what we have.
    assert needs_backfill("500", "500", "450", always=True, offline_since=300) == 450
    # Nothing happened during the downtime.
    assert needs_backfill("200", "200", None, always=True, offline_since=300) is None


def test_always_catch_up_on_first_run_falls_back_to_unread_only():
    assert needs_backfill("500", "500", None, always=True, offline_since=None) is None
    assert needs_backfill("500", "400", None, always=True, offline_since=None) == 400


def test_never_opened_channel_is_capped_by_age_not_fetched_from_the_beginning():
    # No read marker, nothing stored: without the age cap this meant "fetch the
    # newest 25 whatever their age" -- years-old messages treated as new.
    assert needs_backfill("500", None, None, oldest_allowed=450) == 450
    # Whole channel is older than the cap: nothing to fetch at all.
    assert needs_backfill("400", None, None, oldest_allowed=450) is None
    # The cap also bounds "always catch up" and ordinary unread channels.
    assert needs_backfill("500", "100", None, oldest_allowed=450) == 450
    assert needs_backfill("500", "500", None, always=True, offline_since=100, oldest_allowed=450) == 450
    # A newer read marker / stored message still wins over the cap.
    assert needs_backfill("500", "480", None, oldest_allowed=450) == 480


def test_backfill_compares_snowflakes_numerically():
    # Lexically "99" > "100"; numerically it isn't.
    assert needs_backfill("100", "99", None) == 99
