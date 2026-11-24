# Strategy assumptions and rule provenance

Current strategy configuration: 3.1.0. The strategy is a research hypothesis, not a
calibrated probability model or a claim of historical profitability.

The current phase requirements in PAPER_SYSTEM_DESIGN.md supersede the older
v2 sizing and entry-window assumptions. Advanced feature limitations are
recorded in ADVANCED_FEATURES_READINESS.md; earlier audit counts do not certify
later changes.

## Explicit user requirements

- Maximum initial stop distance: 8% of the confirmed simulated option fill; tighter is allowed.
- Trailing candidates: [1.5, 2.0]; effective distance: minimum, 1.5 option-premium price units.
- Profit target: a deterministic strength-sensitive percentage between 10% and 15% of entry premium.
- Five mandatory gates, completed 5-minute entries and 15-minute confirmation, independent risk approval, long NIFTY CE/PE only, isolated paper execution.

## Research defaults retained or introduced

Analysis uses the nearest eligible NIFTY future's actual OHLCV. Spot is a
separate strike reference. SuperTrend uses ATR 10 and multiplier 3; MACD uses
12/26/9 and a crossover within three completed entry bars; ADX uses Wilder 14
and minimum 25. Zero-line and DI confirmation remain configurable. Session
VWAP uses the same future's completed entry-candle typical price and volume;
missing session opening data or volume blocks execution, including a current
session whose first completed entry candle does not start at the open. Maximum
VWAP extension is 80 basis points. At least 80 entry and higher-timeframe bars
are required. Histories never combine futures identities across rollover.

Missing broker candles are never repaired or interpolated. A gap inside the
session being evaluated blocks that series. A gap in an earlier session
discards everything up to it, and only the verified continuous suffix after the
latest gap is evaluated; the 80-bar warm-up, freshness, 15-minute and session
VWAP requirements then apply to that suffix unchanged. Before this, one missing
minute anywhere in the nine-day window blocked every signal until that day left
the window.

PCR defaults to OI, with volume explicitly selectable. Scope is one dated
expiry's full native master strike universe, not the 47-strike tracker window.
An optional `pcr_expiry` preserves a selected expiry; otherwise the nearest
eligible expiry is chosen. CE and PE must cover identical strikes. Maximum
source age is 90 seconds and maximum cross-leg skew is five seconds. Bullish
support starts at 1.5; bearish support is below 1.0. The midpoint does not pass.
The exact complete-market coverage and subscription entitlement require real
broker verification. Unknown master freshness or missing source fields block.

New paper accounts start with ₹20,000; existing balances never reset. Sizing
permits 1–3 lots subject to confidence, capital, depth, at most ₹400 planned
loss including estimated costs and buffer, and at least ₹350 projected net
reward. Only one primary entry per session is allowed. The retained 1.5% daily
loss gate is additional protection. Primary entry is 10:30–before 14:45 IST;
the holding limit is 45 minutes and exits are requested by 15:10 or five minutes
before an earlier native NFO close. The approved NFO calendar is required;
special sessions remain disabled. A loss blocks the next eligible session.
Monthly loss locks at ₹2,000; an optional configured profit target latches its
own monthly lock. Locks do not block exits or reset equity.

## Strength method: five-indicator-v1

Scoring runs only after every mandatory gate passes. Each component is clipped
to [0,1], receives weight 0.2 and contributes at most 20 points:

| Component | Normalized strength |
| --- | --- |
| SuperTrend | Half confirmed duration / 10, half absolute trend distance / (3 ATR) |
| MACD | Half crossover recency `1 - age/(freshness+1)`, half directional histogram / ATR |
| VWAP | `1 - abs(extension_bps)/configured_limit`; passing directional alignment is mandatory |
| ADX | `(ADX - minimum)/max(1,100-minimum)` |
| PCR | Directional margin beyond the qualifying threshold divided by that threshold |

Contributions retain normalized values, weights, points and explanations.
The sum, rounded to six decimals, is a strength score from 0 to 100.
Nominal target fraction is `target_min + (target_max-target_min)*score/100`.
Higher strength permits the configured lot-score tiers but never relaxes risk. Invalid scoring rejects
entry. Tick rounding preserves target bounds; if no valid tick exists inside
them, entry is rejected. Both nominal and tick-adjusted target fractions are
retained with the trade.

Trailing activation at entry +1.5 premium points is an implementation
assumption, independently configurable. Entry 100 produces initial stop 92;
bid 101.50 arms the trail; eligible peak 106 gives stop 104.50; peak 110 gives
108.50. A falling bid never lowers protection. Thresholds round upward to
valid contract ticks. Gaps, latency, stale data and insufficient depth can
produce worse realized results or leave an exit unfilled.

Configured fees are deterministic research estimates, not a statement of
current statutory rates. Brokerage and transaction, GST, STT, stamp and SEBI
rates are versioned. Verify their applicable effective rates before forwarding
a real-market paper study. Costs are included in sizing, final admission and
journal P&L. No historical accuracy is inferred from synthetic fixtures.
