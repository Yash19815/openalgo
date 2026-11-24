"""Confirmed cross-boundary defects from the corrective audit; offline only."""

from datetime import timedelta
from json import loads

import pytest

from services.nifty_algo.discord_bot import DiscordSettings, command_response
from services.nifty_algo.paper_executor import OrderRefused
from test.test_nifty_algo_discord import configuration, interaction
from test.test_nifty_algo_paper_executor import (
    NOW,
    USER,
    FakeMarket,
    buy_intent,
    executor,
    instrument,
    listed,
    running,
)
from test.test_nifty_algo_safety_center import store as store


def test_heartbeat_cannot_refresh_old_entry_readiness(store):
    state = store.read(USER)
    later = NOW + timedelta(seconds=31)
    store.claim_runner(
        USER,
        "audit-owner",
        later,
        payload={
            "entries_ready": True,
            "configuration_id": state["configuration_id"],
            "assessed_at": NOW.isoformat(),
        },
    )
    status = store.runner_status(USER, later)
    assert status["operational"]
    assert status["entries_ready"] is False


def test_discord_health_reports_actual_runner_fields(store):
    response = command_response(
        store, USER, DiscordSettings.model_validate(configuration()), interaction("health"), NOW
    )
    result = loads(response["data"]["content"])
    assert result["runner"]["operational"] is False
    assert result["runner"]["reason"] == "RUNNER_NOT_ATTACHED"
    assert result["entry_blocked"] is True


