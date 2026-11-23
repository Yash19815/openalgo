# Advanced Performance Analytics

Analytics reads `NiftyTrade` and the original reconciled BUY/SELL fill rows.
It does not maintain another P&L ledger. The existing workspace and PDF renderer
provide period filters, realized curves, pagination and exports.

## Accounting and formulas

Periods are half-open. All financial calculations use Decimal. Trades with
partial exits share one entry identity; cash realizes on each exit timestamp.

| Metric | Formula / requirement |
| --- | --- |
| Gross realized | Sum((exit price − entry price) × closed quantity) |
| Costs | Persisted allocated entry charges plus exit charges |
| Net realized | Gross realized minus costs; must reconcile with stored net |
| Win rate | Positive-net trades / trades with realized exits in period |
| Profit factor | Sum positive trade net / absolute sum negative trade net; null without losses |
| Average win/loss | Mean net within the winning/losing subset |
| Expectancy | Total trade net / trade count; null for an empty sample |
| Equity | ₹20,000 seed plus committed net realized results |
| Maximum drawdown | Largest prior realized-equity peak minus subsequent realized equity |
| Holding duration | Final included exit time minus entry time |
| Sampled MFE | max(0, highest observed bid − entry price) × closed quantity |
| Sampled MAE | max(0, entry price − lowest observed bid) × closed quantity |
| Gross profit capture | Realized gross / sampled gross MFE; null without positive MFE |

Capture can exceed one if sampled bids missed a better fill. It is not a
continuous-market extreme or a net-of-fees counterfactual. Missing historical
low-bid evidence is null, not zero. Observed MTM drawdown and unrealized P&L are
unavailable without an authoritative mark series.

Breakdowns include IST day/week/month, entry hour, CE/PE, expiry distance,
moneyness, confidence, selector score, weekday, duration and exit reason.
Missing dimensions use UNAVAILABLE. Group trade counts can overlap for partial
exits across periods; do not add them as independent trades.

## Trade inspection and exit research

`GET /api/nifty-algo/analytics/trades/<id>` verifies owner and fill arithmetic,
then supplies frozen signal/configuration, selector sizing, fill observations,
protection, bounded stop history and incident timeline. Timeline correlation by
time is explicitly weaker than proven causality. Stop history retains 256
transitions and reports omissions. Sampling counts and maximum gaps are exposed.

The independent capture job observes recently closed trades using cached,
validated bids until the approved effective session close. It accepts samples
no older than two seconds, refuses duplicate/reordered timestamps and preserves
calendar identity. Checkpoints at 5, 15 and 30 minutes require observations
within two seconds; it does not interpolate missing checkpoints or stop at
45 minutes. A calendar change requires review rather than rewriting history.

`nifty_algo_exit_study` stores bounded aggregate research per closed fill, not
realized returns. No valid feed means unavailable research. Recorded extrema
are sampled, and gaps remain visible. A later favorable price does not prove
the earlier protective exit was wrong.

Primary Paper, inaccessible Live, independent Shadow, non-additive actual
mirrors and research remain separate. Complete comparative dashboards,
evidence-based recommendation generation, continuous excursion coverage,
execution-quality metrics and external validation remain acceptance gaps.
Daily/monthly PDFs now include recorded protection and safety event counts
through the original report and Gmail delivery workflow.
