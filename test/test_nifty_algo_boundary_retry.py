"""Deterministic boundary retries use real durable state, never sleep."""

from datetime import timedelta
from unittest.mock import Mock

import pytest

from services.nifty_algo.runner import NiftyRunner
from test.test_nifty_algo_paper_executor import NOW, USER
from test.test_nifty_algo_paper_executor import store as feature_store


@pytest.fixture
def store(request):
    return request.getfixturevalue("feature_store")


def decision(config, at, *, fresh):
    end = NOW if fresh else NOW - timedelta(minutes=5)
    return {
        "decision_id": f"offline-{end.isoformat()}",
        "timestamp": at.isoformat(),
        "config_id": config.version_id,
        "analysis_token": "OFFLINE",
        "snapshot": {"end": end.isoformat()},
        "eligible": False,
        "side": None,
        "checks": [{"rule": "R-FRESH", "state": "PASS" if fresh else "FAIL", "detail": "age"}],
        "reasons": [] if fresh else ["R-FRESH: age"],
    }


def test_delayed_publication_retries_once_and_commits_one_decision(store):
    reads = Mock(side_effect=lambda config, at: decision(config, at, fresh=reads.call_count > 1))
    runner = NiftyRunner(store, USER, assessment=reads, clock=lambda: NOW)
    assert runner.evaluate(NOW) is None
    assert store.decisions(USER) == []
    assert runner.evaluate(NOW + timedelta(seconds=5)) is not None
    assert runner.evaluate(NOW + timedelta(seconds=10)) is None
    assert reads.call_count == 2
    assert len(store.decisions(USER)) == 1


def test_expiry_and_permanent_refusals_never_retry(store):
    reads = Mock(side_effect=lambda config, at: decision(config, at, fresh=False))
    runner = NiftyRunner(store, USER, assessment=reads, clock=lambda: NOW)
    for seconds in range(0, 36, 5):
        runner.evaluate(NOW + timedelta(seconds=seconds))
    assert reads.call_count == 7
    assert store.decisions(USER) == []


def test_restart_uses_durable_completed_boundary(store):
    reads = Mock(side_effect=lambda config, at: decision(config, at, fresh=True))
    runner = NiftyRunner(store, USER, assessment=reads, clock=lambda: NOW)
    assert runner.evaluate(NOW) is not None
    store.release_runner(USER, runner.owner)
    restored = NiftyRunner(store, USER, assessment=reads, clock=lambda: NOW)
    assert restored.evaluate(NOW + timedelta(seconds=5)) is None
    assert reads.call_count == 1


def test_restart_recovers_temporary_failure_without_duplicate_decisions(store):
    reads = Mock(side_effect=lambda config, at: decision(config, at, fresh=reads.call_count > 1))
    runner = NiftyRunner(store, USER, assessment=reads, clock=lambda: NOW)
    runner.evaluate(NOW)
    store.release_runner(USER, runner.owner)
    restored = NiftyRunner(store, USER, assessment=reads, clock=lambda: NOW + timedelta(seconds=5))
    assert restored.evaluate(NOW + timedelta(seconds=5)) is not None
    assert reads.call_count == 2 and len(store.decisions(USER)) == 1


def test_elapsed_fetch_cannot_extend_freshness_window(store):
    clock = [NOW]

    def late(config, at):
        clock[0] = NOW + timedelta(seconds=31)
        return decision(config, at, fresh=True)

    runner = NiftyRunner(store, USER, assessment=late, clock=lambda: clock[0])
    assert runner.evaluate(NOW) is None
    assert not store.decisions(USER)


def test_concurrent_evaluations_have_one_claim(store):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    entered, release = Event(), Event()

    def assessment(config, at):
        entered.set()
        assert release.wait(10)
        return decision(config, at, fresh=True)

    runner = NiftyRunner(store, USER, assessment=assessment, clock=lambda: NOW)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runner.evaluate, NOW)
        try:
            assert entered.wait(10)
            assert runner.evaluate(NOW) is None
        finally:
            release.set()
        assert future.result(timeout=10) is not None
    assert len(store.decisions(USER)) == 1


def test_expired_claim_result_is_fenced(store):
    from services.nifty_algo.config import StrategyConfig

    store.ensure_user(USER)
    config_id = StrategyConfig().version_id
    boundary = int(NOW.timestamp()) // 300
    assert store.claim_runner(USER, "owner", NOW)
    old = store.claim_assessment(USER, "owner", boundary, config_id, NOW)
    new = store.claim_assessment(USER, "owner", boundary, config_id, NOW + timedelta(seconds=5))
    assert old and new and old != new
    assert not store.finish_assessment(
        USER, "owner", boundary, config_id, old, NOW + timedelta(seconds=6)
    )
    assert store.finish_assessment(
        USER, "owner", boundary, config_id, new, NOW + timedelta(seconds=6)
    )
