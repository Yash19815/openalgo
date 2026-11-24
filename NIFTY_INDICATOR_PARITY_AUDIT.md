# NIFTY Indicator Parity and Strategy Guideline Audit

Auditor mode: read-only. No application source, test file, configuration, threshold, period or weight was changed. The only file written inside the repository is this report. Throwaway comparison scripts live in the session scratchpad, outside the repository.

- Branch: `feat/nifty-paper-trading-system`
- Audited HEAD: `1a0be77917cc66841926cf63c9adf6062b881803` (working tree clean at the start of this audit)
- Reference audit: `NIFTY_COMPLIANCE_AUDIT.md`
- Reference library: `openalgo` SDK 2.0.5 as installed in the project `.venv` (`openalgo.ta`, compute core `_oaindicators` Rust extension; the pure NumPy fallback in `openalgo/indicators/_backend.py` is the readable specification of the same kernels)
- Date: 2026-11-24

Concurrent-edit note: the working tree was clean at HEAD when the audit started, but by the end about 25 files were modified by another writer (expected to be Codex), including `paper_executor.py` and `runner.py`. Every file a finding depends on was re-checked against `HEAD`: `indicators.py`, `signal_engine.py`, `selection_scoring.py`, `depth_quote.py`, `contract_resolver.py`, `protection.py`, `risk_manager.py`, `market_data.py`, `assessment.py`, `native_data.py`, `config.py`, `execution_replay.py` and `database/nifty_algo_db.py` are unchanged from `HEAD`. In `paper_executor.py` the cited lines (`_charges` at 36, `self._depth(candidate, now)` at 274-275, `moneyness(instrument, spot)` at 417, `_depth` at 466) are identical at `HEAD`, and the working-tree diff of `paper_executor.py` and `runner.py` touches none of the OI, depth or moneyness code. All findings therefore apply to `1a0be77`. This report is the only file this audit added; it is untracked.

Environment note: the first `uv run` of a comparison script printed `Building openalgoui` and `Uninstalled 1 package / Installed 1 package`, meaning `uv` re-synced the editable project package in `.venv`. No repository file changed (the git tree stayed clean). Later runs used `uv run --no-sync`.

Names of labels follow the assignment: `PARITY PASS`, `INTENTIONAL DIFFERENCE`, `STRATEGY-SPEC VIOLATION`, `OPENALGO CONTRACT VIOLATION`, `SIGNAL-CHANGING BUG`, `UNVERIFIED`.

## 0. Method and limits

- Importing the SDK works independently of the repository: `uv run python -I` imports `openalgo` from `site-packages` (the repository root has `openalgoUI.egg-info` but no `openalgo/` package directory), so no name-collision blocker exists. The reference results below are real calls to `openalgo.ta`, not reconstructions.
- Fixtures are synthetic completed 5-minute candles (75 per IST session, 09:15 to 15:30, contiguous, one futures token). They are for numerical verification only and say nothing about profitability.
- Tolerance: absolute 1e-9 (relative to value for prices). Anything above that is reported as a divergence, and its size is shown so a reader can judge it.
- Evidence of how the strategy consumes the series: `assess_current` (`services/nifty_algo/assessment.py:92-205`) requests 1-minute futures history from `today - 9 days`, aggregates each IST session separately into 5-minute and 15-minute candles (`market_data.aggregate`, `market_data.py:11-60`), and feeds the whole multi-day series to `Rules.evaluate`. Indicators therefore run continuously across sessions on roughly 4 to 7 trading days, about 300 to 525 entry bars and 100 to 175 confirmation bars. `R-WARMUP` only requires 80 completed bars on each timeframe (`signal_engine.py:63-67`).
- Strategy specification used as the "approved" reference: `docs/nifty-algo/STRATEGY_ASSUMPTIONS.md` and `PAPER_SYSTEM_DESIGN.md`, and `StrategyConfig` defaults (`services/nifty_algo/config.py`).

## 1. SuperTrend (Priority 1)

Source: `services/nifty_algo/indicators.py:44-77` (`supertrend`) against `ta.supertrend(high, low, close, 10, 3.0)`; SDK specification `openalgo/indicators/_backend.py:2036-2062` and `trend.py:335-` (Pine-compatible).

| Aspect | NIFTY | OpenAlgo `ta.supertrend` | Result |
| --- | --- | --- | --- |
| ATR | Wilder, first value is the mean of the first 10 true ranges, bar 0 true range is `high - low` (`indicators.py:8-41`) | `atr_wilder` with the same seeding, first valid at bar 9 | PARITY PASS. Maximum absolute ATR difference over 15 fixtures: 5.3e-15. First valid bar is 9 in both |
| Basic bands | `hl2 +/- multiplier * ATR` | same | PARITY PASS |
| Final bands | `upper = basic if basic < prev or prev_close > prev_upper else prev` and the mirror for lower (`indicators.py:60-61`) | same Pine recursion | PARITY PASS |
| Reversal | strict: up to down when `close < lower`, down to up when `close > upper` | strict, same | PARITY PASS |
| Direction convention | `+1` uptrend, `-1` downtrend | `-1` uptrend, `+1` downtrend (documented in `docs/prompt/indicators/trend - openalgo indicators.md:243`) | INTENTIONAL DIFFERENCE. Sign mapping `ours == -sdk` holds on every bar where the two agree; all NIFTY consumers (`R-ST`, side mapping `CE if direction == 1`) are internally consistent with `+1 = bullish` |
| Initial direction | first valid bar: `+1` if `close >= hl2` else `-1` (`indicators.py:56-58`) | always downtrend (`+1`) on the first valid bar (Pine `na(atr[1])` rule) | INTENTIONAL DIFFERENCE, see below |
| Incomplete candle | skipped (`not bar.complete`) and upstream `completed_series` already drops incomplete candles | no concept | NIFTY stricter; PARITY not applicable |

First divergence: bar 9 (the first valid bar) in 781 of 1,500 random fixtures, caused only by the initial direction rule. Values and directions then agree again after the first genuine reversal. In the 15 named fixtures the last mismatching bar was at index 20 to 42.

