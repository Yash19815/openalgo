import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select

from database.engine_factory import create_db_engine
from database.nifty_algo_db import (
    NiftyAccount,
    NiftyCalendarVersion,
    NiftyConfiguration,
    NiftyEvent,
    NiftyState,
    NiftyStore,
)
from services.nifty_algo import calendar as session_calendar
from services.nifty_algo.config import StrategyConfig, migrate_configuration
from services.nifty_algo.contract_resolver import Resolver
from services.nifty_algo.models import Instrument, Quote
from services.nifty_algo.paper_executor import NiftyPaperExecutor, OrderRefused, _charges
from services.nifty_algo.protection import initial_protection
from services.nifty_algo.risk_manager import AccountRisk, entry_reasons, plan_entry
from test.test_nifty_algo_paper_executor import (
    NOW,
    USER,
    FakeMarket,
    _paper_test_config,
    buy_intent,
    executor,
    instrument,
    running,
)

D = Decimal
IST = ZoneInfo("Asia/Kolkata")


class Phase1MarketCalendar:
    db_session = SimpleNamespace(remove=lambda: None)

    @staticmethod
    def get_special_session(day, exchange):
        return None

    @staticmethod
    def get_effective_session_window(day, exchange):
        return None

    @staticmethod
    def get_market_timing(exchange):
        return {"start_offset": 33_300_000, "end_offset": 55_800_000}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(
        session_calendar, "_legacy_calendar", lambda: Phase1MarketCalendar()
    )
    engine = create_db_engine(f"sqlite:///{tmp_path / 'phase1.db'}")
    value = NiftyStore(engine)
    value.initialize()
    value.ensure_user(USER)
    _seed_approved_calendar(value, USER)
    yield value
    engine.dispose()


def candidate(token="candidate", *, strike=22000, lot_size=25, tick_size="0.05"):
    local_date = NOW.astimezone(IST).date()
    item = Instrument(
        token=token,
        symbol=f"PHASE1-{token}",
        exchange="NFO",
        underlying="NIFTY",
        kind="CE",
        expiry=local_date + timedelta(days=5),
        strike=strike,
        lot_size=lot_size,
        tick_size=D(tick_size),
        master_date=local_date,
    )
    quote = Quote(
        token=token,
        source_time=NOW,
        received_time=NOW,
        ltp=D("129.5"),
        bid=D("129"),
        ask=D("130"),
        bid_size=1000,
        ask_size=1000,
        volume=5000,
        provider="PHASE1_TEST",
    )
    return item, quote


def account(*, equity="20000", available="20000", **kwargs):
    return AccountRisk(
        D(equity),
        D(available),
        D(equity),
        reconciled=True,
        entries_enabled=True,
        **kwargs,
    )


def no_charges(side, price, quantity, config):
    return D("0")


def active_config(store, config=None, user=USER):
    config = _paper_test_config(config)
    _seed_approved_calendar(store, user)
    store.ensure_user(user)
    with store.sessions.begin() as db:
        state = db.get(NiftyState, user)
        state.configuration = config.model_dump(mode="json")
        state.configuration_id = config.version_id
        state.state = "RUNNING"
    store.account(user, NOW)
    return config


def _seed_approved_calendar(store, user):
    year = NOW.astimezone(IST).year
    if store.approved_calendar_version(user, year) is not None:
        return
    data = f"date,name\n{year}-01-26,Republic Day (fixture)\n".encode()
    draft = store.create_calendar_draft(
        user,
        year=year,
        segment="NFO",
        source_filename="fixture.csv",
        sha256=sha256(data).hexdigest(),
        uploader=user,
        entries=[{"date": f"{year}-01-26", "name": "Republic Day (fixture)"}],
        issues=[],
        data=data,
        extension="csv",
    )
    store.approve_calendar(
        user,
        draft["id"],
        confirmed_year=year,
        confirmed_segment="NFO",
        actor=user,
    )


def pending_order(config, intent_id, created_at=NOW, expires_at=None):
    item, item_quote = candidate()
    return {
        "order_id": f"order-{intent_id}",
        "intent_id": intent_id,
        "side": "BUY",
        "symbol": item.symbol,
        "token": item.token,
        "quantity": item.lot_size,
        "payload": {
            "instrument": item.model_dump(mode="json"),
            "configuration": config.model_dump(mode="json"),
            "confidence": {"method": config.confidence_method, "score": 50},
            "reserved_capital": "1000",
            "reserved_risk": "100",
        },
        "eligible_at": created_at,
        "expires_at": expires_at or created_at + timedelta(minutes=1),
        "created_at": created_at,
    }


