# Advanced Features Readiness

## Remaining-gap implementation — 24 November 2026

This section supersedes the earlier implementation-gap statements below. The
working tree continues `784b059d5ee282ca5a2c1fbcb7bd937604100e51` on
`feat/nifty-paper-trading-system`. No branch, commit or push is part of this work.

| Feature | Previous software gap | Current implementation | External acceptance |
| --- | --- | --- | --- |
| Historical Replay | Quote inspection without execution replay or archive | Typed native FRAME/QUOTE/LEDGER evidence; isolated deterministic A/B/C execution; pinned multi-session splits; verified archive/restore and UI | Genuine synchronized futures/PCR/spot/options/depth coverage and achievable fill assumptions |
| Advanced Analytics | Incomplete comparative modes and execution quality | Reconciled PAPER/independent Shadow views; non-additive mirrors; quality/coverage/suggestions; verified research summaries; JSON/PDF exports | Real observed execution quality and sample coverage |
| Discord | Missing digests, heartbeat, buckets, operator replay and private report attachments | Durable bounded digests, heartbeat/outage status, channel/global rate scheduling, definite-failure replay and ephemeral deferred reports | Genuine permission/deadline/delivery, SMTP fallback and supervision tests |
| Smart Option Selector | OI omitted from liquidity | Owner-approved fresh OI cap on existing volume contribution; missing OI earns zero for that term | Trustworthy source OI, Greeks, depth and latency |
| Execution Safety Center | Compatibility preservation | Existing stop/resume, incident, reconciliation and Live gates retained | Forward PAPER recovery and deployment acceptance |

Final Windows verification passes **842 backend/NIFTY/SMTP/parity tests** and
**97 frontend tests**, with zero failures/skips in those final runs. TypeScript,
production build, scoped Ruff/Biome and strict static concurrency/sleep gates pass.
Exact commands, failures corrected and the complete 50-file inventory are in
[ADVANCED_FEATURES_TESTING.md](ADVANCED_FEATURES_TESTING.md).
Local Linux tests are explicitly deferred to GitHub CI by owner instruction.
The existing backend CI matrix now includes offline NIFTY/SMTP/dependency tests;
CI has not been run or claimed successful from this working tree.

Acceptance categories:

- **Implemented and verified:** all requested remaining software gaps have passing
  deterministic fixture/regression coverage. This proves behavior under the stated
  evidence gates and execution assumptions, not genuine market/provider performance.
- **Implemented but requiring external validation:** native recording, financial
  replay gates, provider delivery, command deadlines, deployment and forward PAPER.
- **Unfinished software:** none identified within the requested remaining gaps.
  Acceptance checks remain open: Linux/worker CI and installed dependency consistency.
- **Unsupported by available source data:** genuine historical options performance
  without synchronized option prices/depth and causal signal evidence; continuous
  market extrema and actual broker execution quality without recorded observations.

No strategy/risk parameter or PAPER capital reset is introduced. Replay and
Discord workers are explicit separate processes. Research definitions and
suggestions never activate configuration. Live remains blocked.

**Final verdict: PARTIAL acceptance.** Installed `filelock==4.2.4` violates
`litellm`'s `filelock>=3.16.1,<4.0` requirement; no dependency change was made in
this scoped task. Installed Node 26.2.0 is outside the declared supported ranges.
Linux CI is deferred as requested and has not been triggered or claimed passing.
Genuine Angel One feed coverage, expired-option history, Discord/SMTP delivery,
DigitalOcean resource/supervision behavior and forward PAPER remain external
validation. No experimental setting was activated and no live order was placed.

## Initial gap checklist — before this completion work

This checklist is the implementation boundary for the completion task. Earlier
test totals below are historical. No live transport or active strategy change
is authorized by research results.

