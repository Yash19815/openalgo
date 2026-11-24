# NIFTY PAPER offline acceptance - November 2026

Baseline: `origin/main` at `a89854a5545c4232ccf37d96605e011e69326e49`.
Branch: `test/nifty-paper-offline-safety`.

## What this establishes, and what it does not

This record covers deterministic, offline acceptance of the NIFTY PAPER feature:
synthetic candles, synthetic options, simulated depth, a fake clock and an
isolated SQLite file per test. No broker, feed, API key, static IP, Discord or
SMTP service was used, and no order of any kind was sent. The new test module
raises if any code it exercises imports a broker, the shared Sandbox or a
generic order service, or opens a network connection (`offline_guard` in
`test/test_nifty_algo_offline_acceptance.py`; `test_the_runtime_guard_is_not_vacuous`
proves the guard fires).

**Offline acceptance does not establish profitability.** It shows that the
ledger, risk gates, session rules, data-rejection paths and restart recovery
behave as documented for these inputs. It says nothing about expected returns,
about how a real Angel One feed behaves, about real-market fills or slippage,
or about whether the strategy has any edge. Real-feed items are listed under
"Gaps requiring an authorized broker feed".

The MACD crossover freshness boundary (`cross_age <= 3`, default freshness 3)
was not touched and is not assessed here. It remains an open interpretation
question owned elsewhere; no indicator logic or configuration changed.

## Method

1. Read the strategy assumptions, the compliance record, the paper executor,
   risk manager, protection, runner, contract resolver, depth quote, native
   data, replay, the store, and the existing NIFTY tests.
2. Listed which end-to-end invariants the existing suites did not cover (the
   existing suites are mostly per-function or per-phase) and wrote tests only
   for those.
3. Drove the real `NiftyPaperExecutor` and `NiftyStore` through a small
   harness (`Desk`, `Feed`) that supplies a fake clock and a fake cache. Only
   the clock, the market cache and the master listing are faked.
4. Checked that the tests can fail: five temporary production mutations (loosen
   the planned-loss gate, make live mode undetectable, make the 45-minute hold
   off by one, make the PCR skew boundary inclusive, open the entry window
   early) were applied and reverted; the first four were caught by the named
   tests. The fifth mutation raised a `NameError` in production code, which
   makes the suite fail for the wrong reason, so it is not counted.
   Production files were restored and are unchanged in the diff.

## Result summary

| Item | Value |
| --- | --- |
| New file | `test/test_nifty_algo_offline_acceptance.py` |
| Collected | 132 (62 test functions, parametrised) |
| Passed | 129 |
| Expected failures (strict `xfail`, each a documented defect) | 3 |
| Failed | 0 |
| Run | Windows, Python 3.12.11, `pytest -o addopts=""` with `--basetemp` |

The three strict `xfail` tests assert the behavior the specification asks for
and fail today. They are strict: when the defect is fixed they start to pass,
the run fails with XPASS, and whoever fixed it removes the marker. They name the
defect in their `reason` and are restricted to the expected failure type
(`raises=`), so an unrelated error cannot hide behind them.

Status words below: PASS means asserted and green; FAIL means a defect is
demonstrated by a strict xfail; UNVERIFIED means it cannot be checked offline.

## Requirements tested

### 1. PAPER execution isolation

| Requirement | Test | Status |
| --- | --- | --- |
| No broker, Sandbox or order service import or call in any NIFTY source (services, `database/nifty_*`, `blueprints/nifty_*`), including dynamic imports | `test_no_nifty_source_imports_or_calls_a_broker_sandbox_or_order_service` (39 files) | PASS |
| The same holds at runtime for everything the suite executes | `offline_guard` (autouse) and `test_the_runtime_guard_is_not_vacuous` | PASS |
| `LiveAdapterStub` refuses with `LIVE_NOT_READY`; Live readiness is never empty even for the most favorable broker status | `test_live_adapter_stub_refuses_and_live_readiness_is_never_empty` | PASS |
| A Live mode request is refused and the account stays PAPER | `test_a_live_mode_request_is_refused_and_the_account_stays_paper` | PASS |
| No live fallback: a corrupted LIVE mode row refuses a new entry, still lets the paper position be closed by simulation | `test_a_corrupted_live_mode_row_still_cannot_open_a_position_but_can_close_one` | PASS |
| User and account boundaries: orders, positions, fills, exits and monthly locks never cross users | `test_accounts_do_not_share_orders_positions_locks_or_fills` | PASS |
| Fill accounting is separate from the shared Sandbox (tables, engine, reconciliation from NIFTY tables alone) | `test_nifty_ledger_tables_are_disjoint_from_the_shared_sandbox`, `test_paper_fills_reconcile_from_the_nifty_ledger_alone` | PASS |

