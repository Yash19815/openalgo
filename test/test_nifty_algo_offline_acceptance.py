"""Offline PAPER acceptance for the NIFTY feature (no broker, feed, key or order).

Every dependency is a deterministic fake: synthetic candles, synthetic options,
simulated depth, a fake clock and an isolated SQLite file per test. The module
installs two guards for its whole run: any import of a broker, shared Sandbox or
generic order service raises, and any attempt to open a network connection
raises. A test therefore cannot pass by quietly reaching a real service.

What this suite does and does not establish
-------------------------------------------
It shows that the PAPER ledger, risk gates, session rules, data-rejection paths
and restart recovery behave as documented for these synthetic inputs. It says
nothing about profitability, about how a real Angel One feed behaves, or about
real-market fills. See ``docs/nifty-algo/OFFLINE_ACCEPTANCE_2026-11.md``.

The MACD crossover freshness boundary (``cross_age <= 3``) is deliberately not
touched here; it is an open interpretation question owned elsewhere.
"""

import ast
import builtins
import socket
import sys
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from database.nifty_algo_db import (
    NiftyEvent,
    NiftyMode,
    NiftyMonth,
    NiftyOrder,
    NiftyState,
    NiftyStore,
    NiftyTrade,
)
from services.nifty_algo import calendar as nifty_calendar
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.contract_resolver import Resolver, SelectionUnavailable, current_moneyness
from services.nifty_algo.depth_quote import depth_quote
from services.nifty_algo.models import Instrument, Quote
from services.nifty_algo.native_data import NativeDataAdapter
from services.nifty_algo.paper_executor import NiftyPaperExecutor, OrderRefused, _charges
from services.nifty_algo.protection import mandatory_exit_reason
from services.nifty_algo.risk_manager import AccountRisk, plan_entry
from services.nifty_algo.trading_mode import (
    LIVE_ADAPTER,
    LIVE_NOT_READY,
    live_readiness,
    request_mode,
)
from test.nifty_calendar_helpers import seed_approved_nfo_calendar
from test.test_nifty_algo_paper_executor import market_calendar as market_calendar
from test.test_nifty_algo_paper_executor import store as store

IST = ZoneInfo("Asia/Kolkata")
D = Decimal
USER = "acceptance"
OTHER = "acceptance-other"

THU, FRI, SAT, MON = date(2026, 11, 19), date(2026, 11, 20), date(2026, 11, 21), date(2026, 11, 23)
EXPIRY = date(2026, 11, 24)  # Tuesday; expiry day itself is avoided by default


def ist(day, hour, minute, second=0, micro=0):
    return datetime(
        day.year, day.month, day.day, hour, minute, second, micro, tzinfo=IST
    ).astimezone(UTC)


# --- guards: nothing reaches a broker, the shared Sandbox or the network -------

FORBIDDEN_MODULES = (
    "broker",
    "sandbox",
    "database.sandbox_db",
    "services.sandbox_service",
    "services.place_order_service",
    "services.place_smart_order_service",
    "services.place_options_order_service",
    "services.options_multiorder_service",
    "services.basket_order_service",
    "services.split_order_service",
    "services.modify_order_service",
    "services.cancel_order_service",
    "services.cancel_all_order_service",
    "services.close_position_service",
    "services.order_router_service",
    "services.place_gtt_order_service",
)
FORBIDDEN_CALLS = {
    "place_order",
    "place_smart_order",
    "place_options_order",
    "cancel_order",
    "cancel_all_orders",
    "modify_order",
    "close_position",
}


def _forbidden(name):
    return any(name == root or name.startswith(root + ".") for root in FORBIDDEN_MODULES)


@pytest.fixture(autouse=True)
def offline_guard(monkeypatch):
    real_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0:
            names = [name] + [f"{name}.{item}" for item in (fromlist or ()) if item != "*"]
            for candidate in names:
                if _forbidden(candidate):
                    raise AssertionError(f"PAPER code reached a forbidden service: {candidate}")
        return real_import(name, globals, locals, fromlist, level)

    def no_network(*args, **kwargs):
        raise AssertionError("PAPER acceptance attempted a network connection")

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)


# --- synthetic world -----------------------------------------------------------


def contract(day, strike=22000, kind="CE", *, lot_size=25, expiry=EXPIRY):
    return Instrument(
        token=f"{kind.lower()}-{strike}",
        symbol=f"SYNTH{strike}{kind}",
        exchange="NFO",
        kind=kind,
        expiry=expiry,
        strike=strike,
        lot_size=lot_size,
        tick_size=D("0.05"),
        master_date=day,
    )


class Feed:
    """Cached market-data stand-in: one mode-3 depth snapshot per option, spot on mode 2."""

    def __init__(self, stamp, *, spot="22000", bid="164.00", ask="165.00", size=100, volume=5000):
        self.stamp, self.spot, self.spot_stamp = stamp, spot, None
        self.bid, self.ask, self.size, self.volume, self.oi = bid, ask, size, volume, 5000
        self.received = None  # defaults to the source time
        self.overrides = {}

    def get_all_data(self, symbol, exchange):
        if exchange == "NSE_INDEX":
            if self.spot is None:
                return {}
            stamp = self.spot_stamp or self.stamp
            return {
                "source_observations": {
                    "2": {"ltp": float(self.spot), "ltt": stamp, "received_time": stamp}
                }
            }
        depth = {}
        if self.bid is not None:
            depth["buy"] = [{"price": str(self.bid), "quantity": self.size}]
        if self.ask is not None:
            depth["sell"] = [{"price": str(self.ask), "quantity": self.size}]
        raw = {
            "symbol": symbol,
            "exchange": exchange,
            "ltt": self.stamp,
            "received_time": self.received or self.stamp,
            "depth": depth,
            "ltp": str(self.ask or self.bid or "100"),
            "volume": self.volume,
            "oi": self.oi,
        }
        raw.update(self.overrides.get(symbol, {}))
        return {"source_observations": {"3": raw}}


class Desk:
    """One user's PAPER account driven through the real executor and store."""

    STRIKES = (21900, 21950, 22000, 22050, 22100)

    def __init__(
        self,
        store,
        user=USER,
        *,
        config=None,
        feed=None,
        holidays=(),
        session_close=time(15, 40),
        calendar=True,
    ):
        self.store, self.user = store, user
        self.config = config or StrategyConfig()
        store.ensure_user(user)
        if calendar:
            seed_approved_nfo_calendar(store, user, 2026, list(holidays))
        if config is not None:
            with store.sessions.begin() as db:
                state = db.get(NiftyState, user)
                state.configuration = self.config.model_dump(mode="json")
                state.configuration_id = self.config.version_id
        self.feed = feed or Feed(ist(THU, 10, 30))
        self.now = self.feed.stamp
        self.session_close = session_close
        self.seq = 0
        self.exe = NiftyPaperExecutor(
            store=store,
            user_id=user,
            config=self.config,
            market_data=self.feed,
            clock=lambda: self.now,
            session_reader=self._session,
            master=self._master,
        )

    def _session(self, day, exchange):
        return {
            "start_ms": ist(day, 9, 15).timestamp() * 1000,
            "end_ms": ist(day, self.session_close.hour, self.session_close.minute).timestamp()
            * 1000,
        }

    def _master(self, now):
        day = now.astimezone(IST).date()
        return [contract(day, s, k) for k in ("CE", "PE") for s in self.STRIKES]

    def stamp(self, when):
        self.feed.stamp = self.now = when
        return when

    def running(self):
        with self.store.sessions.begin() as db:
            db.get(NiftyState, self.user).state = "RUNNING"

    def intent(self, when, *, strike=22000, kind="CE", score=50, tag=None):
        self.seq += 1
        tag = tag or f"{self.seq}"
        self.store.record_decision(
            self.user,
            {
                "decision_id": f"d-{tag}",
                "eligible": True,
                "side": kind,
                "config_id": self.config.version_id,
                "timestamp": when.isoformat(),
                "confidence": {"method": self.config.confidence_method, "score": score},
            },
        )
        item = contract(when.astimezone(IST).date(), strike, kind)
        return {
            "intent_id": f"i-{tag}",
            "decision_id": f"d-{tag}",
            "side": "BUY",
            "symbol": item.symbol,
            "token": item.token,
            "instrument": item,
            "candidates": [item],
        }

    def buy(self, when, **kwargs):
        self.stamp(when)
        order, created = self.exe.admit(self.intent(when, **kwargs), when)
        assert created
        return order

    def process(self, when):
        self.stamp(when)
        return self.exe.process(when)

    def enter(self, when, **kwargs):
        """Admit and fill one entry a second later; returns the filled order row."""
        order = self.buy(when, **kwargs)
        fills = self.process(when + timedelta(seconds=1))
        assert [row["status"] for row in fills] == ["FILLED"], fills
        return next(row for row in fills if row["order_id"] == order["order_id"])

    def leave(self, when, bid, reason="TARGET_HIT"):
        """Request the exit and fill it a second later at the given best bid."""
        self.feed.bid, self.feed.ask = str(bid), str(D(str(bid)) + D("0.50"))
        self.stamp(when)
        held = self.store.positions(self.user)[0]
        self.seq += 1
        self.exe.admit(
            {
                "intent_id": f"x-{self.seq}",
                "side": "SELL",
                "symbol": held["symbol"],
                "token": held["token"],
                "instrument": held["instrument"],
                "quantity": held["quantity"],
                "exit_reason": reason,
            },
            when,
        )
        return self.process(when + timedelta(seconds=1))


@pytest.fixture
def desk(store):
    value = Desk(store)
    value.running()
    return value


def snapshot(store, user=USER, now=None):
    """Everything the ledger says about one user, for before/after comparisons."""
    now = now or ist(THU, 12, 0)
    account = store.account(user, now)
    account.pop("updated_at")
    for key in ("equity", "available", "starting_day_equity", "realized_day"):
        account[key] = D(account[key])  # '20000' on creation, '20000.0000' once read back
    return {
        "account": account,
        "positions": [(p["token"], p["quantity"], p["entry_price"]) for p in store.positions(user)],
        "pending": [o["order_id"] for o in store.pending_orders(user)],
        "trades": [(t["entry_order_id"], t["net"]) for t in store.trades(user)],
    }


def sized(ask, score, *, available=D("20000")):
    """The pure sizing decision for one synthetic quote (no ledger, no I/O)."""
    now = ist(THU, 10, 31)
    ask = D(str(ask))
    bid = (ask * D("0.995") / D("0.05")).to_integral_value(rounding=ROUND_FLOOR) * D("0.05")
    item = contract(THU)
    quote = Quote(
        token=item.token,
        source_time=now,
        received_time=now,
        ltp=ask,
        bid=bid,
        ask=ask,
        bid_size=1000,
        ask_size=1000,
        volume=5000,
        oi=5000,
        provider="native_depth",
    )
    risk = AccountRisk(available, available, available, reconciled=True, entries_enabled=True)
    return plan_entry(risk, [(item, quote)], StrategyConfig(), score, _charges, now=now)


# =============================================================================
# 1. PAPER execution isolation
# =============================================================================

NIFTY_SOURCES = (
    sorted(Path("services/nifty_algo").glob("*.py"))
    + sorted(Path("database").glob("nifty_*.py"))
    + sorted(Path("blueprints").glob("nifty_*.py"))
)


def test_the_nifty_sources_to_scan_were_found():
    assert len(NIFTY_SOURCES) >= 30  # a wrong working directory must not pass vacuously


