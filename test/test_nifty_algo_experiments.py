"""Immutable research definitions, not executable backtests or trading settings."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from json import dumps
from threading import Event

import pytest
from sqlalchemy import event, update

from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyResearchExperiment, NiftyResearchRecording, NiftyStore
from services.nifty_algo.config import StrategyConfig
from test.test_nifty_algo_recording import NOW, append, create


@pytest.fixture
def store(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'experiments.db'}")
    value = NiftyStore(engine)
    value.initialize()
    value.ensure_user("recorder-owner")
    yield value
    engine.dispose()


def dataset(store):
    manifest = create(store)
    append(store, manifest)
    return store.seal_recording("recorder-owner", manifest["id"], NOW, expected_count=1)


def define(store, manifest, **changes):
    arguments = {
        "expected_count": manifest["count"],
        "expected_sha256": manifest["content_sha256"],
        "configuration": StrategyConfig(adx_min=30).model_dump(mode="json"),
        "train_end": NOW - timedelta(seconds=40),
        "validation_end": NOW - timedelta(seconds=20),
    }
    arguments.update(changes)
    return store.create_experiment("recorder-owner", manifest["id"], NOW, **arguments)


def test_experiment_freezes_configuration_dataset_and_half_open_splits(store):
    manifest = dataset(store)
    before = deepcopy(store.read("recorder-owner"))
    result = define(store, manifest)
    assert result["mode"] == "RESEARCH"
    assert result["status"] == "DEFINED"
    assert result["execution_eligible"] is False
    assert result["performance"] is None
    snapshot = deepcopy(result["snapshot"])
    assert snapshot["dataset"] == manifest
    assert snapshot["configuration"]["adx_min"] == 30
    assert snapshot["configuration_id"] == StrategyConfig(adx_min=30).version_id
    train, validation, test = snapshot["splits"]
    assert [part["kind"] for part in snapshot["splits"]] == ["TRAIN", "VALIDATION", "TEST"]
    assert train["start"] == manifest["starts_at"]
    assert train["end"] == validation["start"]
    assert validation["end"] == test["start"]
    assert test["end"] == NOW.isoformat()
    assert snapshot["interval"] == "[start,end)"
    assert len(result["sha256"]) == 64
    result["snapshot"]["configuration"]["adx_min"] = 99
    assert store.experiment("recorder-owner", result["id"])["snapshot"] == snapshot
    assert store.read("recorder-owner") == before
    reopened = NiftyStore(store.engine)
    reopened.initialize()
    assert reopened.experiment("recorder-owner", result["id"])["sha256"] == result["sha256"]


@pytest.mark.parametrize("field", ["train_end", "validation_end"])
def test_experiment_refuses_invalid_or_future_split(store, field):
    manifest = dataset(store)
    for value in (NOW, NOW.replace(tzinfo=None), NOW + timedelta(seconds=1)):
        with pytest.raises(ValueError):
            define(store, manifest, **{field: value})
    assert store.experiments("recorder-owner") == []


def test_experiment_requires_seal_and_pinned_source_integrity(store):
    manifest = create(store)
    with pytest.raises(ValueError, match="sealed"):
        define(store, manifest)
    manifest = store.seal_recording("recorder-owner", manifest["id"], NOW, expected_count=0)
    with pytest.raises(ValueError, match="identity"):
        define(store, manifest, expected_sha256="0" * 64)
    assert store.experiments("recorder-owner") == []


def test_experiment_reads_are_owner_scoped_detached_and_select_only(store):
    result = define(store, dataset(store))
    statements = []
    event.listen(
        store.engine,
        "before_cursor_execute",
        lambda _c, _u, statement, *_a: statements.append(statement),
    )
    assert store.experiment("other-owner", result["id"]) is None
    assert store.experiments("other-owner") == []
    assert store.experiment("recorder-owner", "missing") is None
    assert store.experiments("recorder-owner") == [result]
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)


def test_experiment_insert_failure_rolls_back_and_closes_every_connection(store):
    manifest = dataset(store)
    counts = {"opened": 0, "closed": 0, "failed": 0}

    def opened(*_):
        counts["opened"] += 1

    def closed(*_):
        counts["closed"] += 1

    def fail_after_insert(_connection, _cursor, statement, *_):
        if statement.lstrip().upper().startswith("INSERT INTO NIFTY_ALGO_RESEARCH_EXPERIMENT "):
            counts["failed"] += 1
            raise RuntimeError("injected after experiment insert")

    event.listen(store.engine, "connect", opened)
    event.listen(store.engine, "close", closed)
    event.listen(store.engine, "after_cursor_execute", fail_after_insert)
    try:
        for _ in range(100):
            with pytest.raises(RuntimeError, match="injected"):
                define(store, manifest)
            assert counts["opened"] == counts["closed"]
    finally:
        event.remove(store.engine, "after_cursor_execute", fail_after_insert)
    assert counts["failed"] == 100
    assert store.experiments("recorder-owner") == []
    assert define(store, manifest)["status"] == "DEFINED"
    assert len(store.experiments("recorder-owner")) == 1
    assert counts["opened"] == counts["closed"]


def test_experiment_digest_is_deterministic_and_covers_dataset_config_and_splits(store):
    manifest = dataset(store)
    first, second = define(store, manifest), define(store, manifest)
    assert first["id"] != second["id"]
    assert first["sha256"] == second["sha256"]
    encoded = dumps(first["snapshot"], sort_keys=True, separators=(",", ":")).encode()
    assert first["sha256"] == sha256(encoded).hexdigest()
    changed = define(store, manifest, configuration=StrategyConfig().model_dump(mode="json"))
    split = define(store, manifest, train_end=NOW - timedelta(seconds=41))
    assert len({first["sha256"], changed["sha256"], split["sha256"]}) == 3
    changed["snapshot"]["dataset"]["count"] = 999
    assert store.experiment("recorder-owner", changed["id"])["snapshot"]["dataset"]["count"] == 1


@pytest.mark.parametrize(
    "configuration",
    [{"broker": "angel"}, {"max_lots": 10}, {"adx_min": float("nan")}, None],
)
def test_experiment_refuses_invalid_configuration_without_side_effects(store, configuration):
    manifest = dataset(store)
    before = store.read("recorder-owner")
    with pytest.raises(ValueError):
        define(store, manifest, configuration=configuration)
    assert store.experiments("recorder-owner") == []
    assert store.read("recorder-owner") == before


def test_experiment_fences_source_change_at_the_transaction_lock(store):
    manifest = dataset(store)
    fired = False

    def change_before_lock(_connection, _cursor, statement, *_):
        nonlocal fired
        if not fired and statement.lstrip().upper().startswith("UPDATE NIFTY_ALGO_STATE "):
            fired = True
            with store.sessions.begin() as db:
                db.execute(
                    update(NiftyResearchRecording)
                    .where(
                        NiftyResearchRecording.user_id == "recorder-owner",
                        NiftyResearchRecording.id == manifest["id"],
                    )
                    .values(content_sha256="f" * 64)
                )

    event.listen(store.engine, "before_cursor_execute", change_before_lock)
    try:
        with pytest.raises(ValueError, match="changed"):
            define(store, manifest)
    finally:
        event.remove(store.engine, "before_cursor_execute", change_before_lock)
    assert fired
    assert store.experiments("recorder-owner") == []


def test_experiment_quota_holds_when_competing_writer_arrives_at_insert(store):
    manifest = dataset(store)
    for _ in range(49):
        define(store, manifest)
    inserting, competing = Event(), Event()

    def at_write(_connection, _cursor, statement, *_):
        sql = statement.lstrip().upper()
        if sql.startswith("INSERT INTO NIFTY_ALGO_RESEARCH_EXPERIMENT "):
            inserting.set()
            assert competing.wait(5), "competing writer did not reach owner lock"
        elif inserting.is_set() and sql.startswith("UPDATE NIFTY_ALGO_STATE "):
            competing.set()

    event.listen(store.engine, "before_cursor_execute", at_write)
    try:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="experiment-quota") as pool:
            first = pool.submit(define, store, manifest)
            assert inserting.wait(5), "first writer did not reach insert"
            second = pool.submit(define, store, manifest)
            assert first.result(timeout=10)["status"] == "DEFINED"
            with pytest.raises(ValueError, match="quota"):
                second.result(timeout=10)
    finally:
        competing.set()
        event.remove(store.engine, "before_cursor_execute", at_write)
    assert len(store.experiments("recorder-owner")) == 50


def test_experiment_read_refuses_corrupt_snapshot(store):
    result = define(store, dataset(store))
    with store.sessions.begin() as db:
        row = db.get(NiftyResearchExperiment, ("recorder-owner", result["id"]))
        corrupt = deepcopy(row.snapshot)
        corrupt["configuration"]["adx_min"] = 99
        row.snapshot = corrupt
    with pytest.raises(ValueError, match="integrity"):
        store.experiment("recorder-owner", result["id"])
    with pytest.raises(ValueError, match="integrity"):
        store.experiments("recorder-owner")