### 2. Capital and loss limits

| Requirement | Test | Status |
| --- | --- | --- |
| New accounts start at 20,000; capital cannot be configured to another value | `test_new_accounts_start_at_20000_and_the_capital_cannot_be_configured_away` | PASS |
| Existing balances do not reset on re-initialisation, restart or day rollover | `test_existing_balances_survive_reinitialisation_restart_and_day_rollover` | PASS |
| Position size 1-3 lots; planned loss at most 400; projected net reward at least 350; cash within funds, for every price and score in a sweep (6 scores x 1,160 prices) | `test_every_sized_plan_respects_lots_loss_reward_and_cash_limits` | PASS |
| Configured ceilings cannot be loosened | `test_the_configured_risk_ceilings_cannot_be_loosened` | PASS |
| One-, two- and three-lot entries carry the sized quantity and the limits through to the filled order | `test_a_filled_entry_carries_the_sized_quantity_and_modeled_limits` (2), `test_three_lots_need_a_high_score_and_a_cheap_premium` | PASS |
| A stop at the modeled exit loses exactly the modeled amount less the buffer, never above 400 | `test_a_stop_at_the_modeled_exit_loses_exactly_the_modeled_amount_less_the_buffer` | PASS |
| One filled primary entry per session (a second is refused after a flat exit; an unfilled expiry does not consume the session; no second pending entry) | `test_one_filled_primary_entry_per_session_even_after_flat_but_an_expiry_does_not_count`, `test_a_second_entry_cannot_be_admitted_while_the_first_is_pending` | PASS |
| Rejected orders do not corrupt the ledger (refused at admission; rejected at fill; bad fill inputs) | `test_refused_admissions_leave_the_ledger_byte_for_byte_unchanged`, `test_fills_that_fail_final_revalidation_do_not_move_money_or_use_the_entry`, `test_fill_inputs_that_are_not_the_observed_depth_are_refused_and_change_nothing` | PASS |
| Charges are whole ceilinged amounts; an exact round trip conserves cash; equity equals 20,000 plus journaled net over several sessions of wins and a loss | `test_charges_are_whole_ceilinged_amounts_and_an_exact_round_trip_conserves_cash`, `test_cash_and_equity_stay_consistent_over_several_sessions_of_wins_and_a_loss` | PASS |
| Daily loss protection (1.5 percent) pauses entries and the loss cooldown applies next session; the exit that caused it is never blocked | `test_the_daily_loss_lock_pauses_entries_but_never_blocks_the_exit_that_caused_it` | PASS |
| Monthly loss lock at exactly 2,000 of realized net (-1,999.99 open, -2,000 locked); latches and survives a later recovery; exits stay permitted; rolls over at the IST month boundary to the second | `test_monthly_loss_lock_threshold_is_exactly_2000_of_realized_net` (4), `test_the_monthly_lock_latches_stays_through_a_recovery_and_does_not_block_exits`, `test_the_monthly_lock_rolls_over_at_the_ist_month_boundary` | PASS |

### 3. Time-based protections

