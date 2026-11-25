# NIFTY indicator parity against OpenAlgo SDK 2.4.1

Historical applicability: this report records strategy 3.2.0 and SuperTrend
10/3. Strategy 3.3.0 adds 20/2 tests without replacing those fixtures. See
[remaining remediation](REMAINING_REMEDIATION_2026-11.md) and
[initialization measurements](evidence/initialization.md). Historical results
below remain intact.

Date: 2026-11-24. Baseline: `a89854a5545c4232ccf37d96605e011e69326e49`
(`origin/main`). Branch: `test/nifty-sdk-241-parity`.

## Verdict and scope

**PARITY PASS** for the equivalent mathematical operations described below.
**INTENTIONAL DIFFERENCE** for SuperTrend initialization/direction, MACD EMA
seeding, ADX seeding/zero denominators, and conservative missing-volume handling.
The custom indicators are not interchangeable with the public SDK outputs at
the 80-bar admission boundary, or at every later index.

No **SIGNAL-CHANGING BUG** or **STRATEGY-SPEC VIOLATION** in production was
established by these fixtures. There are reproducible, decision-changing
initialization differences. They must not be described as universal signal
parity after a fixed history length. **UNVERIFIED**: whether the strategy owner
intends a different seed or a three-position crossover window.

Only the new test module and this report change. Production code, settings,
existing ledger tests, dependency manifests, CI, and frontend output are untouched.
No broker client, credential, order, or real-market data is required by the tests.
These results make no claim about profitability or market correctness.

## Installed implementation and API inspection

The reference was an actual installed `openalgo==2.4.1` Windows wheel, with
`openalgo.indicators._backend.HAVE_RUST == True`, not an emulation. Inspection
used `importlib.metadata.version`, `inspect.signature`, public method calls, and
the installed sources in `indicators/__init__.py`, `trend.py`, `momentum.py`,
`hybrid.py`, `volume.py`, and `_backend.py`. Tests also exercise the NumPy fallback.

| Tested API | Arguments used | NumPy output order |
| --- | --- | --- |
| `ta.atr` | `high, low, close, period=10` | ATR array |
| `ta.supertrend` | `high, low, close, period=10, multiplier=3` | `(value, direction)` |
| `ta.ema` | `data, period=12` and `period=26` | EMA array |
| `ta.macd` | `data, fast_period=12, slow_period=26, signal_period=9` | `(line, signal, histogram)` |
| `ta.adx` | `high, low, close, period=14` | `(+DI, -DI, ADX)` |
| `ta.vwap` | `high, low, close, volume, anchor, source, timestamps, session_starts` | VWAP array |
| `_backend.ema_sma` | `data, period` | SMA-seeded EMA array; supplementary private reference |

`ta.vwap` retains the positional `anchor` then `source` arguments. Its full
signature also includes the six existing standard-deviation/percentage band
multiplier arguments before the new `timestamps` and `session_starts` arguments.
Tests assert the exact parameter names/order and array/tuple shapes.

The public SDK does not return MACD crossover age or ADX slope/DX separately.
Tests derive these causally from the returned histogram, ADX, and DI arrays.
SDK `NaN` denotes unavailable numeric output; NIFTY uses `None`.

## Reproducible fixtures and tolerances

The committed generator is `fixture_bars` in
`test/test_nifty_algo_sdk_241_parity.py`. It uses NumPy `default_rng`/PCG64.
For each invocation, it draws all normal steps, upper wicks, lower wicks, and
integer volumes in that order. The standard path has 525 bars and a single
`SDK241-FUT` token. Sessions contain 75 completed five-minute candles starting at
09:15 Asia/Kolkata on weekdays from 2026-11-02. Weekday dates are synthetic,
not an assertion that the exchange was open. Each candle uses the previous close
as its open, and valid high/low bounds with asymmetric wicks.

Six named paths use seed 241:

- Rising/falling: `22000 +/- 2*i` closes.
- Sideways: `22000 + 0.1*sin(i/3)` closes, symmetric 20-point wicks.
- Volatile: `22000 + cumsum(N(0,8))` closes.
- Reversal: `22000 + 3*i` before index 100, then `22300 - 5*(i-100)`.
- Low volatility: the normal steps scaled by 0.001, retaining the wider wicks.