def admit_direct(store, config, intent_id, created_at=NOW, expires_at=None, user=USER):
    return store.admit_order(
        user,
        pending_order(config, intent_id, created_at, expires_at),
    )


def test_v3_defaults_validation_and_v2_migration():
    config = StrategyConfig()
    assert config.strategy_version == "3.1.0"
    assert config.virtual_capital == D("20000")
    assert config.max_lots == 3 and config.max_daily_entries == 1
    assert config.candidate_strike_window == 2
    assert config.entry_after == time(10, 30)
    assert config.shadow_entry_after == time(9, 15)
    assert config.lot_score_thresholds == (D("0"), D("40"), D("70"))
    assert config.max_planned_loss == D("400")
    assert config.min_projected_net_reward == D("350")
    assert config.planned_loss_buffer == D("10")
    assert "risk_fraction" not in config.model_dump()
    with pytest.raises(ValidationError):
        StrategyConfig(lot_score_thresholds=(0, 0))
    with pytest.raises(ValidationError):
        StrategyConfig(profit_lock_floor_net=400, profit_lock_activation_net=400)
    with pytest.raises(ValidationError):
        StrategyConfig(shadow_entry_after=time(10, 31))
    assert StrategyConfig(candidate_strike_window=0).candidate_strike_window == 0
    assert StrategyConfig(candidate_strike_window=5).candidate_strike_window == 5
    with pytest.raises(ValidationError):
        StrategyConfig(candidate_strike_window=-1)
    with pytest.raises(ValidationError):
        StrategyConfig(candidate_strike_window=6)

    old = config.model_dump(mode="json")
    old.update(
        strategy_version="2.0.0",
        risk_fraction="0.005",
        max_lots=10,
        max_daily_entries=3,
        entry_after="09:30:00",
        virtual_capital="100000",
    )
    migrated = migrate_configuration(old)
    assert migrated.strategy_version == "3.1.0"
    assert migrated.max_lots == 3
    assert migrated.max_daily_entries == 1
    assert migrated.entry_after == time(10, 30)
    assert not hasattr(migrated, "risk_fraction")
    legacy = old | {"strategy_version": "1.0.0", "selection": "OTM"}
    assert migrate_configuration(legacy).strategy_version == "3.1.0"
    assert migrate_configuration(legacy).selection == "ATM"


def test_new_account_capital_and_v2_migration_preserve_funding(store):
    fresh = store.account("new-user", NOW)
    assert D(fresh["equity"]) == D("20000")
    assert D(fresh["available"]) == D("20000")

    old = StrategyConfig().model_dump(mode="json")
    old.update(strategy_version="2.0.0", risk_fraction="0.005", max_daily_entries=3)
    store.account(USER, NOW)
    with store.sessions.begin() as db:
        state = db.get(NiftyState, USER)
        state.configuration = old
        state.configuration_id = "v2"
        state.state = "RUNNING"
        funded = db.get(NiftyAccount, USER)
        funded.equity = funded.available = funded.starting_day_equity = D("100000")
    store.ensure_user(USER)
    state = store.read(USER)
    funded = store.account(USER, NOW)
    assert state["state"] == "PAUSED"
    assert state["configuration"]["strategy_version"] == "3.1.0"
    assert D(funded["equity"]) == D("100000")
    assert D(funded["available"]) == D("100000")
    with store.sessions() as db:
        history = db.get(NiftyConfiguration, (USER, state["revision"]))
        events = list(db.scalars(select(NiftyEvent).where(NiftyEvent.user_id == USER)))
    assert history.configuration["strategy_version"] == "3.1.0"
    migration = next(event for event in events if event.kind == "configuration_migration")
    assert migration.payload == {
        "from": "2.0.0",
        "to": "3.1.0",
        "revision": state["revision"],
    }


