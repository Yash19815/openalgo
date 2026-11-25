from decimal import Decimal
from zoneinfo import ZoneInfo

from .models import Instrument

IST = ZoneInfo("Asia/Kolkata")


def liquid(instrument, quote, now, config):
    return not liquidity_reasons(instrument, quote, now, config)


def liquidity_reasons(instrument, quote, now, config):
    """Explain the same executable-quote gates used by the baseline resolver."""
    if quote is None:
        return ["QUOTE_UNAVAILABLE"]
    if quote.token != instrument.token:
        return ["QUOTE_TOKEN_MISMATCH"]
    if not 0 <= (now - quote.source_time).total_seconds() <= config.quote_max_age:
        return ["QUOTE_STALE"]
    if not quote.source_time <= quote.received_time <= now:
        return ["QUOTE_TIME_INVALID"]
    if (
        not quote.bid
        or not quote.ask
        or quote.bid_size < instrument.lot_size
        or quote.ask_size < instrument.lot_size
    ):
        return ["DEPTH_INSUFFICIENT"]
    reasons = []
    if (quote.ask - quote.bid) / quote.ask * 10000 > config.max_spread_bps:
        reasons.append("SPREAD_EXCESSIVE")
    if quote.volume is None or quote.volume < config.min_volume:
        reasons.append("VOLUME_INSUFFICIENT")
    return reasons


def moneyness(instrument, spot, atm_strike=None):
    """Classify an option against spot, treating the listed ATM strike as ATM."""
    spot = Decimal(str(spot))
    strike = Decimal(str(instrument.strike))
    if atm_strike is not None and strike == Decimal(str(atm_strike)):
        return "ATM"
    if strike == spot:
        return "ATM"
    if instrument.kind == "CE":
        return "ITM" if strike < spot else "OTM"
    if instrument.kind == "PE":
        return "ITM" if strike > spot else "OTM"
    raise ValueError("Moneyness requires a CE or PE instrument")


def nearest_listed_strike(strikes, spot):
    """The listed strike nearest to spot, the lower strike at the exact midpoint.

    This is only the nearest strike. Whether it may be called ATM is decided by
    ``atm_reference``, which every consumer uses.
    """
    spot = Decimal(str(spot))
    strikes = sorted({Decimal(str(strike)) for strike in strikes if strike is not None})
    return min(strikes, key=lambda strike: (abs(strike - spot), strike)) if strikes else None


# NSE strike interval for NIFTY 50 weekly and monthly option contracts: 50
# points at every index level, 35-1-35 strikes (in the money, at the money, out
# of the money), set from the previous day's close. Source: NSE, "NIFTY 50 F&O",
# Strike Price Intervals,
# https://www.nseindia.com/static/products-services/equity-derivatives-nifty50
# (read 24 November 2026). Quarterly and half-yearly contracts use wider,
# level-dependent intervals (100 to 1500 points); the selector never chooses
# them, because it takes the nearest expiry. Do not widen this for them: a
# longer-dated contract then has no ATM label and falls back to the strict spot
# comparison, which refuses an out-of-the-money strike.
NIFTY_SHORT_TERM_STRIKE_INTERVAL = Decimal("50")
MAX_ATM_DISTANCE = NIFTY_SHORT_TERM_STRIKE_INTERVAL / 2


