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
        atm = min(strikes, key=lambda s: (abs(s - spot), s))
        atm_strike = atm
        if config.selection == "ITM":
            itm_strikes = [
                strike
                for strike in strikes
                if moneyness(next(i for i in options if i.strike == strike), spot, atm_strike)
                == "ITM"
            ]
            if not itm_strikes:
                raise SelectionUnavailable(
                    "ITM_STRIKE_UNAVAILABLE", "Adjacent listed ITM strike missing"
                )
            selected_strike = min(itm_strikes, key=lambda strike: abs(strike - atm_strike))
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
            "atm_strike": str(atm_strike),
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
