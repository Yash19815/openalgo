"""NIFTY sizing and entry gates, with exits evaluated by OpenAlgo's shared RMS."""

from dataclasses import dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo

from services.risk.models import PositionRisk
from services.risk.position import evaluate_position

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
    premium = quote.ask
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
    """Caller supplies native calendar and reconciled Sandbox account observations."""
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
    entry_price, quantity, bid, config, *, highest_price=None, stop_price=None
):
    """Translate percentage settings once and defer price-exit decisions to shared RMS."""
    entry = float(entry_price)
    high = max(entry, float(highest_price or entry), float(bid or entry))
    initial_stop = entry * (1 - float(config.premium_stop))
    # The shared continuous trail accepts an absolute distance. Recompute that
    # distance from the observed peak to retain the configured percentage trail.
    risk = PositionRisk(
        side="BUY",
        entry_price=entry,
        quantity=quantity,
        initial_stop_price=initial_stop,
        stop_price=stop_price,
        target_price=entry * (1 + float(config.target)),
        trailing_enabled=high > entry,
        highest_price=highest_price,
        trail_step=high * float(config.trailing),
        trail_trigger=0,
    )
    return evaluate_position(risk, bid)
