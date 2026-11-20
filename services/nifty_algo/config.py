"""Validated research settings; configuration changes create immutable versions."""

from datetime import date, time
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from .models import Model


class StrategyConfig(Model):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    strategy_version: Literal["2.0.0"] = "2.0.0"
    confidence_method: Literal["five-indicator-v1"] = "five-indicator-v1"
    virtual_capital: Decimal = Field(default=Decimal("100000"), gt=0)
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
    selection: Literal["ATM", "ITM", "OTM", "DELTA"] = "ATM"
    delta_target: float = Field(default=0.5, gt=0, lt=1)
    avoid_expiry_day: bool = True
    max_spread_bps: float = Field(default=150, gt=0, le=1000)
    min_volume: int = Field(default=1000, ge=1)
    quote_max_age: int = Field(default=5, ge=1, le=30)
    risk_fraction: Decimal = Field(default=Decimal("0.005"), gt=0, le=Decimal("0.02"))
    daily_loss_fraction: Decimal = Field(default=Decimal("0.015"), gt=0, le=Decimal("0.1"))
    max_positions: Literal[1] = 1
    max_lots: int = Field(default=1, ge=1, le=10)
    max_daily_entries: int = Field(default=3, ge=1, le=100)
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
    max_hold_minutes: int = Field(default=45, ge=1, le=360)
    technical_exit: bool = True
    atr_exit_multiple: float = Field(default=2, gt=0, le=10)
    entry_after: time = time(9, 30)
    entry_before: time = time(14, 45)
    exit_by: time = time(15, 10)
    latency_ms: int = Field(default=250, ge=1, le=10000)
    slippage_ticks: int = Field(default=1, ge=0, le=20)
    order_ttl_seconds: int = Field(default=10, ge=1, le=60)

    @model_validator(mode="after")
    def ordered(self):
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
        if self.trailing_distance_points != min(self.trailing_candidates):
            raise ValueError("Trailing distance must equal minimum trailing candidate")
        return self

    @property
    def version_id(self):
        """Content identity for immutable strategy settings."""
        return sha256(self.model_dump_json().encode()).hexdigest()


def migrate_configuration(values):
    """Return a validated v2 revision. The caller retains history and pauses entries.

    Only the known v1 schema is migrated automatically. Unknown configurations
    remain blocked rather than receiving guessed settings.
    """
    if values.get("strategy_version", "1.0.0") != "1.0.0":
        return StrategyConfig.model_validate(values)
    changed = dict(values)
    changed.pop("target", None)
    changed.pop("trailing", None)
    changed["strategy_version"] = "2.0.0"
    try:
        changed["premium_stop"] = str(
            min(Decimal(str(values.get("premium_stop", "0.08"))), Decimal("0.08"))
        )
    except ArithmeticError:
        raise ValueError("Invalid legacy premium stop") from None
    return StrategyConfig.model_validate(changed)
