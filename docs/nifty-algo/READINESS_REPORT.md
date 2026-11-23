# NIFTY paper-trading readiness report

## Corrective audit — 23 November 2026

The final scoped Linux regression matrix passes: **795 passed**. The clean
worker suite passes **1,456 tests with three documentation skips**. The final
health/runtime slice also passes. Historical counts below do not certify the current working
tree. This audit preserves the three pre-existing edited
code files and the inherited corrective test file. No branch, commit, broker
order, production database or external notification is changed.

### A. Phases 1–7

| Phase | Review status | Issues found | Fixes applied | Tests |
| --- | --- | --- | --- | --- |
| 1 Account, risk and order admission | Boundary review and regressions | Fallback identity, liquidity and atomic quote checks; whole-position exit depth at entry fill | Validate all candidates; choose liquid fallback; reprice under admission lock; require full bid quantity | phase1, gap_p1, paper_executor, selector and corrective suites |
| 2 Protection | Pure Decimal evaluator and integration reviewed | Discord discarded persisted stop-transition details | Allowlist recorded transition fields; evaluator and parameters unchanged | phase2, v2, corrective |
| 3 Calendar, cooldown and monthly limits | Code and existing regression coverage reviewed | Obsolete v2 risk/window documentation | Synchronize strategy assumptions; retain approved-calendar and latched-lock policies | calendar, phase3b, phase1 |
| 4 Shadow and research | Separate ledgers, mirrors and causal observations reviewed | No additional confirmed defect in reviewed paths | No accounting/strategy changes | phase4, research, recording, capture suites |
| 5 Trading modes and broker settings | Hard-block and authenticated controls reviewed | No additional confirmed defect in reviewed paths | Live stub retained without transport | phase5, pipeline, safety_center |
| 6 Reports and SMTP | Claims, uncertain delivery, paths and totals reviewed | Existing Windows email diagnostic startup timeout | No unrelated timeout or transport changes | phase6 and neighboring SMTP suites |
| 7 Hardening | Leases, readiness, recovery and resource ownership reviewed | Heartbeat could expose stale entry readiness; held-position feed loss lacked durable incident | Freshness-bound status; idempotent critical incident while exits continue | corrective, pipeline, safety_center and Linux worker suite |

### B. Five-feature verification

| Feature | Review status | Issues found | Fixes applied | Tests |
| --- | --- | --- | --- | --- |
| Discord Notifications | Implemented paths reviewed; full acceptance incomplete | Incorrect health fields/block flag; missing lock details and existing control/data event routing | Fresh actual runner health; allowlisted risk/control/warning projection | discord, notification_outbox, corrective; 79 scoped frontend tests |
| Advanced Analytics | Stored-fill arithmetic, owner filters, half-open periods and sampled research reviewed | No new confirmed arithmetic defect; comparative dashboards and execution coverage remain incomplete | No ledger changes; sampled-data limitations retained | analytics, analytics_integration, exit_studies and UI suites |
| Execution Safety Center | Incident lifecycle, admission/fill interlock and separate resume reviewed | Stale held-position feed had no durable critical incident | Persist one incident per missing-data episode; leave exits and reconciliation controls active | safety_center, corrective, UI |
| Historical Replay / Backtesting Lab | Causal quote evidence and immutable experiments reviewed; financial replay incomplete | Full signal/execution A/B/C simulator and required historical inputs absent | Preserve explicit refusal and null performance; do not invent returns | recording_replay, experiments, experiment_api, replay_lab, UI |
| Smart Option Selector | Current metadata, risk-approved ranking and execution boundaries reviewed | Fallback could cross signal side; invalid first candidate hid fallback; quote changed before reservation; fill accepted too little exit depth | Candidate checks, liquid fallback, atomic reprice, full-quantity bid gate | selector, weighted_selector, selector_integration, paper_executor, corrective |

### C. Trading-rule compliance

Every rule below except the explicitly ambiguous morning-regime row passed
offline code/fixture verification in the full NIFTY matrix. These results are
not guarantees of execution or profitability; real feed/calendar applicability
and fee rates remain external acceptance work.

