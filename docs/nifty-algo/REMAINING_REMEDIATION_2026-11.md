# NIFTY remaining audit remediation (batch B) - November 2026

Applies to strategy 3.3.0. Strategy 3.1.0 and 3.2.0 records keep their original
semantics and are not described as current here. Companion documents:
[audit remediation register](AUDIT_REMEDIATION_2026-11.md),
[confidence decision](CONFIDENCE_OWNER_DECISION_2026-11.md),
[charge evidence](CHARGES_EVIDENCE_2026-11.md),
[review coverage](REVIEW_COVERAGE_2026-11.md) and the generated
[evidence](evidence/remaining-analysis.md).

## Provenance

- Original audit: PR #9, commit `1cc30502d3d66a8611fd2127f29e5169e0b3f021`,
  `docs/nifty-algo/COMPLETE_STRATEGY_CODEBASE_AUDIT.md`. Read from that commit.
  The audit branch was not merged.
- Batch A: draft PR #10 (`fix/nifty-audit-execution-correctness`, head
  `b18b05bb7`). It was **still open and unmerged** when this work was done, so
  this batch sits on top of it locally and is not pushed to that branch.
- Starting `origin/main`: `dcfb8df6e0f5ef3e3d9365b6e449d91c81c1f09d`.
- An earlier session had left this work uncommitted in the working tree. It was
  reviewed, its failing tests were triaged and fixed here, and it was committed
  in logical pieces. Nothing in it was assumed correct without a test run.

## What changed

| Area | Change |
|---|---|
| Strategy version | 3.3.0 is current. 3.1.0 and 3.2.0 are legacy: they load, replay and protect held positions with their own rules and cannot start a new entry. |
| SuperTrend | Defaults 20 and 2.0 in `StrategyConfig`, the `supertrend()` function default, the 5-minute and 15-minute evaluation (one call site, `signal_engine.snapshot`), research overrides (`atr_period`, `atr_multiplier`), the settings API and the settings page. Legacy configurations keep 10 and 3. |
| Migration | Additive and idempotent. An omitted indicator key proves an implicit default and migrates to 20/2. Explicit 10/3 is ambiguous (old saves wrote defaults and custom choices the same way) and needs `approve_supertrend`; the stored configuration then pauses entries and records `SUPERTrend_MIGRATION_APPROVAL_REQUIRED`. Any other explicit pair is kept. Lower-than-published charge inputs need `approve_fees`. A version change is refused while an order is pending or a position is held (`MIGRATION_EXPOSURE_ACTIVE`; `StateConflict` from `NiftyStore.change`). Same-version edits stay allowed, because held positions keep their own pinned configuration. |
| Diagnostics | Each new decision records `effective_configuration`, `config_id` and `charge_model`; `/api/nifty-algo/indicators` returns them; the settings page shows the strategy version. |
| Confidence | `five-indicator-v2-pinned` for 3.3.0 (SuperTrend duration /10, ATR distance /3, MACD recency denominator 3). Legacy versions keep `five-indicator-v1`. The validator ties the method to the version. |
| Charges | `fees.py` is a pure module. 3.3.0 uses the published-rate estimate; 3.1.0/3.2.0 keep the exact historical formula. Sandbox charges are not imported. |
| Candle retry | `NiftyAssessmentAttempt` is a durable, fenced claim per (user, 5-minute boundary, configuration): bounded to 7 attempts, 5 s apart, only inside the existing 30 s window. Only `R-FRESH` and `R-HISTORY` failures and timeouts retry. Permanent refusals commit once. |
| Session completeness | `market_data.session_series` is the one completeness policy for live PAPER and replay. A missing opening bucket, interior gap, missing previous-session tail or missing calendar day is refused or discarded; no future information is used. Replay engine version is `causal-options-execution-v2` for 3.3.0 and `-v1` for legacy. |
| Calendar | The approved NIFTY calendar and the native calendar must both allow a new entry. A native window of `None` on an approved trading day is `CALENDAR_DISAGREEMENT` and locks entries. A protective SELL is blocked only on positive evidence that the session is over (a valid native window that excludes the time). An unreadable or disagreeing calendar never blocks it. |
| Feed provenance | The Angel adapter and the shared cache keep `quote_time`, `last_trade_time`, `broker_time` and `received_time` apart. Depth freshness uses `quote_time` only. Untyped `ltt` or receipt time cannot certify a book, except for legacy 3.1.0/3.2.0. Duplicate and out-of-order packets do not replace the cache. |
| Diagnostics for real feeds | `feed_diagnostics.snapshot_evidence` is an allowlist (no packets, headers, credentials or exceptions), bounded to 1000 rows per PCR read. |
| Reports | The month report query selects only the event kinds the report reads (`report_policy.REPORT_EVENT_KINDS`, with a drift test) through an additive index. Report content is unchanged. |
| Hygiene | The two historical source patchers now exit with `RETIRED` before reading or writing. `.ignore` keeps search tools out of dependency junctions. `scripts/nifty_review_inventory.py` lists files from the git index. |

