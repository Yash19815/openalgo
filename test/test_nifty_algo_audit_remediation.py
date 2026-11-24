"""Offline regressions for the November audit; no broker evidence implied."""

from datetime import time, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.contract_resolver import (
    Resolver,
    SelectionUnavailable,
    atm_reference,
    current_moneyness,
)
from test.test_nifty_algo_paper_executor import NOW, instrument
from test.test_nifty_algo_paper_executor import store as store


def test_pending_order_respects_configured_cutoff_after_restart(store, monkeypatch):
    from database.nifty_algo_db import NiftyStore
    from test import test_nifty_algo_paper_executor as fixtures

    now = NOW.replace(hour=8, minute=29, second=55)  # 13:59:55 IST
    monkeypatch.setattr(fixtures, "NOW", now)
    fixtures.running(store)
    config = StrategyConfig(entry_before=time(14))
    executor = fixtures.executor(store, config=config)
    order, _ = executor.admit(fixtures.buy_intent(), now)
    reopened = NiftyStore(store.engine)
    reopened.expire_pending(fixtures.USER, now + timedelta(seconds=5))
    assert reopened.orders(fixtures.USER, now=now)[0]["status"] == "EXPIRED"


@pytest.mark.parametrize("side", ["CE", "PE"])
@pytest.mark.parametrize("reverse", [False, True])
def test_missing_midpoint_grid_strike_never_grants_atm(side, reverse):
    chain = [
        instrument().model_copy(update={"kind": side, "strike": Decimal(s), "token": s})
        for s in ("24900", "25000")
    ]
    if reverse:
        chain.reverse()
    assert atm_reference([i.strike for i in chain], Decimal("24975")) is None
    upper = next(i for i in chain if i.strike == 25000)
    assert current_moneyness(upper, 24975, chain)[:2] == ("OTM" if side == "CE" else "ITM", None)


@pytest.mark.parametrize(
    "strikes,spot,expected",
    [
        ([24950, 25000], 24975, 24950),
        ([25000], 25000, 25000),
        ([24900, 25000], 24960, None),
        ([24900, 25000], 24990, None),
        ([24950, 25000], 24990, 25000),
        ([24960, 25010], 24990, None),
    ],
)
def test_atm_requires_actual_grid_neighbors(strikes, spot, expected):
    assert atm_reference(strikes, spot) == expected


@pytest.mark.parametrize(
    "side,spot,strikes",
    [
        ("CE", 25000, [24900, 25000, 25050]),
        ("PE", 25000, [24950, 25000, 25100]),
    ],
)
def test_itm_does_not_substitute_deeper_strike(side, spot, strikes):
    chain = [
        instrument().model_copy(update={"kind": side, "strike": Decimal(s), "token": str(s)})
        for s in strikes
    ]
    with pytest.raises(SelectionUnavailable) as caught:
        Resolver().assess(chain, {}, spot, side, NOW, StrategyConfig(selection="ITM"))
    assert caught.value.code == "ITM_STRIKE_UNAVAILABLE"


def test_macd_validation_identifies_field():
    with pytest.raises(ValidationError) as caught:
        StrategyConfig(crossover_freshness=3)
    assert caught.value.errors()[0]["loc"] == ("crossover_freshness",)


def test_replay_expires_entry_at_early_close_buffer(monkeypatch):
    from services.nifty_algo import execution_replay as replay
    from test.test_nifty_algo_execution_completion import qualifying, tape

    monkeypatch.setattr(replay, "decision_at", qualifying)
    at = NOW.replace(hour=7, minute=24, second=59, microsecond=900000)
    rows = tape(at)
    for session in rows[0]["payload"]["sessions"]:
        if session["date"] == at.date().isoformat():
            session["end"] = at.replace(hour=7, minute=30, second=0, microsecond=0).isoformat()
    result = replay._run(rows, StrategyConfig(), True, at, at + timedelta(minutes=1))
    assert any(row["code"] == "ENTRY_EXPIRED" for row in result["rejections"])
    assert result["performance"]["trades"] == 0


def test_off_grid_master_row_never_becomes_atm():
    assert atm_reference([24950, 24975, 25000], 24975) == 24950


def test_runner_selector_refusal_uses_order_rejection_channel(store, monkeypatch):
    from services.nifty_algo.paper_executor import NiftyPaperExecutor, OrderRefused
    from services.nifty_algo.runner import NiftyRunner
    from test.test_nifty_algo_paper_executor import USER
    from test.test_nifty_algo_pipeline import pipeline

    native = pipeline()
    runner = NiftyRunner(
        store,
        USER,
        native=native,
        executor=NiftyPaperExecutor(store, USER, market_data=native.market_data),
    )

    def refuse(*args, **kwargs):
        raise SelectionUnavailable("ATM_REFERENCE_UNVERIFIED", "private provider details")

    monkeypatch.setattr(Resolver, "assess", refuse)
    try:
        with pytest.raises(OrderRefused) as caught:
            runner._entry_candidates({"side": "CE", "decision_id": "test"}, StrategyConfig(), NOW)
        assert caught.value.reasons == ["ATM_REFERENCE_UNVERIFIED"]
        event = store.events(USER, kind="contract_selector:PAPER", limit=1)[0]
        assert event["payload"]["reasons"] == caught.value.reasons
        assert "private provider details" not in str(event)
    finally:
        runner.close()


@pytest.mark.parametrize("cutoff", [time(14), time(14, 45)])
@pytest.mark.parametrize("early", [False, True])
def test_shared_expiry_exact_boundary_and_timezone(cutoff, early):
    from datetime import UTC, datetime

    from services.nifty_algo.session_policy import IST, entry_cutoff, pending_entry_expiry

    config = StrategyConfig(entry_before=cutoff)
    close = datetime.combine(NOW.date(), time(13) if early else time(15, 30), IST)
    boundary = datetime.combine(NOW.date(), time(12, 55) if early else cutoff, IST)
    now = boundary - timedelta(seconds=2)
    assert entry_cutoff(now, config, close) == boundary
    assert pending_entry_expiry(now, config, close) == boundary
    assert pending_entry_expiry(now.astimezone(UTC), config, close) == boundary
    assert pending_entry_expiry(boundary, config, close) == boundary
    assert pending_entry_expiry(boundary - timedelta(seconds=20), config, close) == (
        boundary - timedelta(seconds=10)
    )
