# Advanced Features Testing

## Gap-completion verification — 24 November 2026

This section supersedes earlier counts for the completion task. Final frozen-source
Windows verification passed **842 tests in 411.28 seconds: zero failed, zero skipped**.
The feature frontend suite passed **97 tests: zero failed, zero skipped**.
These are 939 distinct backend/frontend cases; focused reruns are not added again.
No local Linux tests are part of this completion, as instructed
by the owner. The existing CI backend matrix now runs all offline NIFTY tests,
SMTP neighbors and requirements parity on Python 3.12/3.13/3.14. No CI result is
claimed before that workflow executes.

| Check | Observed result |
| --- | --- |
| Full NIFTY backend, SMTP neighbors and requirements parity | 842 passed, 411.28 seconds; zero failures/skips |
| Notification completion tests after report-history correction | 23 passed, 6.70 seconds |
| Final stale-attempt / opaque-token API slice | 2 passed, 3.24 seconds |
| NIFTY frontend, final paged notification controls | 97 passed across 15 files, 49.34 seconds; zero failures/skips |
| TypeScript build check | Passed; Vite ran only after a successful `tsc -b` exit |
| Production Vite build, isolated output | Passed in 1m 50s; output under `tmp/nifty-completion-dist-verified` |
| Backend Ruff | Passed; 24 changed Python files pass format check |
| Frontend Biome | Passed; 14 changed files checked, no fixes required |
| Strict sleep gate | Passed; 763 files, zero unsafe-under-lock/eventlet branches, six reviewed sites |
| Strict check-then-act gate | Passed; 807 files, 28 reviewed sites, zero unreviewed |
| Requirements parity | Passed within the complete backend run |
| Installed dependency compatibility | FAILED: 225 packages checked; installed `filelock==4.2.4` conflicts with `litellm`'s `filelock>=3.16.1,<4.0` requirement |
| Linux runtime/worker verification | Deferred to GitHub CI by owner instruction; not passed locally |

No dependency was installed or changed. The installed-package incompatibility is
an environment blocker outside the scoped NIFTY implementation. Genuine provider,
SMTP, deployment and forward PAPER tests remain external acceptance requirements.

**Verdict: PARTIAL acceptance.** The requested software gaps are implemented and
covered by the passing Windows checks. Installed dependency consistency fails,
Linux/worker CI results remain pending, and external acceptance has not occurred.
This is not a claim of real historical backtesting or Live readiness. No live
execution, broker order, external notification, production DB migration, commit,
push, merge or branch change was performed. HEAD remains
`784b059d5ee282ca5a2c1fbcb7bd937604100e51`. Unrelated work was preserved.

Earlier failed iterations are not hidden: a misplaced new test-helper return was
corrected; the notification-health extra DB session was removed; a stale replay
revision incorrectly caught as ValueError now propagates StateConflict/409.
The corrected resource test preserves its original 300-open/300-close assertion.
A frontend fork run passed 68 tests but failed to start two workers. Isolated
threads subsequently passed all 97 tests with unchanged assertions/timeouts.
Build warnings remain for an existing unresolved asset reference, large chunks,
plugin timing and Node deprecation. Installed Node 26.2.0 is outside the declared
supported ranges; CI's supported Node matrix remains necessary. Tracked build
assets were restored; the final build writes only temporary output.

### Commands

Commands below preserve the executed test arguments; shell output redirection
to `tmp/nifty-completion-*.txt` is omitted. The system-temp root is unique per run
and checked before use. All broker/feed/provider behavior is controlled by fixtures.

