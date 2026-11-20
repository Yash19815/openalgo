"""NIFTY sizing, entry gates and Decimal option-premium protection adapters."""

from dataclasses import dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo

from .contract_resolver import liquid


@dataclass(frozen=True)
class AccountRisk:
    equity: Decimal
    available: Decimal
    starting_day_equity: Decimal
    open_positions: int = 0
    pending_entries: int = 0
    daily_entries: int = 0
    killed: bool = False
    daily_locked: bool = False
    reconciled: bool = False
    entries_enabled: bool = False

    def __post_init__(self):
        for field in ("equity", "available", "starting_day_equity"):
            value = Decimal(str(getattr(self, field)))
            if not value.is_finite() or value < 0:
                raise ValueError("Finite nonnegative account values required")
            object.__setattr__(self, field, value)
        if self.starting_day_equity <= 0:
            raise ValueError("Positive starting-day equity required")
        counts = (self.open_positions, self.pending_entries, self.daily_entries)
        if any(type(value) is not int or value < 0 for value in counts):
            raise ValueError("Nonnegative integer account counts required")


def size_quantity(account, instrument, quote, config, round_trip_cost_per_lot):
    """Floor whole lots after adverse stop tick and conservative round-trip cost."""
    money = (account.equity, account.available, round_trip_cost_per_lot)
    if any(not value.is_finite() or value < 0 for value in money) or not quote.ask:
        return 0
    premium = quote.ask + instrument.tick_size * config.slippage_ticks
    loss_per_unit = premium * config.premium_stop + instrument.tick_size * config.slippage_ticks
    for lots in range(config.max_lots, 0, -1):
        quantity = lots * instrument.lot_size
        costs = round_trip_cost_per_lot * lots
        if (
            loss_per_unit * quantity + costs <= account.equity * config.risk_fraction
            and premium * quantity + costs <= account.available
        ):
            return quantity
    return 0


def entry_reasons(account, instrument, quote, now, config, *, session_open, data_healthy):
    """Caller supplies native calendar and reconciled feature-ledger observations."""
    local = now.astimezone(ZoneInfo("Asia/Kolkata"))
    reasons = []
    checks = (
        (account.reconciled, "RECONCILIATION_REQUIRED"),
        (account.entries_enabled, "ENTRIES_PAUSED"),
        (not account.killed, "KILL_SWITCH"),
        (not account.daily_locked, "DAILY_LOCKOUT"),
        (session_open, "SESSION_CLOSED"),
        (data_healthy, "DATA_UNAVAILABLE"),
        (
            config.entry_after <= local.time().replace(tzinfo=None) < config.entry_before,
            "ENTRY_WINDOW",
        ),
        (
            instrument.exchange == "NFO"
            and instrument.underlying == "NIFTY"
            and instrument.kind in ("CE", "PE"),
            "INSTRUMENT_RESTRICTED",
        ),
        (
            instrument.tradable
            and instrument.expiry is not None
            and instrument.expiry >= local.date()
            and instrument.master_date == local.date(),
            "METADATA_INVALID",
        ),
        (not config.avoid_expiry_day or instrument.expiry != local.date(), "EXPIRY_DAY"),
        (liquid(instrument, quote, now, config), "LIQUIDITY_UNAVAILABLE"),
        (account.open_positions < config.max_positions, "POSITION_LIMIT"),
        (account.pending_entries == 0, "PENDING_ENTRY"),
        (account.daily_entries < config.max_daily_entries, "DAILY_ENTRY_LIMIT"),
        (
            account.starting_day_equity > 0
            and account.equity > account.starting_day_equity * (1 - config.daily_loss_fraction),
            "DAILY_LOSS_LIMIT",
        ),
    )
    for passed, reason in checks:
        if not passed:
            reasons.append(reason)
    return reasons


def evaluate_premium_exit(
    entry_price,
    quantity,
    bid,
    config,
    *,
    confidence,
    tick_size,
    highest_price=None,
    stop_price=None,
):
    """Pure Decimal adapter. Durable monitoring uses the same protection functions."""
    from types import SimpleNamespace

    from .protection import initial_protection, observe_bid

    protection = initial_protection(entry_price, tick_size, config, confidence)
    if highest_price is not None:
        protection = observe_bid(protection, entry_price, highest_price, tick_size, config)
        protection["exit_reason"] = None
    if stop_price is not None:
        protection["stop_price"] = str(
            max(Decimal(str(stop_price)), Decimal(protection["stop_price"]))
        )
    result = observe_bid(protection, entry_price, bid, tick_size, config)
    return SimpleNamespace(
        breached=bool(result["exit_reason"]),
        stop_price=Decimal(result["stop_price"]),
        target_price=Decimal(result["target_price"]),
        reason=result["exit_reason"],
    )