Decision impact:

- Eligibility gate `R-ST` (`(close - value) * direction > 0`) was compared bar by bar from bar 80 onward over 181,500 bars (1,500 series, 200 bars each): 0 disagreements. Direction itself agreed from bar 80 onward in all series with realistic range-to-body ratios, for series lengths 90, 150, 375 and 525 bars.
- Persistence caveat: in synthetic fixtures where bar-to-bar movement is very small compared with the wick-driven ATR (step volatility one fifth of the baseline), price never leaves the +/- 3 ATR band, no reversal occurs, and the initial-direction difference persists for the whole series (65 of 400 series, at every length including 525 bars). In such a market the two implementations would give opposite SuperTrend sides. This only arises when price stays inside a band three ATR wide for the entire multi-day history, which is not a plausible state for NIFTY futures over 4 to 7 sessions, and the other gates (`R-ADX` at or above 25, a fresh `R-MACD` crossover) are not satisfiable in such a range. I treat it as a documented, non-signal-changing initialization difference, not a defect. `UNVERIFIED` against real Angel One history because no real data was used.
- Exact boundary: `R-ST` uses a strict `> 0`, so a bar that closes exactly on the active band value is refused. This is stricter than the SDK direction output and consistent with the strict reversal rule. INTENTIONAL.

Verdict: PARITY PASS on values; INTENTIONAL DIFFERENCE on initial direction and direction sign.

Existing coverage: `test/test_nifty_algo_core.py:87` (`test_adx_and_supertrend_independent_monotone_reference`) tests a monotone hand reference. No test compares against `openalgo.ta`. See finding N-01.

## 2. MACD (Priority 2)

Source: `indicators.py:80-117` (`macd`, `smooth`/`ema` at lines 8-28) against `ta.macd(close, 12, 26, 9)`; SDK `_backend.py:128-145` and `234-238`.

| Aspect | NIFTY | OpenAlgo | Result |
| --- | --- | --- | --- |
| EMA seeding | simple average of the first `period` values, output starts at `period - 1` (`indicators.py:17-20`) | `ta.ema` and therefore `ta.macd` seed from the first value and are valid from bar 0 (`_backend.py:139-144`) | INTENTIONAL DIFFERENCE. The SDK also ships an SMA-seeded kernel `ema_sma` (`_backend.py:1928`) |
| MACD line | `EMA12 - EMA26`, first valid at bar 25 | same formula | PARITY PASS |
| Signal | EMA(9) of the MACD line, seeded on the first 9 valid values, first valid at bar 33 | EMA(9) of the line, seeded on the first value | follows seeding |
| Histogram | `line - signal` | same | PARITY PASS |
| Required history | 34 completed bars | 1 bar (values are valid but not converged) | NIFTY stricter |

Independent check: building MACD from the SDK's own SMA-seeded kernel (`ema_sma`) reproduces NIFTY's histogram to 9.6e-12 with the same first valid bar (33). So the NIFTY series is numerically identical to OpenAlgo's SMA-seeded kernel and differs from the public first-value-seeded `ta.macd` only through the seed.

Convergence of the seed difference (|hist difference|, one random fixture, 525 bars): 0.526 at bar 50, 0.054 at bar 80, 1.1e-3 at bar 130, 5.3e-6 at bar 200, 2.4e-9 at bar 300, 4.2e-13 at bar 500. Production series are about 300 to 525 bars, so the difference is below 1e-8 by the start of the usable history.

Decision impact (signal-engine logic `R-MACD`: cross direction equals trade direction, cross age no more than 3 bars, histogram sign agrees; zero-line filter off by default): over 600 random fixtures of 525 bars, 75 bar-level `R-MACD` disagreements occurred, all with bar index 126 or earlier (examples: bar 101, histogram -0.00096 against +0.00056; bar 80, -1.020 against -1.149). None occurred beyond bar 126. A separate run of 300 fixtures found 37 disagreements in 133,500 bars (0.028 percent), also confined to the first 126 bars. With real history of at least roughly 300 entry bars the divergence is negligible, but the `R-WARMUP` gate admits signals at 80 bars, where the two implementations can differ (0.05 percent of bars in the 80 to 126 window range).

No lookahead or forming-candle use: `macd` consumes only the list it is given, and `completed_series` (`signal_engine.py:9-28`) removes candles whose `end > now` or that are not `complete` before any indicator runs. Zero cross and cross age are computed from past values only.

Crossover lookback ambiguity: `STRATEGY_ASSUMPTIONS.md:22` says "a crossover within three completed entry bars"; the gate is `cross_age <= crossover_freshness` with default 3 (`signal_engine.py:91`, `config.py:25`). Age 0 is the latest bar, so a crossover on the fourth most recent completed bar passes. Whether "within three bars" means ages 0 to 2 or 0 to 3 is not defined in the documents. `UNVERIFIED` interpretation; no numerical error.

Verdict: PARITY WITH DOCUMENTED EXCEPTIONS (INTENTIONAL DIFFERENCE: SMA seeding; matches the SDK SMA kernel exactly).

Existing coverage: `test_nifty_algo_core.py:78` (`test_macd_linear_series_hand_reference_and_prefix_causality`).

## 3. ADX (Priority 3)

Source: `indicators.py:120-155` against `ta.adx(high, low, close, 14)`; SDK `_backend.py:728-756`.

| Aspect | NIFTY | OpenAlgo `ta.adx` | Result |
| --- | --- | --- | --- |
| True range, +DM, -DM | standard; bar 0 excluded (`tr[0] = None`, first +DM/-DM at bar 1, `indicators.py:121-130`) | bar 0 included in the seed (`tr[0] = high - low`, DM 0) | INTENTIONAL DIFFERENCE |
| Smoothing | Wilder, seeded with the mean of the first 14 transitions | Wilder, seeded with the mean of the first 14 values including bar 0 | differs by one bar of seed |
| DI+/DI-, DX | `100 * smoothed_dm / smoothed_tr`, `100 * abs(diff) / sum` | same formulas | PARITY PASS |
| ADX | Wilder smoothing of DX, seeded on 14 DX values, first valid at bar 27 | first valid at bar 26 | follows seeding |
| Zero denominators | `0` when `t == 0` or `a + b == 0` | `NaN` when `sm_atr <= 0` or `dsum <= 0` | minor INTENTIONAL DIFFERENCE |

