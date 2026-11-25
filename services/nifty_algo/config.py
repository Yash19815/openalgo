"""Validated research settings; configuration changes create immutable versions."""

from datetime import date, time
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator

from .models import Model

CURRENT_STRATEGY_VERSION = "3.3.0"
# Strategy versions whose stored records (held protection, pending orders,
# research manifests, replay baselines) still load and replay with their own
# rules. None of them may evaluate a new entry: see active_configuration.
LEGACY_STRATEGY_VERSIONS = ("3.1.0", "3.2.0")
# Approved 2026-11-24: a qualifying MACD crossover lies in one of the latest
# three completed 5-minute candles. The crossover candle is age 0, so ages 0,
# 1 and 2 qualify and age 3 or older does not. Version 3.1.0 admitted age 3.
MAX_MACD_CROSSOVER_AGE = 2


class StrategyConfig(Model):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    strategy_version: Literal["3.1.0", "3.2.0", "3.3.0"] = CURRENT_STRATEGY_VERSION
    confidence_method: Literal["five-indicator-v1", "five-indicator-v2-pinned"] = (
        "five-indicator-v2-pinned"
    )
    virtual_capital: Decimal = Field(
        default=Decimal("20000"), ge=Decimal("20000"), le=Decimal("20000")
    )
    atr_period: int = Field(default=20, ge=2, le=100)
    atr_multiplier: float = Field(default=2, gt=0, le=10)
    macd_fast: int = Field(default=12, ge=2, le=100)
    macd_slow: int = Field(default=26, ge=3, le=200)
    macd_signal: int = Field(default=9, ge=2, le=100)
    # Oldest admitted crossover age, inclusive. The range stays 0..20 only so
    # stored 3.1.0 records still load and replay unchanged; from 3.2.0 the
    # validator below caps it at MAX_MACD_CROSSOVER_AGE.
    crossover_freshness: int = Field(default=MAX_MACD_CROSSOVER_AGE, ge=0, le=20)
    macd_zero_required: bool = False
    adx_period: int = Field(default=14, ge=2, le=100)
    adx_min: float = Field(default=25, ge=0, le=100)
    di_confirmation: bool = False
    vwap_basis: Literal["typical", "close"] = "typical"
    vwap_max_bps: float = Field(default=80, gt=0, le=1000)
    pcr_kind: Literal["OI", "VOLUME"] = "OI"
    pcr_expiry: date | None = None
    pcr_bull: float = Field(default=1.5, gt=0, le=10)
    pcr_bear: float = Field(default=1, gt=0, le=10)
    pcr_max_age: int = Field(default=90, ge=1, le=600)
    pcr_max_skew_seconds: int = Field(default=5, ge=0, le=90)
    entry_timeframe: Literal[5] = 5
    confirmation_timeframe: Literal[15] = 15
    previous_candle_break: bool = False
    selection: Literal["ATM", "ITM", "DELTA"] = "ATM"
    candidate_strike_window: int = Field(default=2, ge=0, le=5)
    delta_target: float = Field(default=0.5, gt=0, lt=1)
    selector_weights: tuple[Decimal, Decimal, Decimal, Decimal, Decimal] = (
        Decimal("30"),
        Decimal("25"),
        Decimal("15"),
        Decimal("20"),
        Decimal("10"),
    )
    avoid_expiry_day: bool = True
    max_spread_bps: float = Field(default=150, gt=0, le=1000)
    min_volume: int = Field(default=1000, ge=1)
    quote_max_age: int = Field(default=5, ge=1, le=30)
    daily_loss_fraction: Decimal = Field(default=Decimal("0.015"), gt=0, le=Decimal("0.1"))
    max_positions: Literal[1] = 1
    max_lots: int = Field(default=3, ge=1, le=3)
    max_daily_entries: int = Field(default=1, ge=1, le=1)
    lot_score_thresholds: tuple[Decimal, ...] = (
        Decimal("0"),
        Decimal("40"),
        Decimal("70"),
    )
    max_planned_loss: Decimal = Field(default=Decimal("400"), ge=0, le=Decimal("400"))
    min_projected_net_reward: Decimal = Field(default=Decimal("350"), ge=Decimal("350"))
    planned_loss_buffer: Decimal = Field(default=Decimal("10"), ge=0)
    profit_lock_activation_net: Decimal = Field(
        default=Decimal("400"), ge=Decimal("400"), le=Decimal("400")
    )
    profit_lock_floor_net: Decimal = Field(
        default=Decimal("350"), ge=Decimal("350"), lt=Decimal("400")
    )
    early_booking_min_net: Decimal = Field(default=Decimal("300"), ge=Decimal("300"))
    early_booking_retrace_fraction: Decimal = Field(
        default=Decimal("0.30"),
        gt=0,
        le=1,
        description="Testable hypothesis for discretionary profit-booking retrace.",
    )
    monthly_loss_limit: Decimal = Field(default=Decimal("2000"), ge=0, le=Decimal("2000"))
    monthly_profit_target: Decimal | None = Field(default=None, gt=0)
    premium_stop: Decimal = Field(default=Decimal("0.08"), gt=0, le=Decimal("0.08"))
    target_min: Decimal = Field(default=Decimal("0.10"), ge=Decimal("0.10"), le=Decimal("0.15"))
    target_max: Decimal = Field(default=Decimal("0.15"), ge=Decimal("0.10"), le=Decimal("0.15"))
    trailing_candidates: tuple[Decimal, ...] = (Decimal("1.5"), Decimal("2.0"))
    trailing_distance_points: Decimal = Field(default=Decimal("1.5"), gt=0)
    trailing_activation_points: Decimal = Field(default=Decimal("1.5"), gt=0)
    point_unit: Literal["OPTION_PREMIUM"] = "OPTION_PREMIUM"
    brokerage: Decimal = Field(default=Decimal("20"), ge=0)
    transaction_rate: Decimal = Field(default=Decimal("0.000355299"), ge=0, le=1)
    gst_rate: Decimal = Field(default=Decimal("0.18"), ge=0, le=1)
    stt_sell_rate: Decimal = Field(default=Decimal("0.0015"), ge=0, le=1)
    stamp_buy_rate: Decimal = Field(default=Decimal("0.00003"), ge=0, le=1)
    sebi_rate: Decimal = Field(default=Decimal("0.000001"), ge=0, le=1)
    max_hold_minutes: int = Field(default=45, ge=1, le=45)
    technical_exit: bool = True
    atr_exit_multiple: float = Field(default=2, gt=0, le=10)
    shadow_entry_after: time = Field(default=time(9, 15), ge=time(9, 15))
    entry_after: time = Field(default=time(10, 30), ge=time(10, 30))
    entry_before: time = Field(default=time(14, 45), le=time(14, 45))
    exit_by: time = Field(default=time(15, 10), le=time(15, 10))
    latency_ms: int = Field(default=250, ge=1, le=10000)
    slippage_ticks: int = Field(default=1, ge=0, le=20)
    order_ttl_seconds: int = Field(default=10, ge=1, le=60)

    @model_validator(mode="before")
    @classmethod
    def historical_indicator_defaults(cls, values):
        # Sparse historical documents must not acquire new mathematical inputs
        # merely because they are deserialized by a newer application.
        if isinstance(values, dict) and values.get("strategy_version") in LEGACY_STRATEGY_VERSIONS:
            values = dict(values)
            values.setdefault("atr_period", 10)
            values.setdefault("atr_multiplier", 3)
            values.setdefault("confidence_method", "five-indicator-v1")
            values.setdefault("transaction_rate", "0.0005")
            values.setdefault("stt_sell_rate", "0.000625")
        return values

    @field_validator("confidence_method")
    @classmethod
    def pinned_confidence_method(cls, value, info):
        expected = (
            "five-indicator-v1"
            if info.data.get("strategy_version") in LEGACY_STRATEGY_VERSIONS
            else "five-indicator-v2-pinned"
        )
        if value != expected:
            raise ValueError("Confidence method must match the pinned strategy version")
        return value

    @field_validator("crossover_freshness")
    @classmethod
    def valid_crossover_freshness(cls, value, info):
        if info.data.get("strategy_version") != "3.1.0" and value > MAX_MACD_CROSSOVER_AGE:
            raise ValueError("MACD crossover must lie in the latest three completed entry candles")
        return value

    @model_validator(mode="after")
    def ordered(self):
        if (
            any(weight < 0 or weight > 100 for weight in self.selector_weights)
            or sum(self.selector_weights) != 100
        ):
            raise ValueError("Selector weights must be nonnegative and sum to 100")
        if self.macd_fast >= self.macd_slow or self.pcr_bear >= self.pcr_bull:
            raise ValueError("Invalid indicator bounds")
        if not self.entry_after < self.entry_before < self.exit_by:
            raise ValueError("Trading windows must be ordered")
        if self.target_min > self.target_max:
            raise ValueError("Profit target bounds must be ordered")
        if not self.trailing_candidates or any(
            not x.is_finite() or x <= 0 for x in self.trailing_candidates
        ):
            raise ValueError("Positive finite option-premium trailing candidates required")
        if (
            not self.lot_score_thresholds
            or len(self.lot_score_thresholds) > 3
            or self.lot_score_thresholds[0] != 0
            or any(not x.is_finite() or not 0 <= x <= 100 for x in self.lot_score_thresholds)
            or any(
                a >= b
                for a, b in zip(
                    self.lot_score_thresholds, self.lot_score_thresholds[1:], strict=False
                )
            )
        ):
            raise ValueError("Lot score thresholds must ascend from zero within 0..100")
        if self.profit_lock_floor_net >= self.profit_lock_activation_net:
            raise ValueError("Profit-lock floor must be below activation")
        if self.shadow_entry_after > self.entry_after:
            raise ValueError("Shadow entry must not start after entry")
        if self.trailing_distance_points != min(self.trailing_candidates):
            raise ValueError("Trailing distance must equal minimum trailing candidate")
        if self.trailing_distance_points != Decimal("1.5"):
            raise ValueError("Trailing distance is fixed at 1.5 option-premium points")
        return self

    @property
    def version_id(self):
        """Content identity for immutable strategy settings."""
        # Default ranking weights are identified by the stored ranking-policy
        # version. Preserve existing v3.1 strategy identities and held protection
        # during this additive extension; edited weights create a new identity.
        default_weights = type(self).model_fields["selector_weights"].default
        excluded = {"selector_weights"} if self.selector_weights == default_weights else None
        return sha256(self.model_dump_json(exclude=excluded).encode()).hexdigest()