## Behaviour a reader must act on

- A new install or a 3.2.0 configuration with omitted indicator keys becomes
  3.3.0 with SuperTrend 20/2 and **paused entries**. Start must be pressed again.
- A stored explicit 10/3 stays 3.2.0 and paused until the trader reviews the
  upgrade on the settings page (the "Review approved 20/2 upgrade" button).
- A 3.3.0 entry is refused if its charge inputs sit below the published floors
  (brokerage 20, transaction 0.000355299, STT sell 0.0015, GST 0.18, SEBI
  0.000001, stamp 0.00003). Higher custom values are allowed.
- The 3.3.0 charge estimate is higher on the sell side (STT 0.15 percent versus
  0.0625 percent) and lower on the exchange charge. Feasible premium bands move
  by a few rupees of planned loss. In a 25-unit test fixture, a 165 premium no
  longer fits the INR 400 loss cap at admission under the 3.3.0 estimate.
- Replay results of 3.3.0 are not comparable with 3.2.0 replays. The engine
  version differs on purpose.
- F-04 and F-26 are active only because the owner approval quoted in the
  confidence decision document was recorded in the earlier session. It could not
  be re-verified here; please confirm it (see outstanding questions).

## Test failures found and fixed in this pass

The inherited tree failed **20** tests in the CI-selected set. None was skipped,
deselected or marked as expected failure.

| Cause | Tests | Resolution |
|---|---|---|
| Fixtures set `ltt` but not `quote_time`; depth freshness now needs `quote_time` | 7 capture-runner, 6 offline-acceptance OI ranking | Fixtures updated. The production rule is the F-07 fix. |
| A new `CALENDAR_DISAGREEMENT` day was neither `TRADING` nor an "unknown" day in the report scanner, so a report day could be skipped silently and the cursor advanced | `test_unknown_session_window_is_recorded_and_retried` | Production bug fixed: the scanner records and rechecks the day like other unknown sessions. Test parametrized over both statuses. |
| Protective SELL gating had been removed entirely | `test_exits_are_still_governed_by_the_real_session...` | Production fixed: SELL waits only on a valid window that excludes the time. |
| Configuration edits refused while any exposure existed, contradicting the pinned-protection test | `test_entry_snapshot_does_not_follow_later_config` | Production fixed: only version changes wait for flat exposure. |
| 3.3.0 charges push a 165 premium past the INR 400 cap | 2 `test_nondefault_tick_slippage...` | Fixture admits at 160. The cap is unchanged. |
| A missing minute now discards today's bars; warmup passes from prior sessions while freshness and `SESSION_VWAP_INCOMPLETE` refuse | `test_end_to_end_a_missing_minute_today_still_refuses` | Assertion names the real refusal reasons. The entry is still refused. |
| Cold-cache subprocess import exceeded its 30 s limit under load | `test_pytest_import_resolution[False]` | Passes in 5 s warm. Environmental; no code change. |

## Verification

See the "Final verification" section of the register for command lines and
counts. Python-path runs use `NUMBA_DISABLE_JIT=1`. The 20/2 SDK parity test
asserts the installed Rust extension (`HAVE_RUST`) and compares it with the
pure-Python fallback, so compiled parity is exercised there. No other compiled
path is claimed.

## Evidence still required, and decisions still open

1. F-05: a dated Angel rounding and invoicing specification, or sanitized
   contract-note component totals (several orders, partial exits, STT totals
   near 50 paise, IPFT GST treatment). Note: Angel's own charges page gives STT
   0.15 percent in its table and 0.1 percent in its FAQ (fetched 25 November
   2026). The code follows NSE and the table; the conflict is unresolved.
2. F-06 and F-07: raw, sanitized Angel full-chain packets with trade, quote and
   receive times, plus a dated complete expiry master. Whether a 90 s age and
   5 s skew are reachable across the whole chain, and whether the adapter's
   `exchange_timestamp` is a book-update time, cannot be known offline. The
   native session quota (1000) against `required_native_subscriptions` is
   reported per PCR read.
3. F-15: observed premium, lot and spread data. The tables are arithmetic only.
4. F-16: whether ranking should use the ask denominator like the gate.
5. F-18: whether to seed SuperTrend direction like the SDK. The evidence shows
   ranging data keeps opposite directions for hundreds of bars before a
   reversal, so the 80-bar warmup does not guarantee convergence.
6. F-23: a retention and archive policy. Nothing is deleted or compacted.