Independent reference: I wrote a textbook Wilder (1978) ADX, with sum smoothing and transitions starting at bar 1, in the scratchpad. NIFTY's ADX matches it to 1.4e-14 over 498 bars with the same first valid bar (27). `ta.adx` differs from it by up to 0.95 and `ta.adx`'s alternative kernel `adx_talib` by up to 0.60, so NIFTY follows the textbook definition and the public SDK function uses a different seeding. (The reference is my own implementation, so this shows consistency with the textbook, not proof of an external authority.)

Convergence of the seed difference (|ADX difference| at bars 50, 80, 130, 200, 300, 500): 0.507, 0.043, 1.1e-3, 1.3e-5, 1.3e-8, 1.8e-14. DI difference is about one tenth of that.

Decision impact: for the approved threshold `adx >= 25` (`signal_engine.py:97`, `config.py:28`), 10 bar-level threshold disagreements occurred in 600 fixtures of 525 bars, all at bar index 110 or earlier; one DI-sign disagreement at bar 103. With short history (100 bars) 7 threshold disagreements occurred in 6,000 bars (0.12 percent). With 300 or more bars none occurred. Exact boundary: the gate is inclusive (`>=`), consistent with "minimum 25" in `STRATEGY_ASSUMPTIONS.md:22`. Optional DI confirmation (`di_confirmation`, default off) compares `plus_di - minus_di` with a strict sign.