Additional explicit fixtures cover band equality, DM ties, gaps, zero range,
weighted VWAP, missing/zero volume, contract changes, and an IST midnight edge.
The midnight fixture checks calendar behavior only, not an NSE trading session.

All numeric comparisons use absolute tolerance `1e-9` plus relative tolerance
`1e-12`, with matching unavailable-value masks. Thus the maximum comparison
tolerance near a 22,000 price is approximately `2.3e-8`. Convergence assertions
state their separate bounds explicitly. Gate comparisons use the production
strict/inclusive comparisons without applying a tolerance to eligibility.
The tests freeze expected disagreement indices, rather than tolerating their loss.

Independent recurrences reconstruct seeded smoothing, TR, DM, DI, DX, ADX, and
both SuperTrend initializations. SDK SMA-seeded EMA is a supplementary reference;
the independent formulas avoid relying solely on private SDK kernels.

## SuperTrend

**PARITY PASS**: ATR(10) seeds from the mean of the first ten true ranges,
including `high[0]-low[0]`, at index 9, then uses Wilder alpha `1/10`.
Both implementations use midpoint bands at three ATRs, recursive final bands,
and strict reversal comparisons. Tests reconstruct both final bands and verify
values, directions, flips, and NIFTY duration. Exact band equality does not flip;
the next close strictly beyond the band does.

**INTENTIONAL DIFFERENCE**: NIFTY seeds bullish when `close >= midpoint`, bearish
otherwise. SDK always seeds bearish. NIFTY uses `+1` bullish / `-1` bearish;
SDK uses `-1` bullish / `+1` bearish. Negate SDK direction before comparison.
Negation alone does not remove an initialization disagreement.

Rising, falling, volatile, and reversal fixtures agree in value and normalized
direction throughout indices 79..524. The sideways and low-volatility fixtures
retain opposite directions over all 446 evaluated bars. The sideways ATR is
40; its opposing bands remain more than 119 points apart at the last bar.
The initial state can persist indefinitely when price never crosses a band.

The random census also finds a nonzero persistence example: seed 4, indices
79..89. At index 79 NIFTY is bullish at `21943.848016773656`; SDK is bearish
at `22006.84178404008`, with close `21957.84272718374`. Both `R-ST` gates pass,
but CE/PE side, MACD alignment, and VWAP alignment can differ. At index 90,
NIFTY reverses and the normalized states agree.

## MACD

**PARITY PASS** for the 12/26/9 formulas with equivalent seeding, histogram
subtraction, crossover signs, and causal age calculation.
**INTENTIONAL DIFFERENCE**: NIFTY seeds EMA(12) and EMA(26) with SMAs at indices
11 and 25. Its signal EMA needs nine valid line values, so its returned MACD
records first become available at index 33. The public SDK uses first-value
seeding and returns MACD from index 0. SDK EMA itself rejects an input shorter
than its period; public MACD accepts short first-value-seeded input.

The NIFTY signal/histogram match SDK `_backend.ema_sma` composition within the
stated tolerance. Each public SDK EMA/MACD output also matches an independently
constructed first-value recurrence. Both bullish and bearish crossover state
and age are compared against the seeded-reference histogram. Prefix checks and
79/80/81/150/300/525-bar histories test initialization and minimum admission.

For the 525-bar seed-241 path, at index 79 (exactly 80 bars), EMA(12) is
`21991.890584771332` versus SDK `21991.890552280565`; EMA(26) is
`21994.99778503263` versus SDK `21994.968970414695`.

**UNVERIFIED — pending strategy decision**: `crossover_freshness=3` and
`cross_age <= 3` accept ages **0, 1, 2, and 3**. The latest completed candle has
age 0; age 3 refers to the fourth most recent completed candle. Tests preserve
all four accepted positions and reject age 4. If “within three completed bars”
means exactly three positions, the suggested alternative is ages **0, 1, 2**
(for example, freshness 2 with the same inclusive comparator). That alternative
requires owner approval and is not implemented here.

**Resolution, 2026-11-24.** The owner approved the three-position reading.
Strategy 3.2.0 admits ages **0, 1 and 2** and rejects age 3 (freshness 2, same
inclusive comparator). The paragraph above records the 3.1.0 behaviour as it
was audited. The indicator values compared in this report are unchanged; see
[MACD_THREE_CANDLE_WINDOW_2026-11.md](MACD_THREE_CANDLE_WINDOW_2026-11.md).