def test_v3_to_v31_migration_pauses_and_records_event(store):
    store.account(USER, NOW)
    legacy = StrategyConfig().model_dump(mode="json")
    legacy.update(strategy_version="3.0.0", selection="OTM")
    with store.sessions.begin() as db:
        state = db.get(NiftyState, USER)
        state.configuration = legacy
        state.configuration_id = "v3"
        state.state = "RUNNING"

    store.ensure_user(USER)
    state = store.read(USER)
    assert state["state"] == "PAUSED"
    assert state["configuration"]["strategy_version"] == "3.1.0"
    assert state["configuration"]["selection"] == "ATM"
    with store.sessions() as db:
        event = db.scalar(
            select(NiftyEvent).where(
                NiftyEvent.user_id == USER,
                NiftyEvent.kind == "configuration_migration",
            )
        )
    assert event.payload["from"] == "3.0.0"
    assert event.payload["to"] == "3.1.0"


@pytest.mark.parametrize(("score", "lots"), [(39, 1), (40, 2), (70, 3)])
def test_plan_entry_lot_thresholds_and_immutable_protection(score, lots):
    config = StrategyConfig().model_copy(update={"min_projected_net_reward": D("0")})
    item, quote = candidate(lot_size=25)
    quote = quote.model_copy(update={"ask": D("60"), "bid": D("59")})
    plan = plan_entry(account(), [(item, quote)], config, score, no_charges)
    assert plan.lots == lots
    assert plan.quantity == lots * item.lot_size
    expected = initial_protection(
        plan.entry_price,
        item.tick_size,
        config,
        {"score": score, "method": config.confidence_method},
    )
    assert plan.target_price == D(expected["target_price"])


def test_plan_entry_loss_and_reward_boundaries():
    config = StrategyConfig(
        max_lots=1,
        lot_score_thresholds=(D("0"),),
        slippage_ticks=0,
    )
    item, quote = candidate(lot_size=50)
    quote = quote.model_copy(update={"ask": D("90"), "bid": D("89")})
    exact_loss = plan_entry(account(), [(item, quote)], config, 100, no_charges)
    assert exact_loss.quantity == 50 and exact_loss.planned_loss == D("370")
    above_limit = config.model_copy(update={"max_planned_loss": D("369")})
    rejected_loss = plan_entry(account(), [(item, quote)], above_limit, 100, no_charges)
    assert rejected_loss.quantity == 0
    assert ("candidate", 1, "PLANNED_LOSS_LIMIT") in rejected_loss.rejections

    reward_config = config.model_copy(
        update={"max_planned_loss": D("10000"), "min_projected_net_reward": D("350")}
    )
    reward_quote = quote.model_copy(update={"ask": D("100")})
    protection = initial_protection(
        100,
        item.tick_size,
        reward_config,
        {"score": 50, "method": reward_config.confidence_method},
    )
    target = D(protection["target_price"])
    gross = (target - D("100")) * 50

    def charges(side, price, quantity, cfg):
        return D("100") if side == "BUY" or price != target else gross - D("450")

    exact_reward = plan_entry(account(), [(item, reward_quote)], reward_config, 50, charges)
    assert exact_reward.quantity == 50
    assert exact_reward.projected_net_reward == D("350")
    below = reward_config.model_copy(update={"min_projected_net_reward": D("350.0001")})
    rejected_reward = plan_entry(account(), [(item, reward_quote)], below, 50, charges)
    assert rejected_reward.quantity == 0
    assert ("candidate", 1, "NET_REWARD_BELOW_MINIMUM") in rejected_reward.rejections