Verdict: PARITY WITH DOCUMENTED EXCEPTIONS (INTENTIONAL DIFFERENCE: textbook Wilder seeding versus the SDK's bar-0 seeding). Not signal-changing for series longer than about 130 bars.

## 4. VWAP (Priority 4)

Source: `indicators.py:158-177` against `ta.vwap(high, low, close, volume, "Session", "hlc3")`; SDK `volume.py:219-` and `_backend.py:704-725`.

| Aspect | NIFTY | OpenAlgo | Result |
| --- | --- | --- | --- |
| Formula | `sum(price * volume) / sum(volume)`, price is `(H+L+C)/3` (`"typical"`) or close | identical (`hlc3`, `close` sources) | PARITY PASS: per-session maximum absolute difference 0.0 on 4 sessions (300 bars), for both bases |
| Session reset | resets when the IST calendar date of `bar.start` changes (`indicators.py:167-169`) | the public `ta.vwap(...)` passes no timestamps or session starts, so the whole input is ONE cumulative session (`volume.py:386-395`) | INTENTIONAL DIFFERENCE. Calling `ta.vwap` on the multi-day series diverges at the first bar of day 2 (bar 75) by up to 184 index points. The two match exactly when `ta.vwap` is called one session at a time |
| Opening bar volume 0 | `None` until volume accumulates | returns the bar's own typical price | NIFTY stricter |
| All volume 0 | `None` | raises `RuntimeError("No volume is provided by the data vendor.")` | NIFTY degrades safely; SDK raises |
| Missing volume (`None`) mid-session | invalidates the rest of the session (`indicators.py:170-171`) | cannot receive `None` | NIFTY stricter, matches `STRATEGY_ASSUMPTIONS.md:25` ("missing volume blocks execution") |
| Contract identity | more than one token in the series returns all `None` (`indicators.py:164-165`) | no concept | NIFTY stricter, satisfies the "no rollover mixing" requirement. Verified: a mixed `FUT1`/`FUT2` series returns all `None` |
| Spot/index volume | instrument kind must be `FUT` | no concept | NIFTY stricter |

Session boundary: `signal_engine.vwap` reset uses the IST date of the candle start, which is correct for NSE sessions that do not cross midnight. Effective session anchoring comes from `aggregate(..., session_open=window[0])` using `get_effective_session_window` (`assessment.py:22-41, 151-155`). `assess_current` also appends `SESSION_VWAP_INCOMPLETE` and refuses eligibility when today's first bar does not equal the effective session start (`assessment.py:173-177`), which is the strict missing-opening-candle rule from `STRATEGY_ASSUMPTIONS.md:24-25`.

Futures expiry and rollover: `assess_current` picks the nearest futures contract (`assessment.py:122-126`), and a series containing two tokens makes VWAP, and `completed_series`, refuse (`signal_engine.py:17`). So a contract change inside the nine-day window yields no signal rather than a mixed VWAP. This is stricter than required.

Verdict: PARITY PASS where inputs are equivalent (single session); INTENTIONAL DIFFERENCE for multi-session handling and zero/missing volume.

Existing coverage: `test_nifty_algo_core.py:97` (`test_vwap_weighted_reference_and_missing_volume`).

## 5. PCR and five-gate confirmation (Priority 5)

PCR has no `openalgo.ta` counterpart. Audited against `STRATEGY_ASSUMPTIONS.md:29-36` and `PAPER_SYSTEM_DESIGN.md`.

| Requirement | Evidence | Result |
| --- | --- | --- |
| Complete selected-expiry CE and PE universe | `get_pcr` (`native_data.py:301-353`) takes every listed CE/PE of one expiry from the verified master; `pcr()` (`indicators.py:180-230`) requires both kinds, a single `(exchange, underlying, expiry)` identity, unique tokens and strikes, and each strike present as both CE and PE | PARITY PASS |
| Dated master | `master_date == today IST`, `tradable`, `expiry >= today` (`indicators.py:191-197`); `MASTER_FRESHNESS_UNVERIFIED` and `MASTER_UNIVERSE_INVALID` refuse (`native_data.py:307-310`) | PARITY PASS |
| One definition, no mixing | `kind` is `OI` or `VOLUME`; only that field is summed; `None` returns `None` (`indicators.py:211-213`) | PARITY PASS |
| No zero-filling | a missing quote makes the whole PCR `None` (`indicators.py:204-206`) | PARITY PASS |
| Source timestamps | quote requires `ltt` and `received_time`, `source <= received <= now` (`native_data.py:279-286`, `indicators.py:207-210`) | PARITY PASS |
| 90 s freshness | `0 <= now - source <= pcr_max_age` (default 90) per contract; re-checked at signal time against `pcr.source_time = min(source times)` (`signal_engine.py:116`) | PARITY PASS |
| 5 s synchronization | `max(times) - min(times) <= pcr_max_skew_seconds` enforced in `get_pcr` (`native_data.py:337-342`), not inside the pure `pcr()` function | PARITY PASS at the integration level. The pure function alone accepts any skew; callers other than `get_pcr` must enforce it |
| Numerator and denominator | `puts / calls`; `calls <= 0` returns `None`, so a zero denominator is refused rather than producing infinity or zero (`indicators.py:221-222`); puts of zero gives PCR 0, a legitimate bearish value | PARITY PASS |
| Bull and bear thresholds | bullish when `pcr >= 1.5`; bearish when `pcr < 1.0`; exactly 1.0 passes neither; 1.0 to below 1.5 passes neither (`signal_engine.py:118-120`, `config.py:34-35`) | matches "bullish starts at 1.5, bearish below 1.0, midpoint does not pass" |
| Strict refusal | `valid_pcr` demands `coverage == 1`, `verified`, matching kind, fresh timestamp; `R-PCR` is `UNAVAILABLE` otherwise and the bias becomes `DATA_UNAVAILABLE` (`signal_engine.py:111-126, 145-146`) | PARITY PASS |

Real-data verification: whether Angel One's depth/quote feed delivers `oi` and `volume` for all listed strikes at a 5 s skew is `UNVERIFIED` (documented as requiring real broker verification in `STRATEGY_ASSUMPTIONS.md:36`).

Five-gate engine (`signal_engine.Rules.evaluate`, `signal_engine.py:45-199`):

| Spec item | Implementation | Result |
| --- | --- | --- |
| Five mandatory gates | `R-ST`, `R-MACD`, `R-ADX`, `R-VWAP`, `R-PCR`, plus `R-WARMUP`, `R-FRESH` and `R-MTF`; eligibility requires every check to be `PASS` (`signal_engine.py:132`) | PARITY PASS |
| Completed 5-minute decision candles | `completed_series` keeps only `complete` candles with `end <= now`, the right token and timeframe, finite positive OHLC, no overlap and no intra-day gap; any violation returns an empty series (`signal_engine.py:9-28`) | PARITY PASS |
| 15-minute confirmation | `R-MTF`: latest completed 15m SuperTrend direction equals the 5m direction and is younger than 15 min 30 s (`signal_engine.py:79-86`) | PARITY PASS |
| Directional mapping | `side = "CE" if direction == 1 else "PE"` (`signal_engine.py:186`) | PARITY PASS |
| No lookahead | indicators run over completed candles only; evaluation timestamp `now` is an argument | PARITY PASS |
| No phantom signal after restart | `decision_id = sha256(token:last_candle_end:config_id)` is deterministic, and `process`/`admit` use intent id idempotency (see section 7). `R-FRESH` also requires the latest completed 5m candle to be no more than 30 s old, so a restart mid-candle cannot trade an old candle | PARITY PASS |
| Candle-break confirmation | `R-CANDLE` exists but `previous_candle_break` defaults to `False` (`config.py:40`), so by default it is not a gate | OPEN QUESTION. `STRATEGY_ASSUMPTIONS.md` does not list it as a mandatory gate, so default-off is consistent with the document; the assignment text lists "candle-break confirmation" as a rule to verify. `UNVERIFIED` which is intended |
| Morning bias and reversal constraints | not implemented. `READINESS_REPORT.md:61, 89, 255` records that no separate frozen morning classification or reversal policy exists because the semantics were ambiguous and were "not invented" | STRATEGY-SPEC GAP, already disclosed. If these rules are required, they are absent from the signal engine |

History-gap behaviour (affects every gate): `aggregate` drops any 5-minute bucket that lacks one of its five minutes (`market_data.py:38-43`), and `completed_series` returns an empty series when two consecutive same-day candles are not contiguous (`signal_engine.py:22-27`). Measured: five sessions of complete minute data give 375 usable 5-minute candles; removing one minute on the first of the five days gives 374 built and **0 usable**, so `R-WARMUP` fails, the indicator gates report `UNAVAILABLE` on the empty snapshot, and the decision is `NO_TRADE` with bias `DATA_UNAVAILABLE`. Because the history window is nine calendar days, one missing broker minute blocks every signal until that day leaves the window. This fails safe and follows the documented "reject ambiguous series instead of repairing" rule, but the spec only names missing session-opening data and missing volume as blocking. See N-04.

## 6. Smart Option Selector (Priority 6)

Sources: `services/nifty_algo/selection_scoring.py:18-86` (`score_plan`), `risk_manager.py:52-160` (`plan_entry`), `contract_resolver.py:9-252` (`liquidity_reasons`, `moneyness`, `Resolver.assess`), `paper_executor.py:120-443` (`admit`, `validate_entry`), `runner.py:312-387` (`_entry_candidates`).

| Requirement | Evidence | Result |
| --- | --- | --- |
| Weights 30 / 25 / 15 / 20 / 10 | `FACTORS` order (liquidity, spread, delta, reward_risk, capital_efficiency) zipped with `selector_weights` default `(30, 25, 15, 20, 10)`; weights must sum to 100 (`config.py:44-50, 109-112`) | PARITY PASS |
| No redistribution | missing delta earns 0 under its unchanged weight (`selection_scoring.py:42-44`); no code path rescales weights | PARITY PASS |
| OI caps volume inside the 30 percent liquidity factor | `liquidity = 0.75 * clamp(depth_ratio / 3) + 0.25 * clamp(min(volume, oi) / (3 * min_volume))`, with the OI term zero when OI is missing or stale (`selection_scoring.py:30-40`) | formula PASS; integration FAIL, see N-02 |
| Missing OI earns zero without excluding | OI is not an exclusion criterion; exclusion comes from `liquidity_reasons` (quote age, token, depth of one lot, spread, volume of at least `min_volume`) | PASS |
| ATM/ITM only | `Resolver.assess` offers the nearest listed strike (labelled ATM through the `atm_strike` argument) plus up to two nearby ITM strikes; OTM is excluded (`contract_resolver.py:110-169, 184-185`) | selection PASS; admission conflict, see N-03 |
| Correct CE/PE direction | resolver filters `instrument.kind == side`; `admit` refuses `candidate.kind != decision.side` (`paper_executor.py:248-256`) | PASS |
| Dated-master lot sizes | `quantity = lots * instrument.lot_size` (`risk_manager.py:110`); `Instrument.lot_size` comes from the dated master, which `docs/prompt/LotSize.md:14` lists as 65 for NIFTY | PASS |
| Genuine bid/ask depth, no LTP fallback | `depth_quote` reads best bid and ask from depth levels only and leaves them `None` when absent, never LTP (`depth_quote.py:56-83`); entry is `ask + slippage`, exits are `bid - slippage` | PASS |
| Net charges | `_charges` adds brokerage, exchange transaction charge, GST on both, STT on the sell side, stamp on the buy side and SEBI fee, rounded up to 0.0001 (`paper_executor.py:36-49`) | arithmetic PASS; rates UNVERIFIED, see section 7 |
| Maximum planned loss 400 | `planned_loss = (entry - stop_exit) * qty + buy_cost + stop_cost + buffer(10)`, refused when `> 400` (`risk_manager.py:114-121`); re-checked at fill against both 400 and the reserved risk (`nifty_algo_db.py:2569-2621`) | PASS (400 itself is allowed) |
| Minimum projected net reward 350 | `reward = (target - entry) * qty - buy_cost - target_cost`, refused when `< 350` (`risk_manager.py:117, 122-123`) | PASS |
| Deterministic tie-break | sort by total descending, then planned loss, cash, expiry, strike, token, lots (`risk_manager.py:145-155`) | PASS |
| Revalidation under the admission lock | `validate_entry` runs inside `admit_order`'s locked transaction and re-prices the chosen contract from the current cache, refusing `SELECTION_CHANGED` if quantity, entry, planned loss or cash moved adversely (`paper_executor.py:406-439`, `nifty_algo_db.py:2299-2300`) | PASS |

Spread definitions differ slightly: the gate uses `(ask - bid) / ask` (`contract_resolver.py:31`, and the fill check `nifty_algo_db.py:2613`), the score uses `(ask - bid) / mid` (`selection_scoring.py:20`). At the 150 bps boundary a contract can pass the gate and score 0 on spread. Monotone and harmless; noted only for consistency.

## 7. Risk, protection and exit mathematics (Priority 7)

Sources: `protection.py` (`initial_protection`, `observe_bid`, `profit_floor_stop`, `modeled_exit_net`, `mandatory_exit_reason`, `early_booking_exit`), `risk_manager.py`, `paper_executor.py`, `nifty_algo_db.py` (fills, months, cooldowns). All monetary arithmetic is `Decimal`. Every check below was executed against the real functions with the default `StrategyConfig`, tick 0.05, lot 65.

| Rule | Executed result | Result |
| --- | --- | --- |
| Initial stop 8 percent, tighter allowed | entry 100.00 gives stop 92.00 (`ceiling_tick(entry * 0.92)`, so the distance never exceeds 8 percent) | PASS, matches `STRATEGY_ASSUMPTIONS.md:71-73` |
| Trailing 1.5 points, activation at entry + 1.5 | bid 101.45: inactive, stop 92.00. Bid 101.50: active, stop 100.00. Peak 106: stop 104.50. Bid falls to 104.60: stop stays 104.50. Peak 110: stop 108.50. Bid 108.50: `TRAILING_STOP` (inclusive) | PASS, exactly the documented example |
| Dynamic target 10 to 15 percent | score 50 gives fraction 0.125, target 112.50 on entry 100; target is the ceiling tick of `entry * (1 + fraction)` capped at the floor tick of `entry * 1.15`, refused if below `entry * 1.10` | PASS |
| Profit lock at modeled net 400, floor at modeled net 350 | 1 lot of 65 at entry 60.05 (entry fees 26.0240): first bid with modeled net at least 400 is 67.10 (net 400.0763), which activates the lock; floor stop 66.35 gives modeled net 351.3856 and one tick lower gives 348.1396, so the floor is the lowest tick meeting 350 | PASS |
| Modeled versus realized | a gap to bid 65.85 below the 66.35 floor exits `PROFIT_LOCK_STOP` with modeled net 318.9251, below 350. The floor is a trigger price, not a guaranteed outcome; `PROFIT_FLOOR_UNREPRESENTABLE` exits immediately when the floor would sit at or above the current bid (`protection.py:233-236`) | PASS, consistent with "a trigger is not a guaranteed fill" |
| Early booking at modeled net 300 with deterioration | peak 68.05, entry 60.05 (gain 8.00), retrace threshold 30 percent (2.40): bid 65.65 (net 305.94) and 65.60 (net 302.69) return `EARLY_PROFIT_BOOKING`; bid 66.05 (retrace 2.00) returns nothing; requires `momentum_weak` (histogram and price both deteriorating against the direction, `protection.py:304-341`) and is disabled once the profit lock is active | PASS |
| 45-minute hold | 44 minutes: none; 45 minutes: `MAX_HOLD` (inclusive) | PASS |
| 15:10 and early-close exit | 15:09:59: none; 15:10:00: `SESSION_EXIT`; with a 13:00 session close, 12:55 gives `SESSION_EXIT` (five minutes before close); no window also exits | PASS |
| Loss cooldown | `_cooldown_reasons` blocks a day after a loss session until the cooldown session is resolved (`nifty_algo_db.py:3253-3270`) | PASS (code read; executed through existing tests only) |
| Monthly 2,000 loss | latched when realized month net is at or below -2,000 (`nifty_algo_db.py:3185-3250`). It is a lock after the fact: a month at -1,900 can still open a trade with planned loss up to 400, so realized monthly loss can exceed 2,000 by one trade plus any gap | INTENTIONAL, matches "Monthly loss locks at 2,000" (`STRATEGY_ASSUMPTIONS.md:46`); it is not a hard cap on the overshoot |
| Idempotency and restart | see `NIFTY_COMPLIANCE_AUDIT.md` (order-path section): deterministic intent ids, locked admission, fills matched by order id | PASS |
| Separate Decimal evaluator | `services/nifty_algo/protection.py` imports nothing from `services/risk/`, and nothing outside NIFTY imports it; CLAUDE.md names it as the documented exception | PASS |

Feasible entry region (a consequence of the approved numbers, not a defect). Computed by running the real sizing path (`initial_protection`, `_charges`, the `plan_entry` formulas) across asks from 5.00 to 600.00 in 0.05 steps, with lot size 65 and capital 20,000:

| Confidence score | 1 lot | 2 lots | 3 lots |
| --- | --- | --- | --- |
| 0 | 62.00 to 64.30 | 31.00 to 31.80 | 20.50 to 21.15 |
| 40 | 51.65 to 64.30 | 25.80 to 31.80 | 17.05 to 21.15 |
| 70 | 45.90 to 64.30 | 22.95 to 31.80 | 15.15 to 21.15 |
| 100 | 41.30 to 64.30 | 20.65 to 31.80 | 13.95 to 21.15 |

So with an 8 percent stop and a 400 planned-loss cap, a single NIFTY lot can only be bought when the ask is at most 64.30; an ask of 100 gives a planned loss of 591.76 and is refused. Whether ATM and ITM NIFTY options (excluding expiry day) commonly trade in this band can only be judged with real option-chain data. If they rarely do, the system will mostly answer `NO_TRADE` through `PLANNED_LOSS_LIMIT` even when all five gates pass. This is internal consistency working as specified; the owner should confirm it is the intended operating envelope.

Fee rates: `_charges` uses STT on the sell side of 0.0625 percent and an exchange transaction rate of 0.05 percent (`config.py:89-94`). The documents call these research estimates, not statutory rates (`STRATEGY_ASSUMPTIONS.md:77-80`). I could not confirm the currently applicable NSE option rates from inside this audit. If the applicable STT or transaction rates are higher, planned loss is understated and reward overstated by a few rupees per lot, which moves the edges of the table above. `UNVERIFIED`.

LIVE isolation: `trading_mode.LiveAdapterStub.submit` always raises `OrderRefused(["LIVE_NOT_READY"])` (`trading_mode.py:46-72`), `admit` calls it for any BUY outside PAPER mode, `admit_order` adds `_mode_reasons`, and the fill path rejects on mode reasons. No broker order function is imported anywhere in `services/nifty_algo/` (checked in the reference audit). PASS.

## 8. Dataset coverage

| # | Dataset | Covered by | Outcome |
| --- | --- | --- | --- |
| 1 | Sustained bull | `path("bull")` fixtures | ST, MACD, ADX gate parity after bar 80 |
| 2 | Sustained bear | `path("bear")` | same |
| 3 | Choppy with repeated crossings | `path("chop")` | same; latest ST direction mismatch at bar 93 in one of 1,500 series |
| 4 | Reversal near boundary | `path("reversal")` | same |
| 5 | Exactly sufficient warm-up | series of 90 and 100 bars | ST: no gate difference; ADX: 7 threshold differences in 6,000 bars |
| 6 | Insufficient history | first valid bars: ST 9, MACD 33, ADX 27 (ours) | below 80 bars `R-WARMUP` fails, so no decision |
| 7 | Incomplete latest candle | `completed_series`, `supertrend` skip incomplete | refused, by code reading and existing test `test_macd_linear_series_hand_reference_and_prefix_causality` |
| 8 | Missing or invalid volume | VWAP fixtures | `None` volume invalidates the rest of the session; zero volume on the opening bar gives `None` for that bar |
| 9 | NSE session reset | four-session VWAP fixture | per-session parity 0.0; continuous `ta.vwap` diverges at bar 75 |
| 10 | Futures rollover | mixed `FUT1`/`FUT2` VWAP fixture | all `None`; `completed_series` also rejects a second token |
| 11 | Exact ADX threshold | code reading | inclusive `>= 25` |
| 12 | Zero and near-zero values | ADX zero denominators, MACD near-zero histogram examples (bar 101: -0.00096 against +0.00056) | sign flips near zero are where seed differences decide; confined to bars at or below 126 |
| 13 | PCR equality and denominator | code reading plus `test_nifty_algo_core.py:103-109` | 1.5 passes bull, 1.0 passes neither, `calls <= 0` refused |
| 14 | Conflicting 5m and 15m direction | `R-MTF` | refused, code reading; not executed here |
| 15 | Missing depth, OI, Greeks | selector code and the OI demonstration | missing delta scores 0; depth absence refuses; OI is dropped even when present (N-02) |

Not executed here: real Angel One history, option chains, Greeks, the 15-minute confirmation on real data, and the end-to-end runner on a live feed.

## A. Mathematical compliance verdict

**PARITY WITH DOCUMENTED EXCEPTIONS** for the four indicators that have OpenAlgo counterparts. Separately, two integration defects in option selection and admission (N-02, N-03) change which contract is bought or whether a buy happens. They are not indicator-parity failures.

## B. Indicator comparison table

| Indicator | OpenAlgo reference | NIFTY result | First difference | Trading decision impact | Verdict |
| --- | --- | --- | --- | --- | --- |
| SuperTrend | `ta.supertrend` (Pine recursion, `-1` = up) | ATR identical to 5.3e-15; bands and reversals identical | bar 9 (first valid bar), initial direction only; converges at the first reversal | 0 `R-ST` differences in 181,500 bars after bar 80; persists only if price never leaves a 3-ATR band over the whole history | INTENTIONAL DIFFERENCE (initial direction, sign convention) |
| MACD | `ta.macd` (EMA seeded from the first value) | identical to the SDK's SMA-seeded kernel `ema_sma` to 9.6e-12 | bar 33 (NIFTY's first value); 0.054 at bar 80, 5.3e-6 at bar 200 | 75 `R-MACD` differences in 600 series, all at bar 126 or earlier; none with production-length history | INTENTIONAL DIFFERENCE (SMA seed) |
| ADX | `ta.adx` (bar 0 included in the Wilder seed) | identical to a textbook Wilder reference to 1.4e-14 | bar 27 against the SDK's bar 26; 0.043 at bar 80, 1.3e-5 at bar 200 | 10 `>= 25` differences in 600 series, all at bar 110 or earlier | INTENTIONAL DIFFERENCE (Wilder seed) |
| VWAP | `ta.vwap(..., "Session", "hlc3")` | identical per session (difference 0.0) | the public SDK call has no session reset; diverges at the first bar of session 2 | none when compared per session; NIFTY is stricter on zero/missing volume and contract identity | PARITY PASS where inputs are equivalent; INTENTIONAL DIFFERENCE for reset and volume handling |
| PCR specification | none in `openalgo.ta`; spec in `STRATEGY_ASSUMPTIONS.md:29-36` | full expiry universe, dated master, one definition, no zero fill, 90 s age, 5 s skew, `calls <= 0` refused, 1.5 / 1.0 thresholds | not applicable | refuses rather than guesses | PARITY PASS against the spec; feed completeness UNVERIFIED |