```powershell
$niftyTestRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('openalgo-nifty-frozen-' + [guid]::NewGuid().ToString('N'))
.venv/Scripts/python.exe -u -m pytest @(Get-ChildItem test/test_nifty_algo_*.py | Select-Object -ExpandProperty FullName) test/test_smtp_error_messages.py test/test_smtp_certificate_verification.py test/test_requirements_parity.py -o addopts= -q --timeout=120 --basetemp=$niftyTestRoot -p no:cacheprovider
.venv/Scripts/python.exe -u -m pytest test/test_nifty_algo_notification_completion.py -o addopts= -q --timeout=120 --basetemp=$niftyTestRoot -p no:cacheprovider
.venv/Scripts/python.exe -u -m pytest test/test_nifty_algo_notification_completion.py::test_dead_letter_replay_api_requires_csrf_owner_and_exact_failed_revision test/test_nifty_algo_notification_completion.py::test_signed_opaque_continuation_token_is_encrypted_and_encoded_as_one_path_segment -o addopts= -q --timeout=120 --basetemp=$niftyTestRoot -p no:cacheprovider
uv pip check --python .venv/Scripts/python.exe
.venv/Scripts/python.exe scripts/gthread_sleep_gate.py --strict
.venv/Scripts/python.exe scripts/gthread_check_then_act.py --strict
git diff --check
```

From `frontend/`:

```powershell
node node_modules/vitest/vitest.mjs run src/features/nifty-algo --pool=threads --maxWorkers=1 --no-file-parallelism --reporter=dot
node node_modules/typescript/bin/tsc -b --pretty false
node node_modules/vite/bin/vite.js build --outDir ../tmp/nifty-completion-dist-verified
node node_modules/@biomejs/biome/bin/biome check src/features/nifty-algo/AnalyticsPanel.tsx src/features/nifty-algo/AnalyticsPanel.test.tsx src/features/nifty-algo/DiscordPanel.tsx src/features/nifty-algo/DiscordPanel.test.tsx src/features/nifty-algo/ReplayPanel.tsx src/features/nifty-algo/SelectorPanel.tsx src/features/nifty-algo/api.ts src/features/nifty-algo/ComparativeAnalytics.tsx src/features/nifty-algo/ComparativeAnalytics.test.tsx src/features/nifty-algo/ExecutionComparison.tsx src/features/nifty-algo/ExecutionComparison.test.tsx src/features/nifty-algo/ResearchOperations.tsx src/features/nifty-algo/ResearchOperations.test.tsx src/features/nifty-algo/CompletionPanels.test.tsx
```

Ruff lint command from the repository root:

```powershell
.venv/Scripts/python.exe -m ruff check blueprints/nifty_algo.py blueprints/nifty_discord.py database/nifty_algo_db.py database/nifty_notifications.py database/nifty_research_analytics.py database/nifty_notification_ops.py database/nifty_replay_storage.py services/nifty_algo test/test_nifty_algo_execution_completion.py test/test_nifty_algo_notification_completion.py test/test_nifty_algo_comparative_completion.py test/test_nifty_algo_capture_runner.py test/test_nifty_algo_experiment_api.py
```

Exact format command:

```powershell
.venv/Scripts/python.exe -m ruff format --check blueprints/nifty_algo.py blueprints/nifty_discord.py database/nifty_algo_db.py database/nifty_notifications.py database/nifty_research_analytics.py database/nifty_notification_ops.py database/nifty_replay_storage.py services/nifty_algo/assessment.py services/nifty_algo/discord_bot.py services/nifty_algo/native_data.py services/nifty_algo/notification_worker.py services/nifty_algo/paper_executor.py services/nifty_algo/replay_lab.py services/nifty_algo/replay_worker.py services/nifty_algo/research.py services/nifty_algo/runner.py services/nifty_algo/selection_scoring.py services/nifty_algo/execution_replay.py services/nifty_algo/execution_quality.py test/test_nifty_algo_execution_completion.py test/test_nifty_algo_notification_completion.py test/test_nifty_algo_comparative_completion.py test/test_nifty_algo_capture_runner.py test/test_nifty_algo_experiment_api.py
```

Existing unrelated calendar/report formatting was left intact.

### Regression and integration evidence

