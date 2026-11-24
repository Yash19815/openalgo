"""Read-only PDF export of an authoritative, bounded analytics snapshot."""

from .reports import render_pdf


def analytics_pdf(snapshot, generated_at):
    metrics = snapshot["metrics"]
    risk = metrics["risk_coverage"]
    details = snapshot["details"]
    sections = [
        (
            "Scope and evidence",
            [
                ["Start (inclusive, UTC)", snapshot["period"]["start"]],
                ["End (exclusive, UTC)", snapshot["period"]["end"]],
                ["Committed trade watermark", str(snapshot["watermark"])],
                ["Opening realized equity (Rs)", snapshot["opening_realized_equity"]],
                ["Marked unrealized P&L", "Unavailable: NO_PERSISTED_MARK_SERIES"],
            ],
            "Paper fills only. Equity is seed plus realized net, not mark-to-market. "
            "Partial exits count once per entry in trade statistics and separately in the fill curve. "
            "Only exits inside this period contribute to period statistics.",
        ),
        (
            "Full-period performance",
            [
                ["Trades with exits", str(metrics["trades"])],
                ["Realized fills", str(metrics["fills"])],
                [
                    "Winners / losers / breakeven",
                    f"{metrics['wins']} / {metrics['losses']} / {metrics['breakeven']}",
                ],
                [
                    "Gross / costs / net (Rs)",
                    f"{metrics['total_gross']} / {metrics['costs']} / {metrics['total_net']}",
                ],
                ["Best / worst (Rs)", f"{metrics['best']} / {metrics['worst']}"],
                [
                    "Win rate",
                    "Unavailable" if metrics["win_rate"] is None else f"{metrics['win_rate']:.2%}",
                ],
                [
                    "Profit factor",
                    str(metrics["profit_factor"])
                    if metrics["profit_factor"] is not None
                    else "Unavailable",
                ],
                ["Realized maximum drawdown (Rs)", metrics["maximum_drawdown"]],
                ["Average realized R", metrics["average_realized_r"] or "Unavailable"],
                ["Planned risk coverage", f"{risk['available']} of {risk['total']}"],
            ],
            "Metrics cover all selected-period fills, independent of the detail page. "
            "Observed mark-to-market drawdown is unavailable.",
        ),
        (
            "Daily realized net (IST)",
            [["Session", "Trades", "Net (Rs)"]]
            + [
                [day, str(values["trades"]), values["net"]]
                for day, values in sorted(metrics["groups"]["daily"].items())
            ],
            None,
        ),
        (
            "Selected fill page",
            [["Contract", "Quantity", "Net (Rs)"]]
            + [[row["symbol"], str(row["quantity"]), row["net"]] for row in details["items"]],
            f"{len(details['items'])} of {details['total']} fills; offset {details['offset']}. "
            "This detail page is not the full ledger. Use the analytics page to navigate other fills.",
        ),
    ]
    return render_pdf("NIFTY realized paper analytics", sections, generated_at)