| Rule | Review result / authority |
| --- | --- |
| ₹20,000 starting paper capital | Fixed configuration seed; existing ledger balances preserved |
| One primary trade per day | Admission and first-fill accounting under user transaction lock |
| 1–3 lots | Confidence tiers, capital, loss/reward and displayed depth constrain each proposal |
| ATM/ITM only | Resolver classification; current spot checked again at admission and fill |
| 09:15–10:30 observation; primary entry from 10:30 | Primary window enforced; independent shadow may observe/enter from 09:15 by explicit Phase 4 decision |
| Entry cutoff 14:45 | Admission expiry and BUY fill cutoff; no fill at cutoff |
| Exit deadline 15:10 | Mandatory exit request, subject to fresh executable bid for actual simulated fill |
| Holding limit 45 minutes | Shared mandatory-exit evaluator for primary and independent shadow |
| Initial premium stop at most 8% | Filled-premium Decimal stop rounded conservatively to tick |
| Planned loss at most ₹400 including estimates | Sizing, reservation and fill revalidation; realized losses may exceed model |
| Projected entry reward at least ₹350 net | Unmodified target and estimated entry/exit fees checked in sizing and fill |
| Dynamic target 10–15% | Five-indicator strength and tick-valid bounds; held configuration frozen |
| Trail 1.5 premium points | Fixed distance, monotonic persisted stop/peak |
| Profit lock at ₹400 estimated net | Pure evaluator, durable activation event |
| Modeled profit floor at least ₹350 | Tick-valid cost-aware floor; gaps remain actual realized outcomes |
| Early booking at least ₹300 net | Requires premium deterioration and fresh completed-candle momentum weakening |
| Monthly loss limit ₹2,000 | Realized exit-month totals and persistent latched lock |
| Monthly profit policy | Optional target, audited changes, latched lock never cleared by editing target |
| Loss cooldown | Next approved eligible normal NFO session; unresolved next-year calendar blocks entries |
| Holidays | User-approved NFO calendar; special sessions disabled |
| Completed five-minute signals / fifteen-minute confirmation | Production Rules and causal aggregation; missing inputs fail closed |
| Morning classification / confirmed reversals | Existing per-candle indicator bias and confirmation gates; no separate frozen morning regime or special reversal policy found. Such additional semantics are ambiguous and were not invented |

### D. Defects corrected

1. **Stale displayed readiness.** Lease heartbeats outlived their assessment.
   `database/nifty_algo_db.py:runner_status` now reuses the configuration-bound
   30-second readiness evaluator. `test_heartbeat_cannot_refresh_old_entry_readiness`
   proves ownership renewal cannot renew assessment evidence.
2. **Misleading Discord health.** The command projected nonexistent runner
   state fields and only incident-based entry blocking. `discord_bot.py` now
   reports operational/readiness/reason timestamps and includes paused/dead
   runner state. `database/nifty_notifications.py:discord_status_snapshot`
   additionally reads persisted monthly locks, cooldown, kill/daily locks and
   account reconciliation without writing. Runner-field and seven persisted
   risk-hold cases cover the projection; the existing SELECT-only command test
   remains unchanged.
3. **Fallback identity bypass.** Only the first candidate matched the decision
   side. `paper_executor.py:admit` validates every candidate's side, exchange,
   expiry, tradability and current master date. The wrong-side regression
   confirms no reservation is written. Existing cooldown refusal precedence is
   preserved; the full suite caught and verified that ordering requirement.
4. **Valid fallback suppressed.** The preliminary gate picked the first non-null
   quote even when illiquid. It now picks the first liquid candidate before
   risk-approved ranking. The liquid-fallback regression confirms selection.
5. **Quote changed before locked admission.** Selection-time depth and price
   survived until reservation. The admission callback now rereads cached depth
   and reruns the existing planner. Liquidity-loss and price-change tests land
   the competing update at `admit_order`, then assert no pending order.
6. **Insufficient exit depth at entry fill.** The final BUY check required only
   one lot of bid depth. `nifty_algo_db.py:fill` now requires the entire selected
   quantity. The two-lot/one-lot-depth regression rejects with LIQUIDITY_LOST.
