# Advanced Features Testing

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
