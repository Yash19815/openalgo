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
| Collected | 247 (85 test functions, parametrized) |
| Passed | 247 |
| Expected failures (strict `xfail`) | 0 |
| Failed | 0 |
| Run | Windows, Python 3.12.11, `pytest -o addopts=""` with `--basetemp` |

History of this file: the first run (baseline `a89854a5`) collected 132 tests,
129 passed and 3 were strict `xfail` (D-1, D-2, D-3). After the D-2 and D-3 fixes
on `fix/nifty-paper-safety` it was 146 passed and 1 `xfail` (D-1). After the D-1
fix on `fix/nifty-atm-strike-validation` the figures above apply and no `xfail`
remains.

All `test/test_nifty_algo_*.py` files together, plus
`test/test_ci_docker_publish_policy.py`: 1214 passed, 0 failed, 0 xfailed
(5 min 38 s). With `contract_resolver.py` temporarily reverted to `main`, the
new D-1 behavioral tests fail, including the original D-1 test, so they detect
the defect.

The strict `xfail` mechanism did its job: when the D-1 fix landed, the former
`xfail` test started to pass, and its marker was removed in the same change.

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
| That entry's stored expiry is the same instant read back, on the cutoff and TTL paths, across a restart, and expires at exactly 14:45:00 IST with no fresh depth | `test_the_cutoff_expiry_is_the_same_instant_after_it_is_stored`, `test_every_persisted_expiry_is_the_intended_utc_instant` (4), `test_a_cutoff_expiry_survives_a_restart_and_expires_exactly_at_1445_ist`, `test_an_entry_admitted_in_the_last_second_is_expired_by_the_sweep_at_1445` | PASS (D-3 fixed) |
| Maximum hold: no forced exit at 44:59, forced exit at 45:00 | `test_a_position_is_force_exited_after_exactly_45_minutes` | PASS |
| Mandatory exit at 15:10, or five minutes before an earlier effective close; precedence; a missing window fails closed | `test_the_1510_session_exit_wins_when_the_hold_limit_is_later`, `test_an_earlier_effective_close_pulls_the_exit_to_five_minutes_before_it`, `test_mandatory_exit_precedence_and_missing_session_window_fail_closed` | PASS |
| Weekends, approved holidays, an unapproved calendar and special sessions never permit entries | `test_entries_are_refused_on_weekends_and_approved_holidays` (2), `test_an_unapproved_calendar_blocks_entries_and_special_sessions_never_enable_them` | PASS |
| An exit never invents a fill when the real session is closed | `test_exits_are_still_governed_by_the_real_session_when_the_calendar_says_closed` | PASS |
| No new entry at or after the effective close minus five minutes; a pending entry cannot outlive that boundary; exits stay permitted; a normal day is unchanged | `test_an_entry_is_not_opened_inside_the_final_exit_buffer_of_an_early_close`, `test_early_close_entry_buffer_boundary_is_exactly_five_minutes_before_the_close` (6), `test_an_entry_admitted_just_before_the_early_close_buffer_never_fills_inside_it`, `test_an_early_close_buffer_does_not_block_the_exit_of_a_held_position`, `test_a_normal_full_day_entry_window_is_unchanged_by_the_exit_buffer` | PASS (D-2 fixed) |
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
| A gappy ladder that does bracket spot does not make a distant strike ATM | `test_a_gappy_ladder_that_brackets_spot_does_not_make_a_distant_otm_strike_atm` | PASS (D-1 fixed) |
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
route to a real order. The acceptance branch changed no production file. Each
defect had a strict `xfail` test and a suggested patch. D-3 and D-2 were then
fixed on `fix/nifty-paper-safety` (see "Fix record" under each) and their
markers removed. D-1 was then fixed on `fix/nifty-atm-strike-validation` (see
its section).

### D-3: an entry admitted in the last 10 seconds before 14:45 IST expires at the wrong instant

Status: FIXED on `fix/nifty-paper-safety`.

Fix record: `paper_executor.admit` now converts every persisted order instant to
UTC (`_utc`): `expires_at` on both the TTL path and the 14:45 IST cutoff path,
and also `eligible_at` and `created_at`, which share the same zone-dropping
column. The 14:45 cutoff is compared and stored as a UTC instant, so a naive
SQLite read-back (always taken as UTC) is the intended instant. The fill's own
hard cutoff in the store is unchanged and still runs as a second layer.
Behavioral consequence: an order admitted in the last ten seconds is now swept
as `EXPIRED` / `ORDER_TTL` at 14:45:00 IST by `expire_pending`, where before it
sat PENDING until 20:15 IST unless a fill was attempted with fresh depth.
An order already stored by an earlier build is not rewritten (no migration: it
is at most one pending order per account, from the last ten seconds of a single
session). It keeps its wrong stored instant, so it stays PENDING until a fill
is attempted, when the fill cutoff expires it, or until that stored instant
passes. It never fills after 14:45 IST either way.