def test_plan_entry_rejections_fallback_and_zero():
    config = StrategyConfig(
        max_lots=1,
        lot_score_thresholds=(D("0"),),
        slippage_ticks=0,
    )
    item, quote = candidate(lot_size=50)
    quote = quote.model_copy(update={"ask": D("90"), "bid": D("89")})
    no_funds = plan_entry(account(available="0"), [(item, quote)], config, 100, no_charges)
    assert ("candidate", 1, "INSUFFICIENT_FUNDS") in no_funds.rejections

    def reservation_charges(side, price, quantity, cfg):
        return D("10") if side == "BUY" else D("20")

    affordable = plan_entry(
        account(available="4530"),
        [(item, quote)],
        config,
        100,
        reservation_charges,
    )
    assert affordable.quantity == 50
    assert affordable.cash_required == D("4530")
    short_by_one_cent = plan_entry(
        account(available="4529.99"),
        [(item, quote)],
        config,
        100,
        reservation_charges,
    )
    assert short_by_one_cent.quantity == 0
    assert ("candidate", 1, "INSUFFICIENT_FUNDS") in short_by_one_cent.rejections

    shallow = quote.model_copy(update={"ask_size": 49})
    no_depth = plan_entry(account(), [(item, shallow)], config, 100, no_charges)
    assert ("candidate", 1, "INSUFFICIENT_DEPTH") in no_depth.rejections

    expensive, expensive_quote = candidate("expensive", lot_size=50)
    expensive_quote = expensive_quote.model_copy(update={"ask": D("1000")})
    fallback, fallback_quote = candidate("fallback", lot_size=50)
    fallback_quote = fallback_quote.model_copy(update={"ask": D("90"), "bid": D("89")})
    selected = plan_entry(
        account(),
        [(expensive, expensive_quote), (fallback, fallback_quote)],
        config,
        100,
        no_charges,
    )
    assert selected.instrument == fallback
    assert selected.quantity == 50
    invalid, invalid_quote = candidate("invalid", lot_size=1, tick_size="0.2")
    invalid_quote = invalid_quote.model_copy(
        update={"ask": D("0.2"), "bid": D("0.2"), "ltp": D("0.2")}
    )
    bad = plan_entry(account(), [(invalid, invalid_quote)], config, 50, no_charges)
    assert ("invalid", 1, "PROTECTION_TICK_INVALID") in bad.rejections
    assert plan_entry(account(), [], config, 50, no_charges).rejections[-1][2] == (
        "NO_SUITABLE_CONTRACT"
    )


def test_entry_window_is_1030_ist_and_resolver_keeps_candidate_order():
    config = StrategyConfig()
    item, item_quote = candidate()
    before = datetime(2026, 11, 19, 10, 29, 59, tzinfo=IST)
    opened = datetime(2026, 11, 19, 10, 30, tzinfo=IST)
    quote = Quote(
        token=item.token,
        source_time=opened,
        received_time=opened,
        ltp=D("130"),
        bid=D("129"),
        ask=D("130"),
        bid_size=100,
        ask_size=100,
        volume=5000,
        provider="PHASE1_TEST",
    )
    assert "ENTRY_WINDOW" in entry_reasons(
        account(), item, quote.model_copy(update={"source_time": before, "received_time": before}),
        before, config, session_open=True, data_healthy=True
    )
    assert "ENTRY_WINDOW" not in entry_reasons(
        account(), item, quote, opened, config, session_open=True, data_healthy=True
    )

    alternatives = [
        candidate("high", strike=22100),
        (item, item_quote),
        candidate("low", strike=21900),
    ]
    choices = [option for option, _quote in alternatives]
    quotes = {option.token: market_quote for option, market_quote in alternatives}
    resolver = Resolver()
    resolved = resolver.candidates(choices, quotes, 22000, "CE", NOW, config)
    assert resolved[0] == item
    assert resolver.resolve(choices, quotes, 22000, "CE", NOW, config) == item


def test_resolver_candidate_window_preserves_selection_and_delta_order():
    strike_options = [
        candidate(f"strike-{strike}", strike=strike)
        for strike in (22100, 21900, 22150, 22000, 22050, 21950, 22200)
    ]
    instruments = [contract for contract, _quote in strike_options]
    quotes = {contract.token: quote for contract, quote in strike_options}
    resolver = Resolver()
    expected = {
        "ATM": [22000, 21950, 21900],
        "ITM": [21950, 22000, 21900],
    }
    for selection, strikes in expected.items():
        config = StrategyConfig(selection=selection)
        actual = resolver.candidates(instruments, quotes, 22000, "CE", NOW, config)
        assert [contract.strike for contract in actual] == strikes

    only_selected = StrategyConfig(candidate_strike_window=0)
    actual = resolver.candidates(instruments, quotes, 22000, "CE", NOW, only_selected)
    assert [contract.strike for contract in actual] == [22000]
    only_itm = StrategyConfig(selection="ITM", candidate_strike_window=0)
    actual = resolver.candidates(instruments, quotes, 22000, "CE", NOW, only_itm)
    assert [contract.strike for contract in actual] == [21950]

    delta_options = []
    for token, strike, delta in (
        ("delta-60", 21950, 0.6),
        ("delta-50", 22000, 0.5),
        ("delta-40", 22050, 0.4),
        ("delta-70", 22100, 0.7),
    ):
        contract, quote = candidate(token, strike=strike)
        delta_options.append(
            (
                contract.model_copy(update={"delta": delta, "delta_time": NOW}),
                quote,
            )
        )
    delta_instruments = [contract for contract, _quote in delta_options]
    delta_quotes = {contract.token: quote for contract, quote in delta_options}
    delta_config = StrategyConfig(selection="DELTA", candidate_strike_window=1)
    assert [
        contract.token
        for contract in resolver.candidates(
            delta_instruments, delta_quotes, 22000, "CE", NOW, delta_config
        )
    ] == ["delta-50", "delta-60"]
    delta_single = delta_config.model_copy(update={"candidate_strike_window": 0})
    assert [
        contract.token
        for contract in resolver.candidates(
            delta_instruments, delta_quotes, 22000, "CE", NOW, delta_single
        )
    ] == ["delta-50"]