7. **Missing durable feed-loss incident.** Exit monitoring previously retained
   exposure without generating an incident when the bid became unavailable.
   `paper_executor.py:monitor_exits` now writes an idempotent CRITICAL STALE_DATA
   incident keyed by entry and last observation. The regression proves one
   incident, one pending exit and no fabricated fill after repeated monitoring.
8. **Missing notification context/routing.** `discord_bot.py:event_projection`
   dropped recorded profit-lock stop transitions and ignored existing operator
   controls/data failures. Explicit allowlists now route those events while
   excluding arbitrary provider text. Profit-lock and parametrized routing
   regressions verify destination, values and secret exclusion.
9. **Contradictory strategy assumptions.** The v2 document still claimed
   0.5% risk, one lot, three daily entries and 09:30 entry. It now records the
   current v3.1 rules and links their authority. No risk parameter changed.

### E. Current test results

| Check | Observed result |
| --- | --- |
| Final Linux NIFTY plus neighboring email/SMTP matrix, including expanded health | **795 passed, 0 failed, 0 skipped**, 419.83 s; all 767 NIFTY tests plus 28 neighboring tests |
| Sequential Linux NIFTY plus neighboring email/SMTP matrix before the final expanded health projection | **788 passed, 0 failed, 0 skipped**, 292.25 s; all 760 NIFTY tests plus 28 neighboring tests; final health correction requires a new full run |
| First Linux matrix before refusal-order correction | 787 passed, 1 failed; existing cooldown test exposed metadata refusal precedence; corrected and full matrix rerun |
| Windows focused corrective plus email/SMTP matrix | 39 passed, 1 failed; all 12 corrective cases passed; existing `test_cli_help_does_not_require_pytest` subprocess exceeded its unchanged 10-second timeout |
| Final Windows corrective plus Discord suite | **56 passed**, 261.75 s; all 19 corrective cases plus 37 existing Discord tests, including SELECT-only commands |
| Earlier inherited corrective file | 8 passed before the four additional cases were added |
| Clean Linux runtime/gate slice | 31 passed, 0 failed; verified fixture-path failure cause |
| Isolated Linux gate slice | 10 passed, 0 failed with fixtures outside repository |
| Full Linux worker suite | **1,456 passed, 0 failed, 3 skipped**, 984.73 s; skips are `test_gthread_strategy_docs.py:57`, no threading note about greenlets. Clean snapshot predates only final read-only health expansion; supplemented by final-source NIFTY/Discord and runtime tests |
| Final-source Linux runtime/gate slice | **31 passed, 0 failed**, 36.14 s, after expanded health correction |
| NIFTY frontend | **79 passed**, 11 files, 85.53 s, outside sandbox |
| Initial sandboxed NIFTY frontend attempt | 6 passed, 9 worker errors; not treated as a feature pass |
| Full frontend attempt | Interrupted after unrelated `Message.viz.test.tsx` took 574.733 s; its per-file output showed 7 tests / 4 skipped; no full-suite total or pass claimed |
| TypeScript / Vite production build | Passed; Vite 8,354 modules, 5m16s; output only under tmp |
| Frontend lint | Passed; 4 warnings and 2 infos in unrelated existing files |
| Ruff / changed-file format / diff whitespace | Passed after final code correction |
| Static runtime gates | Passed: 28/28 check-then-act sites and 7/7 long/looping sleeps reviewed |
| npm dependency tree | `npm ls --depth=0` completed successfully |
| Python dependency consistency | Failed: documented intentional litellm/filelock security override, not changed by this audit |

Earlier broad worker attempts were interrupted when the task container stopped
with exit 143, not an OOM kill. They contained synthetic gate/runtime failures
from repository-local fixtures in a Git archive; clean external-fixture checks
identified that cause. They also contained Historify lifecycle failures whose
cause was not established. The complete clean sequential run is green, but no
unrelated Historify code was fixed and its earlier failures are not erased.

The final Linux matrix covers additive database initialization/migration preservation,
authentication/CSRF and ownership controls, duplicate claims and admissions,
restarts, depth/fill reconciliation, financial calculations, all phase suites,
all five implemented feature paths, and the new corrective tests. Automatic
partial fills remain explicitly unsupported; modeled partial exits retain their
existing tests. No real provider delivery or live market validation is inferred.