| Requirement | Test | Status |
| --- | --- | --- |
| Entries refused before 10:30 and from 14:45 IST, accepted at 10:30:00 and 14:44:59 | `test_primary_entries_are_admitted_only_from_1030_until_before_1445_ist` (8) | PASS |
| An entry admitted in the last second cannot fill at or after 14:45 | `test_an_entry_admitted_in_the_last_second_never_fills_at_or_after_1445` | PASS |
| That entry's stored expiry is the same instant read back | `test_the_cutoff_expiry_is_the_same_instant_after_it_is_stored` | FAIL (D-3) |
| Maximum hold: no forced exit at 44:59, forced exit at 45:00 | `test_a_position_is_force_exited_after_exactly_45_minutes` | PASS |
| Mandatory exit at 15:10, or five minutes before an earlier effective close; precedence; a missing window fails closed | `test_the_1510_session_exit_wins_when_the_hold_limit_is_later`, `test_an_earlier_effective_close_pulls_the_exit_to_five_minutes_before_it`, `test_mandatory_exit_precedence_and_missing_session_window_fail_closed` | PASS |
| Weekends, approved holidays, an unapproved calendar and special sessions never permit entries | `test_entries_are_refused_on_weekends_and_approved_holidays` (2), `test_an_unapproved_calendar_blocks_entries_and_special_sessions_never_enable_them` | PASS |
| An exit never invents a fill when the real session is closed | `test_exits_are_still_governed_by_the_real_session_when_the_calendar_says_closed` | PASS |
| No new entry inside the exit buffer of an early close | `test_an_entry_is_not_opened_inside_the_final_exit_buffer_of_an_early_close` | FAIL (D-2) |
| A position carried over a session boundary is closed at the next open; day counters reset and carried equity is the baseline | `test_a_position_carried_over_a_session_boundary_is_closed_on_the_next_open` | PASS |

### 4. Market-data rejection paths

| Requirement | Test | Status |
| --- | --- | --- |
| Missing OI is never zero; invalid own-contract OI (bool, string, float, negative, list) ranks exactly like missing OI and never better; another contract's OI is not used | `test_an_invalid_own_contract_oi_ranks_exactly_like_a_missing_oi_and_never_better` (5), `test_another_contracts_oi_packet_cannot_supply_oi_or_improve_ranking`, `test_a_missing_oi_is_never_counted_as_zero_in_pcr` | PASS |
| PCR covers one complete dated expiry; an unlisted expiry never falls back to the nearest; expiries are never blended | `test_pcr_covers_one_complete_dated_expiry_and_a_wrong_expiry_never_substitutes` | PASS |
| An incomplete chain or mismatched CE/PE strikes block PCR, with no renormalisation | `test_an_incomplete_chain_blocks_pcr_instead_of_renormalising`, `test_mismatched_ce_and_pe_strike_ladders_block_pcr` | PASS |
| Cross-leg skew over five seconds blocks PCR (5 s passes, 6 s blocks); stale legs block | `test_pcr_blocks_when_cross_leg_source_skew_exceeds_five_seconds` (2), `test_pcr_blocks_when_every_leg_is_older_than_the_source_age_limit` | PASS |
| Option depth must be at most five seconds old, never future-dated, with receipt time between source time and now | `test_option_depth_must_be_fresh_and_never_from_the_future` (4), `test_a_receipt_time_before_the_source_time_or_after_now_is_refused` | PASS |
| A stale spot blocks entry even when option depth is fresh | `test_a_stale_spot_reference_blocks_entry_even_when_option_depth_is_fresh` | PASS |
| Missing, one-sided, sub-lot, wide-spread or low-volume depth blocks entry; LTP never substitutes | `test_unusable_depth_blocks_new_entries_and_ltp_never_substitutes` (5), `test_depth_that_vanishes_before_the_fill_leaves_the_entry_pending_then_expired` | PASS |
| Revalidation before the final fill: spread blow-out, monthly lock latched, kill switch | `test_fills_that_fail_final_revalidation_do_not_move_money_or_use_the_entry`, `test_monthly_lock_and_kill_switch_between_admission_and_fill_stop_the_fill` | PASS |
| Every strike the selector offers is one admission will not call OTM, over a grid of spots (CE and PE, midpoints included) | `test_every_strike_the_selector_offers_is_one_admission_will_not_call_otm` (2) | PASS |
| A ladder that does not bracket spot never labels a strike ATM | `test_a_ladder_that_does_not_bracket_spot_never_labels_a_strike_atm` (8) | PASS |
| A gappy ladder that does bracket spot does not make a distant strike ATM | `test_a_gappy_ladder_that_brackets_spot_does_not_make_a_distant_otm_strike_atm` | FAIL (D-1) |
| A history gap anywhere in the evaluated session, or a missing opening candle, blocks the decision; a gap in an older session does not; history that stops early blocks | `test_minute_history_gaps_and_missing_opening_data_block_the_decision` | PASS |
| A decision older than 30 seconds cannot be admitted | `test_a_decision_made_on_stale_history_cannot_be_admitted` | PASS |

