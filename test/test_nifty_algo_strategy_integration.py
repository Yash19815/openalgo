"""Selector, admission and history integration corrections (N-02, N-03, N-04).

Offline fixtures only: synthetic contracts, synthetic depth snapshots and
synthetic candles. No broker, feed or production database is touched.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest

from database.nifty_algo_db import NiftyOrder
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.contract_resolver import (
    Resolver,
    current_moneyness,
    nearest_listed_strike,
)
from services.nifty_algo.depth_quote import depth_quote
from services.nifty_algo.market_data import aggregate
from services.nifty_algo.models import Candle, Instrument
from services.nifty_algo.native_data import NativeDataAdapter
from services.nifty_algo.paper_executor import NiftyPaperExecutor, OrderRefused
from services.nifty_algo.risk_manager import AccountRisk, plan_entry
from services.nifty_algo.selection_scoring import FACTORS
from services.nifty_algo.signal_engine import Rules, completed_series
from test.test_nifty_algo_paper_executor import (
    NOW,
    USER,
    FakeMarket,
    buy_intent,
    executor,
    running,
)
from test.test_nifty_algo_paper_executor import market_calendar as market_calendar
from test.test_nifty_algo_safety_center import store as store

IST = ZoneInfo("Asia/Kolkata")
DAY = NOW.astimezone(IST).date()


def option(strike, kind="CE", *, token=None, expiry=date(2026, 11, 24), lot_size=25):
    return Instrument(
        token=token or f"{kind.lower()}-{strike}",
        symbol=f"SYNTHETIC{strike}{kind}",
        exchange="NFO",
        kind=kind,
        expiry=expiry,
        strike=strike,
        lot_size=lot_size,
        tick_size=D("0.05"),
        master_date=DAY,
    )


LADDER = [option(strike, kind) for kind in ("CE", "PE") for strike in (21950, 22000, 22050, 22100)]


# --- N-02: OI reaches the PAPER selector from the native depth source ----------


class Snapshots:
    """Per-contract cached market data, as the shared market-data service keeps it."""

    def __init__(self, sources):
        self.sources = sources

    def get_all_data(self, symbol, exchange):
        raw = self.sources.get((symbol, exchange))
        return {"source_observations": {"3": raw}} if raw else {}


def snapshot(item, *, bid, size, volume, oi, **changes):
    return {
        "symbol": item.symbol,
        "exchange": item.exchange,
        "ltt": NOW - timedelta(seconds=2),
        "received_time": NOW - timedelta(seconds=1),
        "depth": {
            "buy": [{"price": bid, "quantity": size}],
            "sell": [{"price": "130.00", "quantity": size}],
        },
        "ltp": "129.95",
        "volume": volume,
        "oi": oi,
        "sequence_number": 7,
        **changes,
    }


A, B = option(22000, token="oi-a"), option(22050, token="oi-b")


def market(oi):
    # A: tighter spread, thinner depth, more volume. B: the reverse. The
    # OI-capped volume term inside liquidity is what decides between them.
    return Snapshots(
        {
            (A.symbol, "NFO"): snapshot(A, bid="129.90", size=25, volume=3000, oi=oi),
            (B.symbol, "NFO"): snapshot(B, bid="129.60", size=40, volume=1000, oi=oi),
        }
    )


def rank(quotes):
    plan = plan_entry(
        AccountRisk(D("20000"), D("20000"), D("20000"), reconciled=True, entries_enabled=True),
        quotes,
        StrategyConfig(),
        30,
        lambda side, price, quantity, config: D("0"),
        now=NOW,
    )
    return [(row["token"], row["lots"], row["total"]) for row in plan.ranking]


def paper_quotes(cache):
    exe = NiftyPaperExecutor(market_data=cache)
    return [(item, exe._depth(item, NOW)) for item in (A, B)]


def research_quotes(cache):
    native = NativeDataAdapter(lambda: [], cache, lambda: NOW)
    return [(item, native.recording_quote(item, NOW)) for item in (A, B)]


def test_paper_selection_receives_fresh_source_oi():
    assert [quote.oi for _, quote in paper_quotes(market(5000))] == [5000, 5000]


def test_paper_and_research_rank_equivalent_snapshots_identically():
    with_oi = market(5000)
    paper, research = rank(paper_quotes(with_oi)), rank(research_quotes(with_oi))
    assert paper == research
    # The approved OI-capped volume term changes the winner, so a path that
    # dropped OI would rank differently from the replay of the same snapshot.
    assert paper[0][0] == "oi-a"
    assert rank(paper_quotes(market(None)))[0][0] == "oi-b"
    assert rank(paper_quotes(market(None))) == rank(research_quotes(market(None)))


def test_selector_weights_stay_the_approved_policy():
    config = StrategyConfig()
    assert dict(zip(FACTORS, config.selector_weights, strict=True)) == {
        "liquidity": 30,
        "spread": 25,
        "delta": 15,
        "reward_risk": 20,
        "capital_efficiency": 10,
    }
    for weights in ((30, 25, 15, 20), (30, 25, 15, 20, 11), ("NaN", 25, 15, 20, 40)):
        with pytest.raises(ValueError):
            StrategyConfig(selector_weights=weights)


@pytest.mark.parametrize("value", [None, True, "5000", 5000.0, -1])
def test_missing_or_malformed_oi_is_never_zero_filled(value):
    raw = snapshot(A, bid="129.90", size=25, volume=3000, oi=value)
    # PAPER keeps the quote (it also prices exits) and drops only the OI.
    paper = depth_quote(A, raw, NOW)
    assert paper is not None and paper.oi is None
    # A strict research read refuses a malformed value, as before; a missing
    # one is simply missing.
    strict = depth_quote(A, raw, NOW, strict=True)
    assert (strict is not None and strict.oi is None) if value is None else strict is None


def test_oi_from_another_contract_or_a_display_fallback_is_not_used():
    other = snapshot(A, bid="129.90", size=25, volume=3000, oi=5000, symbol="ANOTHER")
    assert depth_quote(A, other, NOW).oi is None
    stale = snapshot(A, bid="129.90", size=25, volume=3000, oi=5000)
    stale["ltt"] = NOW - timedelta(seconds=30)
    assert depth_quote(A, stale, NOW) is None
    fallback = NiftyPaperExecutor(market_data=FakeMarket())._depth(option(22000), NOW)
    assert fallback is not None and fallback.oi is None


# --- N-03: one ATM definition, re-applied against fresh spot -----------------


@pytest.mark.parametrize(
    ("kind", "spot", "expected"),
    [
        # Above the 22000/22050 midpoint: 22050 is the listed ATM.
        ("CE", "22030", {22000: "ITM", 22050: "ATM", 22100: "OTM"}),
        ("PE", "22030", {22000: "OTM", 22050: "ATM", 22100: "ITM"}),
        # Below the midpoint: 22000 is the listed ATM.
        ("CE", "22020", {21950: "ITM", 22000: "ATM", 22050: "OTM"}),
        ("PE", "22020", {21950: "OTM", 22000: "ATM", 22050: "ITM"}),
        # Exactly at the midpoint the lower strike is ATM, as the selector says.
        ("CE", "22025", {22000: "ATM", 22050: "OTM"}),
        ("PE", "22025", {22000: "ATM", 22050: "ITM"}),
    ],
)
def test_nearest_listed_strike_is_atm_for_ce_and_pe(kind, spot, expected):
    for strike, classification in expected.items():
        result, atm, refusal = current_moneyness(option(strike, kind), D(spot), LADDER)
        assert refusal is None
        assert result == classification, (kind, spot, strike)
        assert atm == nearest_listed_strike((i.strike for i in LADDER if i.kind == kind), spot)


def test_the_selectors_top_atm_candidate_is_the_one_admission_accepts():
    spot = D("22030")
    quotes = {item.token: None for item in LADDER}
    report = Resolver().assess(LADDER, quotes, spot, "CE", NOW, StrategyConfig())
    assert report["atm_strike"] == "22050"
    assert current_moneyness(option(22050), spot, LADDER)[0] == "ATM"


def test_metadata_the_master_does_not_vouch_for_is_refused():
    assert current_moneyness(option(22050), D("22030"), [])[2] == "MASTER_FRESHNESS_UNVERIFIED"
    relisted = [
        i.model_copy(update={"lot_size": 65}) if i.token == "ce-22050" else i for i in LADDER
    ]
    assert current_moneyness(option(22050), D("22030"), relisted)[2] == (
        "INSTRUMENT_IDENTITY_MISMATCH"
    )
    other_expiry = option(22050, token="ce-22050", expiry=date(2026, 12, 1))
    assert current_moneyness(other_expiry, D("22030"), LADDER)[2] == "MASTER_FRESHNESS_UNVERIFIED"
    assert current_moneyness(option(22050), None, LADDER)[2] == "SPOT_REFERENCE_UNAVAILABLE"


def ladder_executor(store, spot, *, config=None):
    market = FakeMarket(index_ltp=spot)
    exe = executor(store, market=market, config=config)
    exe.master = lambda now: LADDER
    return exe, market


def atm_intent(strike, spot):
    contract = option(strike)
    return buy_intent(instrument=contract, candidates=[contract], spot_reference=D(spot))


def test_selector_atm_above_spot_is_admitted_and_filled(store):
    running(store)
    exe, _ = ladder_executor(store, "22030", config=StrategyConfig(latency_ms=1))
    order, created = exe.admit(atm_intent(22050, "22030"))
    assert created
    assert order["payload"]["candidate_metadata"][0]["moneyness"] == "ATM"
    assert order["payload"]["candidate_metadata"][0]["atm_strike"] == "22050"
    fills = exe.process(now=NOW + timedelta(seconds=1))
    assert [row["status"] for row in fills] == ["FILLED"]


def test_a_stale_selection_label_cannot_admit_a_contract_that_is_otm_now(store):
    running(store)
    # Selected as ATM at 22030, but spot is 22020 at admission: 22000 is the
    # listed ATM now, and CE 22050 is out of the money.
    exe, _ = ladder_executor(store, "22020")
    intent = atm_intent(22050, "22030")
    assert intent["candidate_metadata"][0]["moneyness"] == "ATM"
    with pytest.raises(OrderRefused, match="OTM_PROHIBITED"):
        exe.admit(intent)
    assert store.pending_orders(USER) == []


def test_an_adverse_move_between_admission_and_fill_rejects_the_fill(store):
    running(store)
    exe, market = ladder_executor(store, "22030", config=StrategyConfig(latency_ms=1))
    order, _ = exe.admit(atm_intent(22050, "22030"))
    market.index_ltp = "22020"
    fills = exe.process(now=NOW + timedelta(seconds=1))
    assert [(row["status"], row["reason"]) for row in fills] == [("REJECTED", "OTM_PROHIBITED")]
    assert store.positions(USER) == []
    with store.sessions() as db:
        assert db.get(NiftyOrder, (USER, order["order_id"])).status == "REJECTED"


def test_an_adverse_move_at_the_locked_write_is_refused(store, monkeypatch):
    running(store)
    exe, market = ladder_executor(store, "22030")
    original = store.admit_order

    def competing_update(user, order, **kwargs):
        market.index_ltp = "22020"
        return original(user, order, **kwargs)

    monkeypatch.setattr(store, "admit_order", competing_update)
    with pytest.raises(OrderRefused, match="OTM_PROHIBITED"):
        exe.admit(atm_intent(22050, "22030"))
    assert store.pending_orders(USER) == []


def test_a_genuinely_otm_contract_is_never_admitted(store):
    running(store)
    exe, _ = ladder_executor(store, "22030")
    with pytest.raises(OrderRefused, match="OTM_PROHIBITED"):
        exe.admit(atm_intent(22100, "22030"))


def test_without_current_master_evidence_nothing_is_admitted_or_filled(store):
    running(store)
    exe, _ = ladder_executor(store, "22030", config=StrategyConfig(latency_ms=1))
    exe.master = lambda now: []
    with pytest.raises(OrderRefused, match="MASTER_FRESHNESS_UNVERIFIED"):
        exe.admit(atm_intent(22050, "22030"))
    exe.master = lambda now: LADDER
    exe.admit(atm_intent(22050, "22030"))
    exe.master = lambda now: []
    assert exe.process(now=NOW + timedelta(seconds=1)) == []
    assert len(store.pending_orders(USER)) == 1


# --- N-04: the continuous suffix after the latest gap, never a repair ----------

SESSION_OPEN = (9, 15)


def session_days(count, last=date(2026, 11, 23)):
    days, day = [], last
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return sorted(days)


def candles(days, minutes=5, *, token="future", skip=(), end_of_last=None, price=None):
    rows = []
    for day in days:
        start = datetime(day.year, day.month, day.day, *SESSION_OPEN, tzinfo=IST)
        close = datetime(day.year, day.month, day.day, 15, 30, tzinfo=IST)
        if day == days[-1] and end_of_last is not None:
            close = end_of_last
        while start + timedelta(minutes=minutes) <= close:
            if start not in skip:
                value = price(len(rows)) if price else 22000 + len(rows) % 7
                rows.append(
                    Candle(
                        token=token if not callable(token) else token(day),
                        start=start,
                        end=start + timedelta(minutes=minutes),
                        timeframe=minutes,
                        open=value,
                        high=value + 2,
                        low=value - 2,
                        close=value + 1,
                        volume=100,
                        provenance="SYNTHETIC",
                    )
                )
            start += timedelta(minutes=minutes)
    return rows


def at(day, hour, minute):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)


def test_a_gap_in_an_earlier_session_keeps_the_verified_suffix():
    days = session_days(5)
    gap = at(days[0], 10, 0)
    bars = candles(days, skip={gap})
    now = bars[-1].end
    usable = completed_series(bars, now, "future", 5)
    after = [bar for bar in bars if bar.start > gap]
    assert usable == after
    assert usable[0].start == gap + timedelta(minutes=5)
    assert all(
        a.end == b.start or a.start.date() != b.start.date()
        for a, b in zip(usable, usable[1:], strict=False)
    )
    assert len(usable) >= 80


def test_one_missing_minute_on_an_earlier_day_no_longer_silences_the_series():
    days = session_days(5)
    minutes = []
    for day in days:
        minutes.extend(candles([day], minutes=1))
    dropped = at(days[0], 10, 2)
    minutes = [bar for bar in minutes if bar.start != dropped]
    now = minutes[-1].end
    entry = []
    for day in days:
        session = [bar for bar in minutes if bar.start.astimezone(IST).date() == day]
        entry.extend(aggregate(session, 5, now, session_open=at(day, *SESSION_OPEN)))
    # The 10:00 bucket is incomplete and is dropped, never interpolated.
    assert not any(bar.start == at(days[0], 10, 0) for bar in entry)
    usable = completed_series(entry, now, "future", 5)
    assert usable and usable[0].start == at(days[0], 10, 5)
    assert len(usable) == len(entry) - 9


def test_a_gap_in_the_session_being_evaluated_still_refuses():
    days = session_days(5)
    bars = candles(days, skip={at(days[-1], 11, 0)})
    assert completed_series(bars, bars[-1].end, "future", 5) == []


def test_a_suffix_shorter_than_warmup_is_refused_by_the_warmup_gate():
    days = session_days(5)
    last = days[-1]
    bars = candles(days, skip={at(days[-2], 15, 0)}, end_of_last=at(last, 10, 30))
    higher = candles(days, minutes=15, end_of_last=at(last, 10, 30))
    now = bars[-1].end
    usable = completed_series(bars, now, "future", 5)
    assert 0 < len(usable) < 80
    config = StrategyConfig()
    decision = Rules().evaluate(bars, higher, None, now, config, config.version_id, "future")
    warmup = next(check for check in decision["checks"] if check["rule"] == "R-WARMUP")
    assert warmup["state"] == "FAIL"
    assert decision["eligible"] is False


def test_a_futures_rollover_inside_the_window_is_still_refused():
    days = session_days(5)
    bars = candles(days, token=lambda day: "future-2" if day == days[-1] else "future-1")
    assert completed_series(bars, bars[-1].end, "future-2", 5) == []
    assert completed_series(bars, bars[-1].end, "future-1", 5) == []


def test_a_gap_trimmed_series_evaluates_exactly_like_the_same_clean_suffix():
    days = session_days(5)
    gap = at(days[0], 10, 0)
    bars = candles(days, skip={gap}, price=lambda i: 22000 + i * 0.5)
    higher = candles(days, minutes=15, price=lambda i: 22000 + i * 1.5)
    now = bars[-1].end
    config = StrategyConfig()
    trimmed = Rules().evaluate(bars, higher, None, now, config, config.version_id, "future")
    suffix = [bar for bar in bars if bar.start > gap]
    clean = Rules().evaluate(suffix, higher, None, now, config, config.version_id, "future")
    assert trimmed == clean
    assert trimmed["snapshot"]["end"] == bars[-1].end.isoformat()


def _assessed(drop):
    from test.test_nifty_algo_pipeline import DeterministicMarket, assess, minute_rows, pipeline

    now = NOW - timedelta(minutes=30)
    market = DeterministicMarket()
    market.stamp = now
    rows = minute_rows()
    kept = [row for index, row in enumerate(rows) if index not in drop]
    return assess(pipeline(market), now=now, rows=kept)


def test_end_to_end_a_missing_minute_eight_days_ago_no_longer_blocks_the_signal():
    assert _assessed(set())["eligible"]
    # Minute 40 of the oldest session: its 5- and 15-minute buckets drop, and
    # the series restarts after them instead of being discarded.
    decision = _assessed({40})
    assert decision["eligible"]
    assert all(check["state"] == "PASS" for check in decision["checks"])


def test_end_to_end_a_missing_minute_today_still_refuses():
    today_start = 8 * 375
    decision = _assessed({today_start + 20})
    assert not decision["eligible"]
    warmup = next(check for check in decision["checks"] if check["rule"] == "R-WARMUP")
    assert warmup["state"] != "PASS"


def test_end_to_end_a_dropped_opening_bucket_today_is_session_vwap_incomplete():
    today_start = 8 * 375
    # Minute 0 is present, so only today's first 5-minute bucket is lost.
    decision = _assessed({today_start + 1})
    assert not decision["eligible"]
    assert "SESSION_VWAP_INCOMPLETE" in decision["reasons"]
