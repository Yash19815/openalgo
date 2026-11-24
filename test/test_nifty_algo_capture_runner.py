"""Recorder scheduling reuses a verified native feed without trading authority."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from sqlalchemy import event

from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.runner import NiftyRunner, attach_runner, restore_runners
from test.test_nifty_algo_native_capture import NOW
from test.test_nifty_algo_pipeline import DeterministicMarket, master_rows, pipeline
from test.test_nifty_algo_recording import store as store
from test.test_nifty_algo_recording_api import BODY, URL
from test.test_nifty_algo_safety_center import client as client
from test.test_nifty_algo_safety_center import login

USER = "recorder-owner"


@pytest.fixture
def feed(store, monkeypatch):
    import database.auth_db as auth
    import services.market_data_service as cache
    import services.websocket_service as sockets

    class SourceCache(DeterministicMarket):
        def __init__(self):
            super().__init__()
            self.reads = []
            self.health_monitor = Mock()
            self.health_monitor.get_health.return_value = {"reconnect_count": 0}
            self.process_market_data = Mock()

        def get_all_data(self, symbol, exchange):
            self.reads.append(symbol)
            result = super().get_all_data(symbol, exchange)
            for raw in result["source_observations"].values():
                raw.update(
                    symbol=symbol,
                    exchange=exchange,
                    ltt=self.stamp - timedelta(seconds=2),
                    received_time=self.stamp - timedelta(seconds=1),
                )
            return result

    market = SourceCache()
    market.stamp = NOW
    active = []
    client = Mock(connected=True, authenticated=True)
    client.get_subscriptions.side_effect = lambda: {"subscriptions": list(active)}

    def subscribe(symbols, mode):
        entries = [{**row, "mode": mode, "status": "success"} for row in symbols]
        active.extend(entries)
        return {"status": "success", "subscriptions": entries}

    client.subscribe.side_effect = subscribe
    connection = Mock(return_value=(True, client, None))
    shared_cache = Mock(return_value=market)
    monkeypatch.setattr(auth, "get_api_key_for_tradingview", lambda _: "offline-key")
    monkeypatch.setattr(auth, "get_broker_name", lambda _: "angel")
    monkeypatch.setattr(sockets, "get_websocket_connection", connection)
    monkeypatch.setattr(cache, "get_market_data_service", shared_cache)
    store.ensure_user(USER)
    runner = NiftyRunner(store, USER, native=pipeline(market), clock=lambda: market.stamp)
    runner._native_feed(StrategyConfig(), NOW)
    assert runner._lease(NOW)
    client.subscribe.reset_mock()
    connection.reset_mock()
    shared_cache.reset_mock()
    yield SimpleNamespace(
        runner=runner,
        market=market,
        client=client,
        active=active,
        connection=connection,
        shared_cache=shared_cache,
    )
    runner.close()


def recording(store, **changes):
    return store.create_recording(
        USER, NOW, NOW + timedelta(hours=1), NOW, native_capture=True, **changes
    )


@pytest.mark.parametrize("native_capture", [True, False])
def test_http_opt_in_to_cache_capture_and_seal_preserves_paper_state(
    store, feed, client, monkeypatch, native_capture
):
    import blueprints.nifty_algo as controls

    headers = login(client, USER)
    server_time = Mock(wraps=controls.datetime)
    server_time.now.side_effect = lambda _: feed.market.stamp
    monkeypatch.setattr(controls, "datetime", server_time)
    before = store.read(USER)
    lease = store.runner_status(USER, NOW)
    created = client.post(URL, json={**BODY, "native_capture": native_capture}, headers=headers)
    assert created.status_code == 201
    manifest = created.json["data"]
    page_url = f"{URL}/{manifest['id']}"
    feed.runner.capture()
    feed.market.stamp += timedelta(seconds=3)
    feed.runner.capture()
    page = client.get(page_url).json["data"]
    expected = 2 if native_capture else 0
    assert page["manifest"]["count"] == len(page["items"]) == expected
    if native_capture:
        assert {row["source"] for row in page["items"]} == {"NATIVE_FEED"}
        assert {row["available_at"] for row in page["items"]} == {feed.market.stamp.isoformat()}
        assert page["manifest"]["capture"]["scope"]["broker"] == "angel"
        assert (
            client.get(page_url, query_string={"as_of": NOW.isoformat()}).json["data"]["items"]
            == []
        )
    else:
        assert page["manifest"]["capture"] is None
    sealed = client.post(
        page_url + "/seal",
        json={"expected_count": expected, "confirm": "SEAL_ONLY"},
        headers=headers,
    )
    assert sealed.status_code == 200
    assert sealed.json["data"]["status"] == "SEALED"
    assert sealed.json["data"]["execution_eligible"] is False
    assert feed.runner.capture() is None
    assert store.read(USER) == before
    assert store.runner_status(USER, NOW) == lease
    assert not store.pending_orders(USER) and not store.positions(USER)
    assert not feed.connection.called and not feed.shared_cache.called
    assert not feed.client.subscribe.called
    assert client.get(page_url).headers["Cache-Control"] == "private, no-store"
    login(client, "another-owner")
    assert client.get(page_url).status_code == 404


def test_capture_freezes_server_scope_then_deduplicates_without_renewing_lease(store, feed):
    before = store.read(USER)
    manifest = recording(store)
    heartbeat = store.runner_status(USER, NOW)
    first = feed.runner.capture()
    assert first["count"] == 0
    assert {row["token"] for row in first["capture"]["scope"]["instruments"]} == {"ce", "pe"}
    feed.market.stamp += timedelta(seconds=3)
    saved = feed.runner.capture()
    assert saved["count"] == 2
    assert feed.runner.capture() == saved
    page = store.recording_page(USER, manifest["id"])
    assert page["manifest"] == saved and len(page["items"]) == 2
    assert {row["available_at"] for row in page["items"]} == {feed.market.stamp.isoformat()}
    assert store.runner_status(USER, NOW) == heartbeat
    assert store.read(USER) == before
    assert not feed.client.subscribe.called
    assert not feed.connection.called and not feed.shared_cache.called
    assert not store.pending_orders(USER) and not store.positions(USER)


@pytest.mark.parametrize("state", ["legacy", "sealed", "full", "expired", "missing"])
def test_capture_skips_unavailable_recordings_without_reading_quotes(store, feed, state):
    if state == "legacy":
        store.create_recording(USER, NOW, NOW + timedelta(hours=1), NOW)
    elif state != "missing":
        manifest = recording(store, max_observations=1 if state == "full" else 100)
        if state == "sealed":
            store.seal_recording(USER, manifest["id"], NOW, expected_count=0)
        elif state == "full":
            feed.runner.capture()
            feed.market.stamp += timedelta(seconds=3)
            assert feed.runner.capture()["count"] == 1
        elif state == "expired":
            feed.market.stamp += timedelta(hours=1)
    feed.market.reads.clear()
    assert feed.runner.capture() is None
    assert feed.market.reads == []


@pytest.mark.parametrize(
    "state", ["disconnected", "unauthenticated", "socket", "reconnect", "stale", "master", "depth"]
)
def test_capture_does_not_read_quotes_from_unverified_feed_context(store, feed, state):
    manifest = recording(store)
    if state == "disconnected":
        feed.client.connected = False
    elif state == "unauthenticated":
        feed.client.authenticated = False
    elif state == "socket":
        feed.client.ws = object()
    elif state == "reconnect":
        feed.market.health_monitor.get_health.return_value = {"reconnect_count": 1}
    elif state == "stale":
        feed.market.stamp += timedelta(seconds=11)
    elif state == "master":
        feed.runner.native.master_reader = lambda: {"is_ready": False}
    else:
        feed.active.clear()
    assert feed.runner.capture() is None
    assert feed.market.reads == []
    assert store.recording_page(USER, manifest["id"])["manifest"] == manifest


def test_capture_rechecks_owner_at_append_without_renewal(store, feed, monkeypatch):
    manifest = recording(store)
    feed.runner.capture()
    feed.market.stamp += timedelta(seconds=3)
    append = store.append_recording

    def takeover(*args, **kwargs):
        store.release_runner(USER, feed.runner.owner)
        assert store.claim_runner(
            USER, "replacement", feed.market.stamp, payload={"sentinel": True}
        )
        return append(*args, **kwargs)

    monkeypatch.setattr(store, "append_recording", takeover)
    assert feed.runner.capture() is None
    assert store.recording_page(USER, manifest["id"])["manifest"]["count"] == 0
    assert store.runner_status(USER, NOW)["sentinel"] is True


@pytest.mark.parametrize("changed", ["token", "strike", "master_broker", "master_freshness"])
def test_capture_does_not_freeze_master_identities_changed_between_feed_reads(
    store, feed, monkeypatch, changed
):
    manifest = recording(store)
    original = feed.runner.native._instruments
    reads = 0

    def refreshed(now):
        nonlocal reads
        rows = original(now)
        reads += 1
        if reads == 2:
            option = next(row for row in rows if row["kind"] == "CE")
            option[changed] = {
                "token": "changed-token",
                "strike": 26000,
                "master_broker": "other",
                "master_freshness": "UNVERIFIED",
            }[changed]
        return rows

    monkeypatch.setattr(feed.runner.native, "_instruments", refreshed)
    feed.runner._native_feed(StrategyConfig(), NOW)
    assert feed.runner.capture() is None
    assert feed.market.reads == []
    assert store.recording_page(USER, manifest["id"])["manifest"] == manifest


@pytest.mark.parametrize("changed", ["socket", "reconnect", "context", "shutdown"])
def test_capture_discards_batch_if_feed_changes_during_quote_read(
    store, feed, monkeypatch, changed
):
    manifest = recording(store)
    feed.runner.capture()
    feed.market.stamp += timedelta(seconds=3)
    original = feed.market.get_all_data

    def interrupted(symbol, exchange):
        result = original(symbol, exchange)
        if changed == "socket":
            feed.client.ws = object()
        elif changed == "reconnect":
            feed.market.health_monitor.get_health.return_value = {"reconnect_count": 1}
        elif changed == "context":
            feed.runner.recording_feed = None
        else:
            feed.runner.close()
        return result

    monkeypatch.setattr(feed.market, "get_all_data", interrupted)
    assert feed.runner.capture() is None
    assert store.recording_page(USER, manifest["id"])["manifest"]["count"] == 0


def test_capture_seal_race_never_appends_after_count_fence(store, feed, monkeypatch):
    manifest = recording(store)
    feed.runner.capture()
    feed.market.stamp += timedelta(seconds=3)
    original = store.append_recording

    def sealed(*args, **kwargs):
        store.seal_recording(USER, manifest["id"], feed.market.stamp, expected_count=0)
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "append_recording", sealed)
    assert feed.runner.capture() is None
    page = store.recording_page(USER, manifest["id"])
    assert page["manifest"]["status"] == "SEALED"
    assert page["items"] == []


def test_capture_never_bootstraps_a_cold_feed(store):
    runner = NiftyRunner(store, USER, native=Mock(), clock=lambda: NOW)
    runner._native_feed = Mock(side_effect=AssertionError("capture must not initialize the feed"))
    assert runner.capture() is None
    assert not runner.native.method_calls


def test_capture_lost_owner_cannot_freeze_scope_or_read_quotes(store, feed):
    manifest = recording(store)
    store.release_runner(USER, feed.runner.owner)
    assert store.claim_runner(USER, "replacement", NOW)
    assert feed.runner.capture() is None
    assert feed.market.reads == []
    assert store.recording_page(USER, manifest["id"])["manifest"] == manifest


def test_capture_reads_at_most_100_rotating_instruments_per_tick(store, feed, monkeypatch):
    import services.nifty_algo.runner as module

    monkeypatch.setattr(module, "monotonic", lambda: 0)
    rows = master_rows()
    expanded = [
        {**rows[1], "token": str(index), "symbol": f"BOUNDED_{index:03d}CE"} for index in range(205)
    ]
    feed.runner.native.instrument_loader = lambda: [rows[0], *expanded, rows[-1]]
    feed.runner._native_feed(StrategyConfig(), NOW)
    feed.connection.reset_mock()
    feed.shared_cache.reset_mock()
    recording(store)
    sampled = set()
    for step in (0, 5, 10):
        feed.market.stamp = NOW + timedelta(seconds=step)
        feed.market.reads.clear()
        result = feed.runner.capture()
        assert result is not None
        assert len(feed.market.reads) == 100
        sampled.update(feed.market.reads)
    assert sampled == {row["symbol"] for row in expanded}
    assert not feed.connection.called and not feed.shared_cache.called


def test_capture_stops_sampling_when_loop_time_budget_is_exhausted(store, feed, monkeypatch):
    import services.nifty_algo.runner as module

    recording(store)
    times = iter((0, 0, 0.25))
    monkeypatch.setattr(module, "monotonic", lambda: next(times))
    assert feed.runner.capture()["count"] == 0
    assert len(feed.market.reads) == 1


def test_capture_repeated_samples_close_every_database_connection(store, feed):
    manifest = recording(store)
    feed.runner.capture()
    feed.market.stamp += timedelta(seconds=3)
    assert feed.runner.capture()["count"] == 2
    opened, closed = [], []

    def connected(*_):
        opened.append(1)

    def disconnected(*_):
        closed.append(1)

    event.listen(store.engine, "connect", connected)
    event.listen(store.engine, "close", disconnected)
    try:
        for _ in range(100):
            assert feed.runner.capture()["count"] == 2
            assert len(opened) == len(closed)
        assert len(opened) >= 100
    finally:
        event.remove(store.engine, "connect", connected)
        event.remove(store.engine, "close", disconnected)
    assert store.recording_page(USER, manifest["id"])["manifest"]["count"] == 2


def test_capture_job_attaches_once_and_runs_in_its_own_app_context(store, monkeypatch):
    from flask import has_app_context

    invoked = []
    monkeypatch.setattr(NiftyRunner, "capture", lambda self: invoked.append(has_app_context()))
    app = Flask(__name__)
    app.extensions["nifty_algo_store"] = store
    scheduler = Mock()
    runner = attach_runner(app, scheduler, USER)
    assert attach_runner(app, scheduler, USER) is runner
    jobs = scheduler.add_job.call_args_list
    assert len(jobs) == 4
    capture = next(call for call in jobs if call.kwargs["id"].endswith(":capture"))
    assert capture.kwargs["seconds"] == 5
    assert capture.kwargs["max_instances"] == 1 and capture.kwargs["coalesce"]
    assert capture.kwargs["misfire_grace_time"] == 1
    capture.args[0]()
    assert invoked == [True] and not has_app_context()


@pytest.mark.parametrize("fail_at", [2, 3, 4])
def test_capture_scheduler_failure_rolls_back_all_registered_jobs(store, fail_at):
    app = Flask(__name__)
    app.extensions["nifty_algo_store"] = store
    scheduler = Mock()
    scheduler.add_job.side_effect = [None] * (fail_at - 1) + [RuntimeError("scheduler unavailable")]
    with pytest.raises(RuntimeError, match="scheduler unavailable"):
        attach_runner(app, scheduler, USER)
    registered = scheduler.add_job.call_args_list[:-1]
    assert [call.args[0] for call in scheduler.remove_job.call_args_list] == [
        call.kwargs["id"] for call in reversed(registered)
    ]
    assert app.extensions["nifty_algo_runners"] == {}


def test_shutdown_removes_capture_job_and_releases_context(store, monkeypatch):
    import utils.shutdown as shutdown

    app = Flask(__name__)
    app.extensions["nifty_algo_store"] = store
    store.ensure_user(USER)
    scheduler = Mock()
    hook = Mock()
    monkeypatch.setattr(shutdown, "register_shutdown_hook", hook)
    restore_runners(app, scheduler)
    runner = app.extensions["nifty_algo_runners"][USER]
    hook.call_args.args[0]()
    assert any(call.args[0].endswith(":capture") for call in scheduler.remove_job.call_args_list)
    assert runner.closed and runner.recording_feed is None
    assert app.extensions["nifty_algo_runners"] == {}


def test_native_assessment_records_causal_analysis_without_trading_authority(store, feed):
    from sqlalchemy import select

    from database.nifty_algo_db import NiftyCalendarVersion
    from services.nifty_algo.assessment import assess_current
    from test.nifty_calendar_helpers import seed_nifty_calendar_dependencies
    from test.test_nifty_algo_pipeline import minute_rows, session

    seed_nifty_calendar_dependencies(store, USER, NOW.year)
    # This historical fixture's approval existed before its market observations.
    with store.sessions.begin() as db:
        calendar = db.scalar(
            select(NiftyCalendarVersion).where(NiftyCalendarVersion.user_id == USER)
        )
        calendar.approved_at = NOW - timedelta(days=30)
    manifest = recording(store)
    before = store.read(USER)
    decision = assess_current(
        "offline-fixture-only",
        StrategyConfig(),
        NOW,
        native=feed.runner.native,
        session_reader=session,
        history_reader=lambda **kwargs: (True, {"status": "success", "data": minute_rows()}, 200),
        evidence_sink=feed.runner._record_analysis_frame,
    )
    page = store.recording_page(USER, manifest["id"])
    assert len(page["items"]) == 1
    recorded = page["items"][0]
    assert recorded["kind"] == "FRAME" and recorded["source"] == "NATIVE_FEED"
    payload = recorded["payload"]
    assert len(payload["minute_bars"]) > 1000
    assert payload["pcr"] and payload["spot"] and payload["instruments"]
    assert payload["decision"] == decision
    assert payload["configuration_id"] == StrategyConfig().version_id
    assert all(
        q["source_time"] <= q["received_time"] <= recorded["available_at"]
        for q in payload["quotes"]
    )
    assert store.read(USER) == before
    assert store.pending_orders(USER) == [] and store.positions(USER) == []


def test_research_sink_failure_does_not_change_signal_or_create_orders(store, feed):
    from services.nifty_algo.assessment import assess_current
    from test.test_nifty_algo_pipeline import minute_rows, session

    arguments = {
        "native": feed.runner.native,
        "session_reader": session,
        "history_reader": lambda **kwargs: (
            True,
            {"status": "success", "data": minute_rows()},
            200,
        ),
    }
    before = assess_current("offline-fixture-only", StrategyConfig(), NOW, **arguments)
    broken = Mock(side_effect=OSError("controlled recording interruption"))
    after = assess_current(
        "offline-fixture-only", StrategyConfig(), NOW, evidence_sink=broken, **arguments
    )
    assert after == before and broken.call_count == 1
    assert not store.pending_orders(USER) and not store.positions(USER)
