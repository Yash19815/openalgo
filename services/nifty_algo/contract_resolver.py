from decimal import Decimal
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def liquid(instrument, quote, now, config):
    if quote is None or quote.token != instrument.token:
        return False
    if not 0 <= (now - quote.source_time).total_seconds() <= config.quote_max_age:
        return False
    if not quote.source_time <= quote.received_time <= now:
        return False
    if (
        not quote.bid
        or not quote.ask
        or quote.bid_size < instrument.lot_size
        or quote.ask_size < instrument.lot_size
    ):
        return False
    return (
        (quote.ask - quote.bid) / quote.ask * 10000 <= config.max_spread_bps
        and quote.volume is not None
        and quote.volume >= config.min_volume
    )


class Resolver:
    def resolve(self, instruments, quotes, spot, side, now, config):
        spot = Decimal(str(spot))
        if side not in ("CE", "PE") or not spot.is_finite() or spot <= 0:
            raise ValueError("Valid spot and CE/PE side required")
        day = now.astimezone(IST).date()
        options = [
            i
            for i in instruments
            if i.exchange == "NFO"
            and i.underlying == "NIFTY"
            and i.kind == side
            and i.tradable
            and i.expiry >= day
            and i.master_date == day
            and (not config.avoid_expiry_day or i.expiry > day)
        ]
        if not options:
            raise ValueError("No current valid NIFTY option metadata")
        expiry = min(i.expiry for i in options)
        options = [i for i in options if i.expiry == expiry]
        strikes = sorted({i.strike for i in options})
        atm = min(strikes, key=lambda s: (abs(s - spot), s))
        index = strikes.index(atm)
        if config.selection in ("ITM", "OTM"):
            shift = -1 if (side == "CE") == (config.selection == "ITM") else 1
            if not 0 <= index + shift < len(strikes):
                raise ValueError("Adjacent listed strike missing")
            atm = strikes[index + shift]
        if config.selection == "DELTA":
            # Delta must be attached to current metadata by a trusted same-time Greeks adapter.
            # The initial Angel adapter deliberately does not populate unverified Greeks.
            options = [
                i
                for i in options
                if i.delta is not None
                and i.delta_time is not None
                and 0 <= (now - i.delta_time).total_seconds() <= config.quote_max_age
            ]
            if not options:
                raise ValueError("Reliable synchronized Greeks unavailable")
            selected = min(options, key=lambda i: abs(abs(i.delta) - config.delta_target))
        else:
            selected = next(i for i in options if i.strike == atm)
        if not liquid(selected, quotes.get(selected.token), now, config):
            raise ValueError("Selected contract fails fresh depth, volume or spread requirements")
        return selected