def atm_reference(strikes, spot):
    """The listed ATM strike for this spot, or None when it cannot be verified.

    One rule for the selector, admission, the locked write, fill and replay.
    A strike is ATM only when all of these hold:

    * strikes are listed on both sides of spot (``min <= spot <= max``);
    * it is the nearest listed strike, the lower one at an exact midpoint;
    * it is within half a strike interval of spot (``MAX_ATM_DISTANCE``).

    On the exchange's 50-point grid the nearest strike is never farther than 25
    points, so a larger distance means the grid is incomplete near spot: strikes
    are missing, or the master is partial. Missing strikes are never filled in
    and a gap is never assumed normal. With no ATM reference every caller falls
    back to the strict spot comparison, which refuses out-of-the-money options,
    and the selector refuses the selection outright.
    """
    spot = Decimal(str(spot))
    listed = sorted({Decimal(str(strike)) for strike in strikes if strike is not None})
    if not listed or not listed[0] <= spot <= listed[-1]:
        return None
    # Verify the actual grid neighbors, not the nearest surviving master row.
    # An exact listed grid strike needs no interpolation; between strikes both
    # adjacent grid rows must exist, including the lower midpoint tie-break.
    step = NIFTY_SHORT_TERM_STRIKE_INTERVAL
    lower = (spot // step) * step
    upper = lower if spot == lower else lower + step
    if lower not in listed or upper not in listed:
        return None
    nearest = nearest_listed_strike((lower, upper), spot)
    return nearest if abs(nearest - spot) <= MAX_ATM_DISTANCE else None


def listed_chain(instrument, instruments):
    """Current listed contracts of this option's own side and expiry, by token.

    Mirrors the selector's ladder: same exchange, underlying, expiry and side,
    tradable, on the same dated master. A strike outside it is not listed now.
    """
    return {
        item.token: item
        for item in instruments
        if item.exchange == instrument.exchange
        and item.underlying == instrument.underlying
        and item.expiry == instrument.expiry
        and item.kind == instrument.kind
        and item.tradable
        and item.master_date == instrument.master_date
    }


def current_moneyness(instrument, spot, instruments):
    """Classify an option against fresh spot and the ATM listed in current metadata.

    Returns (classification, atm_strike, reason). The ATM label is recomputed
    from the given spot every time, never carried from an earlier selection, so
    a contract that the underlying has moved away from becomes OTM and is
    refused. ``reason`` is set and the classification is None when the current
    verified metadata cannot vouch for this exact contract.

    The ATM strike comes from ``atm_reference``: the nearest listed strike, but
    only with strikes listed on both sides of spot and within half a strike
    interval of it. Outside the listed range, on a ladder too sparse to bracket
    spot, or with a gap near spot, "nearest" says nothing about moneyness, so
    the strict spot comparison applies and ``atm_strike`` is None: a sparse
    ladder never widens eligibility.
    """
    if spot is None:
        return None, None, "SPOT_REFERENCE_UNAVAILABLE"
    spot = Decimal(str(spot))
    chain = listed_chain(instrument, instruments)
    if not chain:
        return None, None, "MASTER_FRESHNESS_UNVERIFIED"
    if chain.get(instrument.token) != instrument:
        return None, None, "INSTRUMENT_IDENTITY_MISMATCH"
    if _conflicting_records(instrument, instruments):
        # The same token listed twice with different content: which record wins
        # would depend on the order of the master, so no record is trusted.
        return None, None, "INSTRUMENT_IDENTITY_MISMATCH"
    atm = atm_reference([item.strike for item in chain.values()], spot)
    return moneyness(instrument, spot, atm), atm, None


def _conflicting_records(instrument, instruments):
    seen = {}
    for item in instruments:
        if (
            item.exchange == instrument.exchange
            and item.underlying == instrument.underlying
            and item.expiry == instrument.expiry
            and item.kind == instrument.kind
            and item.tradable
            and item.master_date == instrument.master_date
            and seen.setdefault(item.token, item) != item
        ):
            return True
    return False


class SelectionUnavailable(ValueError):
    """Stable audit reason without exposing provider exception text."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class Resolver:
    def assess(self, instruments, quotes, spot, side, now, config):
        spot = Decimal(str(spot))
        if side not in ("CE", "PE") or not spot.is_finite() or spot <= 0:
            raise SelectionUnavailable(
                "SELECTOR_INPUT_INVALID", "Valid spot and CE/PE side required"
            )
        day = now.astimezone(IST).date()
        options, metadata_excluded = [], []
        for instrument in instruments:
            if (
                instrument.exchange != "NFO"
                or instrument.underlying != "NIFTY"
                or instrument.kind != side
            ):
                continue
            if not instrument.tradable:
                reason = "CONTRACT_NOT_TRADABLE"
            elif instrument.expiry < day:
                reason = "CONTRACT_EXPIRED"
            elif instrument.master_date != day:
                reason = "MASTER_STALE"
            elif config.avoid_expiry_day and instrument.expiry == day:
                reason = "EXPIRY_DAY_AVOIDED"
            else:
                options.append(instrument)
                continue
            metadata_excluded.append((instrument, reason))
        if not options:
            raise SelectionUnavailable(
                "CONTRACT_METADATA_UNAVAILABLE", "No current valid NIFTY option metadata"
            )
        identities = {}
        for item in options:
            if item.token in identities and identities[item.token] != item:
                raise SelectionUnavailable(
                    "INSTRUMENT_IDENTITY_MISMATCH", "Conflicting option token metadata"
                )
            identities[item.token] = item
        options = list(identities.values())
        expiry = min(i.expiry for i in options)
        metadata_excluded.extend(
            (i, "OUTSIDE_SELECTED_EXPIRY") for i in options if i.expiry != expiry
        )
        options = sorted(
            (i for i in options if i.expiry == expiry),
            key=lambda i: (i.strike, i.token, i.symbol),
        )
        expiry_options = options
        strikes = sorted({i.strike for i in options})
        # The same rule admission and fill re-apply against fresh spot.
        atm_strike = atm_reference(strikes, spot)
        if atm_strike is None and config.selection in ("ITM", "ATM"):
            # Spot outside the listed range, or a gap near spot: the listed
            # ladder cannot vouch for an ATM or an adjacent ITM strike, and a
            # contract offered here would be refused at admission.
            raise SelectionUnavailable(
                "ATM_REFERENCE_UNVERIFIED",
                "No verified at-the-money strike near spot in the listed strikes",
            )
        if config.selection == "ITM":
            itm_strikes = [
                strike
                for strike in strikes
                if moneyness(next(i for i in options if i.strike == strike), spot, atm_strike)
                == "ITM"
            ]
            adjacent = atm_strike + (
                -NIFTY_SHORT_TERM_STRIKE_INTERVAL
                if side == "CE"
                else NIFTY_SHORT_TERM_STRIKE_INTERVAL
            )
            if adjacent not in itm_strikes:
                raise SelectionUnavailable(
                    "ITM_STRIKE_UNAVAILABLE", "Adjacent listed ITM strike missing"
                )
            selected_strike = adjacent
            ordered_strikes = [selected_strike]
            if config.candidate_strike_window:
                ordered_strikes.append(atm_strike)
                ordered_strikes.extend(
                    strike
                    for strike in sorted(
                        itm_strikes,
                        key=lambda strike: (abs(strike - atm_strike), strike),
                    )[: config.candidate_strike_window]
                    if strike != selected_strike
                )
            ordered_strikes = list(dict.fromkeys(ordered_strikes))
            ordered = [i for strike in ordered_strikes for i in options if i.strike == strike]
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
                raise SelectionUnavailable(
                    "GREEKS_UNAVAILABLE", "Reliable synchronized Greeks unavailable"
                )
            ordered = sorted(
                [i for i in options if moneyness(i, spot, atm_strike) in ("ATM", "ITM")],
                key=lambda i: abs(abs(i.delta) - config.delta_target),
            )[: 2 * config.candidate_strike_window + 1]
        elif config.selection == "ATM":
            itm_strikes = [
                strike
                for strike in strikes
                if moneyness(next(i for i in options if i.strike == strike), spot, atm_strike)
                == "ITM"
            ]
            nearby_itm = sorted(
                itm_strikes,
                key=lambda strike: (abs(strike - atm_strike), strike),
            )[: config.candidate_strike_window]
            ordered = [
                i for strike in (atm_strike, *nearby_itm) for i in options if i.strike == strike
            ]
        # Never silently truncate executable choices; refuse ambiguous oversized metadata.
        if len(ordered) > 100:
            raise SelectionUnavailable(
                "CANDIDATE_BOUND_EXCEEDED", "Contract candidate bound exceeded"
            )
        ordered_tokens = {item.token for item in ordered}
        excluded = [item for item in expiry_options if item.token not in ordered_tokens]
        evidence = [*ordered, *excluded[: 100 - len(ordered)]]
        rows, ranked = [], []
        for instrument in evidence:
            quote = quotes.get(instrument.token)
            classification = moneyness(instrument, spot, atm_strike)
            if instrument.token in ordered_tokens:
                reasons = liquidity_reasons(instrument, quote, now, config)
            elif classification == "OTM":
                reasons = ["OTM_PROHIBITED"]
            elif config.selection == "DELTA" and (
                instrument.delta is None
                or instrument.delta_time is None
                or not 0 <= (now - instrument.delta_time).total_seconds() <= config.quote_max_age
            ):
                reasons = ["GREEKS_UNAVAILABLE"]
            else:
                reasons = ["OUTSIDE_SELECTION_WINDOW"]
            if not reasons:
                ranked.append(instrument.token)
            rows.append(
                {
                    "instrument": instrument.model_dump(mode="json"),
                    "moneyness": classification,
                    "quote": None if quote is None else quote.model_dump(mode="json"),
                    "reasons": reasons,
                    "rank": None if reasons else len(ranked),
                }
            )
        # Rejected metadata never becomes an executable choice or claims a quote.
        for instrument, reason in sorted(
            metadata_excluded,
            key=lambda pair: (
                pair[0].expiry,
                pair[0].strike,
                pair[0].token,
                pair[0].symbol,
                pair[0].master_date,
                pair[1],
            ),
        )[: 100 - len(rows)]:
            rows.append(
                {
                    "instrument": instrument.model_dump(mode="json"),
                    "moneyness": "NOT_ASSESSED",
                    "quote": None,
                    "reasons": [reason],
                    "rank": None,
                }
            )
        return {
            "status": "RANKED" if ranked else "REJECTED",
            "reasons": [] if ranked else ["CONTRACT_LIQUIDITY_UNAVAILABLE"],
            "policy": "listed-preference-v1",
            "configuration_id": config.version_id,
            "evaluated_at": now.isoformat(),
            "spot_reference": str(spot),
            "atm_strike": None if atm_strike is None else str(atm_strike),
            "expiry": expiry.isoformat(),
            "ranked_tokens": ranked,
            "candidates": rows,
            "omitted_candidates": len(expiry_options) + len(metadata_excluded) - len(rows),
        }

    def candidates(self, instruments, quotes, spot, side, now, config):
        report = self.assess(instruments, quotes, spot, side, now, config)
        suitable = [
            Instrument.model_validate(row["instrument"])
            for row in report["candidates"]
            if not row["reasons"]
        ]
        if not suitable:
            raise ValueError("Selected contract fails fresh depth, volume or spread requirements")
        return suitable

    def resolve(self, instruments, quotes, spot, side, now, config):
        return self.candidates(instruments, quotes, spot, side, now, config)[0]
