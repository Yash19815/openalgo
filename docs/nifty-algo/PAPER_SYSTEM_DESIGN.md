# NIFTY paper-trading system: Phase 0 audit and design

Baseline commit `0d367366331b6c69a8fc92cdfd6f1e4503205679`, branch
`feat/nifty-paper-trading-system`. This document is the authoritative design for
the eight implementation phases. Each phase lands as one focused commit.

## 1. Audit findings

Reused as-is (verified by reading the code):

- `database/nifty_algo_db.py` `NiftyStore`: isolated Decimal ledger
  (`nifty_algo_account`), idempotent intent admission keyed by `intent_id`,
  per-user transaction lock (`_lock`), runner lease (`nifty_algo_runner`),
  depth-consumption ledger, protection payload table, reconciliation checks.
  Tables are created with `Base.metadata.create_all`; there is no Alembic.
  Schema evolution is therefore additive: new tables, plus explicit nullable
  column additions guarded by an inspector check.
- `services/nifty_algo/paper_executor.py` `NiftyPaperExecutor`: depth-only fills,
  configured cost schedule `_charges`, latency and TTL.
- `services/nifty_algo/protection.py`: pure Decimal option-premium protection
  (initial 8% stop, 10-15% confidence target, 1.5-point trail).
- `services/nifty_algo/runner.py` `NiftyRunner`: scheduler-attached, leased,
  one assessment per completed five-minute boundary, no retroactive signals.
- `database/market_calendar_db.py`: holidays, special sessions,
  `get_effective_session_window`.
- `utils/email_utils.py`: SMTP settings, TLS context, `send_email` (no
  attachment support yet).
- Broker configuration and credentials: `blueprints/broker_config.py`,
  `blueprints/broker_credentials.py`, `database/auth_db.py`.

Mismatches against the approved specification:

| Item | Current | Required |
| --- | --- | --- |
| `virtual_capital` | 100000 | 20000 for new accounts only |
| `max_lots` | 1 (le 10) | up to 3 |
| `max_daily_entries` | 3 | exactly 1 |
| `risk_fraction` | 0.5% of equity | replaced by a 400 rupee planned-loss ceiling |
| `entry_after` | 09:30 | 10:30 |
| Net reward gate | absent | at least 350 rupees at the unmodified target |
| Profit lock | absent | 400 rupee activation, 350 rupee modeled floor |
| Pending BUY at 14:45 | TTL only | cannot fill at or after 14:45 |
| Monthly limits, cooldown, shadow, research, reports, Paper/Live mode | absent | required |

## 2. Risk-core exception

The shared `services/risk/` core is float-based and serves scalping,
`/strategy` and Flow. NIFTY keeps its intentionally isolated, pure Decimal
evaluator in `services/nifty_algo/protection.py`. All new stop, floor, trail and
early-booking formulas live there as pure functions with no I/O. The runner,
executor, database layer and frontend never recompute them. The shared core and
its TypeScript copy are unchanged. This exception is recorded in `CLAUDE.md`,
`OPENALGO_REUSE_AUDIT.md` and `ARCHITECTURE.md`.

## 3. Configuration (strategy_version 3.0.0)

New and changed `StrategyConfig` fields:

- `virtual_capital = 20000` (applies only when no `nifty_algo_account` row exists).
- `max_lots = 3`, bounded `1..3`.
- `max_daily_entries = 1`, bounded `1..1`.
- `entry_after = 10:30`, `entry_before = 14:45`, `exit_by = 15:10`,
  `shadow_entry_after = 09:15`.
- `max_planned_loss = 400`, `min_projected_net_reward = 350`,
  `planned_loss_buffer = 10` (rupees per trade; a documented, configurable hypothesis).
- `profit_lock_activation_net = 400`, `profit_lock_floor_net = 350`,
  `early_booking_min_net = 300`.
- `monthly_loss_limit = 2000`, `monthly_profit_target: Decimal | None = None`.
- `lot_score_thresholds = (0, 40, 70)`: a research score at or above element `i`
  permits `i + 1` lots. Configurable, testable hypothesis, never a probability.
- `risk_fraction` removed.