| Requirement | Initial status | Implementation / next work |
| --- | --- | --- |
| Immutable recordings, experiments, causal quote playback | IMPLEMENTED | research.py, replay_lab.py, existing owned store/routes |
| Futures/candle/PCR/spot/metadata/decision recording | PARTIAL | Option quotes and metadata exist; extend typed availability-aware evidence |
| Deterministic execution-grade A/B/C replay | MISSING | Reuse production indicators, selector, sizing, costs and protection in isolated research state |
| Evidence gates and signal-only research | PARTIAL | Existing refusal and signal_study retained; integrate into saved comparisons |
| Split-aware comparison API and existing Replay UI | PARTIAL | Definition/inspection UI exists; add validated financial comparison |
| Recording archive, restore, bounded retention | MISSING | Verified immutable owner archives; explicit operations, never silent evidence deletion |
| Authoritative realized PAPER metrics and trade details | IMPLEMENTED | Existing ledger remains authority |
| PAPER / independent Shadow / non-additive mirrors comparison | PARTIAL | Journals exist; integrate filtered views and exports |
| Execution quality and evidence-based suggestions | PARTIAL | Fill/quote/protection evidence exists; calculate only supported quantities |
| Discord signed commands, outbox, reminders, fallback | IMPLEMENTED | Preserve ambiguity holds and read-only allowlist |
| Trailing/research digests and all applicable routing | PARTIAL | Shadow digest exists; add bounded durable checkpoints |
| Worker heartbeat, outage reporting and shutdown | MISSING | Add worker-owned durable status; no protection-job transport |
| Bucket-aware provider scheduling | PARTIAL | Global cooldown exists; add per-route provider bucket evidence |
| Dead-letter inspection and authorized safe replay | PARTIAL | Attempts stored; only definite failures may be replayed |
| Deferred private report attachments | PARTIAL | Owned verified report attachments exist for notifications, not commands |
| Selector OI consideration | PARTIAL | Preserve top-level weights; resolve within existing liquidity policy |
| Real Angel coverage, expired-option history, provider delivery | EXTERNALLY BLOCKED | Mocked software tests cannot certify unavailable genuine data |
| Execution Safety Center / Phase 1–7 risk core | IMPLEMENTED | Compatibility corrections only; no redesign or parameter changes |

This extension is not Live-ready and does not satisfy every requested acceptance
criterion. `LiveAdapterStub` remains the hard gate. No deployment, real order,
external notification, commit or push is performed by this continuation.

## Historical phase status — before this completion work

| Phase | Current status | Remaining acceptance |
| --- | --- | --- |
| 0 Baseline audit | Existing pushed baseline inspected and fetched; prior work retained | External broker/market claims remain unverified |
| 1 Foundations | Existing durable state/outbox extended additively | Final Linux/runtime and resource verification |
| 2 Selector | Weighted eligible contract/quantity ranking, settings, evidence and UI | Real depth/latency; explicit DELTA-mode baseline limitation |
| 3 Safety Center | Existing Paper incident/recovery and manual-resume architecture retained | Live reconciliation, verified protection and emergency flattening unavailable |
| 4 Analytics | Authoritative realized metrics, breakdowns, details, sampled excursions and post-exit research | Full comparable-mode dashboards, execution-quality coverage and research suggestions |
| 5 Replay | Immutable experiment/coverage results, causal quote playback, optional PCR-aware signal function | Full futures/PCR recording, integrated signal runs, financial A/B/C execution replay, retention/archive |
| 6 Discord | Dedicated REST bot, ten mappings, signed authorized commands, outbox, role alerts, reminders, SMTP fallback and UI | Digests beyond shadow, operator dead-letter handling, heartbeat, deadline and real provider tests |
| 7 Integration | Windows/Linux 744-test gates, newest 37 Discord tests, 79 UI tests, build and isolated browser checks pass | Unresolved Historify timeout; full worker/real-provider/market acceptance |
| 8 Handover | Architecture, API, feature, setup, measured testing and readiness documents added | Remaining implementation and operational acceptance listed here |

## Mode assessment

Paper remains an observation/model system with an isolated ₹20,000 seed and
the original protection/risk constraints. Offline tests do not establish real
fillability. Live has no verified transport and cannot activate. Independent
Shadow keeps its own journal and notification checkpoint; mirrors remain
non-additive. Research records and playback never appear as realized returns
or update active settings.

## Deployment checks

- Back up database, report archive, API_KEY_PEPPER and FERNET_SALT together.
- Initialize additive tables using the existing application/store initialization.
- Review saved configuration and ranking weights; preserve existing positions,
  stop history, daily-entry use, cooldowns and monthly locks.
- Install the separate notification process only after configuring encrypted
  bot settings and verifying the ten channel permissions.
- Keep original report scheduler/Gmail delivery; the new dispatcher is additional.
- Verify approved exchange calendar, real source timestamps, instrument metadata,
  fees, restart recovery and worker scheduling in extended forward Paper.
- Resolve the recorded Historify timeout with root-cause evidence before release.
- Keep Live blocked until independently verified authentication, reconciliation,
  protective-order ownership, emergency exits, partial fills and deployment
  readiness exist.

Setup details: [DISCORD_INTEGRATION.md](DISCORD_INTEGRATION.md). Exact test
evidence and failures: [ADVANCED_FEATURES_TESTING.md](ADVANCED_FEATURES_TESTING.md).