## C. Strategy decision comparison

- **Agree:** in 1,500 SuperTrend fixtures and 600 MACD/ADX fixtures of production length (525 bars), every `R-ST` decision after bar 80 agreed, and every `R-MACD` and `R-ADX` decision after bar 126 agreed.
- **Numerically different, same decision:** MACD histogram at bar 105 of seed 70010: NIFTY 0.35373, SDK 0.35485, both positive. ADX at bar 80 differs by 0.043, which leaves almost every bar on the same side of 25.
- **Numerically different, different decision:** MACD at bar 101 of seed 70010: NIFTY histogram -0.00096, SDK +0.00056, so `R-MACD` for a bullish trade fails in NIFTY and passes on the SDK values. ADX threshold: 10 bars in 600 series and 7 bars in 6,000 short-history bars. All such cases sit in the first 126 bars, which production history (about 300 to 525 bars) does not reach.
- **Decision changed by integration, not by indicator maths:** the OI flip demonstration (N-02) picks contract A when OI is passed and contract B on the PAPER path; and the ATM conflict (N-03) turns a selector-approved CE at strike 22050 with spot 22030 into `OTM_PROHIBITED`.
- **Cannot be compared:** anything requiring real Angel One data (section F, question 8).

## D. Risk and selector findings

- **Lot sizing:** `lots * master lot_size`; correct. Score tiers 0 / 40 / 70 permit 1 / 2 / 3 lots, and smaller lot counts are also tried. Under the approved caps two or three lots are only feasible at asks of about 32 or lower.
- **Selector ranking:** weights and tie-break correct; the OI term is never fed on the PAPER path (N-02).
- **Risk planner:** planned-loss and reward formulas correct and re-checked at fill; entry premium is effectively confined to about 41 to 64 for one lot (section 7 table).
- **Transaction charges:** arithmetic correct and conservative (rounded up); the rates themselves are UNVERIFIED.
- **Trailing and profit-floor maths:** exact to the documented examples; floor search returns the lowest tick meeting the floor; gaps below the floor are not hidden.
- **Entry and exit eligibility:** precedence MAX_HOLD, TECHNICAL, SESSION, OPERATOR, discretionary; inclusive boundaries as tested. The ATM conflict (N-03) affects entry eligibility.
- **LIVE isolation:** intact.