`migrate_configuration` gains a 2.0.0 to 3.0.0 step that drops `risk_fraction`,
forces the mandatory values above and keeps the remaining user values. Migration
pauses entries, as the existing 1.0.0 step does. It never touches
`nifty_algo_account`, so a funded account keeps its equity.

Changing `monthly_profit_target` is recorded as an audit event with previous
value, new value and timestamp. It never clears a latched lock.

## 4. Phase design

### Phase 1: account, risk and order admission

- Pure sizing in `risk_manager.plan_entry(account, candidates, config, confidence)`.
  For each candidate contract (ordered by the resolver) and each lot count from
  `min(max_lots, score-permitted lots)` down to 1, compute with Decimal:
  entry price `ask + slippage_ticks * tick`; initial stop from `protection`;
  modeled stop exit `stop - slippage_ticks * tick`; planned loss
  `(entry - stop_exit) * qty + buy charges + sell charges at stop_exit + buffer`;
  projected net reward `(target - entry) * qty - buy charges - sell charges at target`;
  cash `entry * qty + buy charges`; displayed ask size. Choose the first
  candidate/lots combination passing every gate. Otherwise return ZERO with
  per-candidate rejection reasons (`PLANNED_LOSS_EXCEEDS_400`,
  `NET_REWARD_BELOW_350`, `INSUFFICIENT_FUNDS`, `INSUFFICIENT_DEPTH`,
  `SCORE_LOT_LIMIT`). The target is never raised and the stop never widened or
  tightened to make a size pass.
- `Resolver.candidates(...)` returns the ordered suitable contracts; `resolve`
  keeps its current behaviour by returning the first.
- Admission and fill (`admit_order`, `fill`) replace the equity-fraction checks
  with `reserved_risk <= max_planned_loss`.
- One primary BUY per IST trading session, enforced in the database under the
  user lock: a BUY is refused when any primary BUY today is PENDING or has any
  filled quantity. Expired or rejected BUYs with zero fill do not consume the
  allowance. The counter increments on the first fill, including a partial fill.
- BUY `expires_at` is `min(now + ttl, 14:45 IST today)`; a fill at or after
  14:45 is refused with `ENTRY_CUTOFF`.

### Phase 2: protection

Pure functions in `protection.py`:

- `estimated_net_pnl(entry_price, quantity, bid, entry_fees, sell_charges_fn, slippage)`
  values the position at `bid - slippage_ticks * tick` after the remaining entry
  fees and modeled sell charges.
- `profit_floor_stop(entry_price, quantity, entry_fees, floor_net, config, tick)`
  returns the lowest tick-valid price whose modeled exit (minus slippage, minus
  sell charges at that price) leaves at least the floor. It rounds up to a tick.
- `observe_bid` gains: activation at estimated net >= 400 sets
  `profit_lock_active`, `profit_floor_stop`, and records the before/after stop,
  bid, bid depth, estimated net and cost model; the 1.5-point trail continues
  independently; the effective stop is `max(initial, trailing, floor)` and is
  never lowered, including values reloaded after restart.
- `early_booking_exit(...)` requests a discretionary exit only when estimated net
  >= 300 and both a premium deterioration and a fresh completed-candle momentum
  weakening are present. It is ignored once the profit lock is active, and it
  never gates mandatory exits.
- If the floor stop is at or above the current bid, the evaluator returns
  `PROFIT_FLOOR_UNREPRESENTABLE` and requests an immediate protective exit
  instead of claiming a lock.
- The executor persists a `PROFIT_LOCK_ACTIVATED` event once per position.

### Phase 3: calendar, cooldown and monthly limits

- New tables `nifty_algo_calendar_version` (year, segment, source filename,
  sha256, uploader, status DRAFT/APPROVED/REJECTED/SUPERSEDED, approved_at,
  entries JSON, audit JSON). Uploads are size-limited, PDF magic-checked, parsed
  with pypdf, and never auto-approved. Ambiguous rows block approval until
  corrected. Approval writes NFO holidays through the existing
  `market_calendar_db` helpers and marks the version authoritative for the year,
  so a legacy seed cannot override it.
- Trading is blocked with `CALENDAR_UNAPPROVED` when the current year has no
  approved NFO version.
- `nifty_algo_cooldown` (loss session date, cooldown session date, loss event id).
  At session finalisation, a negative primary realized net schedules the next
  eligible normal NFO session. Weekends, holidays and special sessions never
  consume it. Approving a revised calendar recomputes future cooldown dates.
