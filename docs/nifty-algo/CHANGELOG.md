# NIFTY ALGO changelog

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
