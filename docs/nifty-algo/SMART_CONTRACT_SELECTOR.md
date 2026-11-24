# Smart Contract Selector

The resolver supplies only approved-expiry NIFTY ATM/ITM candidates from listed
metadata. The existing risk planner evaluates each permitted contract/lot pair.
No scoring result authorizes execution: admission, current safety state,
reservation and final fill validation remain authoritative.

## Scoring policy

`risk-approved-weighted-v2-oi` uses Decimal arithmetic. Each factor is in [0, 1];
the weighted total is in [0, 100]. `clamp(x)` means min(1, max(0, x)).

| Factor | Default weight | Normalization |
| --- | ---: | --- |
| Liquidity | 30 | 0.75 × clamp(min(bid size, ask size) / quantity / 3) + 0.25 × clamp(min(volume, fresh OI) / (3 × minimum volume)) |
| Spread | 25 | clamp(1 − midpoint spread in basis points / maximum spread) |
| Delta | 15 | clamp(1 − abs(abs(delta) − target) / max(target, 1 − target)) |
| Net reward/risk | 20 | clamp(projected net reward / planned loss / 2) |
| Capital efficiency | 10 | clamp(projected net reward / required cash / maximum target fraction) |

Missing, stale or directionally inconsistent Delta earns zero under its original
15% weight. Other weights are never increased to compensate. The default ATM
candidate path remains usable without Greeks. The pre-existing explicit DELTA
selection mode still requires trustworthy Greeks; this baseline limitation is
not silently removed.

The owner approved fresh OI capping the existing volume contribution. No new
threshold or top-level weight was introduced. Missing OI contributes zero to
that volume term; observed depth retains its existing 75% share of liquidity.
OI uses the same validated source observation and freshness gates as the quote.
Rankings expose OI availability, raw OI and the capped volume. This is a scoring
input, not a substitute for the full-quantity depth and risk admission checks.

Only pairs meeting existing loss, reward, funds, confidence lot limits and
entry/exit displayed-depth requirements are scored. One-to-one reward/risk is
not a hard gate. Required cash includes entry and modeled exit charges.
Ties use lower planned loss, lower required cash, expiry, strike, token and
lot count. Input ordering cannot change a tied winner.

## Settings and evidence

`selector_weights` has five nonnegative values totaling exactly 100, in the
table's order. Strategy Settings exposes validated controls. Default weights
preserve existing v3.1 configuration identities; the ranking policy version
identifies the extension. Nondefault weights create a different configuration
identity. Existing open-position configurations and stops are retained.

`contract_quantities:PAPER` events retain raw inputs, scores, weights, coverage,
proposals and rejection codes. Entry orders freeze the winning sizing plan and
alternatives. Independent Shadow freezes sizing in its own protection payload,
without writing primary events. `GET /api/nifty-algo/selector` joins quantity
evidence only for the same decision/configuration identity. A refused Shadow
entry does not create an independent position record; its returned risk refusal
is not presented as a successful selection.

The panel distinguishes listed-contract eligibility from risk-approved weighted
proposals. A proposal is still an estimate. No qualified pair means zero lots
and NO TRADE. Ranking never changes ₹400 planned loss, ₹350 minimum projected
reward, the 8% initial stop or existing profit-lock behavior.

The inherited quote-age default is five seconds, not the requested initial
two-second engineering proposal. Real-feed threshold calibration and latency
evidence remain required. This difference is recorded in the integration audit.
