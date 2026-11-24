# NIFTY Advanced Features Work Plan

## Scope and gates

Extend the completed NIFTY implementation rather than replace its strategy,
ledger, protection evaluator, broker ownership, calendar or reporting services.
The user's full specification is in the conversation. Live must stay
hard-blocked until independently verified broker capabilities exist.

## Baseline

- Workspace: D:/DATA/Documents(old)/projects/Main_Projects/openalgo-fork/openalgo
- Branch: feat/nifty-paper-trading-system
- Inspected HEAD and fetched origin branch match:
  84b899ab9d91eaba4a12decff2c1474a29bb5d99.
- Working tree was clean on entry. User confirms baseline work is ready.
- Do not commit, push, deploy, send external messages or place real orders.
- No subagents: user has not requested them.

## Phases

0. Complete: compatibility audit, targeted source inspection and baseline tests
   (324 passed; see progress.md and the audit for the Windows ACL retry).
1. Complete: additive durable safety/events/outbox foundation; preserve accounting.
2. Implemented; current acceptance being verified: weighted ATM/ITM contract/lot
   proposals, configurable weights, frozen evidence and integrated UI. Existing
   atomic admission/fill gates remain authoritative. Real-feed evidence pending.
3. Complete (offline integration): Safety Center states, audited recovery,
   explicit manual resume, incidents and controls.
4. IN PROGRESS: authoritative analytics, drill-downs, exit research and report extension.
   Authoritative snapshots, realized charts, daily groups, fill pagination and
   PDF reporting now pass offline tests (444 backend; 49 feature frontend).
   Exit research and remaining acceptance checks are not complete.
5. IN PROGRESS: bounded forward recorder, causal replay, immutable experiments and UI.
   Authenticated recording controls, durable sample identities and strict native
   depth reads, server-frozen capture and the lazy-loaded recording UI are wired.
   Immutable experiment definitions now have authenticated controls and
   lazy-loaded UI with isolated browser proof. Causal option execution replay,
   experiment runs/results and exit studies remain incomplete.
   See the canonical integration audit for checkpoint-specific
   verification and evidence limitations.
6. IN PROGRESS: dedicated Discord REST bot, ten ID destinations, encrypted settings,
   signed authorized read-only commands/acknowledgement, durable delivery and
   escalation, separate Shadow digest, independent Gmail fallback and UI added.
   Production latency/provider proof and documented remaining software gaps persist.
7. IN PROGRESS: corrected full NIFTY gates pass 744 tests on each OS; the latest
   37 Discord tests pass on each OS, including four cases added after full gates.
   Frontend 79 tests/build/browser checks pass. Shadow boundary tests are unchanged.
   Existing Historify timeout and production/runtime acceptance remain unresolved.
8. IN PROGRESS: requested architecture, feature, test, readiness and setup files
   now exist and measured continuation evidence is synchronized. Readiness lists
   remaining software, unavailable execution evidence and operational blockers.

## Constraints

- Create docs/nifty-algo/FIVE_FEATURES_INTEGRATION_AUDIT.md before feature code.
- Existing pure Decimal protection.py is the NIFTY-specific risk authority.
- NiftyStore owns paper accounts, orders, positions, fills and realized results.
- Reuse the host's three APScheduler jobs; keep network/report work off protection.
- All request work must support eventlet, gthread and dev threading.
- SQLite uses the existing engine factory with NullPool and transaction locks.
- No fabricated prices, PCR, Greeks, depth, fills or production performance.
- Experimental/replay settings never update active Paper/Live settings.
- Discord cannot trade, resume, change stops or change settings.
- Critical incidents cannot be disabled; acknowledgement is not resolution.
- Mock tests cannot establish Live readiness.

## Errors and unresolved checks

- Prior thread ran git from parent directory and got "not a git repository".
  Correct workspace now explicitly passed to exec commands.
- Full Linux gthread suite remains required before any commit/PR; Windows skips
  do not prove worker correctness.
- Docker is now available. Container `openalgo-nifty-analytics-runtime` was
   created from the existing local verified-environment image with `--init` and
   `--network none`. Linux source copy passes 444 NIFTY tests and 1,456 worker
   tests, with three documentation skips (latest shell `488b30`, exit 0).
   The first run's check-then-act failure is resolved by recording verified
   transaction locking for three new incident revision updates. No behavioral
   code or gate tests changed to obtain that pass.
- That analytics checkpoint is historical. The latest Linux worker gate has an
  unresolved Historify eventlet child timeout; do not rerun it into green.
  See the canonical integration audit for the named failure and current gates.
- Current selector integration passes 385 offline NIFTY tests, including durable
  evidence, authenticated reads, full identity and locked current-spot admission
  checks, final fill proof and pre-ranking refusal envelopes. The frontend slice
  has 37 passing tests with Biome and TypeScript build-mode checks. Excluded
  metadata evidence is bounded and deterministic. Separate architecture diagrams
  and final Linux/runtime gates remain. Canonical status lives in the integration audit.
