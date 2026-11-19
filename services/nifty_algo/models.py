"""Provider-neutral domain contracts. Monetary values use Decimal rupees."""

from datetime import UTC, date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IST_NAME = "Asia/Kolkata"
D = Decimal


def utcnow() -> datetime:
    return datetime.now(UTC)


def money(value: Decimal) -> Decimal:
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_assignment=True)


class Instrument(Model):
    token: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    exchange: Literal["NSE", "NFO"]
    underlying: Literal["NIFTY"] = "NIFTY"
    kind: Literal["SPOT", "FUT", "CE", "PE"]
    expiry: date | None = None
    strike: Decimal | None = None
    lot_size: int = Field(gt=0)
    tick_size: Decimal = Field(gt=0)
    master_date: date
    tradable: bool = True
    delta: float | None = None
    delta_time: datetime | None = None

    @model_validator(mode="after")
    def metadata(self):
        if self.kind != "SPOT" and (self.exchange != "NFO" or self.expiry is None):
            raise ValueError("Derivative requires NFO and expiry")
        if self.kind in ("CE", "PE") and (self.strike is None or self.strike <= 0):
            raise ValueError("Option requires positive strike")
        if self.kind == "SPOT" and self.exchange != "NSE":
            raise ValueError("Spot requires NSE")
        if self.delta is not None and not -1 <= self.delta <= 1:
            raise ValueError("Invalid option delta")
        if self.delta_time is not None and self.delta_time.tzinfo is None:
            raise ValueError("Delta timestamp requires timezone")
        return self


class Quote(Model):
    token: str
    source_time: datetime
    received_time: datetime
    ltp: Decimal = Field(gt=0)
    bid: Decimal | None = Field(default=None, gt=0)
    ask: Decimal | None = Field(default=None, gt=0)
    bid_size: int = Field(default=0, ge=0)
    ask_size: int = Field(default=0, ge=0)
    volume: int | None = Field(default=None, ge=0)
    oi: int | None = Field(default=None, ge=0)
    sequence: int = 0
    provider: str

    @field_validator("source_time", "received_time")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def spread(self):
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("Crossed quote")
        return self


class Candle(Model):
    token: str
    start: datetime
    end: datetime
    timeframe: Literal[1, 5, 15]
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int | None = Field(default=None, ge=0)
    complete: bool = True
    provenance: str

    @field_validator("start", "end")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid(self):
        if self.start.tzinfo is None or self.end.tzinfo is None or self.end <= self.start:
            raise ValueError("Invalid candle timestamps")
        if self.high < max(self.open, self.close, self.low) or self.low > min(
            self.open, self.close
        ):
            raise ValueError("Invalid OHLC")
        if (self.end - self.start).total_seconds() != self.timeframe * 60:
            raise ValueError("Candle interval does not match timeframe")
        return self


class PCR(Model):
    value: float = Field(ge=0)
    kind: Literal["OI", "VOLUME"]
    scope: str
    source_time: datetime
    coverage: float = Field(ge=0, le=1)
    verified: bool = False

    @field_validator("source_time")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        return value.astimezone(UTC)