## E. Findings for Codex

### N-02 (High, SIGNAL-CHANGING BUG): open interest is dropped on the PAPER selection and admission path

- File and function: `services/nifty_algo/depth_quote.py:56-83` (`depth_quote`), reached through `paper_executor.NiftyPaperExecutor._depth` (`paper_executor.py:466-495`), used by `runner._entry_candidates` (`runner.py:333-337`) and `admit` (`paper_executor.py:274-276`, `421`).
- Root cause: `depth_quote` builds the `Quote` without `oi`, so every PAPER quote has `oi = None`, `score_plan` treats OI as unavailable, and the volume part of liquidity (up to 7.5 of 100 points) is always zero. The research reader `NativeDataAdapter.recording_quote` (`native_data.py:205-235`) does copy `oi` from the same mode-3 source, so replay ranks with OI and PAPER ranks without it.
- Reproduction (executed): a raw mode-3 source with `oi = 5000` gives `depth_quote(...).oi == None`. Two candidates: A (spread 10 bps, depth 130, volume 3000) and B (spread 30 bps, depth 195, volume 1000). With OI present A wins (65.96 against 65.12); with OI dropped B wins (62.62 against 58.46).
- Smallest safe correction: in `depth_quote`, pass `oi=raw.get("oi")`, accepting only a non-negative integer that is not a bool, the same way `recording_quote` does; under `strict=True` refuse a malformed value. Do not invent zero.
- Regression test: feed `_depth` a cached mode-3 observation with `oi`, assert `quote.oi`; then run `plan_entry` through `admit` with two candidates whose order depends on the OI-capped volume term and assert the winner matches the replay path.
- Changes PAPER results: yes, contract choice; it does not change whether the five gates pass.