### 5. Recovery and persistence

| Requirement | Test | Status |
| --- | --- | --- |
| Restart (new store object on the same database) preserves holdings, protection (peak, ratcheted stop), locks and reconciliation; the entry intent is idempotent and a second entry is refused | `test_restart_preserves_holdings_protection_locks_and_never_duplicates_the_entry` | PASS |
| An exception inside a SELL fill rolls the whole fill back, is surfaced, and a retry fills once with consistent cash | `test_an_exception_inside_a_sell_fill_rolls_the_whole_fill_back_and_retries_cleanly` | PASS |
| An exception inside a BUY fill leaves the order pending with no debit | `test_an_exception_inside_a_buy_fill_leaves_the_order_pending_with_no_debit` | PASS |
| A failure path is durably observable (one critical `STALE_DATA` incident, entries interlocked) with no notification sent | `test_losing_depth_on_an_open_position_is_durably_visible_without_any_notification_send` | PASS |

## Existing coverage reused, not repeated

The new tests import the existing executor and pipeline fixtures
(`test_nifty_algo_paper_executor`, `test_nifty_algo_pipeline`) and rely on, but
do not re-assert:

- Idempotent admission, ask-plus-slippage and bid-minus-slippage fills, TTL
  expiry, uncovered sells (`test_nifty_algo_paper_executor.py`).
- Selector and admission agreement on ATM/ITM, adverse moves between admission
  and fill, no master evidence, gap-trimmed history, rollover refusal
  (`test_nifty_algo_strategy_integration.py`).
- Runner end to end without order services, import-graph check of
  `services/nifty_algo/` (`test_nifty_algo_pipeline.py`).
- Cooldown and monthly lock mechanics (`phase3b`, `phase4`, `phase6`), Live
  stub readiness (`phase5`), calendar statuses (`calendar`), profit lock,
  trailing and early booking (`phase4`, `v2`).

## New coverage added

Items the existing suites did not assert as whole-system invariants:

- A runtime and static no-broker, no-Sandbox, no-network guard across the
  services, database and blueprint sources and everything the suite runs.
- A sizing sweep that checks lots, loss, reward and cash for every price and
  confidence tier, with non-vacuity checks.
- The exact modeled-loss identity at the modeled stop, and cash conservation
  over multiple sessions.
- Exact boundaries: 10:29:59 / 10:30:00, 14:44:59 / 14:45:00, 44:59 / 45:00,
  15:09:59 / 15:10:00, skew 5 s / 6 s, depth age 5.000 s / 5.001 s, monthly
  loss -1,999.99 / -2,000, and the IST month rollover to the second.
- Invalid-OI ranking equivalence, PCR expiry, completeness and skew paths.
- A moneyness property over a grid of spots, plus sparse and unbracketed
  ladders.
- Crash atomicity of a fill, restart recovery of protection state and locks,
  and durable failure evidence.

## Defects discovered

None of these changes any ledger amount for an order that fills, and none is a
route to a real order. Production files were not changed; each has a strict
`xfail` test and a suggested patch for the owner to review.

### D-3: an entry admitted in the last 10 seconds before 14:45 IST expires at the wrong instant

Severity: low. Never fills after 14:45; the harm is a lingering PENDING order.

`NiftyPaperExecutor.admit` (`services/nifty_algo/paper_executor.py`, the block
that begins `if side == "BUY": cutoff = datetime.combine(...)`) caps the
expiry with `min(expires_at, cutoff)`, where `cutoff` is built with
`tzinfo=IST`. When the cutoff wins (an entry admitted from 14:44:50), the
IST-aware value is stored through SQLAlchemy's SQLite `DateTime`, which keeps
the wall time and drops the zone. It is read back by `_instant()` as UTC.
Observed: stored `2026-11-19 14:45:00`, read back as `14:45 UTC`, which is
20:15 IST.

