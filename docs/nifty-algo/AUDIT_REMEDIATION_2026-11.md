# NIFTY audit remediation — November 2026

## Scope and provenance

Execution batch A, incomplete overall remediation. Do not merge as certification of all audit findings.

- Starting origin/main: `dcfb8df6e0f5ef3e3d9365b6e449d91c81c1f09d`.
- Audit report commit: `1cc30502d3d66a8611fd2127f29e5169e0b3f021`, fetched using Git without merging its branch.
- Branch: `fix/nifty-audit-execution-correctness`; [draft PR #10](https://github.com/Yash19815/openalgo/pull/10).
- Implementation commit: `d7a9f2a936712e69238db18104d3c55fbaa5969e`.
- CI at publication: backend lint, frontend lint, one frontend build and several platform smoke checks passed; remaining jobs pending. No final green-CI claim.
- Historical audit PR #9 was not modified. Findings below distinguish code evidence from unverified policy and feed assumptions.
- This batch does not claim full end-to-end audit reproduction, full manifest reading, or completion of PR B/C.

## Finding register

| Finding | Confirmed? | Resolution status | Code change / disposition | Tests | PR | Remaining risk |
|---|---|---|---|---|---|---|
| F-01 | Yes | `DEFERRED_WITH_REASON` | Indicator alignment belongs to PR B; current defaults remain 10/3. | Static review or pending | — | See disposition |
| F-02 | Yes | `DEFERRED_WITH_REASON` | Factor alignment belongs to PR B. | Static review or pending | — | See disposition |
| F-03 | Stale | `ALREADY_FIXED` | Main includes 3.2.0 MACD ages 0–2; existing MACD suite passes. | MACD window suite | — | See disposition |
| F-04 | Policy | `REQUIRES_OWNER_DECISION` | Keep documented /10 and /3 normalization or approve parameter-dependent normalization. | Static review or pending | — | See disposition |
| F-05 | Unverified | `DEFERRED_WITH_REASON` | No dated statutory fee and rounding verification completed; estimates unchanged. | Static review or pending | — | See disposition |
| F-06 | Unverified | `REQUIRES_REAL_FEED_EVIDENCE` | Need complete dated expiry master plus raw full-chain packets with trade, quote and receive times. | Static review or pending | — | See disposition |
| F-07 | Unverified | `REQUIRES_REAL_FEED_EVIDENCE` | Need native depth update timestamp contract and raw packets during inactive trading. | Static review or pending | — | See disposition |
| F-08 | Yes | `DEFERRED_WITH_REASON` | 20/2 tests belong with versioned indicator alignment. | Static review or pending | — | See disposition |
| F-09 | Yes | `DEFERRED_WITH_REASON` | Current indicator documentation remains pending PR B; historical provenance preserved. | Static review or pending | — | See disposition |
| F-10 | Static evidence | `NOT_YET_INVESTIGATED` | Boundary marked before assessment; deterministic retry reproduction still required. | Static review or pending | — | See disposition |
| F-11 | Static evidence | `NOT_YET_INVESTIGATED` | Opening-bucket mismatch and prior-session tails need complete parity regressions. | Static review or pending | — | See disposition |
| F-12 | No fabrication | `VERIFIED_NOT_A_BUG` | Raw OI remains None; zero is conservative scoring support, with explicit coverage flags. | Static review or pending | — | See disposition |
| F-13 | No | `VERIFIED_NOT_A_BUG` | indicators.adx applies period 14 to TR/DM and DX smoothing. | Static review or pending | — | See disposition |
| F-14 | Unverified | `NOT_YET_INVESTIGATED` | Historical root tools left intact; no removal authorized or needed by this patch. | Static review or pending | — | See disposition |
| F-15 | Research limitation | `REQUIRES_REAL_FEED_EVIDENCE` | Risk ceilings retained; feasibility needs observed premium, lot and fee evidence. | Static review or pending | — | See disposition |
| F-16 | Intentional distinction | `REQUIRES_OWNER_DECISION` | Gating uses ask denominator; ranking uses midpoint. Unifying changes ranking policy. | Static review or pending | — | See disposition |
| F-17 | No regular-session mismatch | `VERIFIED_NOT_A_BUG` | VWAP resets by IST date; observed bars are filtered to session, futures identity checked upstream. | Static review or pending | — | See disposition |
| F-18 | Historical semantics | `REQUIRES_OWNER_DECISION` | Initial SuperTrend direction unchanged; alternative seeding requires versioned parity analysis. | Static review or pending | — | See disposition |
| F-19 | Static evidence | `NOT_YET_INVESTIGATED` | Calendar authority reconciliation needs separate reproduction; exit semantics unchanged. | Static review or pending | — | See disposition |
| F-20 | Intentional | `VERIFIED_NOT_A_BUG` | Shadow has a separate ledger and documented entry/monthly-lock rules. | Static review or pending | — | See disposition |
| F-21 | Tooling limitation | `DEFERRED_WITH_REASON` | Recursive dependency junction is unrelated upstream tooling; no dependency deletion. | Static review or pending | — | See disposition |
| F-22 | Yes | `FIXED_AND_TESTED` | Replay pending expiry includes early-close buffer through session_policy. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |
| F-23 | Growth observation | `REQUIRES_OWNER_DECISION` | Retention would delete historical evidence; no deletion performed. | Static review or pending | — | See disposition |
| F-24 | Yes | `DEFERRED_WITH_REASON` | Full-month event payload materialization remains; memory optimization not implemented. | Static review or pending | — | See disposition |
| F-25 | Yes | `FIXED_AND_TESTED` | ATM requires actual adjacent 50-point grid rows; exact midpoint picks lower; shared consumers inherit. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |
| F-26 | Yes | `REQUIRES_OWNER_DECISION` | Eligibility stays ages 0–2; score normalization remains unchanged pending explicit policy. | Static review or pending | — | See disposition |
| F-27 | Yes | `FIXED_AND_TESTED` | ITM requires strike exactly one interval inside ATM, otherwise specific refusal. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |
| F-28 | Yes | `FIXED_AND_TESTED` | Admission expiry and locked fill honor earlier configured cutoff; restart regression. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |
| F-29 | Yes | `FIXED_AND_TESTED` | Selector refusal converted to OrderRefused after safe structured event, preserving specific code. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |
| F-30 | Yes | `FIXED_AND_TESTED` | One SESSION_EXIT_BUFFER definition shared by risk, expiry and protection. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |
| F-31 | Yes | `FIXED_AND_TESTED` | Field validator reports crossover_freshness instead of empty model location. | Audit regression / focused existing suites | A | Offline proof; full acceptance matrix remains pending |

## Batch B disposition (strategy 3.3.0) - 2026-11-25

Supersedes the table above for every finding it re-dispositions. The table above
is kept as the record of what batch A claimed. Details, behaviour changes and the
failures found in this pass: [REMAINING_REMEDIATION_2026-11.md](REMAINING_REMEDIATION_2026-11.md).
Batch B sits on top of batch A locally; PR #10 was still an open draft, so
nothing was pushed to its branch.

Status words: FIXED_AND_TESTED needs an offline regression that failed before or
guards the rule. It never means real-feed or contract-note evidence exists.

| Finding | Orig. | Class | Status | Disposition | Tests | Open risk or evidence |
|---|---|---|---|---|---|---|
| F-01 | HIGH | Confirmed | `FIXED_AND_TESTED` | ATR length 20 for new 3.3.0 configurations on both timeframes; legacy keep 10. | `test_nifty_algo_supertrend_alignment.py`, `test_nifty_algo_phase1.py` | Existing explicit 10/3 needs trader review. |
| F-02 | HIGH | Confirmed | `FIXED_AND_TESTED` | Factor 2.0, same scope as F-01. | same | same |
| F-03 | HIGH | Stale | `ALREADY_FIXED` | MACD ages 0-2 only; age 3 refused. Revalidated. | `test_nifty_algo_macd_window.py` | none |
| F-04 | MED | Policy | `FIXED_AND_TESTED` | `five-indicator-v2-pinned` for 3.3.0 (ST /10, /3). v1 kept for legacy. | `test_nifty_algo_confidence_comparison.py`, `test_nifty_algo_pipeline.py` | Active on the approval recorded in the confidence decision document; owner to reconfirm. |
| F-05 | MED | Confirmed | `DEFERRED_WITH_REASON` | Published rates and GST base applied to 3.3.0 estimates; legacy formula kept. Not a contract-note claim. | `test_nifty_algo_fee_candidates.py` | Rounding and IPFT invoicing evidence missing; Angel page contradicts itself on STT (0.15 vs 0.1 percent). |
| F-06 | MED | Unverified | `REQUIRES_REAL_FEED_EVIDENCE` | Diagnostics, subscription-quota report and completeness tests added. Thresholds not weakened. | `test_nifty_algo_feed_provenance.py` | Needs raw full-chain packets and a dated master. |
| F-07 | MED | Confirmed in code | `REQUIRES_REAL_FEED_EVIDENCE` | Depth freshness uses `quote_time` only; trade time cannot certify a book. | `test_nifty_algo_timestamp_provenance.py`, `test_nifty_algo_native_capture.py` | Whether Angel's `exchange_timestamp` is a book-update time is unproven. |
| F-08 | LOW | Confirmed | `FIXED_AND_TESTED` | 20/2 parity against independent recursion and the installed Rust SDK and its fallback; 10/3 parity kept. | `test_nifty_algo_supertrend_alignment.py`, `test_nifty_algo_sdk_241_parity.py` | none |
| F-09 | LOW | Confirmed | `FIXED_AND_TESTED` | Current docs state 20/2; historical docs keep their version. | doc review | none |
| F-10 | LOW | Reproduced | `FIXED_AND_TESTED` | Durable bounded retry inside the existing 30 s window. | `test_nifty_algo_boundary_retry.py` | Real publication latency not measured. |
| F-11 | LOW | Reproduced | `FIXED_AND_TESTED` | One completeness policy for live and replay. | `test_nifty_algo_session_completeness.py`, `test_nifty_algo_strategy_integration.py` | none |
| F-12 | LOW | No fabrication | `VERIFIED_NOT_A_BUG` | OI stays None; zero volume term is conservative. | acceptance OI tests | none |
| F-13 | LOW | Not a bug | `VERIFIED_NOT_A_BUG` | ADX 14/14. | indicator suite | none |
| F-14 | LOW | Confirmed | `FIXED_AND_TESTED` | Patchers retired, kept for provenance. | `test_nifty_algo_retired_tools.py` | none |
| F-15 | INFO | Arithmetic only | `REQUIRES_REAL_FEED_EVIDENCE` | Synthetic feasibility tables from the real planner. Risk limits unchanged. | `test_nifty_algo_confidence_comparison.py` | No observed premiums or lots. |
| F-16 | INFO | Intentional | `REQUIRES_OWNER_DECISION` | Both definitions documented and pinned. No unification. | `test_nifty_algo_spread_definitions.py` | Owner decides if ranking should change. |
| F-17 | INFO | Not a bug | `VERIFIED_NOT_A_BUG` | Session VWAP on the checked future. | active invariants | none |
| F-18 | INFO | Historical | `REQUIRES_OWNER_DECISION` | Initialization unchanged; evidence in `evidence/initialization.md`. | evidence script | New seeding needs a version and approval. |
| F-19 | INFO | Reproduced | `FIXED_AND_TESTED` | Disagreement locks entries; protective SELL needs only fresh bid depth and an unexcluded session. Report scanner records the day. | `test_nifty_algo_calendar_reconciliation.py`, `test_nifty_algo_phase6.py` | Authority between calendars is documented, not unified. |
| F-20 | INFO | Intentional | `VERIFIED_NOT_A_BUG` | Shadow ledger separate. | existing | none |
| F-21 | INFO | Tooling | `DEFERRED_WITH_REASON` | Mitigated with `.ignore` and a git-index inventory. Upstream package layout untouched. | inventory script | Recursive junction remains upstream. |
| F-22 | LOW | Confirmed | `FIXED_AND_TESTED` | Batch A. Revalidated. | audit regression | none |
| F-23 | INFO | Growth | `REQUIRES_OWNER_DECISION` | Additive report index only. Nothing deleted. | n/a | Retention policy needs approval. |
| F-24 | INFO | Confirmed | `FIXED_AND_TESTED` | Report query selects only consumed kinds. | `test_nifty_algo_report_filtering.py` | none |
| F-25 | LOW | Confirmed | `FIXED_AND_TESTED` | Batch A. Revalidated. | audit regression | none |
| F-26 | MED | Confirmed | `FIXED_AND_TESTED` | MACD recency denominator 3 pinned for 3.3.0. | `test_nifty_algo_confidence_comparison.py` | Same approval note as F-04. |
| F-27 | LOW | Confirmed | `FIXED_AND_TESTED` | Batch A. Revalidated. | audit regression | none |
| F-28 | LOW | Confirmed | `FIXED_AND_TESTED` | Batch A. Revalidated. | audit regression | none |
| F-29 | LOW | Confirmed | `FIXED_AND_TESTED` | Batch A. Revalidated. | audit regression | none |
| F-30 | INFO | Confirmed | `FIXED_AND_TESTED` | Batch A. Revalidated. | audit regression | none |
| F-31 | LOW | Confirmed | `FIXED_AND_TESTED` | Batch A. Revalidated. | audit regression | none |

Totals: 23 resolved or closed (18 `FIXED_AND_TESTED`, 1 `ALREADY_FIXED`, 4
`VERIFIED_NOT_A_BUG`); 8 open (F-05, F-21 deferred; F-06, F-07, F-15 need real
feed evidence; F-16, F-18, F-23 need an owner decision).

## Regression evidence

Before production edits, sparse midpoint CE/PE and reordered records, missing adjacent ITM, off-grid ladder and MACD validation location produced **9 failures / 4 passes**. After those fixes: **13 passed**. Configured 14:00 cutoff persisted PENDING across restart at exactly 14:00 before the expiry fix (**1 failed / 13 passed**); afterward **14 passed**. Early-close replay regression failed before the replay expiry change. An additional off-grid master-row test failed before restricting the ATM choice to grid neighbors. The 20-test expanded batch then passed. Selector refusal test failed with SelectionUnavailable before conversion into the established OrderRefused path.

Focused existing suites plus the initial 15 audit regressions: **116 passed**, no skips or xfail (169.02 seconds). Suites: audit_remediation, macd_window, paper_executor, execution_completion, compliance, selector. Later selector integration run is recorded below after completion.

Final audit regression and selector integration run: **49 passed** (131.29 seconds), including all **21** new regression cases. Counts overlap the earlier run and must not be added as unique tests. Ruff check and git diff --check passed.

Commands use Windows .venv/Scripts/python.exe, NUMBA_DISABLE_JIT=1 and PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, with pytest -q -o addopts='' and unique --basetemp under tmp/. Disabling JIT avoids startup compilation stalls; this is Python-path verification, not compiled-kernel parity. test/conftest.py disables dotenv and assigns isolated test database URLs. No production migrations or broker requests were made.

## Behavior and compatibility

The user approved grid correctness and cutoff enforcement. Missing grid neighbors now refuse ATM reference; strict spot-based ITM classification remains available to shared checks. ITM preference refuses a missing adjacent strike. Exact grid strikes remain valid. No missing instrument is invented; token, expiry and dated-master checks remain unchanged.

The shared cutoff is min(14:45 IST, configured entry_before, session close minus five minutes). Pending expiry additionally takes min(admission plus TTL). Equality expires. Admission persists UTC. The locked fill reads its order's pinned configuration. The mandatory protection buffer remains five minutes.

Source for short-term grid: [NSE NIFTY 50 F&O](https://www.nseindia.in/static/products-services/equity-derivatives-nifty50), Strike Price Intervals, accessed 2026-11-24; page updated 2025-09-23. Weekly/monthly interval is 50. This does not certify broker master completeness or longer-dated expiry classification.

No strategy/configuration version change in A: current 3.2.0, legacy 3.1.0. SuperTrend is still 10/3 on this branch, so approved 20/2 alignment is **not complete**. MACD stays 12/26/9 close with ages 0–2, ADX 14/14, VWAP session hlc3. No score formula, lot tier, target fraction, risk ceiling, balance or old record is rewritten. Execution corrections can change replay outcomes for affected historical scenarios; no claim of unchanged execution-engine replay semantics is made.

F-26 arithmetic: recency contribution is 10*(1-age/(freshness+1)). At ages 0/1/2, moving freshness 3 to 2 changes points by 0, -0.833333..., -1.666666.... A total of 40.5 at age 2 becomes 38.833333..., crossing the 2-lot permission boundary to 1; 70.5 becomes 68.833333..., crossing 3 to 2. Actual size still depends on every risk/depth/cash gate. Target fraction changes by 0.05*score_delta/100. Restoring denominator 4 or using parameter-independent normalization needs owner approval; neither is implemented.

F-15 exact existing arithmetic remains: planned loss = (entry - stop_exit)*quantity + entry charges + stop-exit charges + buffer; projected reward = (target - entry)*quantity - entry charges - target-exit charges. Maximum 400 loss and minimum 350 reward remain unchanged. No observed feasibility band is claimed.

## Safety and outstanding acceptance

Strict PAPER-only execution remains intact; LiveAdapterStub still refuses LIVE_NOT_READY. No real orders or notifications, no credentials, no Docker publishing changes, no merges or force pushes. Further work remains on F-10/F-11, full runner/API boundary proof, grid checks at every lifecycle stage, indicator migration/UI, dated fee verification and broader NIFTY checks. Pending items are not relabeled as fixed.

## PR #10 CI correction — 2026-11-25

Inspected Actions run `45406772322`, backend jobs `138489826474` (3.12),
`138489826213` (3.13), and `138489826338` (3.14). Each reported the same six
failures in `test_nifty_algo_offline_acceptance.py`, with 1320 other tests passing.
Four assertions retained the superseded distance-only ATM assumption; two
required the ITM sweep to offer candidates on a ladder missing every adjacent
50-point strike.

Disposition: these test assumptions are obsolete under the approved fail-closed
short-term grid policy. The production implementation is unchanged. A listed
strike within 25 points is necessary but insufficient between grid strikes:
both adjacent 50-point grid records must be present. This deliberately refuses
an incomplete neighborhood even when its surviving nearest strike appears
plausible. Exact listed grid strikes need no interpolation. The 100-point fixture
is sparse short-term metadata, not approval to infer a 100-point trading grid.
At an exact listed ATM, ITM mode still needs the actual adjacent 50-point strike;
a deeper listed strike cannot substitute.

Coverage now includes missing lower and upper neighbors, both option sides,
points just below/at/above the midpoint, exact listed sparse-grid ATM, explicit
ITM refusals, restoring only the adjacent ITM contract, and reordered records.
The selector sweep asserts complete refusal for sparse-100 ITM instead of
silently dropping its non-vacuity requirement. CE/PE lifecycle tests demonstrate
that loss of a neighbor removes an OTM contract's ATM exemption at admission
and fill while spot remains bracketed; no position or equity debit results.
Existing complete-ladder, identity, replay-label and PAPER isolation tests remain.

Verification: the complete CI-selected offline NIFTY and notification regression
set passed locally on Windows Python 3.12.11: **1354 passed**, zero failures,
errors or skips, in **549.19 seconds**. This includes the complete offline
acceptance module and all 28 added parameterized cases. The original six failed
nodes are included, not deselected. Ruff check, Ruff format check and
`git diff --check` passed. No production code changed for this correction.

The full run expanded `test/test_nifty_algo_*.py` and included
`test_pytest_import_resolution.py`, `test_rotate_pepper_salt.py`,
`test_fernet_salt_warning.py`, `test_smtp_error_messages.py`,
`test_smtp_certificate_verification.py` and `test_requirements_parity.py`, matching
the failed CI step. It used `-q -o addopts='' -p pytest_timeout --timeout=120
-p no:cacheprovider`, a fresh Windows TEMP basetemp, `NUMBA_DISABLE_JIT=1` and
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. Local JUnit evidence is
`tmp/pr10-full-nifty.xml`; console evidence is `tmp/pr10-full-nifty.log`.
An earlier local attempt ended after a Windows native access violation and is
not counted as successful verification. The complete clean run above finished
with exit code zero; no tests were suppressed to obtain that result. Python
3.13/3.14 and compiled-kernel validation remain GitHub Actions responsibilities.


## PR #11 CI correction: assessment claim check-then-act gate - 2026-11-25

Inspected Actions run `45571710187`, jobs `gthread-gates` (`139059700964`) and
`gthread-migration` (`139059700922`). Both failed on one site:
`database/nifty_algo_db.py` `NiftyStore.claim_assessment`, `guard-augassign
row.attempts`. In `gthread-migration` the same scanner runs inside
`test/test_gthread_deploy_gates.py`, which was the single failure there (1 failed,
1471 passed, 3 skipped). Nothing else failed in either job.

Finding: **protected, not a race.** The new durable retry budget (added with the
bounded candle-retry work) reads `row.attempts` and writes `row.attempts += 1`.
The scanner flags every read-then-write of an attribute and cannot see a lock held
by a helper. The whole method runs inside one `sessions.begin()` transaction whose
first statement is `_lock(db, user_id)`, an `UPDATE` of the user's
`NiftyState` row. That is the SQLite write lock or a PostgreSQL row lock and it is
held to commit. The runner lease, the state row, the attempt row, the
`COMPLETE` / `attempts >= 7` / `next_at` check and the increment all follow it, so
a second claimant is parked on the lock and decides only on the committed result.
`finish_assessment` takes the same lock and compares `claim_id`, `owner`, status
and the live lease, so a stale holder cannot finish a newer claim. No production
code changed.

The site is recorded in `scripts/gthread_check_then_act_reviewed.txt` with that
reason and the tests that prove it. It is not a blanket entry: the key is the
function and the attribute, so a second unguarded increment added to the method
would still be reported.

Proof, in `test/test_nifty_algo_assessment_claim_concurrency.py` (6 tests):

- A competing claim is staged at the attempt write itself, for a first claim and
  for a retry claim. The competitor's first statement is the owner lock, it waits
  there while the first claim writes, and it then loses: one claim id, attempts 1
  (or 2), status `IN_FLIGHT`.
- Four writers per five-second step across ten steps grant exactly one claim at
  each of the seven steps inside the thirty-second window and none after it;
  attempts end at 7.
- A completed boundary is not claimed again by four racing writers.
- Restart recovery: an owner whose lease expired is replaced, cannot claim or
  finish afterwards, the replacement waits for `next_at` and then claims once
  (attempts 2), and the dead owner's claim id is fenced.
- Retry expiry: a claim at exactly the deadline is granted, one microsecond later
  is refused.

Mutation check (not committed): with `_lock` replaced by a no-op, 3 of the 6
tests fail (both staged-write cases and the four-writer budget case); with it in
place all 6 pass. The three that pass either way cover sequential fencing and
deadline semantics, which do not depend on the lock. The existing
`test_nifty_algo_boundary_retry.py` (7 tests, including the single-flight and
fenced-expiry cases) is unchanged and passes.

Verification (Windows, Python 3.12.11, `-o addopts=''`, `--timeout=120`):
`scripts/gthread_check_then_act.py` exits 0 (the site is REVIEWED);
`scripts/gthread_sleep_gate.py` exits 0; `test/test_gthread_deploy_gates.py`
**10 passed**; the remaining `test/test_gthread_*.py` files (all but the two
named below): **1315 passed, 126 skipped, 1 failed**; `test/test_nifty_algo_*.py` plus
`test/risk`: **1614 passed**, no failures or skips. The 126 skips are the Linux and
eventlet-only tests, which is why the Linux job is the authority.

Unresolved. The Linux `gthread-migration` run cannot be reproduced locally: WSL
has no Linux distribution, and most gthread files skip on Windows. On Windows,
`test_gthread_brokers_a_deltaexchange_session.py` hangs in
`test_a_pooled_thread_holds_no_connection_after_the_lookup` until the timeout
dump; it does not touch NIFTY code, was left out of the local run and is covered
by the Linux CI job. `test_gthread_sandbox_positions.py::
test_orders_on_different_positions_do_not_wait_for_each_other` fails on this Windows
machine on a wall-clock bound (about 1.4 s against `< 1.0`, repeated twice in
isolation). The branch changes no sandbox code and the test was not run against
`main` here, so whether it also fails there is unconfirmed; the Linux job decides.
The open findings listed above (F-05, F-21, F-06, F-07,
F-15, F-16, F-18, F-23) are unchanged by this correction.
