"""Validated research settings; configuration changes create immutable versions."""

from datetime import date, time
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from .models import Model


class StrategyConfig(Model):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    strategy_version: Literal["3.1.0"] = "3.1.0"
    confidence_method: Literal["five-indicator-v1"] = "five-indicator-v1"
    virtual_capital: Decimal = Field(
        default=Decimal("20000"), ge=Decimal("20000"), le=Decimal("20000")
    )
    atr_period: int = Field(default=10, ge=2, le=100)
    atr_multiplier: float = Field(default=3, gt=0, le=10)
    macd_fast: int = Field(default=12, ge=2, le=100)
    macd_slow: int = Field(default=26, ge=3, le=200)
    macd_signal: int = Field(default=9, ge=2, le=100)
    crossover_freshness: int = Field(default=3, ge=0, le=20)
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
    transaction_rate: Decimal = Field(default=Decimal("0.0005"), ge=0, le=1)
    gst_rate: Decimal = Field(default=Decimal("0.18"), ge=0, le=1)
    stt_sell_rate: Decimal = Field(default=Decimal("0.000625"), ge=0, le=1)
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


def migrate_configuration(values):
    """Return a validated v3.1 revision; unknown versions remain blocked."""
    version = values.get("strategy_version", "1.0.0")
    if version not in ("1.0.0", "2.0.0", "3.0.0"):
        return StrategyConfig.model_validate(values)
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
    return StrategyConfig.model_validate(changed)
