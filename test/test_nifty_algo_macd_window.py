"""MACD crossover window: the latest three completed 5-minute entry candles.

Approved 2026-11-24. The crossover candle is age 0, so ages 0, 1 and 2 pass the
R-MACD freshness condition and age 3 or older does not. Strategy 3.1.0 admitted
age 3 (``cross_age <= 3``); 3.2.0 caps ``crossover_freshness`` at 2.

The boundary cases run the real indicator and the real ``Rules.evaluate`` on
deterministic synthetic candles: nothing here replaces the snapshot or the
gate. A search over seeded random walks finds the candle at which the actual
MACD reports each crossover age with a matching SuperTrend direction, so the
age under test is the one the indicator computed, not a patched value.
Passing R-MACD is not an entry permission: every other gate still applies.
"""

from datetime import datetime, timedelta
from functools import cache
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from pydantic import ValidationError

from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyConfiguration, NiftyEvent, NiftyState, NiftyStore
from services.nifty_algo import confidence as confidence_module
from services.nifty_algo.config import (
    CURRENT_STRATEGY_VERSION,
    MAX_MACD_CROSSOVER_AGE,
    StrategyConfig,
    active_configuration,
    migrate_configuration,
)
from services.nifty_algo.indicators import macd, supertrend
from services.nifty_algo.models import Candle
from services.nifty_algo.signal_engine import Rules, snapshot

IST = ZoneInfo("Asia/Kolkata")
TOKEN = "MACD-WINDOW-FUT"
USER = "macd-window-user"


