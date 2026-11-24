"""Recorded evidence replay; no account, feed or execution authority."""

from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import event

from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyStore
from services.nifty_algo import research
from test.test_nifty_algo_recording import NOW, append, create, freeze_scope, quote


@pytest.fixture
def store(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'replay.db'}")
    value = NiftyStore(engine)
    value.initialize()
    value.ensure_user("recorder-owner")
    yield value
    engine.dispose()


def cursor(store, manifest, **changes):
    return research.recording_cursor(
        store,
        "recorder-owner",
        manifest["id"],
        expected_count=manifest["count"],
        expected_sha256=manifest["content_sha256"],
        **changes,
    )


def sealed(store):
    manifest = create(store)
    rows = [
        quote(source=NOW - timedelta(seconds=4), available=NOW - timedelta(seconds=3)),
        quote(source=NOW - timedelta(seconds=10), available=NOW - timedelta(seconds=1)),
        quote(source=NOW - timedelta(seconds=2), available=NOW - timedelta(seconds=1)),
    ]
    append(store, manifest, rows)
    return store.seal_recording("recorder-owner", manifest["id"], NOW, expected_count=3)


def test_replay_uses_arrival_order_and_never_exposes_late_quotes_at_source_time(store):
    manifest = sealed(store)
    replay = cursor(store, manifest)
    early = replay.advance(NOW - timedelta(seconds=5))
    assert early["items"] == []
    first = replay.advance(NOW - timedelta(seconds=2))
    assert [item["sequence"] for item in first["items"]] == [1]
    assert first["execution_eligible"] is False
    assert first["mode"] == "QUOTE_EVIDENCE_ONLY"
    second = replay.advance(NOW, limit=1)
    assert [item["sequence"] for item in second["items"]] == [2]
    assert second["items"][0]["source_time"] < first["items"][0]["source_time"]
    assert [item["sequence"] for item in replay.advance(NOW)["items"]] == [3]
    assert replay.advance(NOW)["items"] == []
    with pytest.raises(ValueError, match="backward"):
        replay.advance(NOW - timedelta(seconds=1))


def test_replay_requires_owner_seal_and_pinned_identity(store):
    manifest = create(store)
    with pytest.raises(ValueError, match="sealed"):
        cursor(store, manifest)
    manifest = store.seal_recording("recorder-owner", manifest["id"], NOW, expected_count=0)
    with pytest.raises(ValueError, match="identity"):
        cursor(store, {**manifest, "content_sha256": "0" * 64})
    with pytest.raises(ValueError, match="identity"):
        cursor(store, {**manifest, "count": 1})
    with pytest.raises(ValueError, match="not found"):
        research.recording_cursor(
            store,
            "another-owner",
            manifest["id"],
            expected_count=0,
            expected_sha256=manifest["content_sha256"],
        )


def test_cursor_is_detached_and_defensive_and_never_writes(store):
    manifest = sealed(store)
    statements = []
    event.listen(
        store.engine,
        "before_cursor_execute",
        lambda _c, _u, statement, *_a: statements.append(statement),
    )
    replay = cursor(store, manifest)
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    original = deepcopy(replay.manifest)
    replay.manifest["configuration"]["version_id"] = "caller-mutation"
    assert replay.manifest == original
    store.engine.dispose()
    page = replay.advance(NOW, limit=1)
    page["items"][0]["payload"]["bid"] = "caller-mutation"
    assert [item["sequence"] for item in replay.advance(NOW)["items"]] == [2, 3]


@pytest.mark.parametrize("limit", [True, 0, 101, 1.5])
def test_cursor_rejects_invalid_bounds_without_consuming_evidence(store, limit):
    replay = cursor(store, sealed(store))
    with pytest.raises(ValueError):
        replay.advance(NOW, limit=limit)
    with pytest.raises(ValueError):
        replay.advance(NOW.replace(tzinfo=None))
    assert len(replay.advance(NOW)["items"]) == 3


def test_cursor_loads_sealed_native_scope_chain_without_inventing_observations(store):
    manifest = create(store, native_capture=True)
    assert store.claim_runner("recorder-owner", "capture-owner", NOW - timedelta(seconds=10))
    freeze_scope(store, manifest)
    manifest = store.seal_recording("recorder-owner", manifest["id"], NOW, expected_count=0)
    replay = cursor(store, manifest)
    assert replay.manifest["capture"]["scope_sha256"] == manifest["capture"]["scope_sha256"]
    assert replay.advance(NOW)["items"] == []


def test_cursor_loads_multiple_pages_with_no_future_prefix_effect(store):
    manifest = create(store)
    rows = [
        quote(
            source=NOW - timedelta(seconds=4),
            available=NOW - timedelta(seconds=3) + timedelta(microseconds=index),
        )
        for index in range(115)
    ]
    append(store, manifest, rows[:100])
    append(store, manifest, rows[100:], count=100)
    manifest = store.seal_recording("recorder-owner", manifest["id"], NOW, expected_count=115)
    replay = cursor(store, manifest)
    prefix = replay.advance(NOW - timedelta(seconds=3))
    assert [item["sequence"] for item in prefix["items"]] == [1]
    assert len(replay.advance(NOW)["items"]) == 100
    assert [item["sequence"] for item in replay.advance(NOW)["items"]] == list(range(102, 116))


@pytest.mark.parametrize("fault", ["price", "sequence", "missing", "configuration", "bytes"])
def test_loader_rejects_changed_or_truncated_evidence_before_returning_cursor(
    store, monkeypatch, fault
):
    manifest = sealed(store)
    read = store.recording_page

    def changed(*args, **kwargs):
        page = read(*args, **kwargs)
        if fault == "price":
            page["items"][0]["payload"]["bid"] = "99"
        elif fault == "sequence":
            page["items"][0]["sequence"] = 2
        elif fault == "missing":
            page["items"] = []
        elif fault == "configuration":
            page["manifest"]["configuration"]["version_id"] = "changed"
        else:
            page["manifest"]["size_bytes"] += 1
        return page

    monkeypatch.setattr(store, "recording_page", changed)
    with pytest.raises(ValueError):
        cursor(store, manifest)


def test_repeated_load_and_validation_failure_close_all_connections(store, monkeypatch):
    manifest = sealed(store)
    counts = {"opened": 0, "closed": 0}

    def opened(*_):
        counts["opened"] += 1

    def closed(*_):
        counts["closed"] += 1

    event.listen(store.engine, "connect", opened)
    event.listen(store.engine, "close", closed)
    for _ in range(100):
        assert len(cursor(store, manifest).advance(NOW)["items"]) == 3
        assert counts["opened"] == counts["closed"]
    read = store.recording_page

    def corrupt(*args, **kwargs):
        page = read(*args, **kwargs)
        page["items"][0]["sha256"] = "0" * 64
        return page

    monkeypatch.setattr(store, "recording_page", corrupt)
    for _ in range(100):
        with pytest.raises(ValueError, match="integrity"):
            cursor(store, manifest)
        assert counts["opened"] == counts["closed"]
    assert counts["opened"] >= 200