## ADX

**PARITY PASS** for Wilder(14) recurrence, true-range gap handling, strict
directional-movement comparisons (equal up/down movements contribute neither),
DI ratios, DX, slope calculation, and the inclusive `ADX >= 25` gate.

**INTENTIONAL DIFFERENCE**: NIFTY excludes bar 0 from the TR/DM seed, produces
DI/DX at index 14, and seeds ADX from 14 DX values at index 27. SDK includes
bar 0 (zero DM), produces DI at index 13, and ADX at index 26. The public SDK's
DI arrays remain separately available before its ADX becomes available.
Independent references exercise each seeding convention rather than asserting
that unequal seeds should produce equal arrays.

NIFTY maps zero denominators to zero; a flat zero-range path produces ADX/DI
zero and slope zero after warm-up, classed `WEAK`. SDK returns all-NaN DI/ADX
for that path. Both block the ADX eligibility gate, but availability differs.

Slope means `ADX[i]-ADX[i-1]`; NIFTY's first available slope is zero. At the
seed-45/index-149 threshold divergence, slopes are `1.2451442875976717`
(NIFTY) and `1.24512748501202` (SDK). Slope is not an `R-ADX` eligibility input.
Optional DI confirmation is exercised through the actual rule engine alongside
the optional MACD zero-line filter; both remain off by default.

## VWAP

**PARITY PASS** for typical-price `(H+L+C)/3` and closing-price VWAP on
equivalent session inputs, with positive cumulative volume. Four complete
sessions are compared independently against both hand cumulative sums and SDK
calls. Explicit IST date-change markers and timezone-aware IST timestamps also
match NIFTY resets. A cumulative multi-day SDK call is only a negative control,
never the parity reference. Epoch seconds denote UTC days in the SDK; prefer
IST-aware timestamps or explicit markers for this strategy.

**SDK 2.4.1 behavior changed** relative to direct 2.0.5 calls:

| Condition | SDK 2.0.5 | SDK 2.4.1 | NIFTY |
| --- | --- | --- | --- |
| Leading zero volume | Returns current source price | NaN until cumulative volume is positive | `None` until positive volume |
| All-zero session | Raises `RuntimeError("No volume is provided by the data vendor.")` | All NaN | All `None` |
| Missing volume represented as NaN | Hand fixture returns each current source from the missing observation onward | NaN on missing observation; skips it and resumes previous sums | Invalidates remainder of session |
| Explicit session markers/timestamps on public `ta.vwap` | Not exposed | Supported | Resets on IST candle-start date |

**INTENTIONAL DIFFERENCE**: SDK resumption after missing volume does not satisfy
the strategy's complete-volume rule. Seed 0, 80-bar fixture, volume missing at
index 77: the actual NIFTY `R-VWAP` at index 79 is `UNAVAILABLE`; replacing only
VWAP with SDK's `22062.28100736435` makes it `PASS`. This is a concrete
**STRATEGY-SPEC VIOLATION if SDK VWAP is substituted without preserving the
session invalidation guard**, not a current production defect.

Zero volume after positive volume leaves both sums unchanged. Missing volume
clears on the next IST session. Multiple tokens return all `None`; the rule
engine also rejects mixed identities. Non-FUT input is unavailable to custom VWAP.
SDK has no contract-identity or instrument-kind validation.

The pure VWAP function cannot establish whether history starts at the exchange
open. `completed_series` rejects a current-session gap and trims a historical
gap to the continuous suffix; indicators and the unchanged warm-up rule rerun
on that suffix. `aggregate` drops an incomplete opening bucket.
`assessment.assess_current` owns the effective-session-opening check and adds
`SESSION_VWAP_INCOMPLETE` when that opening is missing. New tests cover the
pure-series/aggregation boundaries; existing pipeline and strategy integration
tests exercise the assessment guard. A truncated series' numeric VWAP is not
proof of complete historical coverage.

## Decision census and exact counterexamples

The census uses **64 seeds (0..63), 525 bars each, indices 79..524 inclusive**:
**28,544 evaluated bar positions**. Indices below are zero-based. Each fixture
must be generated at length 525, then prefixed; changing generation length also
changes later RNG draws used for wicks/volume.