- Real five-indicator completed-candle evaluation with warmed deterministic futures,
  causal PCR/spot/options evidence and risk-approved simulated fills.
- Reproducible A/B/C results across identical pinned recordings and disjoint splits;
  no financial output for future/missing/stale/corrupt evidence, protection gaps,
  unsupported identities or unresolved operations. Loss cooldown and monthly locks
  are checked independently of the ₹400 modeled entry-loss cap.
- Native cache assessment recording, frozen metadata/calendar identities, failure
  isolation, actual owned fill quote/reason capture and no broker order authority.
- Archive corruption, ownership, interrupted writes, restore, immutable hashes,
  abandoned worker claims and stale-worker compare-and-set rejection.
- PAPER ledger reconciliation, independent Shadow isolation, non-additive mirrors,
  filters, missing quality observations and private comparative PDF consistency.
- Durable heartbeat/outage state, per-channel/global 429 semantics, definite versus
  ambiguous outcomes, safe replay authorization/CSRF/revisions, all-history failure
  paging, digests without primary-ledger writes and restart idempotence.
- Deferred ephemeral report acknowledgement, current authorization, encrypted opaque
  continuation tokens, path encoding, owned PDF hash/size checks, revocation, 429,
  expiry, abandoned in-flight ambiguity and monthly report selection past 100 newer
  daily records. Existing Gmail generation/delivery tests remain unchanged.
- Original phase/safety/runner tests continue to cover primary limits, entry/exit
  boundaries, atomic admission/fill validation, restart reconciliation, manual resume,
  live isolation, incident persistence and protective exits.

### Changed files and purpose

Confirmed corrective defects within the completed features:

| Problem / root cause | Small correction | Regression proof |
| --- | --- | --- |
| Health reads opened a second session for worker health | `database/nifty_notifications.py` and `nifty_notification_ops.py` reuse the caller's DB session | Existing 100-cycle/300-open/300-close test remains unchanged |
| Stale replay attempts returned 400 because StateConflict subclasses ValueError | `blueprints/nifty_discord.py` re-raises StateConflict for the existing 409 handler | `test_dead_letter_replay_api_requires_csrf_owner_and_exact_failed_revision` |
| Monthly reports vanished behind 100 newer unrelated reports | `database/nifty_notification_ops.py` selects the latest owned generated report of the requested kind directly | `test_monthly_report_selection_is_not_truncated_by_newer_daily_history` |
| Private continuation tokens assumed an undocumented alphabet | `discord_bot.py` and `nifty_notification_ops.py` treat bounded tokens as opaque and encode one URL segment | `test_signed_opaque_continuation_token_is_encrypted_and_encoded_as_one_path_segment` |
| New execution definitions retained quote-only capability labels | `database/nifty_algo_db.py` labels schema-2 definitions as requiring validated execution evidence; legacy definitions are preserved | Bundle restart/archive/reproducibility test checks the capability metadata |
| Frame privacy validation covered only the decision subtree | `execution_replay.py` validates the whole bounded frame and rejects sensitive keys outside the decision | Invalid analysis/secret payload parameterized tests |

The remaining entries below implement the documented software gaps. They do not
change the agreed strategy or replace working Phase 1–7 components.

All paths are relative to the repository root. This inventory excludes temporary
test/build output and the unrelated untracked `start-app.bat`, which was untouched.

