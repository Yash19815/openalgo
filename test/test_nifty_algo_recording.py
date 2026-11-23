"""Point-in-time evidence contracts; no broker or primary-ledger authority."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import event

from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyStore, StateConflict
from services.nifty_algo import research
from test.test_nifty_algo_native_capture import instrument

NOW = datetime(2026, 11, 19, 6, 0, tzinfo=UTC)


def quote(*, source=None, available=None, **changes):
    source = source or NOW - timedelta(seconds=2)
    available = available or NOW - timedelta(seconds=1)
    return {
        "kind": "QUOTE",
        "source_time": source.isoformat(),
        "available_at": available.isoformat(),
        "source": "NATIVE_FEED",
        "payload": {
            "token": "fixture-option",
            "source_time": source.isoformat(),
            "received_time": available.isoformat(),
            "bid": "100.05",
            "ask": "100.10",
            "bid_size": 25,
            "ask_size": 25,
            "provider": "TEST_FIXTURE",
            **changes,
        },
    }


def normalize(rows, now=NOW):
    return research.recording_batch(rows, now)


def test_recording_batch_preserves_availability_and_decimal_quote_evidence():
    first = quote()
    # A delayed older quote becomes available later, never at its source time.
    late = quote(source=NOW - timedelta(seconds=10), available=NOW)
    rows = normalize([first, late])
    assert rows[0]["available_at"] == first["available_at"]
    assert rows[1]["source_time"] == late["source_time"]
    assert rows[1]["available_at"] == NOW.isoformat()
    assert rows[0]["payload"]["bid"] == "100.05"
    assert len(rows[0]["sha256"]) == 64
    assert normalize([first])[0]["sha256"] == rows[0]["sha256"]
    assert first["payload"]["bid"] == "100.05"


@pytest.mark.parametrize(
    "change",
    [
        {"bid": "NaN"},
        {"bid": "101", "ask": "100"},
        {"bid_size": -1},
        {"api_key": "must-not-persist"},
        {"source_time": (NOW + timedelta(seconds=1)).isoformat()},
        {"received_time": NOW.replace(tzinfo=None).isoformat()},
    ],
)
def test_recording_rejects_invalid_or_secret_bearing_payloads(change):
    with pytest.raises(ValueError):
        normalize([quote(**change)])


def test_recording_refuses_future_availability_and_reversed_arrival_order():
    with pytest.raises(ValueError):
        normalize([quote(available=NOW + timedelta(seconds=1))])
    with pytest.raises(ValueError):
        normalize([quote(available=NOW), quote()])


def test_recording_refuses_mismatched_source_time_and_empty_or_oversized_batches():
    row = quote()
    row["source_time"] = (NOW - timedelta(seconds=8)).isoformat()
    with pytest.raises(ValueError):
        normalize([row])
    for rows in ([], [quote()] * 101):
        with pytest.raises(ValueError):
            normalize(rows)


def test_recording_refuses_unknown_envelope_fields_and_naive_now():
    with pytest.raises(ValueError):
        normalize([{**quote(), "authorization": "must-not-persist"}])
    with pytest.raises(ValueError):
        normalize([quote()], now=NOW.replace(tzinfo=None))


def test_recording_refuses_exact_duplicates_even_after_normalization():
    same = quote()
    equivalent = quote()
    equivalent["available_at"] = equivalent["available_at"].replace("+00:00", "Z")
    with pytest.raises(ValueError):
        normalize([same, equivalent])


@pytest.fixture
def store(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'recording.db'}")
    value = NiftyStore(engine)
    value.initialize()
    value.ensure_user("recorder-owner")
    yield value
    engine.dispose()


def create(store, **changes):
    return store.create_recording(
        "recorder-owner",
        NOW - timedelta(minutes=1),
        NOW + timedelta(minutes=45),
        NOW,
        **changes,
    )


def append(store, dataset, rows=None, count=0, **changes):
    return store.append_recording(
        "recorder-owner",
        dataset["id"],
        [quote()] if rows is None else rows,
        NOW,
        expected_count=count,
        **changes,
    )


def freeze_scope(store, dataset, **changes):
    arguments = {
        "instruments": [instrument().model_copy(update={"token": "fixture-option"})],
        "broker": "angel",
        "runner_owner": "capture-owner",
    }
    arguments.update(changes)
    return store.freeze_recording_scope(
        "recorder-owner", dataset["id"], NOW - timedelta(seconds=5), **arguments
    )


def test_native_recording_scope_is_explicit_frozen_hashed_and_restart_safe(store):
    legacy = create(store)
    native = create(store, native_capture=True)
    assert legacy["capture"] is None
    assert native["capture"] == {"scope": None, "scope_sha256": None}
    assert store.claim_runner("recorder-owner", "capture-owner", NOW - timedelta(seconds=10))
    with pytest.raises(StateConflict):
        freeze_scope(store, legacy)
    saved = freeze_scope(store, native)
    scope = saved["capture"]["scope"]
    assert scope["broker"] == "angel"
    assert scope["instruments"][0]["token"] == "fixture-option"
    assert scope["frozen_at"] == (NOW - timedelta(seconds=5)).isoformat()
    assert len(saved["capture"]["scope_sha256"]) == 64
    assert saved["content_sha256"] != native["content_sha256"]
    assert freeze_scope(store, native) == saved
    reopened = NiftyStore(store.engine)
    assert reopened.recording_page("recorder-owner", native["id"])["manifest"] == saved
    assert (
        next(row for row in reopened.recordings("recorder-owner") if row["id"] == native["id"])
        == saved
    )
    with pytest.raises(StateConflict):
        freeze_scope(store, native, broker="other")
    with pytest.raises(StateConflict):
        freeze_scope(store, native, instruments=[instrument()])
    assert reopened.recording_page("recorder-owner", native["id"])["manifest"] == saved


@pytest.mark.parametrize("lease", ["missing", "expired", "other"])
def test_freezing_native_scope_requires_current_owner(store, lease):
    native = create(store, native_capture=True)
    if lease != "missing":
        assert store.claim_runner(
            "recorder-owner",
            "replacement" if lease == "other" else "capture-owner",
            NOW - timedelta(seconds=40 if lease == "expired" else 10),
        )
    with pytest.raises(StateConflict):
        freeze_scope(store, native)
    assert store.recording_page("recorder-owner", native["id"])["manifest"] == native


@pytest.mark.parametrize(
    "instruments",
    [
        [],
        [instrument()] * 1001,
        [instrument(), instrument()],
        [instrument().model_copy(update={"master_date": NOW.date() - timedelta(days=1)})],
        [instrument().model_copy(update={"expiry": NOW.date() - timedelta(days=1)})],
        [instrument().model_copy(update={"tradable": False})],
        [instrument().model_copy(update={"token": "x" * 33})],
        [instrument().model_copy(update={"symbol": "NIFTY" + "X" * 64})],
        [instrument().model_copy(update={"tick_size": Decimal("Infinity")})],
        [instrument().model_copy(update={"strike": Decimal("Infinity")})],
        [{"token": "caller", "api_key": "must-not-persist"}],
    ],
)
def test_native_scope_rejects_invalid_unbounded_or_ineligible_identity(store, instruments):
    native = create(store, native_capture=True)
    assert store.claim_runner("recorder-owner", "capture-owner", NOW - timedelta(seconds=10))
    with pytest.raises(ValueError):
        freeze_scope(store, native, instruments=instruments)
    assert store.recording_page("recorder-owner", native["id"])["manifest"] == native


def test_scope_encoded_metadata_has_a_hard_byte_limit(store):
    native = create(store, native_capture=True)
    assert store.claim_runner("recorder-owner", "capture-owner", NOW - timedelta(seconds=10))
    huge = [
        instrument().model_copy(
            update={"token": str(index), "symbol": f"NIFTY{index}", "lot_size": 10**1000}
        )
        for index in range(1000)
    ]
    with pytest.raises(ValueError, match="512 KiB"):
        freeze_scope(store, native, instruments=huge)
    assert store.recording_page("recorder-owner", native["id"])["manifest"] == native


def test_scope_hash_ignores_input_order_and_keeps_first_freeze_time(store):
    native = create(store, native_capture=True)
    assert store.claim_runner("recorder-owner", "capture-owner", NOW - timedelta(seconds=10))
    first = instrument().model_copy(update={"token": "fixture-option"})
    second = instrument().model_copy(update={"token": "other", "symbol": "OTHER"})
    frozen = freeze_scope(store, native, instruments=[second, first])
    assert (
        store.freeze_recording_scope(
            "recorder-owner",
            native["id"],
            NOW,
            instruments=[first, second],
            broker="angel",
            runner_owner="capture-owner",
        )
        == frozen
    )
    assert (
        store.runner_status("recorder-owner", NOW)["expires_at"]
        == (NOW + timedelta(seconds=20)).isoformat()
    )


def test_scope_is_owner_scoped_and_cannot_freeze_after_concurrent_seal(store, monkeypatch):
    native = create(store, native_capture=True)
    assert store.claim_runner("recorder-owner", "capture-owner", NOW - timedelta(seconds=10))
    assert store.claim_runner("another-owner", "capture-owner", NOW - timedelta(seconds=10))
    with pytest.raises(ValueError, match="Recording not found"):
        store.freeze_recording_scope(
            "another-owner",
            native["id"],
            NOW,
            instruments=[instrument()],
            broker="angel",
            runner_owner="capture-owner",
        )
    lock = store._lock
    competed = False

    def seal_before_lock(db, user):
        nonlocal competed
        if not competed:
            competed = True
            store.seal_recording(user, native["id"], NOW, expected_count=0)
        return lock(db, user)

    monkeypatch.setattr(store, "_lock", seal_before_lock)
    with pytest.raises(StateConflict):
        freeze_scope(store, native)
    saved = store.recording_page("recorder-owner", native["id"])["manifest"]
    assert saved["status"] == "SEALED"
    assert saved["capture"] == native["capture"]
    assert saved["content_sha256"] == native["content_sha256"]


def test_scope_rollback_closes_connections_and_preserves_hash_after_100_write_failures(store):
    native = create(store, native_capture=True)
    assert store.claim_runner("recorder-owner", "capture-owner", NOW - timedelta(seconds=10))
    live, peak = 0, 0

    def connected(*_):
        nonlocal live, peak
        live += 1
        peak = max(peak, live)

    def closed(*_):
        nonlocal live
        live -= 1

    def fail_scope_write(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE nifty_algo_research_capture"):
            raise RuntimeError("scope storage unavailable")

    event.listen(store.engine, "connect", connected)
    event.listen(store.engine, "close", closed)
    event.listen(store.engine, "before_cursor_execute", fail_scope_write)
    try:
        for _ in range(100):
            with pytest.raises(RuntimeError, match="scope storage unavailable"):
                freeze_scope(store, native)
            assert live == 0
            assert store.recording_page("recorder-owner", native["id"])["manifest"] == native
    finally:
        event.remove(store.engine, "before_cursor_execute", fail_scope_write)
        event.remove(store.engine, "connect", connected)
        event.remove(store.engine, "close", closed)
    assert live == 0 and peak == 1
    assert freeze_scope(store, native)["capture"]["scope"] is not None


def test_native_scope_controls_append_without_adopting_imports_or_foreign_tokens(store):
    native = create(store, native_capture=True)
    assert store.claim_runner("recorder-owner", "capture-owner", NOW - timedelta(seconds=10))
    with pytest.raises(StateConflict):
        append(store, native, runner_owner="capture-owner", deduplicate_samples=True)
    frozen = freeze_scope(store, native)
    with pytest.raises(StateConflict):
        append(store, native, deduplicate_samples=True)
    for row in (
        {**quote(), "source": "IMPORT"},
        quote(token="other-option"),
        quote(source=NOW - timedelta(seconds=6)),
    ):
        with pytest.raises(ValueError):
            append(
                store, native, rows=[row], runner_owner="capture-owner", deduplicate_samples=True
            )
    assert store.recording_page("recorder-owner", native["id"])["manifest"] == frozen
    assert (
        append(store, native, runner_owner="capture-owner", deduplicate_samples=True)["count"] == 1
    )
    sealed = store.seal_recording("recorder-owner", native["id"], NOW, expected_count=1)
    assert sealed["capture"] == frozen["capture"]
    with pytest.raises(StateConflict):
        freeze_scope(store, native)


def test_recording_seals_immutable_manifest_and_survives_restart(store):
    before = store.read("recorder-owner")
    dataset = create(store)
    saved = append(store, dataset)
    assert saved["count"] == 1
    sealed = store.seal_recording("recorder-owner", dataset["id"], NOW, expected_count=1)
    assert sealed["status"] == "SEALED"
    assert sealed["mode"] == "RESEARCH"
    assert sealed["execution_eligible"] is False
    assert len(sealed["content_sha256"]) == 64
    assert sealed["configuration_id"] == before["configuration_id"]
    reopened = NiftyStore(store.engine)
    page = reopened.recording_page("recorder-owner", dataset["id"], limit=1)
    assert page["manifest"] == sealed
    assert page["items"][0]["sequence"] == 1
    assert page["items"][0]["payload"]["bid"] == "100.05"
    assert reopened.read("recorder-owner") == before
    assert reopened.seal_recording("recorder-owner", dataset["id"], NOW, expected_count=1) == sealed
    with pytest.raises(StateConflict):
        append(reopened, dataset, count=1)


def test_sample_deduplication_keeps_first_availability_across_restart(store):
    dataset = create(store)
    saved = append(store, dataset, deduplicate_samples=True)
    later = NOW + timedelta(seconds=1)
    repeated = quote(available=later)
    repeated["payload"]["received_time"] = quote()["payload"]["received_time"]
    reopened = NiftyStore(store.engine)
    actual = reopened.append_recording(
        "recorder-owner",
        dataset["id"],
        [repeated],
        later,
        expected_count=1,
        deduplicate_samples=True,
    )
    assert actual == saved
    page = reopened.recording_page("recorder-owner", dataset["id"])
    assert len(page["items"]) == 1
    assert page["items"][0]["available_at"] == quote()["available_at"]
    with pytest.raises(StateConflict):
        append(reopened, dataset, count=0, deduplicate_samples=True)
    sealed = reopened.seal_recording("recorder-owner", dataset["id"], later, expected_count=1)
    with pytest.raises(StateConflict):
        append(reopened, dataset, count=1, deduplicate_samples=True)
    assert reopened.recording_page("recorder-owner", dataset["id"])["manifest"] == sealed


def test_native_capture_append_requires_current_runner_without_renewing_readiness(store):
    dataset = create(store)
    assert store.claim_runner(
        "recorder-owner", "capture-owner", NOW, payload={"entries_ready": False}
    )
    heartbeat = store.runner_status("recorder-owner", NOW)
    saved = append(store, dataset, runner_owner="capture-owner", deduplicate_samples=True)
    assert saved["count"] == 1
    assert store.runner_status("recorder-owner", NOW) == heartbeat


@pytest.mark.parametrize("lease", ["missing", "other-owner", "expired", "released"])
def test_native_capture_append_refuses_lost_runner_ownership_atomically(store, lease):
    dataset = create(store)
    if lease != "missing":
        at = NOW - timedelta(seconds=31) if lease == "expired" else NOW
        owner = "other-owner" if lease == "other-owner" else "capture-owner"
        assert store.claim_runner("recorder-owner", owner, at)
        if lease == "released":
            store.release_runner("recorder-owner", owner)
    with pytest.raises(StateConflict):
        append(store, dataset, runner_owner="capture-owner", deduplicate_samples=True)
    page = store.recording_page("recorder-owner", dataset["id"])
    assert page["manifest"] == dataset
    assert page["items"] == []
    owner = "other-owner" if lease == "other-owner" else "capture-owner"
    assert store.claim_runner("recorder-owner", owner, NOW)
    assert append(store, dataset, runner_owner=owner, deduplicate_samples=True)["count"] == 1


def test_native_capture_owner_check_runs_after_the_owner_lock(store, monkeypatch):
    dataset = create(store)
    assert store.claim_runner("recorder-owner", "capture-owner", NOW)
    lock = store._lock
    competed = False

    def compete_before_write(db, user):
        nonlocal competed
        if not competed:
            competed = True
            store.release_runner(user, "capture-owner")
            assert store.claim_runner(user, "replacement-owner", NOW)
        return lock(db, user)

    monkeypatch.setattr(store, "_lock", compete_before_write)
    with pytest.raises(StateConflict):
        append(store, dataset, runner_owner="capture-owner", deduplicate_samples=True)
    assert competed
    assert store.recording_page("recorder-owner", dataset["id"])["manifest"] == dataset
    assert (
        append(store, dataset, runner_owner="replacement-owner", deduplicate_samples=True)["count"]
        == 1
    )


def test_sample_deduplication_is_owner_and_recording_scoped(store):
    first, second = create(store), create(store)
    assert append(store, first, deduplicate_samples=True)["count"] == 1
    assert append(store, second, deduplicate_samples=True)["count"] == 1
    with pytest.raises(ValueError, match="Recording not found"):
        store.append_recording(
            "another-owner",
            first["id"],
            [quote()],
            NOW,
            expected_count=0,
            deduplicate_samples=True,
        )


def test_sample_identity_rolls_back_when_recording_quota_refuses_batch(store):
    dataset = create(store, max_observations=1)
    with pytest.raises(ValueError, match="bounds"):
        append(
            store,
            dataset,
            [quote(), quote(available=NOW, bid="100.00")],
            deduplicate_samples=True,
        )
    assert store.recording_page("recorder-owner", dataset["id"])["manifest"] == dataset
    assert append(store, dataset, deduplicate_samples=True)["count"] == 1


def test_recording_is_owner_scoped_and_pages_by_availability_not_source_time(store):
    dataset = create(store)
    late = quote(source=NOW - timedelta(seconds=10), available=NOW)
    append(store, dataset, [quote(), late])
    first = store.recording_page(
        "recorder-owner", dataset["id"], limit=1, as_of=NOW - timedelta(seconds=1)
    )
    assert [row["sequence"] for row in first["items"]] == [1]
    second = store.recording_page("recorder-owner", dataset["id"], after=1, limit=1)
    assert second["items"][0]["source_time"] == late["source_time"]
    assert second["items"][0]["sequence"] == 2
    assert store.recording_page("another-owner", dataset["id"]) is None
    with pytest.raises(ValueError):
        store.append_recording("another-owner", dataset["id"], [quote()], NOW, expected_count=2)
    with pytest.raises(ValueError):
        store.seal_recording("another-owner", dataset["id"], NOW, expected_count=2)


def test_stale_append_and_seal_cannot_overwrite_new_evidence(store):
    dataset = create(store)
    append(store, dataset)
    with pytest.raises(StateConflict):
        append(store, dataset)
    with pytest.raises(StateConflict):
        store.seal_recording("recorder-owner", dataset["id"], NOW, expected_count=0)
    page = store.recording_page("recorder-owner", dataset["id"])
    assert page["manifest"]["count"] == len(page["items"]) == 1
    assert page["manifest"]["status"] == "RECORDING"


def test_recording_refuses_duplicate_evidence_across_batches(store):
    dataset = create(store)
    saved = append(store, dataset)
    with pytest.raises(ValueError, match="Duplicate"):
        append(store, dataset, count=1)
    assert store.recording_page("recorder-owner", dataset["id"])["manifest"] == saved


@pytest.mark.parametrize("limit", [True, 0, -1, 10001, "100", 1.5])
def test_recording_creation_refuses_invalid_limits_before_writes(store, limit):
    with pytest.raises(ValueError):
        create(store, max_observations=limit)


@pytest.mark.parametrize(
    "start,end,now",
    [
        (NOW, NOW, NOW),
        (NOW + timedelta(seconds=1), NOW + timedelta(minutes=1), NOW),
        (NOW, NOW + timedelta(days=1, seconds=1), NOW),
        (NOW.replace(tzinfo=None), NOW + timedelta(minutes=1), NOW),
        (NOW, NOW + timedelta(minutes=1), NOW.replace(tzinfo=None)),
    ],
)
def test_recording_creation_refuses_invalid_time_windows(store, start, end, now):
    with pytest.raises(ValueError):
        store.create_recording("recorder-owner", start, end, now)


def test_recording_quota_is_owner_scoped_and_never_discards_evidence(store):
    datasets = [create(store) for _ in range(20)]
    with pytest.raises(ValueError, match="quota"):
        create(store)
    other = store.create_recording("another-owner", NOW, NOW + timedelta(minutes=1), NOW)
    assert other["status"] == "RECORDING"
    assert all(store.recording_page("recorder-owner", item["id"]) is not None for item in datasets)


def test_recording_limit_and_cross_batch_time_checks_are_atomic(store):
    dataset = create(store, max_observations=2)
    saved = append(store, dataset)
    with pytest.raises(ValueError):
        append(store, dataset, [quote(available=NOW)] * 2, count=1)
    with pytest.raises(ValueError):
        append(
            store,
            dataset,
            [quote(available=NOW - timedelta(seconds=3), source=NOW - timedelta(seconds=4))],
            count=1,
        )
    with pytest.raises(ValueError):
        append(store, dataset, [quote(source=NOW - timedelta(minutes=2))], count=1)
    assert store.recording_page("recorder-owner", dataset["id"])["manifest"] == saved


@pytest.mark.parametrize(
    "page", [{"limit": 101}, {"limit": 0}, {"after": -1}, {"as_of": NOW.replace(tzinfo=None)}]
)
def test_recording_reads_are_bounded(store, page):
    dataset = create(store)
    with pytest.raises(ValueError):
        store.recording_page("recorder-owner", dataset["id"], **page)


def test_recording_page_never_mixes_new_rows_with_an_old_manifest(store):
    dataset = create(store)
    injected = False

    def competing_append(connection, cursor, sql, parameters, context, many):
        nonlocal injected
        if (
            not injected
            and sql.lstrip().startswith("SELECT")
            and "FROM nifty_algo_research_observation" in sql
        ):
            injected = True
            append(store, dataset)

    event.listen(store.engine, "before_cursor_execute", competing_append)
    try:
        page = store.recording_page("recorder-owner", dataset["id"])
    finally:
        event.remove(store.engine, "before_cursor_execute", competing_append)
    assert injected
    assert page["manifest"]["count"] == len(page["items"]) == 0
    assert store.recording_page("recorder-owner", dataset["id"])["manifest"]["count"] == 1


def test_recording_two_writers_cannot_consume_the_same_cursor(store):
    dataset = create(store)
    ready = Barrier(2)

    def writer():
        reopened = NiftyStore(store.engine)
        ready.wait(timeout=5)
        try:
            append(reopened, dataset)
            return "SAVED"
        except StateConflict:
            return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="nifty-recording-test") as pool:
        futures = [pool.submit(writer) for _ in range(2)]
        assert sorted(future.result(timeout=10) for future in futures) == ["CONFLICT", "SAVED"]
    page = store.recording_page("recorder-owner", dataset["id"])
    assert page["manifest"]["count"] == len(page["items"]) == 1


@pytest.mark.parametrize("deduplicate_samples", [False, True])
def test_recording_rolls_back_failed_batches_and_closes_every_connection(
    store, deduplicate_samples
):
    dataset = create(store)
    connections = set()

    def connected(connection, record):
        connections.add(id(connection))

    def closed(connection, record):
        connections.remove(id(connection))

    def fail_insert(connection, cursor, sql, parameters, context, many):
        if sql.startswith("INSERT INTO nifty_algo_research_observation"):
            raise RuntimeError("injected recording storage failure")

    event.listen(store.engine, "connect", connected)
    event.listen(store.engine, "close", closed)
    event.listen(store.engine, "before_cursor_execute", fail_insert)
    try:
        for _ in range(100):
            with pytest.raises(RuntimeError, match="injected recording storage failure"):
                append(store, dataset, deduplicate_samples=deduplicate_samples)
            assert not connections
            page = store.recording_page("recorder-owner", dataset["id"])
            assert page["items"] == []
            assert page["manifest"] == dataset
            assert not connections
    finally:
        event.remove(store.engine, "before_cursor_execute", fail_insert)
        event.remove(store.engine, "connect", connected)
        event.remove(store.engine, "close", closed)
    reopened = NiftyStore(store.engine)
    saved = append(reopened, dataset, deduplicate_samples=deduplicate_samples)
    assert saved["count"] == 1
