# NIFTY ALGO changelog

## 0.6.0 — 2026-11-24 (unreleased)

### Feature

- Complete typed native analysis/execution recording, isolated deterministic
  financial A/B/C replay, immutable multi-session definitions and verified
  explicit recording archive/restore. Unsupported evidence continues to refuse P&L.
- Add authoritative PAPER versus independent Shadow comparisons, non-additive
  mirrors, recorded fill quality, protection coverage and approval-only research
  suggestions with existing ledger drilldowns and private exports.
- Add durable notification heartbeats, provider-bucket scheduling, bounded
  trailing/research digests, definite-dead-letter operator replay and deferred
  ephemeral report commands with verified owned PDF attachments.
- Apply the owner-approved OI cap within the existing volume contribution.
  All five selector weights and risk/strategy parameters remain unchanged.

### Fix

- Correct pytest application/SDK namespace separation while retaining packaged
  and legacy test helpers. Preserve all Python and operating-system CI cells.
- Bound Discord SQLite lock retries cooperatively, isolate runner restoration
  failures, rotate both encrypted Discord columns with their correct keys, and
  exclude private runtime files from ordinary staging and image builds.
- Register direct NIFTY page access, sanitize failure logs and trader messages,
  limit public interactions, and keep spot-cache failures from delaying exits.
  These are unreleased corrections; strategy and Live gates are unchanged.
- See [the compliance record](COMPLIANCE_REMEDIATION.md) for current verification,
  intentional terminology exceptions and the deferred database recommendation.

- Refuse future or corrupt replay evidence, unsupported identities, unobserved
  protection periods and unsafe split boundaries. Preserve unknown financial
  metrics and delivery outcomes instead of substituting zero or retrying blindly.
- Keep notification health reads on one released DB session; isolate provider
  and research work from trading protection. Extend offline regression and CI
  coverage. External feeds, delivery, deployment and forward PAPER remain
  acceptance requirements; no live-readiness claim is made.

## 0.5.0 — 2026-11-23 (unreleased)

### Fix

- Revalidate runner readiness age in status responses and report actual health
  through Discord, including paused/unavailable state, persisted monthly and
  cooldown holds, kill/daily locks and unreconciled accounts without writes.
- Validate every fallback contract against signal side and current metadata;
  allow liquid fallback candidates and recheck quote/price at locked admission.
- Require exit-side depth for the entire selected quantity at BUY fill.
- Persist idempotent critical incidents for unavailable held-position bids while
  retaining protective exit attempts. Include profit-lock transitions, existing
  control events and data warnings in sanitized Discord projections.
- Add corrective regression coverage and replace obsolete v2 risk/window text
  in strategy assumptions. Current verification is recorded separately from
  historical test evidence.

### Feature

- Added risk-approved Decimal weighted contract/quantity proposals, configurable
  weights, explicit missing-Delta coverage and stored scoring explanations.
- Extended owned realized analytics with trade inspection, sampled excursion
  and bounded stop-history evidence, post-exit sampling through effective close,
  and additional performance dimensions without another P&L ledger.
- Added immutable quote-coverage inspection results and receipt-time replay
  controls. Incomplete execution data continues to refuse financial backtests.
- Added a dedicated Discord REST bot, encrypted configuration, signed authorized
  monitoring commands, durable attempts/reminders, independent Gmail fallback
  and a management panel. Delivery uses a separate optional process.
- Added feature architecture, setup, testing and readiness documentation. Live
  transport, full-fidelity execution replay and remaining operational acceptance
  are explicitly unfinished; this version is not a production-readiness claim.

## 0.4.0 — 2026-11-21

### Paper-trading system (Phases 0–7, `feat/nifty-paper-trading-system`)