Windows full and redundant focused attempts were interrupted during prolonged
startup or superseded by the final source. They do not count as complete runs.
Existing warnings include unsupported Node 26.2.0, localStorage notices,
deprecated module registration, unresolved runtime assets, plugin timing and
large build chunks. Lint warnings concern existing agent/trading files, not the
scoped corrections. No assertion, timeout or validation was weakened.

Commands executed from repository root unless marked `frontend/`:

```powershell
$auditTests = (Get-ChildItem test/test_nifty_algo_*.py).FullName
& .venv/Scripts/python.exe -m pytest @auditTests -o addopts= -q --timeout=120 --basetemp=tmp/nifty-audit-current -p no:cacheprovider
& .venv/Scripts/python.exe -m pytest @auditTests -o addopts= -q --timeout=120 --basetemp=tmp/nifty-audit-verified -p no:cacheprovider
.venv/Scripts/python.exe -m pytest test/test_nifty_algo_corrective_audit.py -o addopts= -q --timeout=120 --basetemp=tmp/nifty-audit-focus -p no:cacheprovider
.venv/Scripts/python.exe -m pytest test/test_nifty_algo_corrective_audit.py test/test_email_functionality_pytest.py test/test_smtp_error_messages.py test/test_smtp_certificate_verification.py test/test_gthread_messaging_email.py -o addopts= -q --timeout=120 --basetemp=tmp/nifty-audit-final-focused -p no:cacheprovider
.venv/Scripts/python.exe -m pytest test/test_nifty_algo_corrective_audit.py -o addopts= -q --timeout=120 --basetemp=tmp/nifty-audit-final-only -p no:cacheprovider
.venv/Scripts/python.exe -m pytest test/test_nifty_algo_corrective_audit.py test/test_nifty_algo_discord.py -o addopts= -q --timeout=120 --basetemp=tmp/nifty-audit-health-final -p no:cacheprovider
.venv/Scripts/ruff.exe check services/nifty_algo database/nifty_algo_db.py database/nifty_notifications.py database/nifty_research_analytics.py blueprints/nifty_algo.py blueprints/nifty_discord.py test/test_nifty_algo_*.py
.venv/Scripts/ruff.exe format --check services/nifty_algo/discord_bot.py services/nifty_algo/paper_executor.py database/nifty_algo_db.py database/nifty_notifications.py test/test_nifty_algo_corrective_audit.py
.venv/Scripts/python.exe scripts/gthread_check_then_act.py
.venv/Scripts/python.exe scripts/gthread_sleep_gate.py
.venv/Scripts/python.exe -m pip check
git diff --check
```

Frontend commands, from `frontend/`:

```powershell
node --no-experimental-webstorage node_modules/vitest/vitest.mjs run src/features/nifty-algo --pool=threads --maxWorkers=1
node --no-experimental-webstorage node_modules/vitest/vitest.mjs run --pool=threads --maxWorkers=1
node node_modules/typescript/bin/tsc -b
node node_modules/vite/bin/vite.js build --outDir ../tmp/nifty-audit-build
npm run lint
npm ls --depth=0
```

Linux commands, inside a separate container created from the existing
`openalgo-nifty-phase7-verified-env:local` image, working directory `/audit`:

```sh
/work/.venv/bin/python -m pytest test/test_nifty_algo_*.py test/test_email_functionality_pytest.py test/test_smtp_error_messages.py test/test_smtp_certificate_verification.py test/test_gthread_messaging_email.py -o addopts= -q --timeout=120 --basetemp=tmp/corrective-audit -p no:cacheprovider
/work/.venv/bin/python -m pytest test/test_nifty_algo_*.py test/test_email_functionality_pytest.py test/test_smtp_error_messages.py test/test_smtp_certificate_verification.py test/test_gthread_messaging_email.py -o addopts= -q --timeout=120 --basetemp=tmp/corrective-audit-final -p no:cacheprovider
/work/.venv/bin/python -m pytest test/test_gthread_*.py -o addopts= --timeout=120 -rfs --basetemp=tmp/corrective-workers -p no:cacheprovider
/work/.venv/bin/python -m pytest test/test_gthread_deploy_gates.py -o addopts= -q --timeout=120 --basetemp=/tmp/nifty-corrective-gates -p no:cacheprovider
/work/.venv/bin/python -m pytest test/test_gthread_deploy_gates.py test/test_gthread_foundation_runtime.py -o addopts= -q --timeout=120 --basetemp=/tmp/nifty-clean-runtime -p no:cacheprovider
/work/.venv/bin/python -m pytest test/test_nifty_algo_*.py test/test_email_functionality_pytest.py test/test_smtp_error_messages.py test/test_smtp_certificate_verification.py test/test_gthread_messaging_email.py -o addopts= -q --timeout=120 --basetemp=/tmp/nifty-final-sequential -p no:cacheprovider
/work/.venv/bin/python -m pytest test/test_gthread_*.py -o addopts= --timeout=120 -rfs --basetemp=/tmp/nifty-worker-sequential -p no:cacheprovider
/work/.venv/bin/python -m pytest test/test_nifty_algo_*.py test/test_email_functionality_pytest.py test/test_smtp_error_messages.py test/test_smtp_certificate_verification.py test/test_gthread_messaging_email.py -o addopts= -q --timeout=120 --basetemp=/tmp/nifty-health-complete -p no:cacheprovider
/work/.venv/bin/python -m pytest test/test_gthread_deploy_gates.py test/test_gthread_foundation_runtime.py -o addopts= -q --timeout=120 --basetemp=/tmp/nifty-final-health-runtime -p no:cacheprovider
```

Logs are in `tmp/nifty-audit-*.txt`; production build output is confined to
`tmp/nifty-audit-build`. Tracked frontend build artifacts were not overwritten.
The earlier sequential runs use `/audit-clean`; the first runs use `/audit`.
The expanded-health full matrix uses `/audit-health`, with separate source and
databases. That copy contains HEAD plus all four scoped edited Python modules
and the corrective test file. The clean worker snapshot predates only the final
read-only health projection; its core runtime modules are otherwise identical.
The first failed matrix is retained as evidence;
the final run follows an actual code correction, not an unchanged flaky retry.
An additional Windows diagnostic invoked `pytest.main` on the corrective file
with `faulthandler.dump_traceback_later(45, repeat=True)`; it was interrupted
during import and is not passing test evidence.

### F. Readiness decision

**PARTIAL — Implemented paths verified, but full feature acceptance, broader
checks and external dependencies remain unverified.**

The scoped regression matrix is green. Financial replay and documented
advanced-feature software gaps remain incomplete, so this is not completion of
every requested acceptance criterion. No live-trading readiness is claimed.
No live order was placed, no live transport enabled, no strategy/risk parameter
changed, no dependency installed, and no file committed or pushed. The audit
adds no unrelated product feature and preserves unrelated local work.

### G. Remaining issues and evidence limits

- Full financial A/B/C replay lacks the simulator and synchronized futures,
  PCR, point-in-time option universe and executable price/depth evidence.
- Existing advanced-feature docs disclose unfinished comparative analytics,
  routine research/trailing digests, provider bucket handling, worker heartbeat,
  dead-letter replay, report-command attachments and archival/retention.
- Separate frozen morning classification and reversal timing semantics are not
  specified by the current phase design. Existing safer entry/confirmation
  behavior is retained; no additional trading policy is inferred.
- The confirmed selector scoring policy uses volume and depth but has no
  separate open-interest ranking factor. OI is used by PCR. No new OI threshold
  or weight is invented; that requested selector criterion remains unverified.
- Real Angel data coverage, current fee applicability, actual Discord/Gmail
  delivery, command latency and extended forward-paper operation are unverified.
- Earlier Historify lifecycle failures remain unexplained. The final clean
  worker run passed, but it does not establish a root-cause fix for that prior
  flakiness. No unrelated infrastructure correction was attempted.
- Node 26.2.0 is outside the declared supported engine ranges. Python dependency
  consistency reports litellm's filelock<4 requirement against installed 4.2.4;
  pyproject.toml deliberately overrides this for a documented security fix.