### N-03 (High, SIGNAL-CHANGING BUG, owner decision needed): the selector's ATM is refused as OTM at admission and fill

- Files and functions: `contract_resolver.moneyness` (`contract_resolver.py:38-50`) is called with `atm_strike` by the resolver (`:117, 153, 160, 181`) and in `admit` (`paper_executor.py:203-209`), but without it in `validate_entry` (`paper_executor.py:417-418`), at fill (`nifty_algo_db.py:2602-2607`) and in execution replay (`execution_replay.py:531`).
- Root cause: two definitions of ATM. The resolver treats the nearest listed strike as ATM (its docstring says so). The later checks classify strictly against spot, so the nearest strike is OTM whenever it lies on the far side of spot. The fill check has the comment "Selection-time ATM evidence must not override current spot", and `test_recorded_atm_hint_cannot_override_current_otm_at_fill` covers a 100-point move, but no test covers the zero-move case.
- Reproduction (executed): strikes 22000 and 22050, spot 22030. CE 22050: selector `ATM`, admission and fill `OTM`. PE 22000: selector `OTM`; PE 22050: selector `ATM`, admission `ITM`. When the nearest strike is above spot for CE (or below for PE), which happens in about half of the strike interval, a top-ranked ATM candidate is refused under the lock with `OTM_PROHIBITED` and `admit` does not fall back to the next-ranked ITM candidate.
- Smallest safe correction (pick one, the owner decides what ATM means): (a) at admission and fill, recompute the nearest listed strike of the same expiry from the current spot and pass it as `atm_strike`, so a contract is accepted when it is the ATM strike now or ITM now; or (b) keep the strict rule and make the resolver offer only contracts that are ITM, or exactly at the money, at selection time. Option (a) keeps the existing intent of the fill test (a 100-point adverse move still rejects).
- Regression test: spot 22030, strikes 22000 and 22050, CE side: assert the resolver's top candidate is admitted (option a) or never offered (option b); keep the existing 21900 test.
- Changes signals: yes, `BUY CE` or `BUY PE` against `NO_TRADE`.