- Rupee-gated risk: 0–3 lot sizing under a ₹400 planned-loss ceiling and ₹350 minimum modeled net reward; exactly one primary BUY per session (`390abafdd`).
- Profit lock: ₹400 modeled-net activation, ₹350 tick-aligned floor, early-booking discretionary exit (`5bc72b279`).
- Approved NSE calendar import (DRAFT/APPROVED/REJECTED PDF review) and ATM/ITM-only contract selection (`3b0549fe3`).
- Next-session loss cooldown and monthly loss/profit entry locks, latched and restart-safe (`a7da8467a`).
- Hypothetical shadow positions, primary mirrors (non-additive), and bounded research observations (`0271954dc`).
- Paper/Live trading mode with masked broker readiness; Live hard-blocked by a no-transport stub reporting `LIVE_NOT_READY` (`2b5f44a65`), plus workspace panels for locks, calendar, shadow/research and mode (`c47b8462b`).
- Daily, milestone and month-end PDF reports with bounded, idempotent SMTP delivery and resend (`4ff43de2c`).
- Deliberate deviation: `virtual_capital` is ₹20,000, not the spec's ₹2,000 (user-approved; `monthly_loss_limit` stays ₹2,000). See `PAPER_SYSTEM_DESIGN.md` §5.
- Phase 7 prevents automatic resend after a lost SMTP acknowledgement or an
  expired delivery claim. SMTP acceptance remains successful if `QUIT` fails.
  Skipped deliveries and expired-claim recovery record transactional audit events;
  missing SMTP configuration cannot clear an unresolved delivery claim.
- Phase 7 verification: 283 NIFTY backend + 28 neighboring email + 26 workspace
  tests passed; Linux runtime gate 1,456 passed/3 skipped; Ruff, TypeScript and
  production build passed. Earlier Windows email CLI timeout, unsupported installed
  Node and broader frontend failures are recorded in `TESTING.md`.
  Live mode remains blocked pending independent broker verification.

## 0.3.0 — 2026-11-19

### Fix

- Replaced legacy 15% stop/30% target/percentage trail settings with immutable v2 migration, an 8% maximum filled-premium stop, a 1.5-premium-point trail and deterministic 10–15% targets.
- Removed execution receipt-time fallback, hardcoded ticks, invented depth quantity and non-atomic distinct admission. Added final fill validation, durable reservation, monotonic protection, retry/recovery and proportional entry-fee accounting.

- Added fill/cash/quantity reconciliation, confirmed-fill exit coverage, conservative legacy-peak recovery, risk-admission events, and full-ledger performance aggregation.

### Feature

- Added explainable five-indicator research strength, full dated native PCR integration, source-preserving cache fields and named native scheduler jobs for isolated paper automation.
- Exposed readiness-gated controls, indicator contributions, protection, exit state and journal context in the existing workspace/API. Added signed-session Socket.IO subscriptions and reconnect/listener cleanup.
- Added deterministic offline lifecycle, concurrency, migration and failure regressions. Real-market and Linux worker evidence remain pending.

## 0.2.0 — 2026-11-19

### Paper execution (Phase 6)

- Added an isolated per-user paper ledger (accounts, orders, positions, trades, funds) in `database/nifty_algo_db.py`, kept separate from the shared Sandbox account.
- Implemented `services/nifty_algo/paper_executor.py`: fills only against observed bid/ask depth with configured latency and TTL expiry, deterministic charge schedule, and day-boundary accounting; the generic `submit` boundary stays closed (`PaperExecutionUnavailable`).
- Order admission is idempotent by `intent_id` — durable duplicates return the persisted order before risk re-evaluation; entry checks run through the shared `services/risk` manager; uncovered sells are refused.
- Recovery/reconciliation restores account state from durable rows, expires dead intents and re-marks the reconciled flag; daily rollover resets realized-day counters.
- Wired `/orders`, `/positions`, `/trades` and `/performance` endpoints to the real account; lazy expiry accepts an explicit `as_of` timestamp for deterministic reads.
- 15 dedicated executor tests pass; the full NIFTY suite is 78 green.

## 0.1.0 — 2026-11-19

### Documentation

- Inventoried 98 legacy tracked files and mapped reuse into the existing OpenAlgo fork.
- Audited mutable Analyzer routing, native per-run dispatch, fill assumptions and shared paper-account behavior.
- Established the feature design, safety boundary and phase acceptance tracker.