@pytest.mark.parametrize("path", NIFTY_SOURCES, ids=lambda path: path.as_posix())
def test_no_nifty_source_imports_or_calls_a_broker_sandbox_or_order_service(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported, called = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.append(node.module or "")
            imported.extend(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            target = node.func
            called.append(
                target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
            )
            # Dynamic imports would bypass the static scan above.
            if called[-1] in ("import_module", "__import__") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    imported.append(first.value)
    assert not [name for name in imported if _forbidden(name)], path
    assert not FORBIDDEN_CALLS.intersection(called), path


def test_the_runtime_guard_is_not_vacuous():
    with pytest.raises(AssertionError, match="forbidden service"):
        __import__("services.place_order_service")
    with pytest.raises(AssertionError, match="forbidden service"):
        __import__("services", fromlist=["place_smart_order_service"])
    with pytest.raises(AssertionError, match="network"):
        socket.create_connection(("127.0.0.1", 9))


def test_live_adapter_stub_refuses_and_live_readiness_is_never_empty():
    assert LIVE_ADAPTER.reachable() is False
    with pytest.raises(OrderRefused) as refusal:
        LIVE_ADAPTER.submit({"anything": True})
    assert refusal.value.reasons == [LIVE_NOT_READY] == ["LIVE_NOT_READY"]
    # The most favourable status a caller can construct still cannot clear Live.
    perfect = {
        "available": True,
        "api_key_configured": True,
        "openalgo_api_key_configured": True,
        "auth_token_present": True,
        "revoked": False,
        "session_current": True,
    }
    codes = live_readiness(perfect, {"positions": 0, "pending_orders": 0}, acknowledged=True)
    assert codes and LIVE_NOT_READY in codes
    assert not [name for name in vars(LIVE_ADAPTER) if "client" in name or "session" in name]


def test_a_live_mode_request_is_refused_and_the_account_stays_paper(store):
    store.ensure_user(USER)
    facts = {
        "broker": "angel",
        "broker_name": "Angel One",
        "auth": "token-present",
        "feed_token": "feed-present",
        "revoked": False,
        "session_current": True,
        "keys": SimpleNamespace(api_key="k", api_secret="s", source="env"),
        "openalgo_api_key": True,
    }
    revision = store.trading_mode(USER)["revision"]
    mode, codes, changed = request_mode(
        store, USER, revision, "LIVE", acknowledged=True, actor=USER, reader=lambda user: facts
    )
    assert changed is False and LIVE_NOT_READY in codes
    assert store.trading_mode(USER)["mode"] == "PAPER"


def test_a_corrupted_live_mode_row_still_cannot_open_a_position_but_can_close_one(desk, store):
    desk.enter(ist(THU, 10, 30))
    assert len(store.positions(USER)) == 1
    with store.sessions.begin() as db:
        db.get(NiftyMode, USER).mode = "LIVE"  # state that no supported path can create
    # No fallback to any live adapter: a new entry is refused outright ...
    with pytest.raises(OrderRefused) as refusal:
        desk.buy(ist(THU, 10, 40))
    assert refusal.value.reasons == ["LIVE_NOT_READY"]
    # ... even when the executor is bypassed and the ledger is asked directly.
    pending_before = store.pending_orders(USER)
    assert pending_before == []
    # ... while the paper position can still be closed by simulation.
    fills = desk.leave(ist(THU, 10, 50), "170.00")
    assert [row["status"] for row in fills] == ["FILLED"] and store.positions(USER) == []


def test_accounts_do_not_share_orders_positions_locks_or_fills(store):
    one, two = Desk(store, USER), Desk(store, OTHER)
    one.running(), two.running()
    order = one.enter(ist(THU, 10, 30))
    # The other account is untouched and can still take its own single entry.
    assert snapshot(store, OTHER)["positions"] == []
    assert D(store.account(OTHER)["equity"]) == D("20000")
    assert two.enter(ist(THU, 10, 31))["order_id"] != order["order_id"]
    # A fill, an exit and a position are only ever addressed by (user, id).
    with pytest.raises(Exception):  # noqa: B017 - any refusal; the point is no state change
        store.fill(OTHER, order["order_id"], D("165.05"), D("1"), ist(THU, 10, 32))
    assert len(store.positions(USER)) == len(store.positions(OTHER)) == 1
    token = store.positions(USER)[0]["token"]
    held = store.positions(USER)[0]
    with pytest.raises(OrderRefused) as refusal:
        Desk(store, "stranger").exe.admit(
            {
                "intent_id": "x",
                "side": "SELL",
                "symbol": held["symbol"],
                "token": token,
                "instrument": held["instrument"],
                "quantity": held["quantity"],
            },
            ist(THU, 10, 40),
        )
    assert refusal.value.reasons == ["UNCOVERED_SELL"]
    # One account's monthly lock does not lock the other.
    one.leave(ist(THU, 10, 45), "151.85", "INITIAL_STOP")
    assert store.entry_locks(USER, ist(MON, 10, 30), one.config) == []  # window passed, no breach
    _seed_loss(store, "-2000", ist(THU, 9, 30))
    assert "MONTHLY_LOSS_LOCK" in store.entry_locks(USER, ist(MON, 10, 30), one.config)
    assert "MONTHLY_LOSS_LOCK" not in store.entry_locks(OTHER, ist(MON, 10, 30), two.config)


def test_nifty_ledger_tables_are_disjoint_from_the_shared_sandbox(store):
    import os

    from database.nifty_algo_db import Base

    # Read the Sandbox schema as text: importing it is exactly what must not happen.
    tree = ast.parse(Path("database/sandbox_db.py").read_text(encoding="utf-8"))
    sandbox_tables = {
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(getattr(target, "id", "") == "__tablename__" for target in node.targets)
        and isinstance(node.value, ast.Constant)
    }
    nifty_tables = set(Base.metadata.tables)
    assert sandbox_tables and nifty_tables
    assert all(name.startswith("nifty_algo_") for name in nifty_tables)
    assert not any(name.startswith("nifty_algo_") for name in sandbox_tables)
    assert not nifty_tables & sandbox_tables
    assert str(store.engine.url) != os.environ["SANDBOX_DATABASE_URL"]


def test_paper_fills_reconcile_from_the_nifty_ledger_alone(desk, store):
    """Equity is 20000 plus journaled net, derived with no Sandbox table involved."""
    desk.enter(ist(THU, 10, 30))
    desk.leave(ist(THU, 10, 40), "170.00")
    trades = store.trades(USER)
    account = store.account(USER, ist(THU, 11, 0))
    assert len(trades) == 1
    assert D(account["equity"]) == D("20000") + sum(D(t["net"]) for t in trades)
    assert D(account["available"]) == D(account["equity"])  # flat: nothing reserved


# =============================================================================
# 2. Capital and loss limits
# =============================================================================


def test_new_accounts_start_at_20000_and_the_capital_cannot_be_configured_away(store):
    store.ensure_user("fresh")
    account = store.account("fresh", ist(THU, 10, 0))
    assert D(account["equity"]) == D(account["available"]) == D("20000")
    assert D(account["starting_day_equity"]) == D("20000") and account["daily_entries"] == 0
    for capital in ("19999.99", "20000.01", "50000"):
        with pytest.raises(ValidationError):
            StrategyConfig(virtual_capital=D(capital))


def test_existing_balances_survive_reinitialisation_restart_and_day_rollover(desk, store):
    desk.enter(ist(THU, 10, 30))
    desk.leave(ist(THU, 10, 40), "151.85", "INITIAL_STOP")
    equity = D(store.account(USER, ist(THU, 11, 0))["equity"])
    assert equity < D("20000")
    # ensure_user, a brand-new store object on the same database, and later days.
    store.ensure_user(USER)
    restarted = NiftyStore(store.engine)
    restarted.initialize()
    for later in (ist(THU, 15, 0), ist(FRI, 9, 0), ist(MON, 9, 0)):
        account = restarted.account(USER, later)
        assert D(account["equity"]) == equity != D("20000")
    # The new day's loss baseline is the carried equity, never a reset to 20000.
    assert D(restarted.account(USER, ist(MON, 9, 1))["starting_day_equity"]) == equity


def test_every_sized_plan_respects_lots_loss_reward_and_cash_limits():
    seen_lots, rejections = set(), set()
    for score in (0, 39.99, 40, 69.99, 70, 100):
        for cents in range(1500, 30001, 25):
            plan = sized(D(cents) / 100, score)
            rejections.update(reason for _, _, reason in plan.rejections)
            if plan.instrument is None:
                continue
            seen_lots.add(plan.lots)
            assert 1 <= plan.lots <= 3 and plan.quantity == plan.lots * 25
            assert plan.planned_loss <= D("400"), (cents, score)
            assert plan.projected_net_reward >= D("350"), (cents, score)
            assert plan.cash_required <= D("20000")
            # Score tiers can only cap the lots, never raise them.
            assert plan.lots <= (1 if score < 40 else 2 if score < 70 else 3)
    assert seen_lots == {1, 2, 3}  # non-vacuous: every permitted size occurs
    assert {"PLANNED_LOSS_LIMIT", "NET_REWARD_BELOW_MINIMUM"} <= rejections


def test_the_configured_risk_ceilings_cannot_be_loosened():
    for field, bad in (
        ("max_planned_loss", "401"),
        ("min_projected_net_reward", "349.99"),
        ("monthly_loss_limit", "2001"),
        ("max_lots", 4),
        ("max_daily_entries", 2),
        ("max_hold_minutes", 46),
        ("max_positions", 2),
    ):
        with pytest.raises(ValidationError):
            StrategyConfig(**{field: D(bad) if isinstance(bad, str) else bad})
    config = StrategyConfig()
    assert (config.max_planned_loss, config.min_projected_net_reward) == (D("400"), D("350"))
    assert (config.monthly_loss_limit, config.daily_loss_fraction) == (D("2000"), D("0.015"))


@pytest.mark.parametrize(("ask", "score", "lots"), [("165.00", 50, 1), ("70.00", 50, 2)])
def test_a_filled_entry_carries_the_sized_quantity_and_modeled_limits(store, ask, score, lots):
    desk = Desk(store, feed=Feed(ist(THU, 10, 30), ask=ask, bid=str(D(ask) - D("0.25"))))
    desk.running()
    order = desk.enter(ist(THU, 10, 30), score=score)
    plan = order["payload"]["sizing_plan"]
    assert plan["lots"] == lots and order["quantity"] == lots * 25
    assert D(plan["planned_loss"]) <= D("400") and D(plan["projected_net_reward"]) >= D("350")


def test_three_lots_need_a_high_score_and_a_cheap_premium(store):
    desk = Desk(store, feed=Feed(ist(THU, 10, 30), ask="40.00", bid="39.80"))
    desk.running()
    assert desk.enter(ist(THU, 10, 30), score=80)["quantity"] == 75
    other = Desk(store, OTHER, feed=Feed(ist(THU, 10, 30), ask="40.00", bid="39.80"))
    other.running()
    with pytest.raises(OrderRefused) as capped:  # a middling score cannot buy this size
        other.buy(ist(THU, 10, 30), score=50)
    assert "SCORE_LOT_LIMIT" in capped.value.reasons and store.positions(OTHER) == []


def test_a_stop_at_the_modeled_exit_loses_exactly_the_modeled_amount_less_the_buffer(desk, store):
    order = desk.enter(ist(THU, 10, 30))
    plan = order["payload"]["sizing_plan"]
    stop = D(plan["stop_price"])
    desk.leave(ist(THU, 10, 40), stop, "INITIAL_STOP")
    (trade,) = store.trades(USER)
    modeled = D(plan["planned_loss"]) - desk.config.planned_loss_buffer
    assert D(trade["net"]) == -modeled
    assert -D(trade["net"]) <= D("400")  # the stated maximum modeled loss
    assert D(trade["net"]) == D(trade["gross"]) - D(trade["fees"])


def test_one_filled_primary_entry_per_session_even_after_flat_but_an_expiry_does_not_count(
    desk, store
):
    # An entry that expires unfilled does not consume the session ...
    desk.buy(ist(THU, 10, 30), tag="expired")
    assert desk.process(ist(THU, 10, 45)) == []
    assert store.orders(USER, now=ist(THU, 10, 45))[0]["status"] == "EXPIRED"
    # ... one filled entry does, including after the position is closed again.
    desk.enter(ist(THU, 10, 50), tag="filled")
    desk.leave(ist(THU, 11, 0), "170.00")
    assert store.positions(USER) == []
    with pytest.raises(OrderRefused) as refusal:
        desk.buy(ist(THU, 11, 10))
    assert "DAILY_ENTRY_LIMIT" in refusal.value.reasons
    # The same rule holds at the locked write when the executor's checks are bypassed.
    first = next(o for o in store.orders(USER, now=ist(THU, 11, 11)) if o["side"] == "BUY")
    clone = {
        **first,
        "order_id": "bypass",
        "intent_id": "bypass",
        "eligible_at": ist(THU, 11, 11),
        "expires_at": ist(THU, 11, 12),
        "created_at": ist(THU, 11, 11),
    }
    with pytest.raises(OrderRefused) as locked:
        store.admit_order(USER, clone)
    assert {"DAILY_ENTRY_USED", "DAILY_ENTRY_LIMIT"} & set(locked.value.reasons)


def test_a_second_entry_cannot_be_admitted_while_the_first_is_pending(desk, store):
    desk.buy(ist(THU, 10, 30), tag="first")
    with pytest.raises(OrderRefused) as refusal:
        desk.exe.admit(desk.intent(ist(THU, 10, 30, 1), tag="second"), ist(THU, 10, 30, 1))
    assert "PENDING_ENTRY" in refusal.value.reasons
    assert len(store.pending_orders(USER)) == 1


def test_refused_admissions_leave_the_ledger_byte_for_byte_unchanged(desk, store):
    before = snapshot(store)
    events_before = len(store.events(USER, limit=100))
    stale = Feed(ist(THU, 10, 30) - timedelta(seconds=60))
    cases = [
        (stale, ist(THU, 10, 30)),  # stale depth and spot
        (Feed(ist(THU, 10, 30), ask=None), ist(THU, 10, 30)),  # no ask side
        (Feed(ist(THU, 10, 30), spot=None), ist(THU, 10, 30)),  # no spot reference
        (Feed(ist(THU, 10, 30)), ist(THU, 10, 29, 59)),  # before the entry window
    ]
    for feed, when in cases:
        desk.feed, desk.exe.market_data = feed, feed
        with pytest.raises(OrderRefused):
            desk.exe.admit(desk.intent(when), when)
    after = snapshot(store)
    assert after == before and store.positions(USER) == []
    admitted = [e for e in store.events(USER, limit=100) if e["kind"] == "paper_intent_admitted"]
    assert admitted == [] and len(store.events(USER, limit=100)) >= events_before


def test_fills_that_fail_final_revalidation_do_not_move_money_or_use_the_entry(desk, store):
    desk.buy(ist(THU, 10, 30))
    before = snapshot(store)
    # Spread blows out between admission and fill: refused at the locked write.
    desk.feed.bid, desk.feed.ask = "150.00", "165.00"
    fills = desk.process(ist(THU, 10, 30, 1))
    assert [(row["status"], row["reason"]) for row in fills] == [("REJECTED", "LIQUIDITY_LOST")]
    after = snapshot(store)
    assert after["account"] == before["account"] and after["positions"] == []
    assert after["account"]["daily_entries"] == 0  # a rejected fill never consumes the session


def test_fill_inputs_that_are_not_the_observed_depth_are_refused_and_change_nothing(desk, store):
    order = desk.buy(ist(THU, 10, 30))
    before = snapshot(store)
    when = ist(THU, 10, 30, 1)
    desk.stamp(when)
    observed = desk.exe._depth(order["payload"]["instrument"], when, desk.config)
    from hashlib import sha256

    snapshot_id = sha256(
        f"{observed.token}:{observed.source_time.isoformat()}:BUY".encode()
    ).hexdigest()
    fair = observed.ask + D("0.05")
    fees = _charges("BUY", fair, order["quantity"], desk.config)
    common = {"snapshot_id": snapshot_id, "displayed_size": observed.ask_size}
    common["observation"] = observed.model_dump(mode="json")
    common.update(spot=D("22000"), atm_strike=D("22000"))
    cases = {
        "ltp price": {
            "price": D("164.50"),
            "fees": _charges("BUY", D("164.50"), order["quantity"], desk.config),
        },
        "off-tick price": {"price": fair + D("0.01"), "fees": fees},
        "wrong fees": {"price": fair, "fees": fees - D("0.0001")},
        "wrong snapshot": {"price": fair, "fees": fees, "snapshot_id": "0" * 64},
    }
    for name, values in cases.items():
        arguments = {**common, **values}
        price, fee = arguments.pop("price"), arguments.pop("fees")
        with pytest.raises(ValueError):
            store.fill(USER, order["order_id"], price, fee, when, **arguments)
        assert snapshot(store) == before, name
    # And the genuine fill still works exactly once afterwards.
    assert desk.process(when)[0]["status"] == "FILLED" and len(store.positions(USER)) == 1


def test_charges_are_whole_ceilinged_amounts_and_an_exact_round_trip_conserves_cash(desk, store):
    for price in (D("0.05"), D("19.95"), D("164.55"), D("999.95")):
        for quantity in (25, 50, 75):
            for side in ("BUY", "SELL"):
                charge = _charges(side, price, quantity)
                assert charge == charge.quantize(D("0.0001")) and charge > 0
                assert (charge - charge.quantize(D("0.0001"))) == 0
    desk.enter(ist(THU, 10, 30))
    entry = next(o for o in store.orders(USER, now=ist(THU, 10, 31)) if o["side"] == "BUY")
    desk.leave(ist(THU, 10, 40), "170.00")
    (trade,) = store.trades(USER)
    exit_order = next(o for o in store.orders(USER, now=ist(THU, 10, 42)) if o["side"] == "SELL")
    gross = (D(exit_order["price"]) - D(entry["price"])) * entry["quantity"]
    assert D(trade["gross"]) == gross
    assert D(trade["fees"]) == D(entry["fees"]) + D(exit_order["fees"])
    assert D(trade["net"]) == gross - D(entry["fees"]) - D(exit_order["fees"])
    account = store.account(USER, ist(THU, 11, 0))
    assert D(account["equity"]) == D(account["available"]) == D("20000") + D(trade["net"])


def test_cash_and_equity_stay_consistent_over_several_sessions_of_wins_and_a_loss(store):
    desk = Desk(store)
    desk.running()
    plan = [(THU, "185.70"), (FRI, "186.00"), (MON, "151.85")]
    for day, exit_bid in plan:
        desk.feed.bid, desk.feed.ask = "164.00", "165.00"
        desk.enter(ist(day, 10, 30), tag=day.isoformat())
        assert store.account(USER, ist(day, 10, 31))["daily_entries"] == 1
        desk.leave(
            ist(day, 11, 0), exit_bid, "TARGET_HIT" if exit_bid != "151.85" else "INITIAL_STOP"
        )
        trades = store.trades(USER)
        account = store.account(USER, ist(day, 11, 5))
        assert store.positions(USER) == []
        assert (
            D(account["equity"])
            == D(account["available"])
            == D("20000") + sum(D(t["net"]) for t in trades)
        )
        with store.sessions.begin() as db:  # the loss pause is an operator decision; resume
            db.get(NiftyState, USER).state = "RUNNING"
    assert [D(t["net"]) > 0 for t in reversed(store.trades(USER))] == [True, True, False]


def test_the_daily_loss_lock_pauses_entries_but_never_blocks_the_exit_that_caused_it(store):
    desk = Desk(store)
    desk.running()
    desk.enter(ist(THU, 10, 30))
    fills = desk.leave(ist(THU, 10, 40), "151.85", "INITIAL_STOP")
    assert [row["status"] for row in fills] == ["FILLED"]
    state = store.read(USER)
    assert state["daily_locked"] and state["state"] == "PAUSED"
    account = store.account(USER, ist(THU, 10, 41))
    assert D(account["equity"]) <= D(account["starting_day_equity"]) * D("0.985")
    with pytest.raises(OrderRefused) as refusal:
        desk.buy(ist(THU, 10, 50))
    assert {"DAILY_LOCKOUT", "ENTRIES_PAUSED", "DAILY_LOSS_LIMIT"} & set(refusal.value.reasons)
    # The loss also schedules a next-session cooldown that is still reported on Friday.
    with pytest.raises(OrderRefused) as friday:
        desk.buy(ist(FRI, 10, 30))
    assert friday.value.reasons == ["COOLDOWN_ACTIVE"]


def _seed_loss(store, net, closed_at, user=USER, tag="seed"):
    """Journal a closed trade the way a real fill does: trade row plus month total."""
    with store.sessions.begin() as db:
        db.add(
            NiftyTrade(
                user_id=user,
                entry_order_id=tag,
                exit_order_id=tag,
                symbol="SEED",
                quantity=1,
                entry_price=D("1"),
                exit_price=D("1"),
                gross=D(net),
                fees=D("0"),
                net=D(net),
                reason="SEED",
                opened_at=closed_at - timedelta(minutes=5),
                closed_at=closed_at,
            )
        )
        store._record_month_net(db, user, closed_at, D(net), StrategyConfig())


@pytest.mark.parametrize(
    ("net", "locked"), [("-1999.99", False), ("-2000", True), ("-2500", True), ("500", False)]
)
def test_monthly_loss_lock_threshold_is_exactly_2000_of_realized_net(store, net, locked):
    desk = Desk(store)
    _seed_loss(store, net, ist(THU, 9, 30))
    reasons = store.entry_locks(USER, ist(MON, 10, 30), desk.config)
    assert ("MONTHLY_LOSS_LOCK" in reasons) is locked


def test_the_monthly_lock_latches_stays_through_a_recovery_and_does_not_block_exits(store):
    desk = Desk(store)
    desk.running()
    desk.enter(ist(THU, 10, 30))
    _seed_loss(store, "-2000", ist(THU, 10, 31))
    assert "MONTHLY_LOSS_LOCK" in store.entry_locks(USER, ist(THU, 10, 32), desk.config)
    with store.sessions() as db:
        assert db.get(NiftyMonth, (USER, "2026-11")).loss_locked_at is not None
        assert [e.kind for e in db.query(NiftyEvent).filter_by(kind="MONTHLY_LOSS_LOCKED")]
    # The position taken before the lock can still be protected and closed.
    fills = desk.leave(ist(THU, 10, 40), "170.00")
    assert [row["status"] for row in fills] == ["FILLED"] and store.positions(USER) == []
    # A later profit does not unlock the month: the latch is the contract.
    _seed_loss(store, "1500", ist(FRI, 9, 30), tag="recovery")
    assert "MONTHLY_LOSS_LOCK" in store.entry_locks(USER, ist(MON, 10, 30), desk.config)
    with pytest.raises(OrderRefused) as refusal:
        desk.buy(ist(MON, 10, 30))
    assert "MONTHLY_LOSS_LOCK" in refusal.value.reasons


def test_the_monthly_lock_rolls_over_at_the_ist_month_boundary(store):
    desk = Desk(store)
    _seed_loss(store, "-2000", datetime(2026, 11, 30, 18, 29, 59, tzinfo=UTC))  # 23:59:59 IST, Nov
    assert "MONTHLY_LOSS_LOCK" in store.entry_locks(
        USER, ist(date(2026, 11, 30), 12, 0), desk.config
    )
    december = ist(date(2026, 12, 1), 10, 30)
    assert "MONTHLY_LOSS_LOCK" not in store.entry_locks(USER, december, desk.config)
    _seed_loss(
        store, "-2000", datetime(2026, 11, 30, 18, 30, 0, tzinfo=UTC), tag="dec"
    )  # 00:00 IST, Dec
    assert "MONTHLY_LOSS_LOCK" in store.entry_locks(USER, december, desk.config)


# =============================================================================
# 3. Time-based protections
# =============================================================================


@pytest.mark.parametrize(
    ("clock", "admitted"),
    [
        ((9, 15, 0), False),
        ((10, 29, 59), False),
        ((10, 30, 0), True),
        ((12, 0, 0), True),
        ((14, 44, 59), True),
        ((14, 45, 0), False),
        ((15, 0, 0), False),
        ((15, 10, 0), False),
    ],
)
def test_primary_entries_are_admitted_only_from_1030_until_before_1445_ist(store, clock, admitted):
    when = ist(THU, *clock)
    desk = Desk(store, feed=Feed(when))
    desk.running()
    if admitted:
        assert desk.buy(when)["side"] == "BUY"
    else:
        with pytest.raises(OrderRefused) as refusal:
            desk.buy(when)
        assert "ENTRY_WINDOW" in refusal.value.reasons and store.pending_orders(USER) == []


def test_an_entry_admitted_in_the_last_second_never_fills_at_or_after_1445(store):
    desk = Desk(store, feed=Feed(ist(THU, 14, 44, 59)))
    desk.running()
    order = desk.buy(ist(THU, 14, 44, 59))
    assert order["expires_at"] == ist(THU, 14, 45)  # capped at the entry cutoff, not now + TTL
    # The fill's own hard cutoff is a second layer: it refuses even when the
    # order is still pending at 14:45:00, before any expiry sweep has run.
    refused = store.fill(USER, order["order_id"], "165.00", "10", ist(THU, 14, 45))
    assert (refused["status"], refused["reason"]) == ("EXPIRED", "ENTRY_CUTOFF")
    assert store.positions(USER) == []
    assert D(store.account(USER, ist(THU, 14, 46))["equity"]) == D("20000")


def test_an_entry_admitted_in_the_last_second_is_expired_by_the_sweep_at_1445(store):
    desk = Desk(store, feed=Feed(ist(THU, 14, 44, 59)))
    desk.running()
    order = desk.buy(ist(THU, 14, 44, 59))
    assert desk.process(ist(THU, 14, 45)) == []  # swept as expired, never filled
    (row,) = [o for o in store.orders(USER, now=ist(THU, 14, 45)) if o["side"] == "BUY"]
    assert row["order_id"] == order["order_id"]
    assert (row["status"], row["reason"]) == ("EXPIRED", "ORDER_TTL")
    assert store.positions(USER) == [] and store.pending_orders(USER) == []
    assert D(store.account(USER, ist(THU, 14, 46))["equity"]) == D("20000")


def test_the_cutoff_expiry_is_the_same_instant_after_it_is_stored(store):
    desk = Desk(store, feed=Feed(ist(THU, 14, 44, 59)))
    desk.running()
    desk.buy(ist(THU, 14, 44, 59))
    desk.feed.stamp = ist(THU, 14, 40)  # no fresh depth, so no fill attempt can resolve it
    desk.exe.process(ist(THU, 14, 45, 30))
    assert store.pending_orders(USER) == []  # was PENDING until 20:15 IST (D-3)


def _stored_expiry_wall_time(store, order_id):
    """The raw column value: SQLite keeps the wall time and drops the zone."""
    from sqlalchemy import text

    with store.engine.connect() as connection:
        return connection.execute(
            text("SELECT expires_at FROM nifty_algo_order WHERE order_id = :id"), {"id": order_id}
        ).scalar_one()


@pytest.mark.parametrize(
    ("admitted", "expires"),
    [
        ((14, 44, 50), (14, 45, 0)),  # the cutoff wins, inside the last ten seconds
        ((14, 44, 59), (14, 45, 0)),
        ((14, 44, 49), (14, 44, 59)),  # the TTL (10 s) wins by one second
        ((10, 30, 0), (10, 30, 10)),  # an ordinary entry keeps its TTL
    ],
)
def test_every_persisted_expiry_is_the_intended_utc_instant(store, admitted, expires):
    when = ist(THU, *admitted)
    desk = Desk(store, feed=Feed(when))
    desk.running()
    assert desk.config.order_ttl_seconds == 10
    order = desk.buy(when)
    assert order["expires_at"] == ist(THU, *expires)
    # The stored wall time is UTC, which is what every reader assumes.
    stored = _stored_expiry_wall_time(store, order["order_id"])
    assert str(stored).startswith(ist(THU, *expires).strftime("%Y-%m-%d %H:%M:%S"))
    assert order["created_at"] == when
    assert order["eligible_at"] == when + timedelta(milliseconds=desk.config.latency_ms)


def test_a_cutoff_expiry_survives_a_restart_and_expires_exactly_at_1445_ist(store):
    desk = Desk(store, feed=Feed(ist(THU, 14, 44, 55)))
    desk.running()
    order = desk.buy(ist(THU, 14, 44, 55))
    restarted = NiftyStore(store.engine)  # the process restarted: new objects, same files
    restarted.initialize()
    assert [row["order_id"] for row in restarted.pending_orders(USER)] == [order["order_id"]]
    # One microsecond before 14:45 IST nothing expires, and no depth ever arrives.
    restarted.expire_pending(USER, ist(THU, 14, 44, 59, 999999))
    assert [row["order_id"] for row in restarted.pending_orders(USER)] == [order["order_id"]]
    restarted.expire_pending(USER, ist(THU, 14, 45))
    assert restarted.pending_orders(USER) == []
    (row,) = [o for o in restarted.orders(USER, now=ist(THU, 14, 45, 1)) if o["side"] == "BUY"]
    assert (row["status"], row["reason"]) == ("EXPIRED", "ORDER_TTL")
    assert datetime.fromisoformat(row["expires_at"]) == ist(THU, 14, 45)
    assert restarted.positions(USER) == []
    assert D(restarted.account(USER, ist(THU, 14, 46))["equity"]) == D("20000")


def _hold_scenario(store, open_at, **desk_options):
    desk = Desk(store, feed=Feed(open_at), **desk_options)
    desk.running()
    opened = desk.enter(open_at)
    return desk, store.positions(USER)[0], opened


def test_a_position_is_force_exited_after_exactly_45_minutes(store):
    desk, held, _ = _hold_scenario(store, ist(THU, 10, 30))
    opened_at = datetime.fromisoformat(held["opened_at"])
    before = opened_at + timedelta(minutes=45) - timedelta(seconds=1)
    desk.stamp(before)
    assert desk.exe.monitor_exits(before) == []
    at = opened_at + timedelta(minutes=45)
    desk.stamp(at)
    assert len(desk.exe.monitor_exits(at)) == 1
    assert desk.process(at + timedelta(seconds=1))[0]["status"] == "FILLED"
    assert store.trades(USER)[0]["reason"] == "MAX_HOLD" and store.positions(USER) == []


def test_the_1510_session_exit_wins_when_the_hold_limit_is_later(store):
    desk, held, _ = _hold_scenario(store, ist(THU, 14, 30))
    desk.stamp(ist(THU, 15, 9, 59))
    assert desk.exe.monitor_exits(ist(THU, 15, 9, 59)) == []
    desk.stamp(ist(THU, 15, 10))
    assert len(desk.exe.monitor_exits(ist(THU, 15, 10))) == 1
    assert desk.process(ist(THU, 15, 10, 1))[0]["status"] == "FILLED"
    assert store.trades(USER)[0]["reason"] == "SESSION_EXIT"


def test_an_earlier_effective_close_pulls_the_exit_to_five_minutes_before_it(store):
    desk, _, _ = _hold_scenario(store, ist(THU, 11, 30), session_close=time(12, 0))
    desk.stamp(ist(THU, 11, 54, 59))
    assert desk.exe.monitor_exits(ist(THU, 11, 54, 59)) == []
    desk.stamp(ist(THU, 11, 55))
    assert len(desk.exe.monitor_exits(ist(THU, 11, 55))) == 1
    assert desk.process(ist(THU, 11, 55, 1))[0]["status"] == "FILLED"
    assert store.trades(USER)[0]["reason"] == "SESSION_EXIT"


def test_mandatory_exit_precedence_and_missing_session_window_fail_closed():
    config = StrategyConfig()
    opened = ist(THU, 10, 30)
    window = (ist(THU, 9, 15), ist(THU, 15, 40))
    assert mandatory_exit_reason(opened, ist(THU, 10, 40), config, window) is None
    assert mandatory_exit_reason(opened, ist(THU, 11, 15), config, window) == "MAX_HOLD"
    assert mandatory_exit_reason(opened, ist(THU, 15, 10), config, window) == "MAX_HOLD"
    assert (
        mandatory_exit_reason(ist(THU, 14, 40), ist(THU, 15, 10), config, window) == "SESSION_EXIT"
    )
    # No verifiable window: the position is told to leave rather than assumed open.
    assert mandatory_exit_reason(opened, ist(THU, 10, 40), config, None) == "SESSION_EXIT"


class FakeCalendar:
    """The shared market calendar, with a controllable special session and window."""

    def __init__(self, special=None, windows=None):
        self.special, self.windows = special, windows or {}
        self.db_session = SimpleNamespace(remove=lambda: None)

    def get_special_session(self, day, exchange):
        return self.special if self.special == day else None

    def get_effective_session_window(self, day, exchange):
        return self.windows.get(day)

    def get_market_timing(self, exchange):
        return {"start_offset": 33_300_000, "end_offset": 56_400_000}


@pytest.mark.parametrize(
    ("day", "reason"),
    [(SAT, "SESSION_CLOSED"), (FRI, "SESSION_CLOSED")],
    ids=["weekend", "approved-holiday"],
)
def test_entries_are_refused_on_weekends_and_approved_holidays(store, day, reason):
    desk = Desk(
        store, feed=Feed(ist(day, 10, 30)), holidays=[{"date": FRI.isoformat(), "name": "Holiday"}]
    )
    desk.running()
    status = nifty_calendar.nifty_session(USER, day, store=store)["status"]
    assert status in ("WEEKEND", "HOLIDAY")
    with pytest.raises(OrderRefused) as refusal:
        desk.buy(ist(day, 10, 30))
    assert reason in refusal.value.reasons and store.pending_orders(USER) == []


def test_an_unapproved_calendar_blocks_entries_and_special_sessions_never_enable_them(
    store, monkeypatch
):
    store.ensure_user("no-calendar")
    desk = Desk(store, "no-calendar", calendar=False)
    desk.running()
    with pytest.raises(OrderRefused) as unapproved:
        desk.buy(ist(THU, 10, 30))
    assert unapproved.value.reasons == ["CALENDAR_UNAPPROVED"]
    special = Desk(store, USER)
    special.running()
    monkeypatch.setattr(nifty_calendar, "_legacy_calendar", lambda: FakeCalendar(special=THU))
    assert (
        nifty_calendar.nifty_session(USER, THU, store=store)["status"] == "SPECIAL_SESSION_DISABLED"
    )
    with pytest.raises(OrderRefused) as refusal:
        special.buy(ist(THU, 10, 30))
    assert "SESSION_CLOSED" in refusal.value.reasons and store.pending_orders(USER) == []


def test_exits_are_still_governed_by_the_real_session_when_the_calendar_says_closed(store):
    desk, _, _ = _hold_scenario(store, ist(THU, 10, 30))
    desk.session_close = time(10, 31)  # session over by the time the exit could fill
    fills = desk.leave(ist(THU, 10, 40), "170.00")
    assert fills == [] and len(store.positions(USER)) == 1  # waits, never invents a fill


def _early_close(monkeypatch, close_hour, close_minute):
    window = {
        "start_ms": ist(THU, 9, 15).timestamp() * 1000,
        "end_ms": ist(THU, close_hour, close_minute).timestamp() * 1000,
    }
    monkeypatch.setattr(
        nifty_calendar, "_legacy_calendar", lambda: FakeCalendar(windows={THU: window})
    )


def test_an_entry_is_not_opened_inside_the_final_exit_buffer_of_an_early_close(store, monkeypatch):
    _early_close(monkeypatch, 13, 0)
    desk = Desk(store, feed=Feed(ist(THU, 12, 57)), session_close=time(13, 0))
    desk.running()
    with pytest.raises(OrderRefused):
        desk.buy(ist(THU, 12, 57))  # would be force-exited at 12:55, two minutes earlier


@pytest.mark.parametrize(
    ("clock", "admitted"),
    [
        ((12, 54, 59), True),  # last second before the mandatory exit at 12:55:00
        ((12, 54, 59, 999999), True),
        ((12, 55, 0), False),  # exactly close minus five minutes
        ((12, 55, 1), False),
        ((12, 59, 59), False),
        ((13, 0, 0), False),  # the session itself is over
    ],
)
def test_early_close_entry_buffer_boundary_is_exactly_five_minutes_before_the_close(
    store, monkeypatch, clock, admitted
):
    _early_close(monkeypatch, 13, 0)
    when = ist(THU, *clock)
    desk = Desk(store, feed=Feed(when), session_close=time(13, 0))
    desk.running()
    if admitted:
        order = desk.buy(when)
        assert order["side"] == "BUY"
        # The pending entry may not outlive the buffer either: the executor caps
        # its expiry at the boundary, so it can never fill after 12:55:00.
        assert order["expires_at"] == min(when + timedelta(seconds=10), ist(THU, 12, 55))
    else:
        with pytest.raises(OrderRefused) as refusal:
            desk.buy(when)
        assert "ENTRY_WINDOW" in refusal.value.reasons and store.pending_orders(USER) == []


def test_an_entry_admitted_just_before_the_early_close_buffer_never_fills_inside_it(
    store, monkeypatch
):
    _early_close(monkeypatch, 13, 0)
    desk = Desk(store, feed=Feed(ist(THU, 12, 54, 59)), session_close=time(13, 0))
    desk.running()
    desk.buy(ist(THU, 12, 54, 59))
    assert desk.process(ist(THU, 12, 55)) == []  # fresh depth, but the boundary was reached
    (row,) = [o for o in store.orders(USER, now=ist(THU, 12, 55)) if o["side"] == "BUY"]
    assert (row["status"], row["reason"]) == ("EXPIRED", "ORDER_TTL")
    assert store.positions(USER) == []
    assert store.pending_orders(USER) == []


def test_an_early_close_buffer_does_not_block_the_exit_of_a_held_position(store, monkeypatch):
    _early_close(monkeypatch, 13, 0)
    desk = Desk(store, feed=Feed(ist(THU, 12, 30)), session_close=time(13, 0))
    desk.running()
    desk.enter(ist(THU, 12, 30))  # held 26 minutes, well inside the 45-minute limit
    desk.stamp(ist(THU, 12, 56))  # inside the buffer: a new entry is refused, an exit is not
    assert len(desk.exe.monitor_exits(ist(THU, 12, 56))) == 1
    assert desk.process(ist(THU, 12, 56, 1))[0]["status"] == "FILLED"
    assert store.trades(USER)[0]["reason"] == "SESSION_EXIT" and store.positions(USER) == []


def test_a_normal_full_day_entry_window_is_unchanged_by_the_exit_buffer(store):
    # A 15:40 close puts the buffer at 15:35, long after the 14:45 entry cutoff.
    desk = Desk(store, feed=Feed(ist(THU, 14, 44, 59)), session_close=time(15, 40))
    desk.running()
    assert desk.buy(ist(THU, 14, 44, 59))["expires_at"] == ist(THU, 14, 45)


def test_a_position_carried_over_a_session_boundary_is_closed_on_the_next_open(store):
    desk, held, _ = _hold_scenario(store, ist(THU, 14, 40), session_close=time(15, 40))
    carried = D(store.account(USER, ist(THU, 15, 45))["equity"])
    # Day rollover: counters reset, the carried equity is the new baseline.
    account = store.account(USER, ist(FRI, 9, 0))
    assert account["daily_entries"] == 0 and D(account["realized_day"]) == 0
    assert D(account["starting_day_equity"]) == D(account["equity"]) == carried
    # Nobody monitored it through the close; the next morning's first look exits it.
    desk.feed.bid, desk.feed.ask = "160.00", "160.50"
    morning = ist(FRI, 9, 20)
    desk.stamp(morning)
    assert len(desk.exe.monitor_exits(morning)) == 1
    assert desk.process(morning + timedelta(seconds=1))[0]["status"] == "FILLED"
    (trade,) = store.trades(USER)
    assert trade["reason"] == "MAX_HOLD"
    assert D(store.account(USER, ist(FRI, 9, 30))["realized_day"]) == D(trade["net"])


# =============================================================================
# 4. Market-data rejection paths
# =============================================================================


def source_snapshot(item, *, bid="129.90", size=25, volume=3000, oi=5000, **changes):
    return {
        "symbol": item.symbol,
        "exchange": item.exchange,
        "ltt": ist(THU, 10, 30, 58),
        "received_time": ist(THU, 10, 30, 59),
        "depth": {
            "buy": [{"price": bid, "quantity": size}],
            "sell": [{"price": "130.00", "quantity": size}],
        },
        "ltp": "129.95",
        "volume": volume,
        "oi": oi,
        **changes,
    }


NOW = ist(THU, 10, 31)
OI_A, OI_B = contract(THU, 22000), contract(THU, 22050)
OI_A, OI_B = (
    OI_A.model_copy(update={"token": "oi-a", "symbol": "OI_A"}),
    OI_B.model_copy(update={"token": "oi-b", "symbol": "OI_B"}),
)


class Snapshots:
    def __init__(self, oi):
        self.sources = {
            ("OI_A", "NFO"): source_snapshot(OI_A, bid="129.90", size=25, volume=3000, oi=oi),
            ("OI_B", "NFO"): source_snapshot(OI_B, bid="129.60", size=40, volume=1000, oi=oi),
        }

    def get_all_data(self, symbol, exchange):
        raw = self.sources.get((symbol, exchange))
        return {"source_observations": {"3": raw}} if raw else {}


def ranking(oi):
    exe = NiftyPaperExecutor(market_data=Snapshots(oi))
    quotes = [(item, exe._depth(item, NOW)) for item in (OI_A, OI_B)]
    risk = AccountRisk(D("20000"), D("20000"), D("20000"), reconciled=True, entries_enabled=True)
    plan = plan_entry(risk, quotes, StrategyConfig(), 30, lambda *a: D("0"), now=NOW)
    return [(row["token"], row["lots"], Decimal(row["total"])) for row in plan.ranking]


@pytest.mark.parametrize("bad", [True, "5000", 5000.0, -1, [5000]])
def test_an_invalid_own_contract_oi_ranks_exactly_like_a_missing_oi_and_never_better(bad):
    missing, invalid, valid = ranking(None), ranking(bad), ranking(5000)
    assert invalid == missing
    for (token_m, lots_m, total_m), (token_v, lots_v, total_v) in zip(
        sorted(missing), sorted(valid), strict=True
    ):
        assert (token_m, lots_m) == (token_v, lots_v) and total_m <= total_v
    assert sorted(missing) != sorted(valid)  # valid OI genuinely matters (non-vacuous)


def test_another_contracts_oi_packet_cannot_supply_oi_or_improve_ranking():
    cache = Snapshots(5000)
    cache.sources[("OI_A", "NFO")] = source_snapshot(OI_A, oi=5000, symbol="SOME_OTHER_CONTRACT")
    cache.sources[("OI_B", "NFO")] = source_snapshot(
        OI_B, bid="129.60", size=40, volume=1000, oi=5000, exchange="NSE"
    )
    exe = NiftyPaperExecutor(market_data=cache)
    assert exe._depth(OI_A, NOW).oi is None and exe._depth(OI_B, NOW).oi is None
    assert depth_quote(OI_A, source_snapshot(OI_A, oi=None), NOW).oi is None  # missing is never 0


def _chain_adapter(feed, *, rows=None):
    def master():
        common = {"name": "NIFTY", "exchange": "NFO", "lotsize": 25, "tick_size": 0.05}
        out = []
        for expiry in ("24-NOV-26", "01-DEC-26"):
            for strike in (24900, 25000, 25100):
                for side in ("CE", "PE"):
                    out.append(
                        {
                            **common,
                            "symbol": f"N{expiry[:2]}{strike}{side}",
                            "token": f"{expiry[:2]}-{strike}-{side}",
                            "instrumenttype": "OPTIDX",
                            "expiry": expiry,
                            "strike": strike,
                        }
                    )
        return rows(out) if rows else out

    return NativeDataAdapter(
        instrument_loader=master,
        market_data=feed,
        master_reader=lambda: {"is_ready": True, "download_date": "2026-11-19", "broker": "angel"},
        clock=lambda: ist(THU, 11, 0),
    )


class ChainFeed:
    def __init__(self, stamp=None, *, oi=None, late=None, drop=()):
        self.stamp = stamp or ist(THU, 11, 0)
        self.oi, self.late, self.drop = oi or {}, late or {}, set(drop)

    def get_all_data(self, symbol, exchange):
        if symbol in self.drop:
            return {}
        # symbol format N<dd><strike><side>
        side, expiry_day = symbol[-2:], symbol[1:3]
        stamp = self.stamp - timedelta(seconds=self.late.get(symbol, 0))
        value = self.oi.get(symbol, 1000 if side == "CE" else 2000) * (
            1 if expiry_day == "24" else 3
        )
        return {
            "source_observations": {
                "3": {"ltt": stamp, "received_time": stamp, "ltp": 100, "volume": 5000, "oi": value}
            }
        }


def pcr_of(adapter, **config):
    return adapter.get_pcr(StrategyConfig(**config), ist(THU, 11, 0))


def test_pcr_covers_one_complete_dated_expiry_and_a_wrong_expiry_never_substitutes():
    result = pcr_of(_chain_adapter(ChainFeed()))
    assert (
        result["pcr"].value == 2
        and "2026-11-24" in result["scope"]
        and result["expected_contracts"] == 6
    )
    # An explicitly selected expiry is honoured and its own numbers are used.
    second = pcr_of(_chain_adapter(ChainFeed()), pcr_expiry=date(2026, 12, 1))
    assert second["pcr"].value == 2 and "2026-12-01" in second["scope"]
    # An expiry that is not listed gives no PCR; it never falls back to the nearest.
    unlisted = pcr_of(_chain_adapter(ChainFeed()), pcr_expiry=date(2026, 12, 8))
    assert (
        unlisted["pcr"] is None and unlisted["reason"] == "COMPLETE_TIMESTAMPED_CHAIN_UNAVAILABLE"
    )
    # Mixed-expiry OI is never blended: only the selected expiry's contracts count.
    lopsided = ChainFeed(oi={"N01" + "25000PE": 9999})
    assert pcr_of(_chain_adapter(lopsided))["pcr"].value == 2


def test_an_incomplete_chain_blocks_pcr_instead_of_renormalising():
    for drop in ({"N2425000PE"}, {"N2424900CE"}, {"N2425100PE", "N2425100CE"}):
        result = pcr_of(_chain_adapter(ChainFeed(drop=drop)))
        assert (
            result["pcr"] is None and result["reason"] == "COMPLETE_TIMESTAMPED_CHAIN_UNAVAILABLE"
        )
        assert result["observed_contracts"] == result["expected_contracts"] - len(drop)


def test_mismatched_ce_and_pe_strike_ladders_block_pcr():
    def drop_one_put(rows):
        return [row for row in rows if not (row["symbol"] == "N2425100PE")]

    result = pcr_of(_chain_adapter(ChainFeed(), rows=drop_one_put))
    assert result["pcr"] is None


def test_a_missing_oi_is_never_counted_as_zero_in_pcr():
    class NoOi(ChainFeed):
        def get_all_data(self, symbol, exchange):
            data = super().get_all_data(symbol, exchange)
            if symbol == "N2425000PE":
                data["source_observations"]["3"]["oi"] = None
            return data

    assert pcr_of(_chain_adapter(NoOi()))["pcr"] is None


@pytest.mark.parametrize(("lag", "accepted"), [(5, True), (6, False)])
def test_pcr_blocks_when_cross_leg_source_skew_exceeds_five_seconds(lag, accepted):
    feed = ChainFeed(late={"N2425000PE": lag})
    result = pcr_of(_chain_adapter(feed))
    assert (result["pcr"] is not None) is accepted
    assert accepted or result["reason"] == "PCR_TIMESTAMP_SKEW"


def test_pcr_blocks_when_every_leg_is_older_than_the_source_age_limit():
    fresh = ChainFeed(late=dict.fromkeys(("N2424900CE", "N2424900PE"), 89))
    assert pcr_of(_chain_adapter(fresh), pcr_max_skew_seconds=90)["pcr"] is not None
    stale = ChainFeed(late={f"N24{k}{s}": 91 for k in (24900, 25000, 25100) for s in ("CE", "PE")})
    assert pcr_of(_chain_adapter(stale))["pcr"] is None


@pytest.mark.parametrize(
    ("age", "accepted"), [(5.0, True), (5.001, False), (-0.001, False), (60, False)]
)
def test_option_depth_must_be_fresh_and_never_from_the_future(store, age, accepted):
    when = ist(THU, 10, 30)
    desk = Desk(store, feed=Feed(when - timedelta(seconds=age)))
    desk.running()
    desk.feed.spot_stamp = when  # fresh spot isolates the option's own freshness
    desk.stamp = lambda w: setattr(desk, "now", w)  # keep the feed stamp where the test put it
    desk.now = when
    if accepted:
        assert desk.exe.admit(desk.intent(when), when)[1] is True
    else:
        with pytest.raises(OrderRefused):
            desk.exe.admit(desk.intent(when), when)
        assert store.pending_orders(USER) == []


def test_a_receipt_time_before_the_source_time_or_after_now_is_refused(store):
    when = ist(THU, 10, 30)
    for received in (when - timedelta(seconds=1), when + timedelta(seconds=1)):
        desk = Desk(store, feed=Feed(when))
        desk.running()
        desk.feed.received = received
        with pytest.raises(OrderRefused):
            desk.exe.admit(desk.intent(when, tag=str(received.second)), when)
        assert store.pending_orders(USER) == []


def test_a_stale_spot_reference_blocks_entry_even_when_option_depth_is_fresh(store):
    when = ist(THU, 10, 30)
    desk = Desk(store, feed=Feed(when))
    desk.running()
    desk.feed.spot_stamp = when - timedelta(seconds=6)
    with pytest.raises(OrderRefused) as refusal:
        desk.exe.admit(desk.intent(when), when)
    assert refusal.value.reasons == ["SPOT_REFERENCE_UNAVAILABLE"]
    desk.feed.spot_stamp = when - timedelta(seconds=5)
    assert desk.exe.admit(desk.intent(when, tag="ok"), when)[1] is True


@pytest.mark.parametrize(
    "feed_options",
    [
        {"ask": None},  # no offer
        {"bid": None},  # no bid: nothing to exit into
        {"size": 24},  # less than one lot displayed
        {"bid": "150.00", "ask": "165.00"},  # spread far above the limit
        {"volume": 999},  # below the minimum volume
    ],
    ids=["no-ask", "no-bid", "sub-lot-depth", "wide-spread", "low-volume"],
)
def test_unusable_depth_blocks_new_entries_and_ltp_never_substitutes(store, feed_options):
    when = ist(THU, 10, 30)
    desk = Desk(store, feed=Feed(when, **feed_options))
    desk.running()
    with pytest.raises(OrderRefused):
        desk.exe.admit(desk.intent(when), when)
    assert store.pending_orders(USER) == [] and store.positions(USER) == []


def test_depth_that_vanishes_before_the_fill_leaves_the_entry_pending_then_expired(desk, store):
    desk.buy(ist(THU, 10, 30))
    desk.feed.ask = None  # only an LTP remains
    assert desk.process(ist(THU, 10, 30, 1)) == []
    assert len(store.pending_orders(USER)) == 1 and store.positions(USER) == []
    desk.feed.ask = "165.00"
    desk.feed.size = 10  # now smaller than the 25 ordered
    assert desk.process(ist(THU, 10, 30, 2)) == []
    assert desk.process(ist(THU, 10, 31)) == []
    assert store.orders(USER, now=ist(THU, 10, 31))[0]["status"] == "EXPIRED"
    assert D(store.account(USER, ist(THU, 10, 32))["equity"]) == D("20000")


def test_monthly_lock_and_kill_switch_between_admission_and_fill_stop_the_fill(store):
    desk = Desk(store)
    desk.running()
    desk.buy(ist(THU, 10, 30))
    _seed_loss(store, "-2000", ist(THU, 10, 30, 0, 500))
    fills = desk.process(ist(THU, 10, 30, 1))
    assert [(row["status"], row["reason"]) for row in fills] == [("REJECTED", "MONTHLY_LOSS_LOCK")]
    assert (
        store.positions(USER) == [] and store.account(USER, ist(THU, 11, 0))["daily_entries"] == 0
    )
    other = Desk(store, OTHER)
    other.running()
    other.buy(ist(THU, 10, 30))
    store.change(OTHER, store.read(OTHER)["revision"], action="kill-switch")
    fills = other.process(ist(THU, 10, 30, 1))
    assert [(row["status"], row["reason"]) for row in fills] == [("CANCELED", "ENTRIES_DISABLED")]
    assert store.positions(OTHER) == []


SPOT_GRID = [D(22000) + D(step) for step in range(-120, 121, 7)] + [D(22025), D(21975), D(22075)]


@pytest.mark.parametrize("kind", ["CE", "PE"])
def test_every_strike_the_selector_offers_is_one_admission_will_not_call_otm(kind):
    ladder = [contract(THU, strike, kind) for strike in range(21800, 22301, 50)]
    config = StrategyConfig(candidate_strike_window=2)
    offered_total = 0
    for spot in SPOT_GRID:
        report = Resolver().assess(
            ladder, {i.token: None for i in ladder}, spot, kind, ist(THU, 10, 31), config
        )
        for row in report["candidates"]:
            item = Instrument.model_validate(row["instrument"])
            admitted, atm, refusal = current_moneyness(item, spot, ladder)
            assert refusal is None and admitted == row["moneyness"], (kind, spot, item.strike)
            offered = (
                row["reasons"] not in (["OUTSIDE_SELECTION_WINDOW"], ["OTM_PROHIBITED"])
                and row["moneyness"] != "NOT_ASSESSED"
            )
            if offered:
                offered_total += 1
                assert admitted in ("ATM", "ITM"), (kind, spot, item.strike, admitted)
            if admitted == "OTM":
                assert not offered
    assert offered_total > 100  # the sweep genuinely exercised ranked candidates


@pytest.mark.parametrize(
    ("strikes", "spot", "kind", "expected"),
    [
        ((22050,), "22030", "CE", "OTM"),  # one strike above spot: unbracketed
        ((22050,), "22030", "PE", "ITM"),
        ((22000,), "22040", "CE", "ITM"),  # one strike below spot: unbracketed
        ((22000,), "22040", "PE", "OTM"),
        ((22000, 22100), "22150", "CE", "ITM"),  # spot beyond the top of the ladder
        ((22000, 22100), "22150", "PE", "OTM"),
        ((22000, 22100), "21950", "CE", "OTM"),  # spot beyond the bottom
        ((22000, 22100), "21950", "PE", "ITM"),
    ],
)
def test_a_ladder_that_does_not_bracket_spot_never_labels_a_strike_atm(
    strikes, spot, kind, expected
):
    ladder = [contract(THU, strike, kind) for strike in strikes]
    label, atm, refusal = current_moneyness(ladder[0], D(spot), ladder)
    assert refusal is None and atm is None and label == expected


def test_a_gappy_ladder_that_brackets_spot_does_not_make_a_distant_otm_strike_atm():
    ladder = [contract(THU, strike, "CE") for strike in (22000, 22500)]
    far_call = ladder[1]  # 200 points out of the money at spot 22300
    label, atm, refusal = current_moneyness(far_call, D("22300"), ladder)
    assert (label, atm, refusal) == ("OTM", None, None)  # was ATM (D-1)


# --- D-1: one ATM rule for the selector, admission, fill and replay -------------
#
# NSE lists NIFTY weekly and monthly options every 50 points at all index levels
# (35-1-35 strikes). The selector chooses the nearest expiry, so the ATM strike on
# a complete ladder is never more than 25 points from spot. A larger distance
# means strikes are missing; nothing is filled in and no gap is called normal.

GRID_50 = tuple(range(21500, 22501, 50))
GRID_100 = tuple(range(21500, 22501, 100))  # not an NSE weekly or monthly ladder


def _ladder(strikes, kind="CE", *, day=THU, expiry=EXPIRY):
    return [contract(day, strike, kind, expiry=expiry) for strike in strikes]


def _label(strikes, spot, strike, kind="CE"):
    ladder = _ladder(strikes, kind)
    item = next(i for i in ladder if i.strike == strike)
    return current_moneyness(item, D(str(spot)), ladder)


@pytest.mark.parametrize("kind", ["CE", "PE"])
@pytest.mark.parametrize(
    ("spot", "atm"),
    [
        ("22000", 22000),  # exactly on a listed strike
        ("22010", 22000),
        ("22024.95", 22000),
        ("22025", 22000),  # exact midpoint: the lower strike
        ("22025.05", 22050),
        ("22049.95", 22050),
        ("22075", 22050),  # midpoint again, lower strike
    ],
)
def test_a_complete_50_point_ladder_labels_the_nearest_strike_atm(kind, spot, atm):
    label, found, refusal = _label(GRID_50, spot, atm, kind)
    assert (label, found, refusal) == ("ATM", D(atm), None)


@pytest.mark.parametrize("kind", ["CE", "PE"])
def test_a_complete_ladder_keeps_itm_otm_and_the_strict_midpoint_split(kind):
    spot = "22025"
    itm_strike, otm_strike = (21950, 22100) if kind == "CE" else (22100, 21950)
    assert _label(GRID_50, spot, itm_strike, kind)[0] == "ITM"
    assert _label(GRID_50, spot, otm_strike, kind)[0] == "OTM"
    # The non-ATM neighbour at the midpoint keeps its strict label, never ATM.
    upper_label = _label(GRID_50, spot, 22050, kind)[0]
    assert upper_label == ("OTM" if kind == "CE" else "ITM")


@pytest.mark.parametrize("kind", ["CE", "PE"])
@pytest.mark.parametrize(
    ("strikes", "spot", "listed_atm"),
    [
        # one strike missing: the nearest is still within 25 points, so ATM holds
        (tuple(s for s in GRID_50 if s != 22050), "22040", None),
        (tuple(s for s in GRID_50 if s != 22050), "22010", 22000),
        # the strike nearest to spot is missing and the next one is 50 away
        (tuple(s for s in GRID_50 if s != 22050), "22050", None),
        # several strikes around spot missing
        (tuple(s for s in GRID_50 if not 21950 <= s <= 22150), "22050", None),
        (tuple(s for s in GRID_50 if not 21950 <= s <= 22150), "22000", None),
        # extremely sparse ladders that still bracket spot
        ((22000, 22500), "22300", None),
        ((21000, 23000), "22000", None),
        ((22000, 22100), "22050", None),  # 50 away on each side
        # a single listed strike, and spot outside the listed range
        ((22000,), "22010", None),
        ((22000,), "22000", 22000),
        (GRID_50, "21000", None),
        (GRID_50, "23000", None),
        # a 100-point ladder is not NSE weekly or monthly: nothing 50 away is ATM
        (GRID_100, "22050", None),
        (GRID_100, "22030", None),
        (GRID_100, "22020", 22000),
    ],
)
def test_atm_reference_is_only_issued_within_half_an_interval_of_spot(
    kind, strikes, spot, listed_atm
):
    from services.nifty_algo.contract_resolver import atm_reference

    assert atm_reference(strikes, D(spot)) == (None if listed_atm is None else D(listed_atm))
    for strike in strikes:
        label, found, refusal = _label(strikes, spot, strike, kind)
        assert refusal is None and found == (None if listed_atm is None else D(listed_atm))
        assert label == ("ATM" if strike == listed_atm else _strict(kind, strike, D(spot)))


def _strict(kind, strike, spot):
    if strike == spot:
        return "ATM"
    return (
        ("ITM" if strike < spot else "OTM") if kind == "CE" else ("ITM" if strike > spot else "OTM")
    )


def test_a_missing_ladder_never_turns_an_out_of_the_money_strike_into_itm_or_atm():
    for kind in ("CE", "PE"):
        for strikes in ((22000, 22500), (22000, 22150, 22500), (21000, 22300, 23000)):
            for spot in range(21950, 22551, 13):
                for strike in strikes:
                    label, _, _ = _label(strikes, spot, strike, kind)
                    strict = _strict(kind, strike, D(spot))
                    if strict == "OTM":
                        # Only an ATM within 25 points may soften a strict OTM.
                        assert label == "OTM" or abs(D(strike) - D(spot)) <= 25, (
                            kind,
                            strikes,
                            spot,
                            strike,
                        )
                    if strict == "ITM":
                        assert label in ("ITM", "ATM")


def test_atm_reference_ignores_other_expiries_sides_and_underlyings():
    near = _ladder((22000, 22500))
    other_expiry = _ladder((22300,), expiry=date(2026, 12, 1))
    other_side = _ladder((22300,), "PE")
    other_underlying = [contract(THU, 22300).model_copy(update={"underlying": "BANKNIFTY"})]
    other_underlying[0] = other_underlying[0].model_copy(update={"token": "bank-22300"})
    master = near + other_expiry + other_side + other_underlying
    far = next(i for i in near if i.strike == 22500)
    assert current_moneyness(far, D("22300"), master) == ("OTM", None, None)


def test_atm_reference_is_the_same_for_reordered_and_duplicated_identical_records():
    base = _ladder(GRID_50)
    spot = D("22030")
    target = next(i for i in base if i.strike == 22050)
    expected = current_moneyness(target, spot, base)
    assert expected[0] == "ATM"
    assert current_moneyness(target, spot, list(reversed(base))) == expected
    assert current_moneyness(target, spot, base + base[:5]) == expected
    sparse = _ladder((22000, 22500))
    far = sparse[1]
    reference = current_moneyness(far, D("22300"), sparse)
    assert current_moneyness(far, D("22300"), list(reversed(sparse)) + sparse) == reference


def test_conflicting_duplicate_records_fail_closed_in_either_order():
    ladder = _ladder(GRID_50)
    target = next(i for i in ladder if i.strike == 22000)
    clash = target.model_copy(update={"lot_size": 75})
    for master in (ladder + [clash], [clash] + ladder):
        label, atm, refusal = current_moneyness(target, D("22010"), master)
        assert (label, atm, refusal) == (None, None, "INSTRUMENT_IDENTITY_MISMATCH")


def test_missing_or_invalid_metadata_fails_closed():
    ladder = _ladder(GRID_50)
    target = ladder[0]
    assert current_moneyness(target, None, ladder)[2] == "SPOT_REFERENCE_UNAVAILABLE"
    assert current_moneyness(target, D("22000"), [])[2] == "MASTER_FRESHNESS_UNVERIFIED"
    unlisted = target.model_copy(update={"token": "not-listed"})
    assert current_moneyness(unlisted, D("22000"), ladder)[2] == "INSTRUMENT_IDENTITY_MISMATCH"
    altered = target.model_copy(update={"lot_size": 50})
    assert current_moneyness(altered, D("22000"), ladder)[2] == "INSTRUMENT_IDENTITY_MISMATCH"


def test_a_stale_master_never_supplies_the_ladder():
    yesterday = date(2026, 11, 18)
    stale = _ladder(GRID_50, day=yesterday)
    config = StrategyConfig()
    with pytest.raises(SelectionUnavailable) as raised:
        Resolver().assess(stale, {}, D("22000"), "CE", ist(THU, 10, 31), config)
    assert raised.value.code == "CONTRACT_METADATA_UNAVAILABLE"
    # Stale rows do not repair a gap in today's ladder either.
    today = _ladder((22000, 22500))
    mixed = today + _ladder((22300,), day=yesterday)
    far = today[1]
    assert current_moneyness(far, D("22300"), mixed) == ("OTM", None, None)


LADDERS = {
    "complete-50": GRID_50,
    "complete-100": GRID_100,
    "one-missing": tuple(s for s in GRID_50 if s != 22050),
    "several-missing": tuple(s for s in GRID_50 if not 21950 <= s <= 22150),
    "sparse-two": (22000, 22500),
    "sparse-three": (21500, 22000, 22500),
    "single": (22000,),
}


@pytest.mark.parametrize("selection", ["ATM", "ITM", "DELTA"])
@pytest.mark.parametrize("kind", ["CE", "PE"])
@pytest.mark.parametrize("name", sorted(LADDERS))
def test_selector_admission_fill_and_replay_label_every_offered_contract_alike(
    name, kind, selection
):
    strikes = LADDERS[name]
    ladder = [
        i.model_copy(
            update={"delta": 0.55 if kind == "CE" else -0.55, "delta_time": ist(THU, 10, 31)}
        )
        for i in _ladder(strikes, kind)
    ]
    config = StrategyConfig(selection=selection, candidate_strike_window=2)
    quotes = {i.token: None for i in ladder}
    offered_total = 0
    for spot in [D(s) for s in range(21440, 22561, 11)] + [D("22025"), D("22075")]:
        try:
            report = Resolver().assess(ladder, quotes, spot, kind, ist(THU, 10, 31), config)
        except SelectionUnavailable as refusal:
            # A refusal is explicit. It is never a crash, and a missing ATM is the
            # reason unless an ITM selection simply has no ITM strike left.
            from services.nifty_algo.contract_resolver import atm_reference

            assert selection != "DELTA"
            if refusal.code == "ATM_REFERENCE_UNVERIFIED":
                assert atm_reference([i.strike for i in ladder], spot) is None
            else:
                assert refusal.code == "ITM_STRIKE_UNAVAILABLE" and selection == "ITM"
            continue
        expected_atm = report["atm_strike"]
        for row in report["candidates"]:
            item = Instrument.model_validate(row["instrument"])
            # Admission, the locked write, fill and replay all call this function.
            label, atm, refusal = current_moneyness(item, spot, ladder)
            assert refusal is None
            assert row["moneyness"] == label, (name, kind, selection, spot, item.strike)
            assert (None if atm is None else str(atm)) == expected_atm
            if row["moneyness"] == "OTM":
                assert row["reasons"], "an OTM contract must carry a refusal reason"
            offered = not row["reasons"] or row["reasons"] == ["QUOTE_UNAVAILABLE"]
            if offered and row["rank"] is None and "QUOTE_UNAVAILABLE" in row["reasons"]:
                # Selected for assessment: it must be one admission will not call OTM.
                offered_total += 1
                assert label in ("ATM", "ITM"), (name, kind, selection, spot, item.strike)
    if name in ("complete-50", "complete-100", "one-missing"):
        assert offered_total > 0  # the sweep genuinely offered candidates


def test_the_selector_refuses_with_an_explicit_reason_when_no_atm_can_be_verified():
    ladder = _ladder((22000, 22500))
    for selection in ("ATM", "ITM"):
        config = StrategyConfig(selection=selection)
        with pytest.raises(SelectionUnavailable) as raised:
            Resolver().assess(ladder, {}, D("22300"), "CE", ist(THU, 10, 31), config)
        assert raised.value.code == "ATM_REFERENCE_UNVERIFIED"
    with pytest.raises(ValueError):  # candidates() and resolve() propagate it
        Resolver().candidates(ladder, {}, D("22300"), "CE", ist(THU, 10, 31), StrategyConfig())


def test_ranking_excludes_an_invalid_otm_contract_on_a_gappy_master():
    ladder = [
        i.model_copy(update={"delta": 0.55, "delta_time": ist(THU, 10, 31)})
        for i in _ladder((22000, 22500))
    ]
    quotes = {
        i.token: Quote(
            token=i.token,
            source_time=ist(THU, 10, 30, 58),
            received_time=ist(THU, 10, 30, 59),
            ltp=D("130"),
            bid=D("129.90"),
            ask=D("130.00"),
            bid_size=100,
            ask_size=100,
            volume=5000,
            oi=5000,
            provider="TEST_FIXTURE",
        )
        for i in ladder
    }
    report = Resolver().assess(
        ladder, quotes, D("22300"), "CE", ist(THU, 10, 31), StrategyConfig(selection="DELTA")
    )
    ranked = {row["instrument"]["strike"] for row in report["candidates"] if row["rank"]}
    assert report["atm_strike"] is None and ranked == {"22000"}  # the 22500 call is OTM
    by_strike = {row["instrument"]["strike"]: row for row in report["candidates"]}
    assert by_strike["22500"]["moneyness"] == "OTM"
    assert "OTM_PROHIBITED" in by_strike["22500"]["reasons"]


def test_admission_refuses_a_distant_strike_on_a_gappy_master(store):
    desk = Desk(store, feed=Feed(ist(THU, 10, 30), spot="22300"))
    desk.STRIKES = (22000, 22500)
    desk.running()
    with pytest.raises(OrderRefused) as refusal:
        desk.buy(ist(THU, 10, 30), strike=22500)
    assert refusal.value.reasons == ["OTM_PROHIBITED"] and store.pending_orders(USER) == []
    # The real in-the-money strike on the same master is still admitted.
    assert desk.buy(ist(THU, 10, 30, 5), strike=22000)["side"] == "BUY"


def test_a_pending_entry_is_rejected_at_fill_when_the_master_turns_sparse(store):
    desk = Desk(store, feed=Feed(ist(THU, 10, 30), spot="22040"))
    desk.running()
    order = desk.buy(ist(THU, 10, 30), strike=22050)  # 10 points from spot: ATM on a full grid
    assert order["payload"]["candidate_metadata"][0]["moneyness"] == "ATM"
    desk.STRIKES = (22050, 22500)  # spot 22040 is now below every listed strike: no ATM label
    fills = desk.process(ist(THU, 10, 30, 1))
    assert [(row["status"], row["reason"]) for row in fills] == [("REJECTED", "OTM_PROHIBITED")]
    assert store.positions(USER) == []
    assert D(store.account(USER, ist(THU, 10, 31))["equity"]) == D("20000")


def test_a_complete_master_still_fills_the_atm_and_itm_entries(store):
    desk = Desk(store, feed=Feed(ist(THU, 10, 30), spot="22040"))
    desk.running()
    filled = desk.enter(ist(THU, 10, 30), strike=22050)
    assert filled["status"] == "FILLED" and len(store.positions(USER)) == 1


def test_replay_applies_the_same_rule_to_a_recorded_master():
    # execution_replay calls current_moneyness(...)[0] for the pending entry and
    # Resolver().candidates(...) for selection: both are the functions above.
    import inspect

    from services.nifty_algo import execution_replay

    source = inspect.getsource(execution_replay)
    assert "current_moneyness(instrument, spot.ltp, frame.instruments)" in source
    assert "Resolver().candidates(" in source
    ladder = _ladder((22000, 22500))
    assert current_moneyness(ladder[1], D("22300"), ladder)[0] == "OTM"


def test_minute_history_gaps_and_missing_opening_data_block_the_decision():
    from test.test_nifty_algo_pipeline import DeterministicMarket, assess, minute_rows, pipeline

    now = ist(THU, 10, 30) - timedelta(minutes=30)
    today_open = 8 * 375  # first minute of the evaluated session in the fixture

    def run(drop=(), truncate=None):
        market = DeterministicMarket()
        market.stamp = now
        rows = [r for i, r in enumerate(minute_rows()) if i not in drop]
        return assess(pipeline(market), now=now, rows=rows[:truncate] if truncate else rows)

    baseline = run()
    assert baseline["eligible"] and all(c["state"] == "PASS" for c in baseline["checks"])
    # A hole anywhere in the evaluated session (start, middle, last completed bucket) blocks.
    for index in (today_open + 1, today_open + 23, today_open + 43):
        blocked = run(drop={index})
        assert not blocked["eligible"], index
        assert any(c["state"] != "PASS" for c in blocked["checks"]) or blocked["reasons"], index
    # The session's first candle missing means the session VWAP cannot be proven.
    assert "SESSION_VWAP_INCOMPLETE" in run(drop={today_open})["reasons"]
    # A hole in an older session only costs the older bars; it does not block today.
    assert run(drop={40})["eligible"]
    # History that simply stops early leaves no fresh completed bar to act on.
    stale = run(truncate=len(minute_rows()) - 40)
    assert not stale["eligible"]


def test_a_decision_made_on_stale_history_cannot_be_admitted(store):
    """Even a decision recorded as eligible expires after 30 seconds."""
    when = ist(THU, 10, 30)
    desk = Desk(store, feed=Feed(when + timedelta(seconds=31)))
    desk.running()
    intent = desk.intent(when)
    late = when + timedelta(seconds=31)
    with pytest.raises(OrderRefused) as refusal:
        desk.exe.admit(intent, late)
    assert refusal.value.reasons == ["CONFIDENCE_OR_DECISION_INVALID"]
    on_time = when + timedelta(seconds=30)
    desk.stamp(on_time)
    assert desk.exe.admit(intent, on_time)[1] is True


# =============================================================================
# 5. Recovery and persistence
# =============================================================================


def test_restart_preserves_holdings_protection_locks_and_never_duplicates_the_entry(store):
    desk = Desk(store)
    desk.running()
    desk.enter(ist(THU, 10, 30))
    desk.feed.bid, desk.feed.ask = "169.00", "169.50"  # trailing activates, stop ratchets
    desk.stamp(ist(THU, 10, 35))
    desk.exe.monitor_exits(ist(THU, 10, 35))
    desk.feed.bid, desk.feed.ask = "168.00", "168.50"  # a falling bid never lowers protection
    desk.stamp(ist(THU, 10, 36))
    desk.exe.monitor_exits(ist(THU, 10, 36))
    with store.sessions.begin() as db:  # a latched month, with no fabricated trade to reconcile
        store._record_month_net(db, USER, ist(THU, 9, 30), D("0"), desk.config)
        store._record_month_net(db, USER, ist(THU, 9, 31), D("-2000"), desk.config)
    assert "MONTHLY_LOSS_LOCK" in store.entry_locks(USER, ist(THU, 10, 36), desk.config)
    before = store.positions(USER)[0]
    assert D(before["protection"]["highest_bid"]) == D("169.00")
    locks_before = store.risk_locks(USER, ist(THU, 10, 37))

    restarted = NiftyStore(store.engine)  # the process restarted: new objects, same files
    restarted.initialize()
    revived = Desk(restarted)
    after = restarted.positions(USER)[0]
    assert after == before
    assert restarted.risk_locks(USER, ist(THU, 10, 37)) == locks_before
    report = revived.exe.reconcile(ist(THU, 10, 37))
    assert report["reasons"] == [] and len(report["positions"]) == 1
    # The entry intent is idempotent across the restart, and a new one is refused.
    entry = next(o for o in restarted.orders(USER, now=ist(THU, 10, 37)) if o["side"] == "BUY")
    again, created = revived.exe.admit(
        {**revived.intent(ist(THU, 10, 37), tag="again"), "intent_id": entry["intent_id"]},
        ist(THU, 10, 37),
    )
    assert created is False and again["order_id"] == entry["order_id"]
    with pytest.raises(OrderRefused):
        revived.exe.admit(revived.intent(ist(THU, 10, 38), tag="dup"), ist(THU, 10, 38))
    assert [o["side"] for o in restarted.orders(USER, now=ist(THU, 10, 38))] == ["BUY"]
    # Protection continues from the persisted peak rather than starting over.
    revived.feed.bid, revived.feed.ask = "168.00", "168.50"
    revived.stamp(ist(THU, 10, 39))
    revived.exe.monitor_exits(ist(THU, 10, 39))
    persisted = restarted.positions(USER)[0]["protection"]
    assert D(persisted["highest_bid"]) == D("169.00")
    assert D(persisted["stop_price"]) >= D(before["protection"]["stop_price"])


def test_an_exception_inside_a_sell_fill_rolls_the_whole_fill_back_and_retries_cleanly(
    desk, store, monkeypatch
):
    desk.enter(ist(THU, 10, 30))
    before = snapshot(store)
    original = NiftyStore._record_month_net

    def explode(self, *args, **kwargs):
        raise RuntimeError("simulated crash while journaling")

    monkeypatch.setattr(NiftyStore, "_record_month_net", explode)
    desk.feed.bid, desk.feed.ask = "170.00", "170.50"
    desk.stamp(ist(THU, 10, 40))
    held = store.positions(USER)[0]
    desk.exe.admit(
        {
            "intent_id": "exit-1",
            "side": "SELL",
            "symbol": held["symbol"],
            "token": held["token"],
            "instrument": held["instrument"],
            "quantity": held["quantity"],
            "exit_reason": "TARGET_HIT",
        },
        ist(THU, 10, 40),
    )
    with pytest.raises(RuntimeError, match="simulated crash"):  # surfaced, never swallowed
        desk.process(ist(THU, 10, 40, 1))
    mid = snapshot(store)
    assert mid["account"] == before["account"] and mid["positions"] == before["positions"]
    assert mid["trades"] == [] and len(mid["pending"]) == 1  # the SELL is still pending
    monkeypatch.setattr(NiftyStore, "_record_month_net", original)
    fills = desk.process(ist(THU, 10, 40, 2))
    assert [row["status"] for row in fills] == ["FILLED"]
    assert desk.process(ist(THU, 10, 40, 3)) == []  # and only once
    (trade,) = store.trades(USER)
    account = store.account(USER, ist(THU, 10, 41))
    assert D(account["equity"]) == D("20000") + D(trade["net"]) == D(account["available"])


def test_an_exception_inside_a_buy_fill_leaves_the_order_pending_with_no_debit(
    desk, store, monkeypatch
):
    desk.buy(ist(THU, 10, 30))
    before = snapshot(store)

    def explode(*args, **kwargs):
        raise RuntimeError("simulated crash while reserving")

    monkeypatch.setattr(NiftyStore, "_safety_reasons", staticmethod(explode))
    with pytest.raises(RuntimeError):
        desk.process(ist(THU, 10, 30, 1))
    assert snapshot(store) == before and store.positions(USER) == []
    monkeypatch.undo()
    assert [row["status"] for row in desk.process(ist(THU, 10, 30, 2))] == ["FILLED"]
    assert len(store.positions(USER)) == 1


def test_losing_depth_on_an_open_position_is_durably_visible_without_any_notification_send(
    desk, store
):
    desk.enter(ist(THU, 10, 30))
    desk.feed.bid = None  # the feed has nothing to exit into
    desk.stamp(ist(THU, 10, 31))
    desk.exe.monitor_exits(ist(THU, 10, 31))
    status = store.safety_status(USER)
    assert status["entry_blocked"] and status["reasons"] == ["SAFETY_INTERLOCK"]
    incidents = [i for i in status.get("incidents", []) if i.get("code") == "STALE_DATA"]
    assert incidents and incidents[0]["severity"] == "CRITICAL"
    # The same observation episode is one incident, not a flood.
    desk.stamp(ist(THU, 10, 31, 30))
    desk.exe.monitor_exits(ist(THU, 10, 31, 30))
    assert (
        len(
            [
                i
                for i in store.safety_status(USER).get("incidents", [])
                if i.get("code") == "STALE_DATA"
            ]
        )
        == 1
    )
    # The interlock refuses a further entry, and no socket was needed for any of it
    # (the module-wide guard would have raised on a connection attempt).
    with pytest.raises(OrderRefused) as refusal:
        desk.buy(ist(THU, 10, 32), tag="blocked")
    assert {"SAFETY_INTERLOCK", "ENTRIES_PAUSED"} & set(refusal.value.reasons)