### N-04 (Medium, fails safe): one missing history minute disables signals for up to nine days

- File and function: `market_data.aggregate` (`market_data.py:38-43`) and `signal_engine.completed_series` (`signal_engine.py:22-27`), fed by `assess_current` (`assessment.py:119-155`).
- Root cause: an incomplete 5-minute bucket is dropped, which creates an intra-day gap, and `completed_series` then returns an empty list for the whole nine-day series.
- Reproduction (executed): five complete sessions give 375 usable candles; removing one minute on the first day gives 0 usable.
- Smallest safe correction (behaviour change, owner decision): keep rejecting a gap, but start the series after the last gap instead of discarding all of it (still causal and unrepaired), and let `R-WARMUP` decide if what remains is long enough; or record a specific `HISTORY_GAP` reason so the operator sees why there is no trade.
- Regression test: the five-session fixture above, asserting either a usable suffix or the explicit reason.
- Changes signals: yes, it restores signals that are currently blocked; until changed, the system is only more conservative.

### N-05 (Low, UNVERIFIED): crossover-freshness wording

- `cross_age <= 3` admits a crossover on the fourth most recent completed bar; the document says "within three completed entry bars". Confirm the intended count and add a boundary test at age 3 and age 4. No change unless the owner says otherwise.

### N-01 (Low): no regression test compares against `openalgo.ta`

- `OPENALGO_REUSE_AUDIT.md:28` and `VIDEO_STRATEGY_ANALYSIS.md:24` speak of "native parity tests", but no `test/test_nifty_algo_*.py` file imports `openalgo.ta`.
- Smallest correction: one test per indicator that asserts equality against `ta.supertrend` (with sign mapping, from the first reversal), against the SDK's SMA-seeded EMA for MACD, against a textbook Wilder ADX after bar 130, and against per-session `ta.vwap`. Use the fixtures in this report as a template.
- Changes signals: no.

## F. Final answers

1. **Are SuperTrend, MACD, VWAP and ADX mathematically equivalent to OpenAlgo where they should match?** Yes, with documented seeding and initialization differences. VWAP matches exactly per session; SuperTrend matches on ATR, bands and reversals; MACD matches the SDK's SMA-seeded kernel exactly and the public `ta.macd` after convergence; ADX matches textbook Wilder exactly and `ta.adx` after convergence.
2. **Can differences alter real strategy eligibility?** Only in the first roughly 126 entry bars of a series, and in a SuperTrend market that never leaves a 3-ATR band. Production history is about 300 to 525 bars, so in practice no. The integration defects N-02 and N-03 do alter eligibility or contract choice.
3. **Does the five-indicator confirmation implement the agreed rules?** Yes for the five gates, completed 5m candles, 15m confirmation, thresholds, CE/PE mapping and freshness. Morning bias and reversal constraints are not implemented, as `READINESS_REPORT.md` already discloses. Candle-break confirmation exists but is off by default.
4. **Is the OI-enhanced selector still compliant?** The formula is compliant: weights unchanged, OI only caps volume inside liquidity, missing OI earns zero and does not exclude. The PAPER path never supplies OI, so the approved enhancement is inactive there (N-02).
5. **Are risk and exit calculations internally consistent?** Yes. The worked examples match the documents to the tick, the profit floor is the minimal tick, and modeled and realized outcomes are kept apart. The approved caps confine one-lot entries to asks of about 41 to 64.
6. **Is the separate PAPER evaluator a justified exception?** Yes. It is documented in CLAUDE.md, pure Decimal, isolated in both directions, and its maths checks out.
7. **Are any discrepancies dangerous?** None can cause a loss beyond the caps or a live order. N-03 and N-02 can make the system skip or misrank trades; N-04 can silence it for days. All three fail toward fewer or different paper trades, not toward unprotected exposure.
8. **What cannot be validated without real Angel One data?**
   - Whether mode-3 depth frames carry `oi` and `volume` for every listed strike within 5 seconds, which decides whether PCR is ever available.
   - Real minute-history completeness, which decides how often N-04 triggers.
   - How often ATM and ITM asks fall inside the feasible premium band.
   - Real SuperTrend, MACD and ADX convergence on actual futures history.
   - Fill quality against displayed depth.
   - The applicable fee rates.

## Reproduction

The comparison scripts are throwaway files in the session scratchpad (`parity_lib.py`, `st_parity.py`, `st_stress.py`, `st_stress2.py`, `macd_adx.py`, `macd_adx_idx.py`, `alt_kernels.py`, `adx_ref.py`, `vwap_parity.py`, `money.py`, `feasible.py`, `protect.py`, `oi_flip.py`, `gap.py`). Each one imports `openalgo` before putting the repository root on `sys.path` and was run with `uv run --no-sync python -I <script>`. None writes to the repository. No existing test was re-run in this audit; the reference audit records the last full NIFTY suite result (817 passed).