@pytest.mark.parametrize(
    ("side", "spot", "atm", "itm", "otm"),
    [
        ("CE", D("22040"), D("22050"), D("22000"), D("22100")),
        ("PE", D("22040"), D("22050"), D("22100"), D("22000")),
    ],
)
def test_resolver_never_returns_otm_and_window_counts_itm_strikes(
    side, spot, atm, itm, otm
):
    options = [
        candidate(f"{side}-{strike}", strike=strike)[0].model_copy(update={"kind": side})
        for strike in (D("21900"), D("22000"), D("22050"), D("22100"), D("22150"))
    ]
    quotes = {
        option.token: Quote(
            token=option.token, source_time=NOW, received_time=NOW, bid=D("129"),
            ask=D("130"), bid_size=1000, ask_size=1000, volume=5000,
            provider="PHASE1_TEST"
        )
        for option in options
    }
    resolver = Resolver()
    result = resolver.candidates(
        options, quotes, spot, side, NOW, StrategyConfig(candidate_strike_window=1)
    )
    assert all(contract.strike != otm for contract in result)
    assert result[0].strike == atm
    assert itm in [contract.strike for contract in result]
    assert len([contract for contract in result if contract.strike != atm]) == 1

    for window in (-1, 6):
        with pytest.raises(ValidationError):
            StrategyConfig(candidate_strike_window=window)


@pytest.mark.parametrize(
    ("side", "atm", "itm"),
    [("CE", 22050, 22000), ("PE", 22050, 22100)],
)
def test_resolver_zero_window_keeps_only_atm_or_selected_itm(side, atm, itm):
    options = [
        candidate(f"{side}-{strike}", strike=strike)[0].model_copy(update={"kind": side})
        for strike in (21900, 22000, 22050, 22100, 22150)
    ]
    quotes = {
        option.token: Quote(
            token=option.token, source_time=NOW, received_time=NOW, bid=D("129"),
            ask=D("130"), bid_size=1000, ask_size=1000, volume=5000,
            provider="PHASE1_TEST",
        )
        for option in options
    }
    resolver = Resolver()
    assert [
        option.strike
        for option in resolver.candidates(
            options, quotes, D("22040"), side, NOW,
            StrategyConfig(candidate_strike_window=0),
        )
    ] == [atm]
    assert [
        option.strike
        for option in resolver.candidates(
            options, quotes, D("22040"), side, NOW,
            StrategyConfig(selection="ITM", candidate_strike_window=0),
        )
    ] == [itm]


def test_v3_otm_migration_maps_selection_to_atm():
    migrated = migrate_configuration(
        {"strategy_version": "3.0.0", "selection": "OTM"}
    )
    assert migrated.strategy_version == "3.1.0"
    assert migrated.selection == "ATM"


def test_buy_admission_rejects_otm_candidates(store):
    config = active_config(store)
    exe = executor(store, config=config)
    contract = instrument().model_copy(update={"strike": 22100})
    with pytest.raises(OrderRefused) as refused:
        exe.admit(
            buy_intent(
                instrument=contract,
                candidate_metadata=[
                    {
                        "token": contract.token,
                        "moneyness": "OTM",
                        "spot_reference": "21900",
                        "atm_strike": "22000",
                    }
                ]
            )
        )
    assert refused.value.reasons == ["OTM_PROHIBITED"]


