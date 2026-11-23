"""Durable delivery bookkeeping never treats an unknown remote outcome as a retry."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import event

from database.engine_factory import create_db_engine
from database.nifty_algo_db import (
    Base,
    NiftyAccount,
    NiftyNotificationCursor,
    NiftyNotificationDelivery,
    NiftyOrder,
    NiftyState,
    NiftyStore,
)
from test.test_nifty_algo_paper_executor import NOW, USER


@pytest.fixture
def store(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'outbox.db'}")
    value = NiftyStore(engine)
    value.initialize()
    value.ensure_user(USER)
    yield value
    engine.dispose()


def seed(store, *, mode="PAPER"):
    store.raise_safety_incident(
        USER, "outbox-feed", mode=mode, code="STALE_DATA", severity="CRITICAL", now=NOW
    )
    return store.project_notifications(USER, ["safety", "system"], now=NOW)


def test_projection_is_restart_safe_owner_scoped_and_allowlisted(store):
    store.record_event(USER, "arbitrary", {"secret": "must-not-escape"}, NOW)
    assert seed(store) == 2
    reopened = NiftyStore(store.engine)
    assert reopened.project_notifications(USER, ["safety", "system"], now=NOW) == 0
    rows = reopened.notifications(USER)
    assert len(rows) == 2
    assert not reopened.notifications("another-user")
    for row in rows:
        assert row["envelope"]["schema_version"] == 1
        assert row["envelope"]["mode"] == "PAPER"
        assert row["envelope"]["code"] == "STALE_DATA"
        assert "secret" not in str(row)
        assert "claim_token" not in row


def test_two_store_instances_cannot_claim_the_same_delivery(store):
    seed(store)
    first = store.claim_notification(USER, now=NOW)
    second = NiftyStore(store.engine).claim_notification(USER, now=NOW)
    assert first["id"] != second["id"]
    assert first["claim_token"] != second["claim_token"]
    assert store.claim_notification("another-user", now=NOW) is None
    assert store.claim_notification(USER, now=NOW) is None


def test_success_requires_current_claim_and_is_not_replayed(store):
    seed(store)
    claim = store.claim_notification(USER, now=NOW)
    with pytest.raises(ValueError):
        store.finish_notification(USER, claim["id"], "wrong", "DELIVERED", now=NOW)
    assert store.finish_notification(USER, claim["id"], claim["claim_token"], "DELIVERED", now=NOW)
    with pytest.raises(ValueError):
        store.finish_notification(USER, claim["id"], claim["claim_token"], "DELIVERED", now=NOW)
    assert (
        next(row for row in store.notifications(USER) if row["id"] == claim["id"])["status"]
        == "DELIVERED"
    )


def test_expired_dispatch_is_ambiguous_and_critical_fallback_is_independent(store):
    seed(store)
    abandoned = store.claim_notification(USER, now=NOW)
    later = NOW + timedelta(seconds=61)
    store.claim_notification(USER, now=later)
    rows = store.notifications(USER)
    assert next(row for row in rows if row["id"] == abandoned["id"])["status"] == "AMBIGUOUS"
    assert len([row for row in rows if row["destination"] == "email_fallback"]) == 1
    assert not store.finish_notification(
        USER, abandoned["id"], abandoned["claim_token"], "DELIVERED", now=later
    )


def test_confirmed_retry_respects_deadline_and_attempt_bound(store):
    seed(store)
    # Isolate one route so every retry below names the same delivery.
    other = store.claim_notification(USER, now=NOW)
    store.finish_notification(USER, other["id"], other["claim_token"], "DELIVERED", now=NOW)
    now = NOW
    for attempt in range(1, 6):
        claim = store.claim_notification(USER, now=now)
        assert claim["attempts"] == attempt
        store.finish_notification(
            USER, claim["id"], claim["claim_token"], "RETRY", now=now, retry_after=30
        )
        if attempt < 5:
            assert store.claim_notification(USER, now=now + timedelta(seconds=29)) is None
        now += timedelta(seconds=30)
    rows = store.notifications(USER)
    assert len([row for row in rows if row["status"] == "DEAD"]) == 1
    assert len([row for row in rows if row["destination"] == "email_fallback"]) == 1


@pytest.mark.parametrize("destinations", [["https://evil.invalid"], ["safety"] * 11, "safety", []])
def test_destinations_are_bounded_logical_routes_not_urls(store, destinations):
    with pytest.raises(ValueError):
        store.project_notifications(USER, destinations, now=NOW)


def test_shadow_notifications_remain_labelled_and_cannot_raise_primary_hold(store):
    seed(store, mode="SHADOW")
    assert {row["envelope"]["mode"] for row in store.notifications(USER)} == {"SHADOW"}
    assert not store.safety_status(USER)["entry_blocked"]


def test_competing_claim_writers_have_distinct_transports(store):
    seed(store)
    barrier = Barrier(2)

    def claim():
        other = NiftyStore(store.engine)
        barrier.wait(timeout=10)
        return other.claim_notification(USER, now=NOW)

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="nifty-outbox-test") as pool:
        futures = [pool.submit(claim) for _ in range(2)]
        claims = [future.result(timeout=15) for future in futures]
    assert len({claim["id"] for claim in claims}) == 2
    assert len({claim["claim_token"] for claim in claims}) == 2
    assert store.claim_notification(USER, now=NOW) is None


def test_projection_cursor_and_deliveries_roll_back_together(store):
    store.raise_safety_incident(
        USER, "rollback", mode="PAPER", code="STALE_DATA", severity="CRITICAL", now=NOW
    )

    def refuse_commit(session):
        if any(
            isinstance(row, (NiftyNotificationCursor, NiftyNotificationDelivery))
            for row in session.new
        ):
            raise RuntimeError("injected commit failure")

    event.listen(store.sessions.class_, "before_commit", refuse_commit)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            store.project_notifications(USER, ["safety"], now=NOW)
    finally:
        event.remove(store.sessions.class_, "before_commit", refuse_commit)
    assert store.notifications(USER) == []
    assert store.project_notifications(USER, ["safety"], now=NOW) == 1


def test_repeated_failed_settlements_release_every_database_connection(store):
    seed(store)
    claim = store.claim_notification(USER, now=NOW)
    acquired, released = [], []

    def opened(connection, record):
        acquired.append(id(connection))

    def closed(connection, record):
        released.append(id(connection))

    event.listen(store.engine, "connect", opened)
    event.listen(store.engine, "close", closed)
    try:
        for _ in range(100):
            with pytest.raises(ValueError, match="not current"):
                store.finish_notification(USER, claim["id"], "stale-token", "DELIVERED", now=NOW)
            store.notifications(USER)
            assert len(acquired) == len(released)
    finally:
        event.remove(store.engine, "connect", opened)
        event.remove(store.engine, "close", closed)
    assert len(acquired) >= 200


def test_additive_migration_preserves_existing_locks_balances_and_reservations(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'baseline.db'}")
    new_tables = {
        "nifty_algo_safety_incident",
        "nifty_algo_notification_cursor",
        "nifty_algo_notification_delivery",
        "nifty_algo_research_recording",
        "nifty_algo_research_observation",
        "nifty_algo_research_experiment",
    }
    try:
        Base.metadata.create_all(
            engine,
            tables=[table for table in Base.metadata.sorted_tables if table.name not in new_tables],
        )
        baseline = NiftyStore(engine)
        baseline.ensure_user(USER)
        baseline.account(USER, NOW)
        with baseline.sessions.begin() as db:
            state = db.get(NiftyState, USER)
            state.state, state.killed, state.daily_locked = "KILLED", 1, 1
            account = db.get(NiftyAccount, USER)
            account.available -= Decimal("12000")
            db.add(
                NiftyOrder(
                    user_id=USER,
                    order_id="existing",
                    intent_id="reserved",
                    side="BUY",
                    symbol="NIFTY",
                    token="existing-token",
                    quantity=75,
                    status="PENDING",
                    payload={"reservation": "12000", "frozen_configuration": state.configuration},
                    eligible_at=NOW,
                    expires_at=NOW + timedelta(minutes=5),
                    created_at=NOW,
                )
            )
        before_state = baseline.read(USER)
        before_account = baseline.account(USER, NOW)
        before_order = baseline.order_by_intent(USER, "reserved")
        expanded = NiftyStore(engine)
        expanded.initialize()
        expanded.initialize()
        assert expanded.read(USER) == before_state
        assert expanded.account(USER, NOW) == before_account
        assert expanded.order_by_intent(USER, "reserved") == before_order
        assert not expanded.safety_status(USER)["incidents"]
        assert not expanded.notifications(USER)
        assert expanded.experiments(USER) == []
    finally:
        engine.dispose()