Original finding (kept for the record): severity low. Never fills after 14:45;
the harm is a lingering PENDING order.

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

Status: FIXED on `fix/nifty-atm-strike-validation`.

Original failure: with CE strikes 22000 and 22500 listed and spot 22300, CE 22500
(200 points out of the money) was classified `ATM` and admitted, because
`current_moneyness` treated the nearest listed strike as ATM whenever the ladder
bracketed spot, with no limit on how far that strike was from spot. The
unbracketed cases (spot beyond either end of the ladder, or a single strike) were
already handled. A partially delivered master, which the master check does not
detect because it covers unparseable rows and not missing strikes, could widen
eligibility. Liquidity, spread, volume and the 8 percent stop still applied.

Root cause: two consumers computed the ATM strike separately, and neither bounded
its distance from spot. `current_moneyness` (admission, the locked write, fill
and replay) bracketed spot and took the nearest strike. `Resolver.assess` (the
selector) took the nearest strike with no bracketing check at all, so it offered
the nearest edge strike of a ladder that did not even reach spot, and it did
arithmetic on the ATM strike that would have failed for `None`.

#### Rule

One function, `contract_resolver.atm_reference(strikes, spot)`, now decides, and
`current_moneyness` and `Resolver.assess` both call it. A strike is the ATM
reference only when all of these hold:

1. listed strikes lie on both sides of spot (`min <= spot <= max`);
2. it is the nearest listed strike, the lower strike at an exact midpoint (the
   rule from N-03, unchanged);
3. it is within half a strike interval of spot, that is 25 points.

Otherwise there is no ATM reference. `current_moneyness` then returns the strict
spot comparison with `atm_strike = None` (an out-of-the-money option is refused,
an in-the-money one is still allowed), and `Resolver.assess` refuses an `ATM` or
`ITM` selection with the explicit code `ATM_REFERENCE_UNVERIFIED` instead of
offering a candidate admission would reject. `DELTA` selection needs no ATM and
keeps working on the strict comparison. The report's `atm_strike` is `null` in
that case (the frontend type already allowed it).

Also changed: two records for the same token with different content now refuse
with `INSTRUMENT_IDENTITY_MISMATCH` in either order, where before the last record
won and the result depended on master order. Identical duplicates and reordered
masters give identical results.

#### Source evidence and what is not verified

| Check | Source | Status |
| --- | --- | --- |
| NIFTY 50 weekly and monthly options: strike interval 50 at all index levels, 35 strikes in the money, at the money and out of the money each side (35-1-35), set from the previous day's close | NSE, "NIFTY 50 F&O", Strike Price Intervals, https://www.nseindia.com/static/products-services/equity-derivatives-nifty50, read 24 November 2026 | Verified on NSE's own page. The page shows no effective date for this row, and I could not retrieve the circular that set it. |
| Quarterly and half-yearly (long term) options use wider, level-dependent intervals (100, 500, 1000, 1500) with 5-1-5 or fewer strikes | same page; NSE circular NSE/FAOP/71819 (214/2025), 16 December 2025, interval 1000 to 1500 effective 31 December 2025 | Verified. Not used: the selector takes the nearest expiry, which is weekly or monthly. A longer-dated contract gets no ATM reference and falls back to the strict comparison, which refuses an out-of-the-money strike. |
| NIFTY weekly and monthly expiry day is Tuesday | NSE page; NSE/FAOP/68747 (111/2025), 25 June 2025 | Verified. The selector's expiry is the nearest eligible one, so the 50-point row applies to it. |
| A 100-point gap is valid for the selected expiry | no source | Rejected. The 100-point figure proposed earlier is not an NSE interval for weekly or monthly contracts, so it was not used. The bound is half of the verified 50-point interval. |
| How the master marks weekly, monthly and long-term contracts, and whether any selected expiry could be long-term | no source | Unverified. The code does not classify expiries; it relies on the selector choosing the nearest one. |
| Whether a real broker master lists every strike NSE lists near spot | none, no broker feed | Unverified. Offline tests are synthetic. |

NSE's page describes strikes as added from the previous day's close. During the
day the listed ladder can lag a fast move, so near the edge of the 35-strike
range there may be no ATM reference. That case is refused, never guessed.

#### Behavior, by case