def walk(seed, n=400):
    """Seeded 5-minute random walk, 75 candles per weekday session from 09:15 IST."""
    rng = np.random.default_rng(seed)
    closes = 22000 + np.cumsum(rng.normal(0, 8, n))
    upper, lower = rng.uniform(1, 12, n), rng.uniform(1, 12, n)
    volumes = rng.integers(1, 1000, n)
    days, day = [], datetime(2026, 11, 2, 9, 15, tzinfo=IST)
    while len(days) * 75 < n:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    bars = []
    for i, close in enumerate(closes):
        opening = closes[i - 1] if i else close
        start = days[i // 75] + timedelta(minutes=5 * (i % 75))
        bars.append(
            Candle(
                token=TOKEN,
                start=start,
                end=start + timedelta(minutes=5),
                timeframe=5,
                open=float(opening),
                high=float(max(opening, close) + upper[i]),
                low=float(min(opening, close) - lower[i]),
                close=float(close),
                volume=int(volumes[i]),
                provenance="TEST_FIXTURE",
            )
        )
    return bars


@cache
def cases():
    """First (seed, index) at which the real MACD shows each age and direction.

    A case qualifies when the crossover direction equals the SuperTrend
    direction and the histogram still agrees, so the age is the only thing
    that can decide R-MACD.
    """
    config = StrategyConfig()
    found = {}
    for seed in range(40):
        bars = walk(seed)
        momentum = macd(bars, config.macd_fast, config.macd_slow, config.macd_signal)
        trend = supertrend(bars, config.atr_period, config.atr_multiplier)
        for i in range(79, len(bars)):
            m, st = momentum[i], trend[i]
            if not m or not st or m["cross_age"] is None:
                continue
            direction = st["direction"]
            key = (m["cross_age"], direction)
            if (
                key not in found
                and m["cross_direction"] == direction
                and m["histogram"] * direction > 0
            ):
                found[key] = (seed, i)
        if all((age, d) in found for age in range(5) for d in (1, -1)):
            return found
    raise AssertionError("Deterministic fixture search did not cover every age")


def evaluate(bars, now, config):
    return Rules().evaluate(bars, [], None, now, config, config.version_id, TOKEN)


def macd_gate(result):
    return result["indicator_states"]["macd"]["gate"]


def case_bars(age, direction):
    seed, index = cases()[(age, direction)]
    return walk(seed)[: index + 1]


@pytest.mark.parametrize("direction", (1, -1), ids=("bullish", "bearish"))
@pytest.mark.parametrize(
    ("age", "gate"),
    ((0, "PASS"), (1, "PASS"), (2, "PASS"), (3, "FAIL"), (4, "FAIL")),
)
def test_real_crossover_age_boundary(age, gate, direction):
    bars = case_bars(age, direction)
    config = StrategyConfig()
    # The real indicator reports this age; the gate is not patched.
    actual = snapshot(bars, config)["macd"]
    assert actual["cross_age"] == age
    assert (
        actual["cross_direction"] == direction == snapshot(bars, config)["supertrend"]["direction"]
    )
    result = evaluate(bars, bars[-1].end, config)
    assert macd_gate(result) == gate
    check = next(c for c in result["checks"] if c["rule"] == "R-MACD")
    assert check["state"] == gate
    if gate == "FAIL":
        assert not result["eligible"]


def test_default_window_is_the_latest_three_completed_candles():
    config = StrategyConfig()
    assert config.strategy_version == CURRENT_STRATEGY_VERSION == "3.2.0"
    assert config.crossover_freshness == MAX_MACD_CROSSOVER_AGE == 2
    assert StrategyConfig(crossover_freshness=0).crossover_freshness == 0
    assert StrategyConfig(crossover_freshness=1).crossover_freshness == 1
    for wider in (3, 4, 20):
        with pytest.raises(ValidationError):
            StrategyConfig(crossover_freshness=wider)


def test_stricter_saved_window_still_narrows():
    bars = case_bars(1, 1)
    assert macd_gate(evaluate(bars, bars[-1].end, StrategyConfig())) == "PASS"
    stricter = StrategyConfig(crossover_freshness=0)
    assert macd_gate(evaluate(bars, bars[-1].end, stricter)) == "FAIL"


def test_no_crossover_fails(monkeypatch):
    bars = case_bars(0, 1)
    config = StrategyConfig()
    assert macd_gate(evaluate(bars, bars[-1].end, config)) == "PASS"
    from services.nifty_algo import signal_engine

    def without_cross(series, *args):
        # Direction and histogram stay aligned: only the missing age decides.
        rows = macd(series, *args)
        rows[-1] = rows[-1] | {"cross_age": None}
        return rows

    monkeypatch.setattr(signal_engine, "macd", without_cross)
    assert macd_gate(evaluate(bars, bars[-1].end, config)) == "FAIL"


def test_real_series_before_any_crossover_fails():
    # A monotone rise has a defined histogram but no sign change to report.
    start = datetime(2026, 11, 2, 9, 15, tzinfo=IST)
    bars = [
        Candle(
            token=TOKEN,
            start=start + timedelta(minutes=5 * i),
            end=start + timedelta(minutes=5 * (i + 1)),
            timeframe=5,
            open=22000 + i * i,
            high=22001 + i * i,
            low=21999 + i * i,
            close=22000 + i * i,
            volume=10,
            provenance="TEST_FIXTURE",
        )
        for i in range(75)
    ]
    momentum = snapshot(bars, StrategyConfig())["macd"]
    assert momentum["cross_age"] is None and momentum["cross_direction"] == 0
    assert macd_gate(evaluate(bars, bars[-1].end, StrategyConfig())) == "FAIL"


@pytest.mark.parametrize("age", (0, 1, 2))
def test_wrong_direction_and_unaligned_histogram_fail(monkeypatch, age):
    bars = case_bars(age, 1)
    config = StrategyConfig()
    real = snapshot(bars, config)
    assert macd_gate(evaluate(bars, bars[-1].end, config)) == "PASS"
    from services.nifty_algo import signal_engine

    for change in ({"cross_direction": -1}, {"histogram": -abs(real["macd"]["histogram"])}):
        altered = real | {"macd": real["macd"] | change}
        monkeypatch.setattr(signal_engine, "snapshot", lambda b, c, s=altered: s if b else {})
        assert macd_gate(evaluate(bars, bars[-1].end, config)) == "FAIL"


@pytest.mark.parametrize("value", (-1, 2.0, "1", True, None))
def test_invalid_or_future_crossover_age_fails(monkeypatch, value):
    bars = case_bars(0, 1)
    config = StrategyConfig()
    real = snapshot(bars, config)
    altered = real | {"macd": real["macd"] | {"cross_age": value}}
    from services.nifty_algo import signal_engine

    monkeypatch.setattr(signal_engine, "snapshot", lambda b, c: altered if b else {})
    assert macd_gate(evaluate(bars, bars[-1].end, config)) == "FAIL"


def test_missing_macd_data_fails_safely():
    bars = case_bars(0, 1)
    # Too few candles for MACD 12/26/9: the gate reports UNAVAILABLE, never PASS.
    result = evaluate(bars[-20:], bars[-1].end, StrategyConfig())
    assert result["snapshot"]["macd"] is None
    assert macd_gate(result) == "UNAVAILABLE"
    assert not result["eligible"]
    empty = evaluate([], bars[-1].end, StrategyConfig())
    assert macd_gate(empty) == "UNAVAILABLE" and not empty["eligible"]


@pytest.mark.parametrize("age", (2, 3))
def test_forming_candle_is_never_counted(age):
    bars = case_bars(age, 1)
    now = bars[-1].end
    expected = evaluate(bars, now, StrategyConfig())
    nxt = bars[-1].model_copy(
        update={"start": bars[-1].end, "end": bars[-1].end + timedelta(minutes=5)}
    )
    # A forming candle (end in the future) and one flagged incomplete are both
    # ignored, so the age stays what the completed candles say.
    assert evaluate([*bars, nxt], now, StrategyConfig()) == expected
    incomplete = nxt.model_copy(update={"end": now, "start": now - timedelta(minutes=5)})
    incomplete = incomplete.model_copy(update={"complete": False})
    assert evaluate([*bars[:-1], incomplete], now, StrategyConfig())["snapshot"]["end"] == (
        bars[-2].end.isoformat()
    )
    assert expected["snapshot"]["macd"]["cross_age"] == age


def test_candle_ending_exactly_now_is_completed_and_counted():
    bars = case_bars(2, 1)
    result = evaluate(bars, bars[-1].end, StrategyConfig())
    assert result["snapshot"]["end"] == bars[-1].end.isoformat()
    assert result["snapshot"]["macd"]["cross_age"] == 2
    assert macd_gate(result) == "PASS"
    # One microsecond earlier the last candle is still forming: age 1 on the
    # previous completed candle.
    earlier = evaluate(bars, bars[-1].end - timedelta(microseconds=1), StrategyConfig())
    assert earlier["snapshot"]["end"] == bars[-2].end.isoformat()
    assert earlier["snapshot"]["macd"]["cross_age"] == 1


@pytest.mark.parametrize("zero_required", (False, True))
def test_zero_line_option_unchanged(zero_required):
    bars = case_bars(1, 1)
    config = StrategyConfig(macd_zero_required=zero_required)
    momentum = snapshot(bars, config)["macd"]
    expected = "PASS" if not zero_required or momentum["line"] > 0 else "FAIL"
    assert macd_gate(evaluate(bars, bars[-1].end, config)) == expected


# Compatibility --------------------------------------------------------------


def legacy_record(freshness=3, **changes):
    values = StrategyConfig().model_dump(mode="json")
    values.update({"strategy_version": "3.1.0", "crossover_freshness": freshness} | changes)
    return values


def test_legacy_record_replays_with_its_own_rule():
    """A stored 3.1.0 record keeps its identity and its historical decisions."""
    bars = case_bars(3, 1)
    legacy = StrategyConfig.model_validate(legacy_record())
    assert legacy.crossover_freshness == 3
    # Same content, same identity: the stored configuration_id still matches.
    assert legacy.version_id == StrategyConfig.model_validate(legacy_record()).version_id
    assert legacy.version_id != StrategyConfig().version_id
    assert macd_gate(evaluate(bars, bars[-1].end, legacy)) == "PASS"
    assert macd_gate(evaluate(bars, bars[-1].end, StrategyConfig())) == "FAIL"


@pytest.mark.parametrize("freshness", (3, 4, 20))
def test_legacy_record_cannot_evaluate_new_entries(freshness):
    record = legacy_record(freshness)
    assert StrategyConfig.model_validate(record).crossover_freshness == freshness
    with pytest.raises(ValidationError) as refused:
        active_configuration(record)
    assert [list(e["loc"]) for e in refused.value.errors()] == [["strategy_version"]]
    with pytest.raises(ValidationError):
        active_configuration(StrategyConfig.model_validate(record))


def test_current_version_cannot_claim_a_wider_window():
    values = StrategyConfig().model_dump(mode="json") | {"crossover_freshness": 3}
    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(values)
    with pytest.raises(ValidationError):
        active_configuration(values)


@pytest.mark.parametrize(("saved", "migrated"), ((0, 0), (1, 1), (2, 2), (3, 2), (20, 2)))
def test_migration_narrows_never_widens(saved, migrated):
    config = migrate_configuration(legacy_record(saved))
    assert config.strategy_version == "3.2.0"
    assert config.crossover_freshness == migrated
    # Nothing else in the record changes.
    before = legacy_record(saved)
    after = config.model_dump(mode="json")
    assert {k for k in before if before[k] != after[k]} <= {
        "strategy_version",
        "crossover_freshness",
    }


@pytest.mark.parametrize("version", ("1.0.0", "2.0.0", "3.0.0"))
def test_older_chains_reach_the_three_candle_window(version):
    record = legacy_record(20, strategy_version=version)
    config = migrate_configuration(record)
    assert config.strategy_version == "3.2.0"
    assert config.crossover_freshness == 2


@pytest.mark.parametrize("value", ("3", 3.5, -1))
def test_migration_refuses_an_unreadable_window(value):
    with pytest.raises(ValidationError):
        migrate_configuration(legacy_record(value))


def test_unknown_version_stays_blocked():
    with pytest.raises(ValidationError):
        migrate_configuration(legacy_record(strategy_version="9.9.9"))


def test_confidence_recency_is_relative_to_the_window():
    """Documented scoring effect: recency is 1 - age / (freshness + 1)."""
    st = {"atr": 10.0, "duration": 5, "distance": 5.0, "direction": 1}

    class Pcr:
        value = 2.0

    def score(age, config):
        snap = {
            "supertrend": st,
            "macd": {"cross_age": age, "histogram": 1.0},
            "adx": {"adx": 30.0},
            "price": 100.0,
            "vwap": 100.0,
        }
        result = confidence_module.signal_strength(snap, {"supertrend": st}, Pcr, 1, config)
        return result["contributions"]["macd"]["normalized"]

    current = StrategyConfig()
    assert [score(age, current) for age in (0, 1, 2)] == pytest.approx(
        [0.55, 0.55 - 1 / 6, 0.55 - 1 / 3]
    )
    legacy = StrategyConfig.model_validate(legacy_record())
    assert [score(age, legacy) for age in (0, 1, 2, 3)] == pytest.approx([0.55, 0.425, 0.3, 0.175])


@pytest.fixture
def store(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'macd.db'}")
    value = NiftyStore(engine)
    value.initialize()
    yield value
    engine.dispose()


def test_stored_legacy_configuration_migrates_with_history(store):
    store.read(USER)
    with store.sessions.begin() as db:
        state = db.get(NiftyState, USER)
        state.configuration = legacy_record()
        state.configuration_id = StrategyConfig.model_validate(legacy_record()).version_id
        state.state = "RUNNING"
        previous_revision = state.revision
        previous_id = state.configuration_id
    store.ensure_user(USER)
    state = store.read(USER)
    assert state["state"] == "PAUSED"
    assert state["configuration"]["strategy_version"] == "3.2.0"
    assert state["configuration"]["crossover_freshness"] == 2
    assert (
        state["configuration_id"]
        == StrategyConfig.model_validate(state["configuration"]).version_id
    )
    assert state["configuration_id"] != previous_id
    from sqlalchemy import select

    with store.sessions() as db:
        history = db.get(NiftyConfiguration, (USER, state["revision"]))
        events = list(
            db.scalars(
                select(NiftyEvent).where(
                    NiftyEvent.user_id == USER, NiftyEvent.kind == "configuration_migration"
                )
            )
        )
    assert state["revision"] == previous_revision + 1
    assert history.configuration == state["configuration"]
    assert events[-1].payload == {
        "from": "3.1.0",
        "to": "3.2.0",
        "revision": state["revision"],
    }
    # Idempotent: a second start does not migrate again.
    store.ensure_user(USER)
    assert store.read(USER)["revision"] == state["revision"]


def test_store_refuses_to_save_a_legacy_configuration(store):
    state = store.read(USER)
    with pytest.raises(ValidationError):
        store.change(
            USER,
            state["revision"],
            configuration=StrategyConfig.model_validate(legacy_record()),
        )
    assert store.read(USER)["revision"] == state["revision"]
    saved = store.change(
        USER, state["revision"], configuration=StrategyConfig(crossover_freshness=1)
    )
    assert saved["configuration"]["crossover_freshness"] == 1