| File | Purpose |
| --- | --- |
| `.github/workflows/ci.yml` | Run the offline NIFTY/SMTP/parity suite in the existing backend matrix |
| `README.md` | Document separate research worker and evidence-gated workflows |
| `blueprints/nifty_algo.py` | Owned research queue/comparison/archive and comparative export routes; private cache policy |
| `blueprints/nifty_discord.py` | Owned failure inspection/replay and correct stale-revision responses |
| `database/nifty_algo_db.py` | Additive operations/research tables, recording fences/quotas, bucket-aware claims and trailing transition events |
| `database/nifty_notifications.py` | Digests integration, bucket persistence and same-session health reads |
| `database/nifty_notification_ops.py` | Heartbeats, digests, safe failure inspection/replay and private report claims |
| `database/nifty_replay_storage.py` | Immutable bundles, queued calculation claims and verified archive/restore |
| `database/nifty_research_analytics.py` | Existing-ledger comparisons, fill quality and execution observations |
| `services/nifty_algo/assessment.py` | Optional fail-isolated analysis evidence sink |
| `services/nifty_algo/native_data.py` | Identified source-only spot recording |
| `services/nifty_algo/runner.py` | Opt-in causal analysis/execution capture without protective-job transport |
| `services/nifty_algo/selection_scoring.py` | Approved fresh OI cap and explicit coverage |
| `services/nifty_algo/paper_executor.py` | Record the actual versioned selector policy |
| `services/nifty_algo/research.py` | Typed FRAME/LEDGER validation, archived cursors and evidence-gated replay entry point |
| `services/nifty_algo/replay_lab.py` | Preserve quote inspection and refuse bundle use through legacy paging |
| `services/nifty_algo/execution_replay.py` | Pure deterministic financial simulation using existing strategy/risk/protection functions |
| `services/nifty_algo/replay_worker.py` | Separate bounded research process, restart claims and shutdown cleanup |
| `services/nifty_algo/execution_quality.py` | Decimal recorded-fill slippage/spread and explicit sampled coverage |
| `services/nifty_algo/discord_bot.py` | Provider bucket evidence and private original-response report transport |
| `services/nifty_algo/notification_worker.py` | Heartbeats, digests, private report handling and clean shutdown |
| `scripts/gthread_sleep_reviewed.txt` | Remove stale exemption after signal-aware worker shutdown |
| `frontend/src/features/nifty-algo/api.ts` | Typed scoped completion API helpers |
| `frontend/src/features/nifty-algo/AnalyticsPanel.tsx` | Mount comparative view |
| `frontend/src/features/nifty-algo/ComparativeAnalytics.tsx` | Independent mode results, quality, suggestions and exports |
| `frontend/src/features/nifty-algo/DiscordPanel.tsx` | Worker health, private report status and paged safe failure handling |
| `frontend/src/features/nifty-algo/ReplayPanel.tsx` | Integrate comparison/retention and distinguish raw evidence kinds |
| `frontend/src/features/nifty-algo/ExecutionComparison.tsx` | Evidence-gated side-by-side A/B/C results |
| `frontend/src/features/nifty-algo/ResearchOperations.tsx` | Explicit pinned research approval and archive/restore controls |
| `frontend/src/features/nifty-algo/SelectorPanel.tsx` | Explain observed OI and capped contribution |
| `frontend/src/features/nifty-algo/AnalyticsPanel.test.tsx` | Isolate primary ledger error tests from separately tested comparison |
| `frontend/src/features/nifty-algo/ComparativeAnalytics.test.tsx` | Comparative privacy/unavailable/filter/export states |
| `frontend/src/features/nifty-algo/DiscordPanel.test.tsx` | Outage, ambiguity and uncertain replay protection |
| `frontend/src/features/nifty-algo/ExecutionComparison.test.tsx` | Queue idempotence and unavailable financial fields |
| `frontend/src/features/nifty-algo/ResearchOperations.test.tsx` | Pinned sources and explicit research approval |
| `frontend/src/features/nifty-algo/CompletionPanels.test.tsx` | Cross-panel evidence refusal and uncertain-write recovery |
| `test/test_nifty_algo_execution_completion.py` | Financial replay, causal/risk gates, jobs, archive/recovery and OI regressions |
| `test/test_nifty_algo_notification_completion.py` | Monitoring, bucket/replay/privacy/restart/report regressions |
| `test/test_nifty_algo_comparative_completion.py` | Ledger/Shadow/mirror/quality/filter/export integration |
| `test/test_nifty_algo_capture_runner.py` | Real-shaped recorder integration and sink-failure isolation |
| `test/test_nifty_algo_experiment_api.py` | Scalar bundle metadata compatibility without loading snapshot blobs |
| `docs/nifty-algo/ADVANCED_FEATURES_READINESS.md` | Current gap status and honest acceptance categories |
| `docs/nifty-algo/ADVANCED_FEATURES_TESTING.md` | Exact verification evidence and this file inventory |
| `docs/nifty-algo/READINESS_REPORT.md` | Separate this completion from historical audit counts |
| `docs/nifty-algo/FIVE_FEATURES_INTEGRATION_AUDIT.md` | Link superseding implementation and verification status |
| `docs/nifty-algo/HISTORICAL_REPLAY.md` | Evidence schema, simulation assumptions, worker and retention contracts |
| `docs/nifty-algo/ADVANCED_ANALYTICS.md` | Comparative accounting/quality/coverage/export semantics |
| `docs/nifty-algo/DISCORD_INTEGRATION.md` | Operations, private report protocol and external acceptance |
| `docs/nifty-algo/SMART_CONTRACT_SELECTOR.md` | Owner-approved OI normalization and unchanged weights |
| `docs/nifty-algo/CHANGELOG.md` | Group completion work under unreleased 0.6.0 |