def test_unapproved_calendar_blocks_buy_but_not_position_exit(store):
    config = active_config(store)
    exe = executor(store, config=config)
    exe.admit(buy_intent())
    assert exe.process(NOW + timedelta(seconds=1))[0]["status"] == "FILLED"
    with store.sessions.begin() as db:
        db.execute(delete(NiftyCalendarVersion).where(NiftyCalendarVersion.user_id == USER))

    with pytest.raises(OrderRefused) as refused:
        exe.admit(buy_intent(intent_id="unapproved-buy"), now=NOW + timedelta(seconds=2))
    assert refused.value.reasons == ["CALENDAR_UNAPPROVED"]
    assert exe.monitor_exits(
        now=NOW + timedelta(seconds=3),
        operator_close=True,
    )
    assert any(order["side"] == "SELL" for order in store.pending_orders(USER))


def test_daily_entry_admission_pending_expired_and_concurrent(store):
    config = active_config(store)
    admit_direct(store, config, "first")
    with pytest.raises(OrderRefused) as refused:
        admit_direct(store, config, "pending-second")
    assert "DAILY_ENTRY_USED" in refused.value.reasons

    store.expire_pending(USER, NOW + timedelta(minutes=2))
    admitted, created = admit_direct(
        store, config, "after-expiry", NOW + timedelta(minutes=2)
    )
    assert created and admitted["intent_id"] == "after-expiry"
    assert [order["intent_id"] for order in store.pending_orders(USER)] == ["after-expiry"]


def test_one_daily_buy_after_fill_closed_and_concurrent_writers(store):
    config = active_config(store)
    running(store, USER)
    exe = executor(store, config=config)
    exe.admit(buy_intent())
    assert exe.process(NOW + timedelta(seconds=1))[0]["status"] == "FILLED"
    exe.admit(buy_intent(intent_id="close", side="SELL"))
    assert exe.process(NOW + timedelta(seconds=2))[0]["status"] == "FILLED"
    assert not store.positions(USER)
    with store.sessions.begin() as db:
        db.get(NiftyAccount, USER).daily_entries = 0
    with pytest.raises(OrderRefused) as refused:
        admit_direct(store, config, "after-close")
    assert "DAILY_ENTRY_USED" in refused.value.reasons

    race_user = "nifty-race-user"
    active_config(store, config, race_user)

    def submit(index):
        try:
            _, created = admit_direct(
                store, config, f"race-{index}", user=race_user
            )
            return "ADMITTED" if created else "DUPLICATE"
        except OrderRefused as error:
            return error.reasons

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, range(2)))
    assert outcomes.count("ADMITTED") == 1
    assert sum(isinstance(result, list) for result in outcomes) == 1
    assert "DAILY_ENTRY_USED" in next(result for result in outcomes if isinstance(result, list))


def test_pending_expiry_cap_fill_cutoff_and_no_broker_transmission(store, monkeypatch):
    spy = Mock(side_effect=AssertionError("paper orders must not be transmitted"))
    monkeypatch.setitem(
        sys.modules, "services.place_order_service", SimpleNamespace(place_order=spy)
    )
    monkeypatch.setitem(
        sys.modules,
        "services.place_smart_order_service",
        SimpleNamespace(place_smart_order=spy),
    )
    config = active_config(store, StrategyConfig(latency_ms=1, order_ttl_seconds=60))
    cutoff = datetime(2026, 11, 19, 9, 15, tzinfo=UTC)
    at = cutoff - timedelta(seconds=5)
    store.record_decision(
        USER,
        {
            "decision_id": "d-cutoff",
            "eligible": True,
            "side": "CE",
            "config_id": config.version_id,
            "timestamp": at.isoformat(),
            "confidence": {"method": config.confidence_method, "score": 100},
        },
    )
    exe = executor(store, config=config, market=FakeMarket(stamp=at))
    order, _ = exe.admit(
        buy_intent(intent_id="cutoff", decision_id="d-cutoff"),
        now=at,
    )
    assert order["expires_at"] == cutoff
    assert D(order["payload"]["reserved_capital"]) == D(
        order["payload"]["sizing_plan"]["cash_required"]
    )
    expired = store.fill(
        USER,
        order["order_id"],
        D("130.05"),
        _charges("BUY", D("130.05"), order["quantity"], config),
        cutoff,
    )
    assert expired["status"] == "EXPIRED"
    assert expired["reason"] == "ENTRY_CUTOFF"
    spy.assert_not_called()