- Resource review of the corrections is static: existing transaction/session
  contexts release connections, cache reads create no client/subscription, and
  no thread, executor, cache or unbounded process registry is added. No new
  production resource soak is claimed.

## Historical verification (does not certify the current diff)

Status: Phases 0–6 implemented; Phase 7 hardening verified offline on 21 November 2026
(283 NIFTY backend tests, 28 neighboring email tests, 26 workspace tests,
production build green, Linux runtime gate 1,456 passed/3 skipped — see
`PAPER_SYSTEM_DESIGN.md` §5 and `TESTING.md`). **Real-market forward paper
readiness has not been verified.** Live mode is blocked by design: the adapter
is a stub with no transport that always reports `LIVE_NOT_READY`.

| Area | Implemented and offline evidence | External or remaining evidence |
| --- | --- | --- |
| 8% stop and point trail | Filled-price stop, conservative ticks, delayed activation, monotonic durable peak/stop, gap and depth rejection tests | Live feed latency/liquidity behavior |
| Profit lock | ₹400 activation, ₹350 modeled floor, tick-aligned floor stop, gap-through-floor honesty | Real-time bid-depth behavior |
| Dynamic target | Deterministic per-indicator contributions, bounded tick-valid 10–15% target, immutable entry settings | No calibrated win probability or profitability evidence |
| Data and PCR | Native source cache and futures history connected; full dated master expiry, timestamp/coverage/definition checks | Genuine Angel complete-scope observations and entitlement |
| Calendar | Approved NSE PDF import with DRAFT/APPROVED/REJECTED states; `CALENDAR_UNAPPROVED` blocks entries | A real uploaded NSE circular per year |
| Cooldown and monthly locks | Next-session loss cooldown; ₹2,000 monthly loss lock and optional profit lock, latched and restart-safe | Forward observation |
| Runner | Native IST scheduler, three named jobs (`:protect`, `:entries`, `:reports`), lease, startup floor and restart reconciliation | Full application process lifecycle under Linux workers |
| Paper ledger | Atomic reservation/fills, displayed quantity, costs, retries, partial exit accounting, isolated journal, ₹20,000 virtual capital | Extended unattended forward observation |
| Shadow and research | One active hypothetical shadow, primary mirrors flagged non-additive, bounded research observations | Forward observation |
| Trading modes | Revision CAS under user lock, masked broker status, Live hard-blocked by `LiveAdapterStub` | Independent Live verification (below) |
| Reports | Deterministic sha256 PDFs, idempotent period keys, CAS delivery claim, bounded retry only for definite failures, uncertain outcomes held for operator review, `SKIPPED_NO_SMTP` | Real SMTP deliverability |
| Workspace | Existing route, readiness-gated Start, panels for locks/calendar/shadow/mode/reports | Real-session UI observation |

The offline end-to-end simulator runs actual five-indicator calculations and
verified-fixture PCR, selects a contract, reserves risk, confirms ask fills,
advances protection, exits on bid depth and checks fees/net P&L. Generic order
transport canaries and import checks remain untouched under Analyzer enabled,
disabled and changing. This is offline isolation evidence, not a real broker
session test. Test totals, command failures and platform limits are in TESTING.md.

Before a forward paper session, verify today's broker/master identity, full
expiry coverage within subscription capacity, source-level exchange timestamps,
actual futures volume, an approved NFO calendar for the year, reconnect
recovery, correct fee assumptions, and the production worker startup/shutdown
behavior. If the broker cannot supply the full timestamped scope, entries must
remain blocked. No real historical dataset was replayed and no live-market
paper fill was observed during implementation. Database retention is not
automated.

## Live mode unblock requirements (by design, none are self-certifiable)

`LiveAdapterStub` reports every prerequisite unverified. Replacing it requires
a real adapter plus independent evidence for each: broker authentication and
token validity, market-data quality, protective-order acceptance at the broker,
fill reconciliation against broker records, and deployment prerequisites
including SEBI static-IP whitelisting. A mode request is also refused on any
open exposure and without an explicit acknowledgement. Until then Live cannot
activate; Paper mode is unaffected.