Resources were reviewed statically: DB sessions and files use context managers,
transport uses the shared bounded-timeout client, workers dispose resources on
shutdown, and no new unbounded cache/registry was introduced. The unchanged
100-cycle connection test measures all 300 opened sessions closing. This is not
a production memory/latency soak. Genuine resource/forward-PAPER validation and
the previously recorded Historify lifecycle race remain unverified in this
continuation; no later green result is claimed to fix that historical race.

## Historical evidence

This file records evidence for the current continuation. Earlier checkpoints
remain in [FIVE_FEATURES_INTEGRATION_AUDIT.md](FIVE_FEATURES_INTEGRATION_AUDIT.md)
and `progress.md`; their results do not automatically certify later edits.

## Recorded results

- Pre-continuation Windows baseline: 691 NIFTY tests passed in 328.22 seconds.
- Weighted selector, Discord, sizing and risk slice: 93 passed in 26.07 seconds.
- New weighted/Discord/exit-study/replay slice: 49 passed in 22.09 seconds.
- Expanded Discord tests, including competing writers, SELECT-only commands and
  fallback session cleanup: 33 passed in 9.07 seconds.
- Existing frontend suite: 72 passed. New Discord/replay tests: seven passed.
  Combined frontend suite: 79 passed across 11 files in 43.33 seconds.
- TypeScript noEmit passed for the current frontend source at that checkpoint.
- First expanded full backend gate: 738 passed, two failed in 316.98 seconds.
  Both failures exposed new shadow writes to primary events. The correction
  removes those writes and uses an independent shadow outbox checkpoint.
  Follow-up static coverage also rejected a primary event call in the runner's
  shadow method; that call is removed, and selector reads frozen shadow sizing.
  Existing boundary tests are unchanged. A fresh complete gate is required.

Later final test, browser, build and Linux results are appended below when
actually obtained. No broker, feed, Discord server or Gmail transport was used.

## Acceptance matrix

