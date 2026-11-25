"""Pure versioned fee estimates. Never accesses a broker or either trading ledger.

The candidate schedule is offline-only until statutory and broker rounding are
fully reconciled. See docs/nifty-algo/REMAINING_REMEDIATION_2026-11.md.
"""

from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

D = Decimal


def configured_total(side, price, quantity, config):
    """Pinned simulated estimates, never actual contract-note charges.

    Legacy configurations preserve their historical formula. Strategy 3.3.0
    includes IPFT and SEBI in the GST base, with the configured published-rate
    floors checked before a new entry. Total estimates round upward to 0.0001;
    statutory client/day STT rounding remains distinct from per-fill estimates.
    """
    if config.strategy_version in ("3.1.0", "3.2.0"):
        return configured_legacy_total(side, price, quantity, config)
    turnover = price * quantity
    transaction = turnover * config.transaction_rate
    sebi, ipft = turnover * config.sebi_rate, turnover * D("0.000000001")
    gst = (config.brokerage + transaction + sebi + ipft) * config.gst_rate
    stt = turnover * config.stt_sell_rate if side == "SELL" else D(0)
    stamp = turnover * config.stamp_buy_rate if side == "BUY" else D(0)
    return (config.brokerage + transaction + sebi + ipft + gst + stt + stamp).quantize(
        D("0.0001"), rounding=ROUND_CEILING
    )


def estimate_metadata(config):
    return {
        "method": "configured-legacy-v1"
        if config.strategy_version in ("3.1.0", "3.2.0")
        else "configured-nse-options-2026-04-estimate-v1",
        "actual_contract_note": False,
        "rounding": "TOTAL_CEILING_0.0001_SIMULATED",
        "broker_rounding_verified": False,
        "ipft_rate": "0" if config.strategy_version in ("3.1.0", "3.2.0") else "0.000000001",
    }


def configured_legacy_total(side, price, quantity, config):
    """Exact historical configured-legacy-v1 arithmetic, including its GST base."""
    turnover = price * quantity
    txn = turnover * config.transaction_rate
    gst = (config.brokerage + txn) * config.gst_rate
    stt = turnover * config.stt_sell_rate if side == "SELL" else D(0)
    stamp = turnover * config.stamp_buy_rate if side == "BUY" else D(0)
    sebi = turnover * config.sebi_rate
    return (config.brokerage + txn + gst + stt + stamp + sebi).quantize(
        D("0.0001"), rounding=ROUND_CEILING
    )


def candidate_angel_schedule(day):
    """Published tariff candidates; these do not certify contract-note rounding."""
    if not isinstance(day, date) or day < date(2024, 10, 1):
        raise ValueError("No verified candidate tariff for this date")
    march = day >= date(2026, 3, 1)
    return {
        "version": "angel-nse-options-2026-04-candidate"
        if day >= date(2026, 4, 1)
        else "angel-nse-options-2026-03-candidate"
        if march
        else "angel-nse-options-2024-10-candidate",
        "transaction_rate": D("0.000355299") if march else D("0.0003503"),
        "ipft_rate": D("0.000000001") if march else D("0.000005"),
        "stt_sell_rate": D("0.0015") if day >= date(2026, 4, 1) else D("0.001"),
        "stamp_buy_rate": D("0.00003"),
        "sebi_rate": D("0.000001"),
        "gst_rate": D("0.18"),
        "brokerage": D("20"),
    }


def candidate_breakdown(side, price, quantity, day):
    """Offline sensitivity estimate, unrounded components and conservative total.

    One executed full-quantity order is assumed. The implementation does not
    round STT per fill: published STT rounding belongs to the client's daily
    aggregate. GST/IPFT treatment and remaining component-rounding evidence
    still require reconciliation before activating this model.
    """
    price = D(str(price))
    if side not in ("BUY", "SELL") or not price.is_finite() or price <= 0:
        raise ValueError("Positive finite premium and BUY/SELL required")
    if type(quantity) is not int or quantity <= 0:
        raise ValueError("Positive integer quantity required")
    schedule = candidate_angel_schedule(day)
    turnover = price * quantity
    parts = {"brokerage": schedule["brokerage"]}
    for name, rate in (
        ("exchange", "transaction_rate"),
        ("sebi", "sebi_rate"),
        ("ipft", "ipft_rate"),
    ):
        parts[name] = turnover * schedule[rate]
    parts["gst"] = sum(parts.values()) * schedule["gst_rate"]
    parts["stt"] = turnover * schedule["stt_sell_rate"] if side == "SELL" else D(0)
    parts["stamp"] = turnover * schedule["stamp_buy_rate"] if side == "BUY" else D(0)
    return {
        "method": schedule["version"],
        "components": parts,
        "total": sum(parts.values()).quantize(D("0.0001"), rounding=ROUND_CEILING),
        "actual_contract_note": False,
        "active": False,
    }


def round_daily_stt(components):
    """NSE client/day aggregate rounding; never mutate recorded fill charges."""
    values = [D(str(value)) for value in components]
    if any(not value.is_finite() or value < 0 for value in values):
        raise ValueError("Finite nonnegative STT components required")
    return sum(values, D(0)).quantize(D("1"), rounding=ROUND_HALF_UP)