- `nifty_algo_month` (IST month, realized net, loss_locked_at, profit_locked_at,
  milestone report ids). Locks latch for the month, survive restarts, mode
  changes and target edits, and reset only on a new month. Equity never resets.
- Implementation decisions (Phase 3b):
  - A session is final when the single primary position is fully flat. It is a
    loss when the summed net of that entry's trades is below zero (exactly zero
    is not a loss). The loss date is the entry's IST date.
  - Calendar lookups run outside the user lock. A new cooldown is stored with no
    date and resolved after the SELL fill, at admission, or at calendar approval.
    An undated cooldown refuses entries with `COOLDOWN_UNRESOLVED`.
  - Days between the loss session and the cooldown session are blocked as well.
    Recompute only touches today's and future cooldowns and never moves one
    before today.
  - The monthly loss lock sets when realized net is negative and the loss is at
    least `monthly_loss_limit`. A trade counts in the IST month of its exit fill;
    a new month row is first backfilled from the trade journal.
  - Locks only refuse new entries; they never pause the strategy or block exits.
  - Refusal codes: `COOLDOWN_ACTIVE`, `COOLDOWN_UNRESOLVED`, `MONTHLY_LOSS_LOCK`,
    `MONTHLY_PROFIT_LOCK`. Checks run in the runner before contract resolution,
    in the executor before sizing, and authoritatively in `admit_order` and at
    BUY fill under the user lock.

### Phase 4: shadow and research

- `nifty_algo_shadow_position` and `nifty_algo_shadow_event` with their own
  hypothetical ledger. At most one active shadow row, mirrors included.
  Independent entries from 09:15 to before 14:45, not during cooldown, holiday
  or closure. A primary fill ends an active independent shadow as
  `PREEMPTED_BY_ACTUAL_MIRROR` and opens a mirror linked by entry order id.
  Mirror P&L is flagged non-additive.
- `nifty_algo_opportunity` keyed by a stable id of candle end, direction and
  configuration id. Observation steps run inside the existing scheduler tick and
  stop at the first terminal threshold, 45 minutes, or 15:10.
- Shadow and research code never imports or calls any order placement API.
- Implementation decisions (Phase 4):
  - One active shadow is enforced twice: a check under the user lock and a
    `UNIQUE(user_id, active_slot)` constraint, where `active_slot` is 1 while
    active and NULL once ended (portable; NULLs never collide). `shadow_key`
    (`independent:<decision_id>` or `mirror:<entry_order_id>`) makes each
    signal and each primary entry open at most once.
  - Independent entries need an eligible decision on verified data, an
    approved `TRADING` session inside its window, 09:15 to before 14:45, no
    cooldown, no active shadow, and no primary position or pending primary BUY.
    They are not bound to the one-per-session primary allowance. Monthly locks
    guard primary capital only and do not block shadows.
  - The shadow entry runs after the primary attempt in the same tick, so a
    primary BUY admitted that tick takes precedence and is mirrored instead.
  - Shadow sizing is `plan_entry` against the hypothetical ledger: the
    configured `virtual_capital` plus realized net of independent shadows only.
    The hypothetical entry fills at ask plus slippage on the observed quote.
  - Mirror sync runs in the 1-second protection job after primary fills. A
    preempted shadow is valued at its last observed bid with the modeled exit;
    without one its net is NULL (`UNAVAILABLE`). The mirror copies the primary
    entry and protection, never evaluates exits itself, and closes from the
    primary trade journal (`PRIMARY_JOURNAL`) with `additive = 0`.
  - Shadow exits use `observe_bid`, `modeled_exit_net` and the shared
    `mandatory_exit_reason` (max hold, 15:10 / session-end square-off), which
    the primary `monitor_exits` now calls too. A latched exit closes on a bid
    that covers the quantity; after the session ends without one, the shadow
    closes at its last observed bid (`LAST_BID`).
  - Opportunities are recorded for eligible decisions whose candle ends before
    `exit_by` (15:10). Steps use completed 5-minute closes of the same analysis
    future. Terminal thresholds are one entry-candle ATR favorable or adverse
    (adverse checked first), a documented hypothesis in `research.py`. The
    deadline is `min(candle end + 45 minutes, 15:10)`; the protection job
    closes overdue rows even without a new candle.
  - Read-only API: `GET /api/nifty-algo/shadow` and
    `GET /api/nifty-algo/research/opportunities`.