| Scenario | Test evidence |
| --- | --- |
| Weight normalization, missing Delta, deterministic ties, frozen financial limits | `test_nifty_algo_weighted_selector.py` |
| Existing primary admission/fill and protection invariants | Existing NIFTY phase/pipeline tests |
| Shadow/research cannot reach orders or change primary counters | Unchanged `test_nifty_algo_phase4.py` boundary tests |
| Session/CSRF, credential encryption, token masking, signed Discord PING | `test_nifty_algo_discord.py` |
| Wrong guild/channel/user and prohibited commands | Discord command authorization tests |
| Lost response, 429, 403, 5xx and independent Gmail fallback | Mock transport/outbox tests |
| Restart-safe claims, reminders and acknowledgements | Notification and outbox tests |
| Concurrent settings edits, one winner | Barrier-synchronized independent-store test |
| Repeated DB reads/conflicts release connections | 100-cycle/300-connection notification test |
| SMTP lookup failure releases sessions before transport | Fallback cleanup failure-path tests |
| Owned reconciled trade detail and sampled post-exit tracking past 45 minutes | `test_nifty_algo_exit_studies.py` |
| Missing execution evidence refuses all three variants | `test_nifty_algo_replay_lab.py` |
| Receipt-time causality, corrupt results, ownership and immutable results | Replay/experiment tests |
| PCR receipt availability and out-of-order refusal | Signal replay tests |
| UI credential clearing, uncertain writes without retries, UTC playback | New Discord/replay frontend tests |

## Reproduction

On PowerShell, pass expanded filenames; pytest does not expand a literal shell
wildcard itself:

```powershell
$niftyTests = (Get-ChildItem test/test_nifty_algo_*.py).FullName
& .venv/Scripts/python.exe -m pytest @niftyTests -o addopts='' -q
```

On Linux: `.venv/bin/python -m pytest test/test_nifty_algo_*.py -o addopts='' -q`.
Frontend: `npm run test:run -- src/features/nifty-algo` from `frontend/`.

## Outstanding operational evidence

An earlier Linux worker gate timed out in
`test_gthread_historify_lifecycle.py::test_connection_retry_allows_green_and_native_writers_without_stopping_hub`.
A bounded diagnostic completed without reproducing it. That does not identify
the race or clear the failure. No unrelated Historify production code was
changed. Do not rerun a flaky gate into green and call the issue resolved.

Real latency/depth, broker partial fills, actual emergency exits, command-response
deadlines, unattended worker behavior, provider delivery and forward-paper
observation remain separate acceptance requirements.

## Final Continuation Verification — 23 November 2026

- Corrected current-source full NIFTY gates: Windows 744 passed in 458.83 seconds;
  Linux 744 passed in 249.02 seconds. Existing isolation tests are unchanged.
- Four newer Discord tests separately pass inside the 37-test focused suite on
  each OS: Windows 22.10 seconds; Linux 7.20 seconds. They cover independent
  Shadow digest checkpoints, permission overwrites and owned attachment hashes.
- Reports/Discord/analytics slice: 95 passed in 209.41 seconds.
- Frontend 79 passed; TypeScript and production tsc-build/Vite build pass.
  Build output is Temp-only. Existing global asset, plugin, chunk and deprecation
  warnings remain. An npm argument-wrapper failure was corrected by invoking
  installed tsc.cmd and vite.cmd; no build configuration was weakened.
- Ruff passes; 21 touched Python files pass format check. Reviewed static gates
  show 28/28 check-then-act sites and 7/7 long/looping sleeps reviewed, with zero
  unsafe-under-lock sleeps. The notification loop runs only as an explicit CLI.
- Visible Chrome checks at 1440/375 pass, with mocked HTTP, exact UTC playback,
  revision-bound saves, cleared token fields and uncertain-write lockout. Zero
  page errors, zero scoped axe WCAG 2/2.1 A/AA violations, no horizontal overflow.
  Both screenshots were viewed. This is not full-application accessibility proof.
- Isolated Linux worker soak without retained mock calls: 220 cycles, 1,980
  opened/closed connections, five FDs at all six samples. RSS after warm-up:
  198979584, 198991872, 199004160, 199004160, 199016448, 199032832 bytes.
  This small-fixture growth is not an unbounded-memory finding or a production
  memory proof. No new persistent Python cache or cursor registry was added.
- Known unresolved release gate: earlier Historify eventlet child timeout.
  No full worker success is inferred from a diagnostic that failed to reproduce it.

No real external services, messages or orders were used. The Readiness document
continues to distinguish implemented components, unfinished software and missing
external evidence. Passing mocks does not establish Live readiness.
