# Integration Findings

## Latest Continuation Findings — 23 November 2026

- The previous selector checkpoint ranked listed preference; it did not satisfy
  requested weighted contract/quantity scoring. The planner now scores eligible
  pairs with Decimal 30/25/15/20/10 weights and explicit optional-Delta coverage.
- New Shadow notification writes initially violated primary-event isolation.
  Existing static/runtime tests caught both violations. The corrected design
  reads the independent Shadow journal through a separate durable notification
  checkpoint and freezes selector sizing inside Shadow protection records.
- Standalone Gmail fallback needed scoped-session cleanup outside Flask. It now
  releases settings/user sessions before SMTP, including failed lookups.
- Quote evidence does not supply futures/PCR/protection continuity required for
  execution backtests. Replay displays missing evidence and immutable coverage
  results rather than generating financial returns. Integrated signal runs,
  full recording/retention and other documented software gaps remain unfinished.
- Fresh final Linux NIFTY gate passes 744 tests in 249.02 seconds. Newest four
  Discord tests were added afterward; their separate verification is recorded
  in progress/testing docs. Windows gate remains in progress at this checkpoint.
- Combined frontend: 79 tests, TypeScript and production build pass. Visible
  Chrome 1440/375 checks pass with exact UTC requests, uncertain-write lockout,
  zero page errors, zero scoped axe violations and no horizontal overflow.
  Both screenshots were inspected. Mock HTTP only; no real delivery or trading.

## Current Analytics And Runtime Checkpoint

Authoritative PAPER analytics, bounded read-only snapshots, fill-timed realized
curves, IST daily groups, independent fill pagination and authenticated PDF
exports are integrated. Latest Windows evidence: 444 backend tests and 49 feature
frontend tests pass; Biome and TypeScript pass. The canonical integration audit
contains semantics and outstanding acceptance work.

Linux Docker is now available. First worker suite: 1,455 passed, three skipped,
one failed review gate. Reviewed all three flagged safety revision increments:
they run under `_lock(db, user_id)` inside one transaction. Recorded exact
locking reasons; all ten gate tests pass. Fresh Linux NIFTY/full worker runs
completed in shell `488b30`, exit 0: 444 NIFTY tests passed, followed by
1,456 worker tests passed and three documentation skips. Use the newest progress
entry for log paths.
Exit research, causal replay and Discord remain unfinished. Live stays blocked.

## Selector Integration Checkpoint

The selector slice now passes 385 offline NIFTY backend tests and 37 feature UI
tests. Missing spot/master/Greeks/ITM and unexpected validation failures persist
stable refusal envelopes before propagating. The read-only UI shows top-level
refusals and explicit unavailable values. Bounded evidence includes excluded
metadata without granting rank, quote provenance or execution authority.
Canonical verification and outstanding operational gates remain in
`docs/nifty-algo/FIVE_FEATURES_INTEGRATION_AUDIT.md`. Safety recovery is next.

## Verified baseline structure

- services/nifty_algo contains the strategy, native data adapters, calendar,
  resolver, confidence, risk_manager, paper_executor, protection, runner,
  analytics, shadow, research, trading_mode and reports.
- database/nifty_algo_db.py (3768 lines) owns NiftyStore and additive tables,
  per-user write locks, atomic intent admission and fill accounting.
- blueprints/nifty_algo.py uses existing auth/CSRF and app-owned NiftyStore.
- Existing React workspace is frontend/src/features/nifty-algo/Workspace.tsx.
- Runner attaches protection, entry and report jobs to the native IST scheduler,
  uses a durable 30-second owner lease and causal startup/reconnect floor.
- LiveAdapterStub has no broker transport. Preserve it.
- Existing resolver limits nearest eligible expiry and ATM/ITM candidates with
  liquid() checks. DELTA mode currently requires Greeks.
- StrategyConfig v3.1.0 enforces 20000 seed, 400 planned loss, 350 minimum reward,
  one entry/day, 0-3 lots, 10:30-14:45 entry, 15:10 exit, 45-minute hold,
  1.5-point trailing and 400 activation / 350 profit floor.
- Approved strategy documentation has stale v2 statements (09:30, one lot,
  three entries and 0.5% equity risk); actual config is v3.1.0. Audit must
  distinguish documentation drift from actual strategy behavior.
- Implementation has advanced beyond this initial inspection. Current status
  and safeguards are in docs/nifty-algo/FIVE_FEATURES_INTEGRATION_AUDIT.md.

## Reuse boundaries

- protection.py is the only NIFTY protection evaluator. CLAUDE.md explicitly
  permits this isolated Decimal evaluator but forbids a third evaluator.
- Existing report service has deterministic PDFs, durable delivery claims,
  uncertain-send handling and Gmail SMTP. Extend, do not replace.
- Existing NiftyEvent is durable but lacks full envelope/checkpoint/outbox support.
- Research already tracks session-close opportunities; verify exact behavior
  before extending exit effectiveness.

## Source-reading progress

Read docs/INDEX.md, baseline ARCHITECTURE.md, READINESS_REPORT.md,
STRATEGY_ASSUMPTIONS.md, config.py, models.py, most contract_resolver.py and
assessment.py. Large combined command output was truncated; re-read targeted
sections of risk_manager, runner, executor and store before editing them.
