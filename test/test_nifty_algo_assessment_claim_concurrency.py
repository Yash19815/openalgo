"""Assessment claims are serialised by the owner lock for the whole transaction.

``NiftyStore.claim_assessment`` increments ``row.attempts`` after reading it.
The increment is only safe because ``_lock`` (an UPDATE of the user's state
row) opens the same transaction and holds the write lock until commit. These
tests stage the competing writer at the attempt write itself, the one place a
check-then-act race can live, and assert that it is parked on the owner lock
and decides only after the first claim has committed.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event, current_thread

import pytest
from sqlalchemy import event

from database.nifty_algo_db import NiftyAssessmentAttempt, NiftyStore
from services.nifty_algo.config import StrategyConfig
from test.test_nifty_algo_paper_executor import NOW, USER
from test.test_nifty_algo_paper_executor import store as feature_store

BOUNDARY = int(NOW.timestamp()) // 300
OWNER = "owner"


@pytest.fixture
def store(request):
    return request.getfixturevalue("feature_store")


@pytest.fixture
def config_id(store):
    store.ensure_user(USER)
    assert store.claim_runner(USER, OWNER, NOW, seconds=300)
    return StrategyConfig().version_id


def claim(store, config_id, at, owner=OWNER):
    # A store of its own per caller: the competitor shares the database file
    # and nothing in memory, as two processes would.
    return NiftyStore(store.engine).claim_assessment(USER, owner, BOUNDARY, config_id, at)


def attempt(store, config_id):
    with store.sessions() as db:
        return db.get(NiftyAssessmentAttempt, (USER, BOUNDARY, config_id))


@pytest.mark.parametrize("prior_attempt", [False, True], ids=["first-claim", "retry-claim"])
def test_competing_claim_parked_at_the_attempt_write_loses(store, config_id, prior_attempt):
    at = NOW
    if prior_attempt:
        assert claim(store, config_id, NOW)
        at = NOW + timedelta(seconds=5)
    at_write, parked = Event(), Event()
    statements = []

    def listener(_connection, _cursor, statement, *_):
        sql = statement.lstrip().upper()
        name = current_thread().name
        if name.startswith("first"):
            if sql.startswith(
                (
                    "INSERT INTO NIFTY_ALGO_ASSESSMENT_ATTEMPT",
                    "UPDATE NIFTY_ALGO_ASSESSMENT_ATTEMPT",
                )
            ):
                at_write.set()
                # The check is done and the write is next: hold here until the
                # competitor is at the owner lock, then let the write land.
                assert parked.wait(5), "competing claim never reached the owner lock"
        elif name.startswith("second"):
            statements.append(sql.split(" (")[0].split(" WHERE")[0])
            if sql.startswith("UPDATE NIFTY_ALGO_STATE "):
                parked.set()

    event.listen(store.engine, "before_cursor_execute", listener)
    try:
        with (
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="first") as first_pool,
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="second") as second_pool,
        ):
            first = first_pool.submit(claim, store, config_id, at)
            assert at_write.wait(5), "first claim never reached its write"
            second = second_pool.submit(claim, store, config_id, at)
            winner, loser = first.result(timeout=15), second.result(timeout=15)
    finally:
        parked.set()
        event.remove(store.engine, "before_cursor_execute", listener)
    assert winner and loser is None
    # The competitor's first statement was the owner lock, before any read.
    assert statements[0].startswith("UPDATE NIFTY_ALGO_STATE")
    row = attempt(store, config_id)
    assert row.attempts == (2 if prior_attempt else 1)
    assert row.claim_id == winner and row.status == "IN_FLIGHT"


def test_racing_claims_never_exceed_the_retry_budget(store, config_id):
    """Four writers per five-second step across the window and past it."""
    wins_per_step = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for step in range(10):
            at = NOW + timedelta(seconds=5 * step)
            barrier = Barrier(4)

            def racer(at=at, barrier=barrier):
                barrier.wait(timeout=10)
                return claim(store, config_id, at)

            results = [f.result(timeout=30) for f in [pool.submit(racer) for _ in range(4)]]
            wins_per_step.append(sum(1 for r in results if r))
    # Seven attempts fit in the thirty second window (0, 5, ... 30), one each;
    # nothing is granted after the budget or the deadline.
    assert wins_per_step == [1] * 7 + [0] * 3
    assert attempt(store, config_id).attempts == 7


def test_completed_boundary_is_not_claimed_again_under_race(store, config_id):
    first = claim(store, config_id, NOW)
    assert store.finish_assessment(USER, OWNER, BOUNDARY, config_id, first, NOW)
    barrier = Barrier(4)

    def racer():
        barrier.wait(timeout=10)
        return claim(store, config_id, NOW + timedelta(seconds=10))

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = [f.result(timeout=30) for f in [pool.submit(racer) for _ in range(4)]]
    assert results == [None] * 4
    assert attempt(store, config_id).attempts == 1


def test_restart_takeover_waits_out_the_window_and_fences_the_old_claim(store, config_id):
    # The owner's lease is short; it claims an assessment and then dies.
    # (A renewal by the same owner never shortens a lease, so release first.)
    store.release_runner(USER, OWNER)
    assert store.claim_runner(USER, OWNER, NOW, seconds=1)
    dead = claim(store, config_id, NOW)
    assert dead
    # A restarted runner takes the lease once it has expired.
    later = NOW + timedelta(seconds=2)
    assert not store.claim_runner(USER, "restarted", NOW + timedelta(seconds=0.5))
    assert store.claim_runner(USER, "restarted", later, seconds=60)
    # The dead owner can neither claim nor finish, so it cannot extend the budget.
    assert claim(store, config_id, later) is None
    assert not store.finish_assessment(USER, OWNER, BOUNDARY, config_id, dead, later)
    # The restarted runner honours the pending retry time, then claims once.
    assert claim(store, config_id, later, owner="restarted") is None
    retry_at = NOW + timedelta(seconds=5)
    fresh = claim(store, config_id, retry_at, owner="restarted")
    assert fresh and fresh != dead
    assert not store.finish_assessment(USER, OWNER, BOUNDARY, config_id, dead, retry_at)
    assert store.finish_assessment(USER, "restarted", BOUNDARY, config_id, fresh, retry_at)
    assert attempt(store, config_id).attempts == 2
    assert claim(store, config_id, retry_at + timedelta(seconds=5), owner="restarted") is None


def test_retry_expiry_is_refused_after_the_deadline(store, config_id):
    assert claim(store, config_id, NOW + timedelta(seconds=30))
    assert claim(store, config_id, NOW + timedelta(seconds=30, microseconds=1)) is None
    assert attempt(store, config_id).attempts == 1