| Gate | Isolate indicator, keep NIFTY direction | Use each implementation's normalized ST direction |
| --- | ---: | ---: |
| `R-ST` | 0 | 0 |
| `R-MACD` | 3 | 6 |
| `R-ADX` | 4 | 4 |
| `R-VWAP` | 0 | 11 |

There are 11 ST side disagreements, all seed 4, indices 79..89. The extra native
direction MACD disagreements are `(4,79)`, `(4,80)`, `(4,81)`; all 11 native
direction VWAP disagreements are `(4,79)` through `(4,89)` inclusive.

Isolated MACD disagreements:

| Seed/index | Direction | NIFTY histogram / age | SDK histogram / age | NIFTY / SDK gate |
| --- | ---: | --- | --- | --- |
| 21 / 80 | +1 | 1.890110512286 / 3 | 1.920915033897 / 4 | PASS / FAIL |
| 49 / 88 | -1 | -3.566423513849 / 4 | -3.547711125861 / 3 | FAIL / PASS |
| 54 / 124 | -1 | +0.000345107274 / 12, last cross bullish | -0.000366124777 / 0, last cross bearish | FAIL / PASS |

Isolated ADX threshold disagreements (all NIFTY FAIL / SDK PASS):

| Seed/index | NIFTY ADX | SDK ADX |
| --- | ---: | ---: |
| 1 / 90 | 24.990321972342 | 25.037432063150 |
| 20 / 106 | 24.994859869464 | 25.002692426580 |
| 45 / 149 | 24.999890971426 | 25.000243473320 |
| 57 / 97 | 24.985031245855 | 25.008409675416 |

Every listed counterexample is replayed through actual `Rules.evaluate`, in
addition to testing the census projection. For seed 54/index 124, all four
studied gates change from a false to a true conjunction. This does **not** assert
full trade eligibility: higher-timeframe, PCR, risk, freshness, and other checks
are outside that four-gate conjunction.

The six seed-241 named fixtures have these native-direction disagreement counts
over 446 evaluated positions each; the exact tuples are regression assertions:

| Path | R-ST | R-MACD | R-ADX | R-VWAP | ST side changes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rising | 0 | 0 | 0 | 0 | 0 |
| Falling | 0 | 0 | 0 | 0 | 0 |
| Sideways | 0 | 189 | 0 | 444 | 446 |
| Volatile | 0 | 0 | 0 | 0 | 0 |
| Reversal | 0 | 0 | 0 | 0 | 0 |
| Low volatility | 0 | 126 | 0 | 446 | 446 |

These are gate disagreements caused primarily by persistent initial direction,
not evidence of eligible trades or favorable outcomes.

**Addendum, 2026-11-24 (strategy 3.2.0).** The census above was taken under the
3.1.0 window (ages 0 to 3). The test keeps it, run against a 3.1.0 record, as
evidence that the indicator mathematics did not change. Under the approved
window (ages 0 to 2) the R-MACD rows become: isolated `(21,79)`, `(49,87)`,
`(54,124)` (3); native direction adds `(4,79)` and `(4,80)` (5). The named
sideways and low-volatility paths show 141 and 100 R-MACD disagreements instead
of 189 and 126. The 3.1.0 counterexamples `(21,80)` and `(49,88)` now agree:
both fail. The other gates and the ST side changes are unchanged.

## Warm-up, causality, and upgrade compatibility

For the 525-bar seed-241 volatile path:

| Index / history count | Absolute histogram difference | Absolute ADX difference |
| --- | ---: | ---: |
| 79 / 80 | 0.0135133035585 | 0.0807036795922 |
| 129 / 130 | 0.000289092173089 | 0.00229019675408 |
| 199 / 200 | 1.32252577600e-6 | 2.40319268023e-5 |
| 299 / 300 | 6.03880057071e-10 | 1.99883736229e-8 |
| 524 / 525 | 3.70015129647e-12 | 7.10542735760e-15 |

Convergence is fixture-specific. The seed-45 ADX counterexample at index 149
supersedes the old audit's suggestion that no ADX signals change after about
130 bars. ST initialization can persist past any fixed warm-up without a flip.

**PARITY PASS** for prefix causality at lengths 9, 10, 27, 34, 79, 80, 81, and
150. Short-input SDK errors are asserted explicitly where the public API
requires a full period; they are not skipped. Appending a future candle or an
extreme forming candle leaves the current rule-engine result unchanged. A
completed higher/entry history of 79 fails `R-WARMUP`; 80 and 81 pass it.
Raw SDK functions have no candle-completion concept; filtering is the caller's
responsibility. Direct indicator calls assume already-filtered input.