@pytest.mark.parametrize(
    "hold", [None, "monthly_loss", "monthly_profit", "cooldown", "killed", "daily", "unreconciled"]
)
def test_discord_health_includes_persisted_risk_holds(store, hold):
    from database.nifty_algo_db import NiftyAccount, NiftyCooldown, NiftyMonth, NiftyState

    running(store)
    store.account(USER, NOW)
    state = store.read(USER)
    store.claim_runner(
        USER,
        "healthy",
        NOW,
        payload={
            "entries_ready": True,
            "configuration_id": state["configuration_id"],
            "assessed_at": NOW.isoformat(),
        },
    )
    with store.sessions.begin() as db:
        if hold in ("monthly_loss", "monthly_profit"):
            db.add(
                NiftyMonth(
                    user_id=USER,
                    month="2026-11",
                    created_at=NOW,
                    updated_at=NOW,
                    loss_locked_at=NOW if hold == "monthly_loss" else None,
                    profit_locked_at=NOW if hold == "monthly_profit" else None,
                )
            )
        elif hold == "cooldown":
            db.add(
                NiftyCooldown(
                    user_id=USER,
                    loss_session="2026-11-18",
                    cooldown_session="2026-11-19",
                    loss_event_id=1,
                    entry_order_id="prior-entry",
                    realized_net=-1,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        elif hold == "killed":
            db.get(NiftyState, USER).killed = 1
        elif hold == "daily":
            db.get(NiftyState, USER).daily_locked = 1
        elif hold == "unreconciled":
            db.get(NiftyAccount, USER).reconciled = 0
    response = command_response(
        store, USER, DiscordSettings.model_validate(configuration()), interaction("health"), NOW
    )
    assert loads(response["data"]["content"])["entry_blocked"] is (hold is not None)


def test_fallback_candidate_cannot_change_signal_option_type(store):
    running(store)
    first = instrument()
    wrong_side = first.model_copy(
        update={
            "token": "wrong-pe",
            "symbol": "WRONG_PE",
            "kind": "PE",
            "delta": -0.5,
            "delta_time": NOW,
        }
    )
    with pytest.raises(OrderRefused, match="INSTRUMENT_RESTRICTED"):
        executor(store).admit(buy_intent(candidates=[first, wrong_side]), NOW)
    assert store.pending_orders(USER) == []


def test_liquidity_is_rechecked_at_atomic_admission(store, monkeypatch):
    running(store)
    market = FakeMarket()
    paper = executor(store, market=market)
    original = store.admit_order

    def at_write(user_id, order, **kwargs):
        market.size = 0
        return original(user_id, order, **kwargs)

    monkeypatch.setattr(store, "admit_order", at_write)
    with pytest.raises(OrderRefused, match="LIQUIDITY"):
        paper.admit(buy_intent(), NOW)
    assert store.pending_orders(USER) == []


def test_price_is_rechecked_at_atomic_admission(store, monkeypatch):
    running(store)
    market = FakeMarket()
    paper = executor(store, market=market)
    original = store.admit_order

    def at_write(user_id, order, **kwargs):
        market.bid, market.ask = "164.05", "165.05"
        return original(user_id, order, **kwargs)

    monkeypatch.setattr(store, "admit_order", at_write)
    with pytest.raises(OrderRefused, match="SELECTION_CHANGED"):
        paper.admit(buy_intent(), NOW)
    assert store.pending_orders(USER) == []


def test_illiquid_first_candidate_does_not_hide_valid_fallback(store):
    running(store)
    first = instrument()
    fallback = first.model_copy(update={"token": "fallback", "symbol": "FALLBACK"})
    market = FakeMarket()
    original = market.get_all_data

    def depth(symbol, exchange):
        data = original(symbol, exchange)
        if symbol == first.symbol:
            data["depth"]["buy"][0]["quantity"] = 0
        return data

    market.get_all_data = depth
    order, created = executor(store, market=market, master=listed(fallback)).admit(
        buy_intent(candidates=[first, fallback]), NOW
    )
    assert created
    assert order["token"] == fallback.token


def test_fill_rechecks_exit_depth_for_entire_selected_quantity(store):
    running(store)
    market = FakeMarket(bid="79.5", ask="80")
    paper = executor(store, market=market)
    order, _ = paper.admit(buy_intent(), NOW)
    assert order["quantity"] == 50
    original = market.get_all_data

    def one_exit_lot(symbol, exchange):
        data = original(symbol, exchange)
        if "depth" in data:
            data["depth"]["buy"][0]["quantity"] = 25
        return data

    market.get_all_data = one_exit_lot
    result = paper.process(NOW + timedelta(seconds=1))
    assert result[0]["status"] == "REJECTED"
    assert result[0]["reason"] == "LIQUIDITY_LOST"
    assert store.positions(USER) == []


def test_stale_position_creates_one_durable_critical_incident_and_still_requests_exit(store):
    running(store)
    market = FakeMarket()
    paper = executor(store, market=market)
    paper.admit(buy_intent(), NOW)
    assert paper.process(NOW + timedelta(seconds=1))[0]["status"] == "FILLED"
    stale_at = NOW + timedelta(seconds=10)
    paper.monitor_exits(stale_at, operator_close=True)
    paper.monitor_exits(stale_at + timedelta(seconds=1), operator_close=True)
    safety = store.safety_status(USER)
    assert len(safety["incidents"]) == 1
    assert safety["incidents"][0]["code"] == "STALE_DATA"
    assert safety["entry_blocked"]
    assert len([o for o in store.pending_orders(USER) if o["side"] == "SELL"]) == 1
    assert store.positions(USER)  # A request with stale data is not a fill.


def test_discord_profit_lock_contains_actual_stop_transition(store):
    from types import SimpleNamespace

    from services.nifty_algo.discord_bot import event_projection

    event = SimpleNamespace(
        id=1,
        user_id=USER,
        kind="PROFIT_LOCK_ACTIVATED",
        created_at=NOW,
        payload={
            "token": "option",
            "stop_before": "170",
            "stop_after": "180",
            "estimated_net": "400",
            "floor_net": "350",
            "secret": "must-not-leak",
        },
    )
    destination, envelope = event_projection(event)
    assert destination == "risk-management"
    assert envelope["stop_after"] == "180"
    assert envelope["floor_net"] == "350"
    assert "secret" not in envelope


def test_trade_detail_preserves_sampled_exit_research_basis(store):
    # Each returned detail must preserve a complete decision/protection provenance;
    # missing observations remain unavailable, never numeric zero extrema.
    from test.test_nifty_algo_exit_studies import closed_trade

    trade = closed_trade(store)
    detail = store.trade_detail(USER, trade["id"])
    assert (
        detail["exit_effectiveness"]["basis"]
        == "SAMPLED_EXECUTABLE_BID_NOT_CONTINUOUS_MARKET_EXTREMA"
    )
    assert detail["mode"] == "PAPER"


@pytest.mark.parametrize(
    ("kind", "route"), [("pause", "bot-status"), ("data_blocked", "system-warnings")]
)
def test_discord_projects_existing_control_and_data_events_without_secrets(kind, route):
    from types import SimpleNamespace

    from services.nifty_algo.discord_bot import event_projection

    event = SimpleNamespace(
        id=2,
        user_id=USER,
        kind=kind,
        created_at=NOW,
        payload={"revision": 3, "reason": "private-provider-secret"},
    )
    destination, envelope = event_projection(event)
    assert destination == route
    assert "private-provider-secret" not in str(envelope)