def active_configuration(values):
    """Return a configuration allowed to evaluate new entries.

    A legacy version validates as a stored record so its protection, fills and
    replay keep their own rules, but it is refused here: a 3.1.0 record may
    admit a crossover older than age 2. Raises ValidationError, a ValueError.
    """
    config = values if isinstance(values, StrategyConfig) else StrategyConfig.model_validate(values)
    if config.strategy_version != CURRENT_STRATEGY_VERSION:
        raise ValidationError.from_exception_data(
            "StrategyConfig",
            [
                {
                    "type": "literal_error",
                    "loc": ("strategy_version",),
                    "input": config.strategy_version,
                    "ctx": {"expected": repr(CURRENT_STRATEGY_VERSION)},
                }
            ],
        )
    requirements = {
        "daily_loss_fraction": config.daily_loss_fraction <= Decimal("0.015"),
        "macd_fast": config.macd_fast == 12,
        "macd_slow": config.macd_slow == 26,
        "macd_signal": config.macd_signal == 9,
        "adx_period": config.adx_period == 14,
        "adx_min": config.adx_min >= 25,
        "vwap_basis": config.vwap_basis == "typical",
        "vwap_max_bps": config.vwap_max_bps <= 80,
        "pcr_max_age": config.pcr_max_age <= 90,
        "pcr_max_skew_seconds": config.pcr_max_skew_seconds <= 5,
        "pcr_bull": config.pcr_bull >= 1.5,
        "pcr_bear": config.pcr_bear <= 1,
        "trailing_activation_points": config.trailing_activation_points == Decimal("1.5"),
        "lot_score_thresholds": all(
            value >= floor
            for value, floor in zip(config.lot_score_thresholds, (0, 40, 70), strict=False)
        ),
        "brokerage": config.brokerage >= Decimal("20"),
        "transaction_rate": config.transaction_rate >= Decimal("0.000355299"),
        "stt_sell_rate": config.stt_sell_rate >= Decimal("0.0015"),
        "gst_rate": config.gst_rate >= Decimal("0.18"),
        "sebi_rate": config.sebi_rate >= Decimal("0.000001"),
        "stamp_buy_rate": config.stamp_buy_rate >= Decimal("0.00003"),
    }
    failures = [
        {
            "type": "value_error",
            "loc": (name,),
            "input": getattr(config, name),
            "ctx": {
                "error": ValueError(
                    "New PAPER entries must retain the approved strategy and published charge floors"
                )
            },
        }
        for name, valid in requirements.items()
        if not valid
    ]
    if failures:
        raise ValidationError.from_exception_data("StrategyConfig", failures)
    return config