Actual installed 2.0.5 and 2.4.1 Rust-backed calls were compared for ATR(10),
SuperTrend(10,3), MACD(12,26,9), and ADX(14) on all six named 525-bar paths.
Maximum absolute difference was **0.0**, with identical NaN masks. This is
finite-fixture evidence, not proof that every possible input behaves identically.
The VWAP signature and volume behavior changes above are confirmed upgrade
changes. The old audit's private `_backend.adx_talib` entry point is absent in
2.4.1; `_backend.adx_wilder_sum(high, low, close, period)` is present. A script
using the old private name needs updating; this report does not assume its seed
matches NIFTY's. The supplementary `_backend.ema_sma(data, period)` remains
available. These private API facts are asserted in the new suite.
No production SDK compatibility regression was found: NIFTY computes
these indicators locally and does not delegate these calculations to `ta`.

## Verification and reproduction

The new file matches CI's `test/test_nifty_algo_*.py` pattern. In an environment
already installed from the committed lockfile, run these offline PowerShell commands:

```powershell
uv run --offline --no-sync python -m pytest test/test_nifty_algo_sdk_241_parity.py test/test_nifty_algo_core.py -o addopts='' -q --timeout=120 -p no:cacheprovider
uv run --offline --no-sync ruff check --no-cache test/test_nifty_algo_sdk_241_parity.py
uv run --offline --no-sync ruff format --check --no-cache test/test_nifty_algo_sdk_241_parity.py
```

Local execution used Windows CPython 3.12.11, NumPy 2.4.4, pandas 2.3.3,
pytest 9.1.1, Pydantic 2.14.3 / core 2.50.4, typing-extensions 4.16.0,
typing-inspection 0.4.5, tzdata 2026.3, and Ruff 0.16.0. SDK, Pydantic, typing,
and timezone packages were installed into `%TEMP%/nifty-sdk-241-site` and placed
first on `PYTHONPATH`; the shared worktree's SDK 2.0.5 environment was preserved.
The interpreter was `../openalgo/.venv/Scripts/python.exe -B`, with
`PYTHONDONTWRITEBYTECODE=1`, pytest cache disabled, and temporary pytest directories.
Dependency installation occurred before verification; the test code makes no
network calls. The entire application dependency environment was not re-synced.

Final Windows verification: **191 passed in 62.47 seconds**, including all 82
new parity cases, existing core/pipeline/strategy-integration/corrective-audit/
native-data regressions, import-resolution tests, and requirements-parity tests.
Ruff lint and format checks pass for the new Python file; whitespace checks pass.
No `skip` or `xfail` was added. An earlier combined run had an existing
import-resolution subprocess exceed its 30-second timeout (183 passed, one
timeout). Its isolated retry passed both cases in 6.97 seconds; the final full
191-case run passed without changing that test or its timeout.

The final regression selection, in addition to the two files in the command
above, was:

```text
test/test_nifty_algo_pipeline.py
test/test_nifty_algo_strategy_integration.py
test/test_nifty_algo_corrective_audit.py
test/test_nifty_algo_native_data.py
test/test_pytest_import_resolution.py
test/test_requirements_parity.py
```

## Limitations and recommendations

- **UNVERIFIED**: cross-platform CI results, live vendor history completeness,
  calendar entitlements, real-market effectiveness, and full trading eligibility.
  No Linux/WSL/Docker/Gunicorn/eventlet runtime suite was run locally.
- Preserve the current documented seed/direction conventions unless a separate
  strategy change is approved. Do not substitute public SDK outputs based only
  on an apparent convergence rule or a sign negation.
- Keep the missing-volume/session-opening/token guards around any future SDK
  VWAP adapter. Use explicit IST markers or IST-aware timestamps.
- Resolve the ages 0..3 versus 0..2 freshness interpretation separately. The
  production threshold and configuration remain unchanged.
  Resolved 2026-11-24: ages 0..2, strategy 3.2.0.
- A future SDK upgrade must rerun this suite. Private `_backend.ema_sma` is
  supplementary and may change; public API inspection and independent references
  remain necessary.