| Case | Result |
| --- | --- |
| Complete 50-point ladder, any spot inside it | nearest strike ATM, lower strike at the midpoint, as before |
| One strike missing, spot within 25 points of a listed strike | unchanged, that strike is ATM |
| One strike missing, nearest listed strike 50 points away | no ATM reference; only ITM strikes are allowed; the selector refuses |
| Several strikes missing around spot, or two strikes listed far apart | no ATM reference; the 22500 call at spot 22300 is OTM and is refused |
| Single strike listed | ATM only when spot equals it exactly, otherwise strict comparison |
| Spot outside the listed range | no ATM reference |
| 100-point ladder (not NSE weekly or monthly) | ATM only within 25 points of a listed strike |

#### Files modified

- `services/nifty_algo/contract_resolver.py`: `atm_reference`, the 50-point
  constant and its sources, the conflicting-record check, `Resolver.assess`.
- `test/test_nifty_algo_offline_acceptance.py`: the D-1 `xfail` removed, new
  tests below.
- `test/test_nifty_algo_core.py`: one fixture moved onto the NSE grid.
  `test_contract_resolver_uses_listed_strikes_and_requires_fresh_depth` listed
  strikes 22000 and 22080 with spot 22040, an 80-point gap NSE does not list and
  nothing within 25 points of spot. It was really testing the lower-strike
  midpoint rule, so it now uses 22000 and 22050 with spot 22025. No assertion was
  weakened.
- `docs/nifty-algo/STRATEGY_ASSUMPTIONS.md` and this record.

Not changed: the paper executor, the store and `execution_replay`, which already
call `current_moneyness`, so admission, the locked write, fill and replay pick up
the rule with no edit. The master is still read before the ledger lock, and no
read was added under it.

#### New tests

All in `test/test_nifty_algo_offline_acceptance.py`:

- `test_a_gappy_ladder_that_brackets_spot_does_not_make_a_distant_otm_strike_atm`
  (the former strict `xfail`, now passing) and the complete-ladder tests for CE
  and PE: exact strike, exact midpoint, just either side of it.
- `test_atm_reference_is_only_issued_within_half_an_interval_of_spot` (30):
  missing one or several strikes, extremely sparse ladders, a single strike, spot
  outside the range, 100-point ladders.
- `test_a_missing_ladder_never_turns_an_out_of_the_money_strike_into_itm_or_atm`:
  a sweep showing a strict OTM strike is never softened beyond 25 points.
- Other expiries, sides and underlyings never repair a gap; reordered and
  duplicated identical records give identical results; conflicting records fail
  closed in both orders; missing or invalid metadata and a stale master fail
  closed.
- `test_selector_admission_fill_and_replay_label_every_offered_contract_alike`
  (42): seven ladders, CE and PE, `ATM`, `ITM` and `DELTA` selection, many spots.
  Every offered candidate carries the label admission computes, and a refusal is
  explicit.
- The selector refuses with `ATM_REFERENCE_UNVERIFIED`; ranking excludes the OTM
  contract; admission refuses the 22500 strike on a gappy master and still admits
  22000; a pending entry is rejected at fill (`OTM_PROHIBITED`, no cash moved)
  when the master turns sparse; a complete master still fills; replay uses the
  same two functions.

With `contract_resolver.py` reverted to `main`, the new behavioral tests fail,
including the original D-1 test.

#### Limits

Synthetic ladders prove the classification logic. They do not prove that a real
broker's instrument master lists every strike NSE lists, how often a master is
partial, or how often the 25-point rule will refuse a real entry. They do not
establish profitability, and no real order, broker call or notification was made.

### D-2: no entry buffer before an early close

Status: FIXED on `fix/nifty-paper-safety`.

Fix record: `risk_manager.entry_reasons` takes an optional `session_close`, the
effective close from the authoritative market-calendar window (`nifty_session`),
and refuses with the existing `ENTRY_WINDOW` reason when
`now >= session_close - 5 minutes` (`SESSION_EXIT_BUFFER`, the same five minutes
as `protection.mandatory_exit_reason`). `paper_executor.admit` and
`execution_replay` pass the window close. A BUY's expiry is also capped at that
boundary so a pending entry can never fill inside the buffer. Exit admission,
the 14:45 entry window, the loss and monthly locks, disabled special sessions
(`SPECIAL_SESSION_DISABLED`, no window) and the missing-window fail-closed path
are unchanged; when `session_close` is omitted only the configured entry window
applies, so a direct caller keeps its earlier behavior. On a normal 15:30 or
15:40 close the buffer (15:25 or 15:35) is after the 14:45 cutoff and changes
nothing.

Original finding (kept for the record): severity low. Only matters on a day
with a shortened effective window.

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
   ladders and daily freshness. D-1 now refuses a gap near spot, but how often
   a real master has one, and how often the 25-point rule will refuse a real
   entry, is unobserved.
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