Effect: `expire_pending` does not expire the order at 14:45. The hard cutoff
inside `fill` still refuses any fill, but only when a fill is attempted with
fresh depth. With no fresh depth the order stays PENDING until 20:15 IST. While
pending it counts as open exposure (the mode-change guard reports
`OPEN_EXPOSURE`) and blocks a further entry with `PENDING_ENTRY`.

Reproduction: `test_the_cutoff_expiry_is_the_same_instant_after_it_is_stored`.

Suggested patch (one line, plus the same for `now + ttl` to be safe):

```python
cutoff = datetime.combine(now.astimezone(IST).date(), time(14, 45), tzinfo=IST).astimezone(UTC)
```

### D-1: a gappy strike ladder that brackets spot labels a distant strike ATM

Severity: low to medium; needs a master with strikes missing near spot.

`contract_resolver.current_moneyness` treats the nearest listed strike as ATM
whenever the ladder brackets spot (`min(strikes) <= spot <= max(strikes)`),
with no limit on how far that strike is from spot. With CE strikes 22000 and
22500 listed and spot 22300, CE 22500 (200 points out of the money) is
classified `ATM` and is admitted. The unbracketed cases (spot beyond either end
of the ladder, or a single strike) are handled correctly and are tested.

Why it matters: the rule is ATM or ITM only. The master check covers
unparseable rows, not strikes that are simply missing, so a partially delivered
master can widen eligibility. Liquidity, spread, volume and the 8 percent stop
still apply.

Reproduction: `test_a_gappy_ladder_that_brackets_spot_does_not_make_a_distant_otm_strike_atm`.

Suggested patch: honour the nearest-strike rule only when the strikes adjacent
to spot are within one normal step, for example

```python
lower = max((s for s in strikes if s <= spot), default=None)
upper = min((s for s in strikes if s >= spot), default=None)
if lower is None or upper is None or upper - lower > MAX_LADDER_STEP:  # 100 for NIFTY
    atm = None  # fall back to the strict spot comparison
```

The step constant is a product decision (NIFTY lists 50-point steps near the
money and wider further out), so it is left to the owner.

### D-2: no entry buffer before an early close

Severity: low. Only matters on a day with a shortened effective window.

`risk_manager.entry_reasons` accepts an entry while the session is open
(`window[0] <= now < window[1]`) and before 14:45. The mandatory exit is five
minutes before the effective close. With an effective close of 13:00, an entry
at 12:57 is admitted and is force-exited from 12:55, paying both sides of the
charges for a position that could never be held. On a normal day this cannot
happen because 14:45 precedes 15:10. Special sessions are disabled, so this
needs a partial-day window from the market calendar.

Reproduction: `test_an_entry_is_not_opened_inside_the_final_exit_buffer_of_an_early_close`.

Suggested patch: pass a `window_close` into `entry_reasons` and refuse when
`now >= window_close - 5 minutes`, or reuse `mandatory_exit_reason` as the gate.

### Observations (not defects)

- A fill attempted under another user's order id raises `AttributeError`
  (`'NoneType' object has no attribute 'status'`) instead of a named refusal.
  No ledger state changes for either user (asserted). Cosmetic robustness only.
- A daily-loss lock sets the state to PAUSED. The next day's rollover clears the
  lock flag but not the PAUSED state, so entries need an explicit operator start
  (the multi-day test resumes the account to model that). The loss cooldown
  blocks the next eligible session anyway.
- A reconcile after a hand-inserted trade with no matching exit fill reports
  `JOURNAL_EXIT_FILL_MISSING`; the restart test therefore latches the month lock
  without fabricating a trade. This is the reconciliation doing its job.
- A genuine OI of zero and a missing OI score the same (already recorded in
  `COMPLIANCE_REMEDIATION.md`).

## Gaps requiring an authorized broker feed

None of these can be verified offline and none is claimed:

1. Real Angel One mode-3 depth, OI and index feed: field names, units, time
   stamps, latency, sequence behavior and reconnects.
2. Completeness and entitlement of the full listed-strike OI/volume chain used
   for PCR, and how often the five-second skew and 90-second age limits trip.
3. Real minute-history completeness, gaps, and the first candle of the session.
4. Real instrument-master delivery, including partially delivered strike
   ladders (the D-1 exposure) and daily freshness.
