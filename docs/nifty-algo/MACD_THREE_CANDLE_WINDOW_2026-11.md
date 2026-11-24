# MACD crossover window: three completed candles (strategy 3.2.0)

Date: 2026-11-24. Branch: `fix/nifty-macd-three-bar-window`. Scope: the NIFTY
PAPER strategy's `R-MACD` freshness condition. PAPER only; the live adapter
stub still refuses with `LIVE_NOT_READY`.

## The approved rule

A qualifying MACD crossover must be present in one of the latest three
completed 5-minute candles. The crossover candle is age 0; ages 0, 1 and 2
qualify, while age 3 or older does not.

| Crossover age | R-MACD freshness |
| --- | --- |
| 0 (latest completed candle) | passes |
| 1 | passes |
| 2 (third most recent completed candle) | passes |
| 3 | fails |
| 4 or older | fails |
| no crossover | fails |

Passing this condition is not an entry. The crossover direction must still
match the SuperTrend direction, the histogram must still agree with it, the
optional zero-line confirmation still applies, and every other gate, the risk
planner and the session rules still decide.

## Root cause: an off-by-one between the words and the comparator

`STRATEGY_ASSUMPTIONS.md` said "a crossover within three completed entry
bars". The gate was `cross_age <= crossover_freshness` with a default of 3.
Age counts from 0 at the latest completed candle, so an inclusive comparison
with 3 admitted four positions, 0 to 3: a crossover on the fourth most recent
completed candle passed. The 2026-11 parity audit (`NIFTY_INDICATOR_PARITY_AUDIT.md`
N-05) and the SDK 2.4.1 parity report recorded the ambiguity and left it for
the owner. The owner approved the three-position reading on 2026-11-24.

The indicator was never wrong: `indicators.macd` computes the age of the last
histogram sign change correctly, and its MACD 12/26/9 values, crossover
detection and EMA seeding are unchanged by this fix.

## The change

- `services/nifty_algo/config.py`: `strategy_version` is now `3.2.0`.
  `MAX_MACD_CROSSOVER_AGE = 2`. `crossover_freshness` defaults to 2, and a
  3.2.0 configuration with a value above 2 fails validation. 0 and 1 remain
  valid stricter choices.
- `services/nifty_algo/signal_engine.py`: the comparator stays inclusive
  (`0 <= cross_age <= crossover_freshness`), and an age that is not a plain
  integer (missing, negative, a float, a boolean, a string) fails instead of
  being compared.
- `active_configuration()` in `config.py` returns a configuration only if it is
  the current version. It is used everywhere a configuration can evaluate or
  admit a new entry: the runner's evaluation (`runner.py`), BUY admission in the
  paper executor (`paper_executor.py`), the configuration save and the manual
  assessment endpoints (`blueprints/nifty_algo.py`) and the store's
  `change()` (`database/nifty_algo_db.py`).
- `migrate_configuration()` gains a 3.1.0 to 3.2.0 step that lowers
  `crossover_freshness` to 2 when it was above 2 and leaves 0, 1 and 2 alone.
  The older 1.0.0, 2.0.0 and 3.0.0 chains now end at 3.2.0 through the same
  step.

## Configuration and replay compatibility

The decision: **narrow forward, keep the past readable**.

- **Saved current configuration.** On the first store access after upgrade,
  `ensure_user` sees 3.1.0, runs the migration, stores the result as a new
  configuration revision with a new `configuration_id`, records a
  `configuration_migration` event (`from: 3.1.0, to: 3.2.0`) and leaves the
  strategy PAUSED, exactly as earlier version bumps did. The old revision row
  stays in `nifty_configurations` untouched. The trader starts the strategy
  again after reviewing it. A record whose window cannot be read as an integer
  is not guessed at: it fails validation and the strategy stays paused with
  `VALIDATION_REQUIRED`.
