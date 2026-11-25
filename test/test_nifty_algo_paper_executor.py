"""Phase 6 — isolated NIFTY paper execution: strict fills, costs, idempotency."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyState, NiftyStore
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.contract_resolver import moneyness
from services.nifty_algo.models import Instrument
from services.nifty_algo.paper_executor import (
    NiftyPaperExecutor,
    OrderRefused,
    PaperExecutionUnavailable,
)
from test.nifty_calendar_helpers import seed_approved_nfo_calendar, seed_market_timing

NOW = datetime(2026, 11, 19, 5, 0, tzinfo=UTC)  # 10:30 IST, entry window opens
USER = "trader"
IST = ZoneInfo("Asia/Kolkata")


def _paper_test_config(config=None):
    # Persisted and payload-embedded configurations are revalidated at every
    # boundary (ensure_user, admit_order, fill), so fixtures must stay inside
    # the production bounds; the ~165 premium satisfies the real risk envelope.
    return config or StrategyConfig()


@pytest.fixture
def store(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'feature.db'}")
    store = NiftyStore(engine)
    store.initialize()
    yield store
    engine.dispose()


@pytest.fixture(autouse=True)
def market_calendar():
    seed_market_timing()


class FakeMarket:
    """Minimal stand-in for the cached market-data service."""

    def __init__(
        self,
        bid="164",
        ask="165",
        ltp="164.5",
        index_ltp="22000",
        volume=5000,
        size=100,
        stamp=None,
    ):
        self.bid = bid
        self.ask = ask
        self.ltp = ltp
        self.index_ltp = index_ltp
        self.volume = volume
        self.size = size
        self.stamp = stamp if stamp is not None else NOW

    def get_all_data(self, symbol, exchange):
        if symbol == "NIFTY" or exchange == "NSE_INDEX":
            return {
                "source_observations": {
                    "2": {
                        "ltp": float(self.index_ltp),
                        "ltt": self.stamp,
                        "received_time": self.stamp,
                    }
                }
            }
        depth = {}
        if self.bid is not None:
            depth["buy"] = [{"price": float(self.bid), "quantity": self.size}]
        if self.ask is not None:
            depth["sell"] = [{"price": float(self.ask), "quantity": self.size}]
        depth["ltt"] = self.stamp
        depth["quote_time"] = self.stamp
        return {
            "depth": depth,
            "ltp": float(self.ltp),
            "volume": self.volume,
            "last_update": self.stamp,
        }


def instrument():
    return Instrument(
        token="token-ce",
        symbol="TEST_CONTRACT",
        exchange="NFO",
        kind="CE",
        expiry=date(2026, 11, 24),
        strike=22000,
        lot_size=25,
        tick_size=Decimal("0.05"),
        master_date=NOW.date(),
    )


def buy_intent(intent_id="i-1", **extra):
    contract = extra.get("instrument", instrument())
    candidate_list = extra.get("candidates") or [contract]
    spot_reference = extra.get("spot_reference", contract.strike)
    atm_strike = extra.get("atm_strike", contract.strike)
    payload = {
        "intent_id": intent_id,
        "side": "BUY",
        "symbol": contract.symbol,
        "token": contract.token,
        "instrument": contract,
        "candidates": candidate_list,
        "candidate_metadata": [
            {
                "token": candidate.token,
                "moneyness": moneyness(candidate, spot_reference, atm_strike),
                "spot_reference": str(spot_reference),
                "atm_strike": str(atm_strike),
            }
            for candidate in candidate_list
        ],
        "decision_id": "d-1",
    }
    payload.update(extra)
    return payload


def listed(*extra):
    """Dated-master fixture: the verified chain the fixture contract is listed in.

    Admission and fill revalidate moneyness against current master evidence, so
    an executor needs one. Tests that admit other contracts list them here.
    """
    return lambda now: [instrument(), *extra]


def executor(store, market=None, config=None, clock=None, master=None):
    # Explicit offline qualifying-decision fixture; never real indicator evidence.
    config = _paper_test_config(config)
    store.ensure_user(USER)
    seed_approved_nfo_calendar(store, USER, NOW.astimezone(IST).year)
    if not store.orders(USER, now=NOW):
        with store.sessions.begin() as db:
            state = db.get(NiftyState, USER)
            state.configuration = config.model_dump(mode="json")
            state.configuration_id = config.version_id
    store.record_decision(
        USER,
        {
            "decision_id": "d-1",
            "eligible": True,
            "side": "CE",
            "config_id": config.version_id,
            "timestamp": NOW.isoformat(),
            "confidence": {"method": config.confidence_method, "score": 50},
        },
    )
    return NiftyPaperExecutor(
        store=store,
        user_id=USER,
        config=config,
        market_data=market or FakeMarket(),
        clock=clock or (lambda: NOW),
        session_reader=lambda day, exchange: {
            "start_ms": NOW.replace(hour=3, minute=45).timestamp() * 1000,
            "end_ms": NOW.replace(hour=10, minute=0).timestamp() * 1000,
        },
        master=master or listed(),
    )


def running(store, user=USER):
    store.ensure_user(user)
    with store.sessions.begin() as db:
        db.get(NiftyState, user).state = "RUNNING"


def test_generic_submit_boundary_stays_closed(store):
    with pytest.raises(PaperExecutionUnavailable):
        executor(store).submit({"anything": True})


def test_buy_admitted_pending_once(store):
    running(store)
    order, created = executor(store).admit(buy_intent())
    assert created is True
    assert order["side"] == "BUY"
    assert order["quantity"] >= 25
    assert store.pending_orders(USER)[0]["status"] == "PENDING"

    again, created_again = executor(store).admit(buy_intent())
    assert created_again is False
    assert again["order_id"] == order["order_id"]
    assert len(store.pending_orders(USER)) == 1
    admissions = [row for row in store.events(USER) if row["kind"] == "paper_intent_admitted"]
    assert len(admissions) == 1
    assert admissions[0]["payload"]["risk_approval"]["approved"]


def test_entries_refused_when_not_running(store):
    store.ensure_user(USER)
    with pytest.raises(OrderRefused):
        executor(store).admit(buy_intent())


def test_stale_or_missing_depth_refuses_admission(store):
    running(store)
    stale = FakeMarket(stamp=NOW - timedelta(seconds=60))
    with pytest.raises(OrderRefused):
        executor(store, market=stale).admit(buy_intent())

    no_ask = FakeMarket(ask=None)
    with pytest.raises(OrderRefused):
        executor(store, market=no_ask).admit(buy_intent())


def test_buy_fills_at_ask_plus_slippage(store):
    running(store)
    exe = executor(store, config=StrategyConfig(latency_ms=1))
    order, _ = exe.admit(buy_intent())
    fills = exe.process(now=NOW + timedelta(seconds=1))
    assert len(fills) == 1
    fill = fills[0]
    assert fill["status"] == "FILLED"
    expected = Decimal("165") + exe._slippage(instrument())
    assert Decimal(fill["price"]) == expected

    positions = store.positions(USER)
    assert len(positions) == 1
    assert positions[0]["token"] == "token-ce"

    account = store.account(USER)
    cost = (expected * fill["quantity"] + Decimal(fill["fees"])).quantize(Decimal("0.0001"))
    assert Decimal(account["available"]) == Decimal("20000") - cost


def test_fill_is_idempotent(store):
    running(store)
    exe = executor(store, config=StrategyConfig(latency_ms=1))
    order, _ = exe.admit(buy_intent())
    exe.process(now=NOW + timedelta(seconds=1))
    available_after = Decimal(store.account(USER)["available"])

    store.fill(USER, order["order_id"], Decimal("165"), Decimal("10"), NOW)
    assert Decimal(store.account(USER)["available"]) == available_after
    assert len(store.positions(USER)) == 1


def test_sell_fills_at_bid_and_journals_trade(store):
    running(store)
    exe = executor(store, config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    exe.process(now=NOW + timedelta(seconds=1))

    sell, _ = exe.admit(buy_intent(intent_id="i-2", side="SELL", exit_reason="TARGET_HIT"))
    fills = exe.process(now=NOW + timedelta(seconds=2))
    fill = fills[0]
    assert fill["status"] == "FILLED"
    expected = Decimal("164") - exe._slippage(instrument())
    assert Decimal(fill["price"]) == expected

    assert store.positions(USER) == []
    trades = store.trades(USER)
    assert len(trades) == 1
    trade = trades[0]
    assert Decimal(trade["fees"]) > Decimal("0")
    assert Decimal(trade["net"]) == Decimal(trade["gross"]) - Decimal(trade["fees"])


def test_uncovered_sell_refused(store):
    running(store)
    with pytest.raises(OrderRefused) as err:
        executor(store).admit(buy_intent(side="SELL"))
    assert "UNCOVERED_SELL" in str(err.value)


def test_pending_waits_for_eligibility(store):
    running(store)
    exe = executor(store, config=StrategyConfig(latency_ms=500))
    order, _ = exe.admit(buy_intent())
    fills = exe.process(now=NOW + timedelta(milliseconds=100))
    assert fills == []
    assert store.orders(USER, now=NOW + timedelta(milliseconds=100))[0]["status"] == "PENDING"

    fills = exe.process(now=NOW + timedelta(seconds=1))
    assert fills[0]["status"] == "FILLED"


def test_order_expires_after_ttl(store):
    running(store)
    exe = executor(store, config=StrategyConfig(latency_ms=1, order_ttl_seconds=5))
    exe.admit(buy_intent())
    fills = exe.process(now=NOW + timedelta(seconds=6))
    assert fills == []
    assert store.orders(USER, now=NOW + timedelta(seconds=6))[0]["status"] == "EXPIRED"


def test_reconcile_recovers_durable_state(store):
    running(store)
    exe = executor(store, config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    exe.process(now=NOW + timedelta(seconds=1))

    recovered = executor(store, config=StrategyConfig())
    report = recovered.reconcile(now=NOW + timedelta(seconds=2))
    assert report["account"]["reconciled"] is True
    assert len(report["positions"]) == 1
    assert report["pending"] == []


def test_reconcile_expires_dead_intents(store):
    running(store)
    exe = executor(store, config=StrategyConfig(latency_ms=1, order_ttl_seconds=5))
    exe.admit(buy_intent())
    report = exe.reconcile(now=NOW + timedelta(seconds=6))
    assert report["pending"] == []
    assert store.orders(USER, now=NOW + timedelta(seconds=6))[0]["status"] == "EXPIRED"


def test_accounts_isolated_per_user(store):
    running(store)
    running(store, user="other")
    exe = executor(store, config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    exe.process(now=NOW + timedelta(seconds=1))

    assert Decimal(store.account("other")["equity"]) == Decimal("20000")
    assert store.positions("other") == []
    assert Decimal(store.account(USER)["equity"]) < Decimal("20000")


def test_daily_rollover_resets_counters(store):
    running(store)
    account = store.account(USER, now=NOW)
    next_day = store.account(USER, now=NOW + timedelta(days=1))
    assert next_day["daily_entries"] == 0
    assert Decimal(next_day["realized_day"]) == Decimal("0")
    assert Decimal(next_day["starting_day_equity"]) == Decimal(account["equity"])


def test_performance_report_shape(store):
    running(store)
    exe = executor(store, config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    exe.process(now=NOW + timedelta(seconds=1))
    perf = store.performance(USER)
    assert isinstance(perf, dict)