5. Real calendar data: partial-day windows and special sessions (D-2).
6. Real spreads, displayed sizes, partial depth consumption and slippage
   against the fixed one-tick assumption.
7. Discord three-second acknowledgements and SMTP delivery; no message was
   sent here.
8. Process-level crash and power-loss recovery (only caught-exception rollback
   and a new store object on the same file were exercised), and the
   deployment's file and database placement.
9. Forward PAPER recovery over multiple real sessions, and any statement about
   expectancy, drawdown or profitability.

## Docker CI (separate deliverable, same branch)

### What failed

Post-merge push CI for `main` at `a89854a5` (run 45365480696, checked while
writing this record) failed in both `docker-build` matrix legs
(`linux/amd64`, `linux/arm64`) at the step `Login to Docker Hub` with the
error `Username and password required`; `docker-manifest` was skipped and every
other job, including `commit-dist`, passed. The earlier push run 45354642815 for
`41e0c8ab` failed identically. The fork has no `DOCKERHUB_USERNAME` or
`DOCKERHUB_TOKEN` secret and no Actions variables (`gh secret list` and
`gh variable list` return nothing). Pull request runs passed because the login
step was skipped for them.

### New policy

Validation and publishing are now separate.

| Event | Login | Push | Manifest | Build and smoke test |
| --- | --- | --- | --- | --- |
| Pull request | no | no | no | yes, both architectures |
| Push to `main`, `DOCKER_PUBLISH` unset (a fork, the default) | no | no | skipped | yes, both architectures |
| Push to `main`, `DOCKER_PUBLISH` = `true`, secrets present | yes | yes, by digest | yes | yes, both architectures, before any push |
| Push to `main`, `DOCKER_PUBLISH` = `true`, a secret missing | fails with a message naming the missing secret | no | skipped | yes |

To publish from a repository, set the repository variable `DOCKER_PUBLISH` to
`true` and keep `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` as secrets. No fake
credential is needed and no secret is exposed. A pull request never publishes.

Changes in `.github/workflows/ci.yml`:

- `docker-build` gets a job-level `PUBLISH` value, true only for a push to `main`
  with `vars.DOCKER_PUBLISH == 'true'`, and an `IMAGE_NAME` that is
  `<username>/openalgo` only when publishing and plain `openalgo` otherwise, so
  the metadata step no longer depends on an unset secret.
- The validation build (`load: true`, no push) and the Kaleido and Chromium
  smoke test now run on every path, not only on pull requests. A fork `main`
  push therefore keeps meaningful amd64 and arm64 coverage.
- Login, the digest build, digest export and upload run only when `PUBLISH` is
  true, and a new first step fails with a named message if a secret is missing.
- `docker-manifest` additionally requires `vars.DOCKER_PUBLISH == 'true'`, has
  the same credential check, and is skipped otherwise. Nothing depends on it.
- The job is not skipped as a whole, the `needs` list, the matrix, the
  `commit-dist` job and the workflow permissions are unchanged.
- `test/test_ci_docker_publish_policy.py` (12 tests, added to the CI-safe list
  in `backend-test`) checks this structure as data, so a future edit that puts a
  login back on the unconditional path fails CI.

Behavior change for any repository that already publishes (including upstream
if this file is merged there): it must set `DOCKER_PUBLISH=true` once, or its
Docker Hub publish stops. That is the intended opt-in. When publishing, each
leg now builds twice (a loaded validation build, then the push by digest); the
second is served from the same layer cache.

### How it was validated

- The workflow parses as YAML, and the policy tests pass locally; a mutation
  that removes the publish condition from the login step fails two of them.
- Expression syntax and context availability (`vars` and `secrets` in job-level
  `env`, `vars` and `github` only in a job-level `if`, `env` in step conditions)
  were reviewed by hand. `actionlint` was not run: an attempt to download it was
  refused by this session's permission policy, and no workaround was attempted.
- **No GitHub run of the new workflow exists at the time of writing.** The
  pull request's own CI is the first real check, including whether the `load`
  build and smoke test pass on the arm64 runner for a push event (they already
  passed for pull requests).