### Phase 5: trading modes and broker settings

- `nifty_algo_mode` (mode PAPER/LIVE, revision, history). Readiness codes include
  `API_MISSING`, `AUTH_EXPIRED`, `BROKER_UNREACHABLE`, `LIVE_NOT_READY`,
  `OPEN_EXPOSURE`, `ACK_REQUIRED`. The live adapter is a stub that always
  reports `LIVE_NOT_READY`, so Live cannot activate in this release.
- Broker status is read from existing OpenAlgo auth and broker configuration,
  with secrets masked. No second credential store.
- Implementation decisions (Phase 5):
  - `nifty_algo_mode` (user, mode, revision, history JSON capped at the last 50
    changes, updated_at) is created by `create_all`. New users get a PAPER row in
    `ensure_user`; users that predate the table get one on first read. Every
    change is a `mode_changed` event and every refusal a `mode_change_refused`
    event (previous, requested, actor, time, exposure, masked readiness snapshot).
  - `services/nifty_algo/trading_mode.py` holds the pure evaluator. Live codes,
    in order: `BROKER_STATUS_UNAVAILABLE`, `API_MISSING`, `AUTH_EXPIRED`,
    `BROKER_UNREACHABLE`, `LIVE_NOT_READY`, `MARKET_DATA_UNVERIFIED`,
    `PROTECTIVE_ORDERS_UNVERIFIED`, `FILL_RECONCILIATION_UNVERIFIED`,
    `STATIC_IP_UNVERIFIED`, `OPEN_EXPOSURE`, `ACK_REQUIRED`. The live adapter
    stub never probes the broker, so reachability counts as unverified and
    `BROKER_UNREACHABLE` is always present. `LIVE_NOT_READY` is added by the
    evaluator and again by `NiftyStore.change_mode` whatever the evaluator says.
  - A mode request is decided once under the user lock: compare-and-set on the
    mode revision (a stale one is `REVISION_CONFLICT`, 409), exposure read in
    the same transaction, then the update. Exposure is primary only: held
    positions and PENDING intents not yet past expiry. Shadows are hypothetical.
  - A request for the current mode is a no-op that succeeds without bumping the
    revision. A real switch with open exposure is refused with `OPEN_EXPOSURE`.
    `ACK_REQUIRED` clears only for a JSON boolean `true`.
  - Broker status reads the `auth` row (token presence and `is_revoked`, never
    decrypted), `live_broker()` for a session from the current trading day,
    `utils.broker_keys.resolve` for key presence and source, and
    `auth_db.get_api_key` for the OpenAlgo API key. It starts no login and calls
    no broker. Masking is one function (`_masked`): only booleans, the broker id
    and the key source leave it, never a character or the length of a secret.
    A failed read returns `BROKER_STATUS_UNAVAILABLE` and logs the exception
    type only.
  - The paper executor refuses BUY intents when the stored mode is not PAPER
    (the stub's `submit` raises `LIVE_NOT_READY`; no transport exists), the
    runner sees the same code from `entry_lock_reasons`, and `admit_order` and
    BUY fills re-check it under the user lock. Exits of existing paper positions
    stay simulated in any mode, so protection never stops.
  - API: `GET/POST /api/nifty-algo/mode` (session and global CSRF). A refusal is
    409 `MODE_CHANGE_REFUSED` with `reasons`. `/risk` keeps its shape and gains
    `trading_mode` (mode, revision, `live_available: false`, `live_readiness`).

### Phase 6: reports and SMTP

- ReportLab daily, milestone and month-end PDFs written under `db/nifty_reports/`.
- `send_email` gains an optional `attachments` argument; existing callers are
  unchanged.
- `nifty_algo_report` stores kind, period key (unique per kind), path, sha256,
  generation status and delivery attempts. Delivery is bounded, retried from the
  scheduler, and duplicate-safe by the unique period key.

### Phase 7: hardening

Restart tests, a full NIFTY regression run, the production frontend build, the
fd-audit procedure, and documentation of the remaining external dependencies.