def migrate_configuration(
    values, *, approve_supertrend=False, approve_fees=False, target_version=CURRENT_STRATEGY_VERSION
):
    """Return a validated current revision; unknown versions remain blocked."""
    if target_version not in ("3.2.0", CURRENT_STRATEGY_VERSION):
        raise ValueError("Unsupported migration target")
    version = values.get("strategy_version", "1.0.0")
    if version not in ("1.0.0", "2.0.0", "3.0.0", "3.1.0", "3.2.0"):
        return active_configuration(values)
    changed = dict(values)
    if version == "1.0.0":
        changed.pop("target", None)
        changed.pop("trailing", None)
        try:
            changed["premium_stop"] = str(
                min(Decimal(str(values.get("premium_stop", "0.08"))), Decimal("0.08"))
            )
        except ArithmeticError:
            raise ValueError("Invalid legacy premium stop") from None
        changed["strategy_version"] = "2.0.0"
    if changed.get("strategy_version") == "2.0.0":
        changed.pop("risk_fraction", None)
        try:
            changed["max_lots"] = min(3, max(1, int(changed.get("max_lots", 1))))
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Invalid legacy lot count") from None
        changed["max_daily_entries"] = 1
        changed["entry_after"] = time(10, 30).isoformat()
        changed["strategy_version"] = "3.0.0"
    if changed.get("strategy_version") == "3.0.0":
        if changed.get("selection") == "OTM":
            changed["selection"] = "ATM"
        changed["strategy_version"] = "3.1.0"
    if changed.get("strategy_version") == "3.1.0":
        # Narrow the MACD window to the approved three completed candles. A
        # stricter saved value (0 or 1) is the trader's choice and is kept; a
        # value that is not an integer is left for validation to refuse.
        freshness = changed.get("crossover_freshness", 3)
        if type(freshness) is int and freshness > MAX_MACD_CROSSOVER_AGE:
            changed["crossover_freshness"] = MAX_MACD_CROSSOVER_AGE
        changed["strategy_version"] = "3.2.0"

    if target_version == CURRENT_STRATEGY_VERSION:
        # Owner approval, 2026-11-25: pin ST /10,/3 and MACD /3 in a new
        # method. Historical records retain v1; only new revisions adopt v2.
        changed["confidence_method"] = "five-indicator-v2-pinned"
        # Explicit 10/3 is ambiguous: old saves serialized defaults and custom
        # choices identically. Equality alone does not prove migration consent.
        if (
            ("atr_period" in values or "atr_multiplier" in values)
            and float(values.get("atr_period", 10)) == 10
            and float(values.get("atr_multiplier", 3)) == 3
        ):
            if not approve_supertrend:
                raise ValueError("SUPERTrend_MIGRATION_APPROVAL_REQUIRED")
            changed.update(atr_period=20, atr_multiplier=2)
        elif "atr_period" not in values and "atr_multiplier" not in values:
            changed.update(atr_period=20, atr_multiplier=2)
        else:
            # Preserve each explicitly customized input and the old default of
            # an omitted partner field. Never infer approval to alter a custom.
            changed.setdefault("atr_period", 10)
            changed.setdefault("atr_multiplier", 3)
        # An explicit lower tariff may be a customized historical estimate.
        # Preserve it and pause until the operator reviews the published floor.
        for name, minimum in (
            ("stt_sell_rate", "0.0015"),
            ("transaction_rate", "0.000355299"),
            ("brokerage", "20"),
            ("gst_rate", "0.18"),
            ("sebi_rate", "0.000001"),
            ("stamp_buy_rate", "0.00003"),
        ):
            try:
                amount = Decimal(str(values[name])) if name in values else Decimal(minimum)
                if not amount.is_finite():
                    raise ValueError("Nonfinite legacy charge")
            except (ArithmeticError, TypeError, ValueError):
                raise ValueError("Invalid legacy charge") from None
            if name in values and amount < Decimal(minimum):
                if not approve_fees:
                    raise ValueError("FEE_MIGRATION_APPROVAL_REQUIRED")
                changed[name] = minimum
        changed["strategy_version"] = CURRENT_STRATEGY_VERSION

    if version == "3.2.0":
        if target_version == "3.2.0":
            changed["confidence_method"] = "five-indicator-v1"
        return (
            StrategyConfig.model_validate(changed)
            if target_version == "3.2.0"
            else active_configuration(changed)
        )

    if target_version == "3.2.0":
        changed["confidence_method"] = "five-indicator-v1"

    def _clamp(name, floor, ceiling=None):
        if name not in changed:
            return
        try:
            value = Decimal(str(changed[name]))
        except (ArithmeticError, TypeError, ValueError):
            return
        if value < floor:
            changed[name] = str(floor)
        elif ceiling is not None and value > ceiling:
            changed[name] = str(ceiling)

    # Legacy values may predate the current risk bounds; normalize them into
    # range rather than letting a persisted v1/v2 config fail validation.
    _clamp("virtual_capital", Decimal("20000"), Decimal("20000"))
    _clamp("max_planned_loss", Decimal("0"), Decimal("400"))
    _clamp("min_projected_net_reward", Decimal("350"))
    _clamp("planned_loss_buffer", Decimal("0"))
    # Existing v1/v2/v3 settings must migrate to the non-weakening guardrails.
    changed["profit_lock_activation_net"] = "400"
    _clamp("profit_lock_floor_net", Decimal("350"), Decimal("399.99"))
    _clamp("early_booking_min_net", Decimal("300"))
    _clamp("monthly_loss_limit", Decimal("0"), Decimal("2000"))
    _clamp("daily_loss_fraction", Decimal("0.0001"), Decimal("0.1"))
    try:
        if Decimal(str(changed.get("profit_lock_floor_net", "350"))) >= Decimal(
            str(changed.get("profit_lock_activation_net", "400"))
        ):
            changed["profit_lock_floor_net"] = "350"
            changed["profit_lock_activation_net"] = "400"
    except (ArithmeticError, TypeError, ValueError):
        pass
    return (
        StrategyConfig.model_validate(changed)
        if target_version == "3.2.0"
        else active_configuration(changed)
    )