- **Stored records keep their own rules.** `StrategyConfig` still validates a
  3.1.0 record, with its saved `crossover_freshness` (0 to 20), because held
  position protection, pending orders, execution quality, research manifests
  and replay baselines all carry the configuration they were made under, and
  refusing them would stop exits or erase evidence. The record's content and
  so its `version_id` are unchanged, and a replay of a 3.1.0 baseline makes
  the same decisions it made before, age 3 included.
- **A stored record never decides a new entry.** `active_configuration`
  refuses 3.1.0 with a field error on `strategy_version`; the runner reports
  `CONFIGURATION_INCOMPATIBLE`, BUY admission refuses, the API answers 400 and
  the store will not save it. A SELL against a held position still uses the
  position's own protection configuration.
- **Identity.** The default configuration's `version_id` changes (the version
  and the window are both in the hashed content), so a decision made under 3.1.0
  can never be admitted as a 3.2.0 decision: admission compares the decision's
  `config_id` with the active configuration's.
- **Research.** A research experiment must keep the baseline's strategy
  version, so a 3.2.0 baseline cannot be paired with a wider experimental
  window. A 3.1.0 baseline replays with 3.1.0 semantics. Research never places
  an order.

## Effect on confidence scoring

The MACD component's recency half is `1 - age / (freshness + 1)`, unchanged in
form. With the default window now 2 instead of 3, recency is 1, 2/3 and 1/3 at
ages 0, 1 and 2 (before: 1, 0.75, 0.5 and 0.25 at ages 0 to 3). The MACD
component contributes at most 20 of the 100 points and recency is half of it,
so at age 1 the score is 0.83 points lower than under 3.1.0 and at age 2 1.67
points lower. A signal near a lot threshold (40 or 70) can therefore size one
lot smaller, and the target fraction moves accordingly within 10 to 15%. No
score rises. Replays of 3.1.0 records score as before.

## Tests

New: `test/test_nifty_algo_macd_window.py` (48 cases). The boundary cases run
the real indicator and the real `Rules.evaluate` on seeded synthetic 5-minute
candles; a search finds the candle where the computed MACD shows each age with
a matching SuperTrend direction, so nothing patches the age or the gate:

- ages 0, 1 and 2 pass and ages 3 and 4 fail, bullish and bearish alike;
- no crossover, a crossover against the trade direction, a histogram that no
  longer agrees, and an invalid or negative age fail;
- missing MACD data reports `UNAVAILABLE`, never `PASS`;
- a forming candle (ending after now) and one flagged incomplete are ignored;
  a candle ending exactly now is counted;
- the optional zero-line confirmation behaves as before;
- a stored 3.1.0 record keeps its identity and still passes age 3 on replay,
  but `active_configuration` and the store refuse it;
- a 3.2.0 configuration cannot carry a window above 2;
- migration lowers 3, 4 and 20 to 2, keeps 0, 1 and 2, changes no other
  field, refuses an unreadable value, keeps unknown versions blocked, and
  writes a new revision and a `configuration_migration` event once;
- the confidence recency values above.

Updated: `test/test_nifty_algo_phase1.py` now expects migrations to end at
3.2.0. `test/test_nifty_algo_sdk_241_parity.py` keeps the frozen 3.1.0 census
as historical evidence (run against a 3.1.0 record, unchanged numbers prove
the indicator mathematics did not move) and adds the census under the current
window: isolated R-MACD disagreements `(21,79)`, `(49,87)`, `(54,124)`; native
direction adds `(4,79)`, `(4,80)`; the sideways and low-volatility paths drop
from 189 and 126 to 141 and 100 disagreements. The 3.1.0 counterexamples
`(21,80)` and `(49,88)` now agree, both failing.

## Limitations

- No evidence says the narrower window is more or less profitable. It is the
  owner's reading of the rule, not an optimisation, and it can only remove
  signals that 3.1.0 admitted.
- Every install with a saved NIFTY configuration is paused once by the
  migration and must be started again by the trader.
- Whether real broker history produces the same crossover ages as the
  synthetic fixtures is not verified here.
- The Linux gunicorn suites were not run locally; CI runs them.
