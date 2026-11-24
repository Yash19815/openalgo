# NIFTY Paper Strategy: OpenAlgo Guideline Compliance Audit

Audit date: 2026-11-24
Branch: `feat/nifty-paper-trading-system`
Baseline: `CLAUDE.md` in the repository root.
Method: static review with the repository search tools, plus the repository's own `scripts/gthread_sleep_gate.py`. Findings are appended as they are found, so the sections below are in the order the work was done.

Severity scale: High (breaks an invariant or can cause loss or an outage), Medium (breaks a stated rule, user-visible or operational), Low (convention or hygiene).

## Scope

Reviewed so far:

- `services/nifty_algo/*.py`
- `blueprints/nifty_algo.py`, `blueprints/nifty_discord.py`
- `database/nifty_*.py`
- `frontend/src/features/nifty-algo/*.tsx`
- `app.py` integration points, `blueprints/react_app.py`, `frontend/src/App.tsx`, `frontend/src/config/navigation.ts`
- `upgrade/` migration registry, `scripts/gthread_sleep_reviewed.txt`

## Findings

### F-01 (Medium): `print()` used in both background workers

Files and lines:

- `services/nifty_algo/notification_worker.py:214`
- `services/nifty_algo/replay_worker.py:108`

Rule: "Never `print()`" and "Error logging is always `logger.exception()`". Both workers catch `Exception` in their main loop and print a fixed string. Neither module defines a logger, so no traceback reaches `log/errors.jsonl`, and a failing worker leaves no record of why.

Note: the comment at `notification_worker.py:213` says the fixed string avoids printing credentials or untrusted response bodies. That intent is sound, but `logger.exception()` routes to the JSON handler, which is the sanctioned place for the detail. If the concern is a provider error body carrying a credential, log the exception class and the worker name, not the body.

Fix: add `logger = get_logger(__name__)` and replace each `print(...)` with `logger.exception(...)`.

### F-02 (Medium): `/nifty-algo` is not registered in `blueprints/react_app.py`

Evidence: `frontend/src/App.tsx:198` has the `<Route>` and `frontend/src/config/navigation.ts:53` has the nav entry, but `blueprints/react_app.py` contains no `nifty` route. The Flask blueprint only owns `/api/nifty-algo`.

Rule: "Adding a page: the three registrations". Without the second one, a direct hit or a refresh on `/nifty-algo` by an unauthenticated visitor falls to the 404 handler, which counts against that IP in `Error404Tracker` and can lead to a ban.

Fix: add a `react_bp.route("/nifty-algo", strict_slashes=False)` view that only calls `serve_react_app()`. Register any child path the page owns.

### F-03 (Medium): Banned vocabulary in text a trader reads

- `frontend/src/features/nifty-algo/Workspace.tsx:69`: tab label `'Paper Trading'`.
- `services/nifty_algo/reports.py:218`: report text "Mirror P&L duplicates the primary paper trade and is never added to totals."

Rule: use "Sandbox mode" and "analyzer mode", never "paper trading" or "virtual trading". The exemption for a specification's internal vocabulary covers a spec, not a screen or a generated report.

Fix: rename the tab and the report sentence to the sandbox terms the rest of the platform uses. Internal identifiers such as `paper_executor.py` are not covered by the rule and can stay.

### F-04 (Low): Design mockups contain banned wording

`stitch_nifty_algo_trading_terminal/**/code.html` contains "Kill Switch [ARMED]", "Kill Switch Armed" and "Paper Trading". "Arm", "armed" and "arming" are banned anywhere a trader reads. These files are mockups, not shipped UI, so this only matters if their copy is reused. If they are not needed in the repository, remove them or exclude them from the shipped tree.

## Checked and found compliant

- No `asyncio`, `threading.Lock/RLock/Event/Condition`, `TTLCache` or `StaticPool` in `services/nifty_algo/`. The only `asyncio` hit is a docstring in `discord_bot.py` saying it is not used.
- Worker engines come from `database.engine_factory.create_db_engine`.
- `scripts/gthread_sleep_gate.py`: 763 files scanned, 0 sleeps under a lock or outside an eventlet branch. The `time.sleep(1)` loops in the two workers run in separate CLI processes and hold no request thread.
- `database/` diff adds no `Column` to an existing table, only new `nifty_algo_*` tables created by `Base.metadata.create_all`. No migration script is required for new tables, but any future column added to an existing `nifty_algo_*` table needs a script in `upgrade/` registered in `migrate_all.py`, because `create_all` never alters an existing table.
- Non-ASCII characters in the NIFTY sources are typographic only (ellipsis, dashes, middle dot, rupee-style punctuation, less-or-equal). No emoji.

### F-05 (Medium): NIFTY runner restore shares a try block with the Python strategy scheduler

Location: `app.py:877-885`.

```python
try:
    init_python_strategy()
    from blueprints.python_strategy import SCHEDULER as nifty_scheduler
    from services.nifty_algo.runner import restore_runners

    restore_runners(app, nifty_scheduler)
    logger.debug("Python strategy scheduler initialized")
except Exception as e:
    logger.error(f"Failed to initialize Python strategy scheduler: {e}")
```

Problems:

1. If `init_python_strategy()` raises, `restore_runners` never runs, so the stop and exit job for any stored open NIFTY position is never attached after a restart. The reverse also holds: a failure inside `restore_runners` (for example a database error reading `NiftyState`) is reported as a Python strategy scheduler failure, which sends the operator to the wrong subsystem.
2. `logger.error(f"...{e}")` drops the traceback. The project rule is `logger.exception()`, because that is what lands in `log/errors.jsonl`.
3. `restore_runners` attaches runners one user at a time with no per-user guard, so one bad row stops the rest.

Fix: give NIFTY its own `try/except` with `logger.exception("NIFTY runner restore failed")`, run after (not inside) the Python strategy block, and wrap each `attach_runner` call in `restore_runners` so one user cannot block another.

### F-06 (Medium): Errors swallowed with no log entry

These handlers catch `Exception` and return a fixed result without logging anything, so a Discord or SMTP outage leaves no trace in `log/errors.jsonl`:

- `blueprints/nifty_discord.py:138` (setup action, returns 502)
- `blueprints/nifty_discord.py:220` (interaction handler)
- `services/nifty_algo/discord_bot.py:374` and `:430`
- `services/nifty_algo/notification_worker.py:174` (`_email`)
- `blueprints/nifty_algo.py:39` (`_socket_room`)
- `services/nifty_algo/runner.py:132-133` (`except Exception: pass` around the feed bootstrap in `evaluate`)

In total there are 35 `except Exception` blocks across the NIFTY modules and only 13 logging calls, in 5 files. Six files that catch broadly never import a logger: `database/nifty_algo_db.py`, `services/nifty_algo/calendar_import.py`, `services/nifty_algo/discord_bot.py`, `services/nifty_algo/notification_worker.py`, `services/nifty_algo/replay_worker.py`, `blueprints/nifty_discord.py`.

Rule: "Error logging is always `logger.exception()`". The concern that provider responses can carry credentials is real, so log the exception class and the operation name, not the response body, but do log it. A delivery marked AMBIGUOUS with no log entry cannot be diagnosed later.

### F-07 (Medium): Discord bot token is not in the Fernet rotation lists

`database/nifty_algo_db.py:139` defines `nifty_algo_discord_settings.token_encrypted`, written with `database.auth_db.encrypt_token` (`database/nifty_notifications.py:170`). That is the auth_db Fernet.

The rotation code lists every Fernet column explicitly:

- `utils/env_check.py` `_migrate_fernet_db` targets (line 969) and `_sample_ciphertexts` (line 888)
- `upgrade/rotate_pepper.py` (its `stats` table and per-column loops)

Neither mentions `nifty_algo_discord_settings`. The project rule is that a new encrypted column goes into both rotation lists, otherwise a pepper or salt rotation strands it. After a rotation the stored bot token would no longer decrypt, and Discord notifications and interactions would stop until the trader re-enters it. Line 193 also defines `NiftyDiscordReportRequest.token_encrypted` (String 2048); confirm what it stores and include it if it is Fernet output.

Fix: add `("nifty_algo_discord_settings", "user_id", "token_encrypted")` (and the second column if applicable) to both lists, and add a rotation test. Note `_migrate_fernet_db` uses an integer `id` key for most tables, so the key column choice needs care for a string primary key.

### F-08 (Medium): Exception class names reach the trader

`services/nifty_algo/runner.py:147` builds `last_issue` as `"DATA_PIPELINE_UNAVAILABLE:" + type(exc).__name__`. The runner publishes that string, and the frontend renders it through `codeLabel` in `frontend/src/features/nifty-algo/labels.ts:48`. A code with no label falls back to `code.replaceAll('_', ' ').toLowerCase()`, and `parts.tsx:19` also prints the raw code beside it. A trader would therefore see text such as "data pipeline unavailable:keyerror".

Rule: "Never put a status code, an exception class, a protocol term or an endpoint in front of a user", and name the cause and the next action. Fix: emit the fixed code `DATA_PIPELINE_UNAVAILABLE`, log the class with `logger.exception()`, and add a label that says what to check (for example that the market-data session is connected).

Related, lower severity: `parts.tsx:19` deliberately prints the raw code next to the label. The codes are domain codes rather than HTTP codes, so this is a judgement call, but it is the same pattern the rule warns about. Several API messages are also written for a developer, not a trader, for example "Recording count and SEAL_ONLY required" (`blueprints/nifty_algo.py:557`), "Provide bounded replay clock and cursor" (`:692`), "Native history failed input validation." (`:291`), and `message=str(error)` on the revision conflict handler (`:78`). These should say what the trader should do ("reload the page and try again").

### F-09 (Low): Public interaction endpoint has no rate limit

`blueprints/nifty_discord.py:183` (`/api/nifty-algo/discord/interactions/<application_id>`) is CSRF exempt and unauthenticated by design, protected by Ed25519 signature verification. It reads up to 64 KiB and performs a database lookup (`store().discord_owner(application_id)`) before verifying the signature. Other public-facing blueprints (`chartink.py`, `telegram.py`, `strategy_*.py`) apply `@limiter.limit`. This one does not, so unauthenticated callers can drive database reads and signature checks without a cap. The signature check, size cap and timestamp window are sound; the gap is only the missing limiter.

Fix: add a limiter decorator consistent with the other public endpoints, and verify the 401 path does not reveal whether an `application_id` exists (it currently returns the same body for an unknown id and a bad signature, which is correct).

### F-10 (Info): Frontend design contract

All 50 session-protected routes in `blueprints/nifty_algo.py` carry `@check_session_validity`, and Socket.IO subscription derives the room from the signed session (`_socket_room`), ignoring caller-supplied users. This is compliant. No finding.

## Verified compliant (second pass)

- Runner jobs use APScheduler on the shared `blueprints.python_strategy.SCHEDULER`, publish through `extensions.emit_from_any_thread`, and take a `KeyedLocks` instance for attach. No private worker loop inside the web process.
- The two CLI workers run as separate processes, close the shared httpx client in `finally`, and dispose the engine.
- `discord_bot.py` uses the shared `utils.httpx_client.get_httpx_client()` with a deadline and refuses redirects (per its docstring; confirm the explicit timeout in the next pass).
- Discord token is stored through `encrypt_token`, never returned to the browser (`token_configured` boolean only).

### F-11 (High): C-served SQLite wait inside a web request

Location: `database/nifty_notification_ops.py:314-316`, method `defer_discord_report`.

```python
with self.sessions.begin() as db:
    if db.bind.dialect.name == "sqlite":
        db.connection().exec_driver_sql("PRAGMA busy_timeout=500")
```

`defer_discord_report` is called from `services/nifty_algo/discord_bot.py:528`, which runs inside the `/api/nifty-algo/discord/interactions/<application_id>` request handler, so it executes on the web worker.

Rule: "Never wait on a C-served timeout." `database/__init__.py` sets `BUSY_TIMEOUT_MS = 100` on every SQLite connection and waits for the write lock in Python (`_retrying`, 50 ms polls) so that the eventlet hub can schedule the lock holder. This PRAGMA overrides that per-connection setting with a 500 ms wait inside SQLite's C code. Under the default eventlet worker the whole process is frozen for up to 500 ms, and the greenlet that holds the write lock cannot run to commit, so the wait can only end in "database is locked". The CLAUDE.md measurement is a holder needing 0.5 s producing a 16 s failure. The cost lands on the one path where Discord requires an answer within three seconds.

The PostgreSQL branch (`SET LOCAL lock_timeout = '500ms'`) is fine because the wait happens on the server and the driver yields.

Fix: remove the SQLite PRAGMA and let the cooperative retry in `database/__init__.py` apply. If a shorter overall budget is wanted for this path, bound it in Python (a deadline around the transaction) and answer Discord with the existing "unavailable, use authenticated OpenAlgo Reports" private response when the budget is spent. Add a test in `test/test_sqlite_lock_cooperative.py` style that runs eventlet in a subprocess and asserts on elapsed time and hub liveness.

### F-12 (Low): `_spot` can raise out of the fill loop

Location: `services/nifty_algo/paper_executor.py:497-502`. `_depth` wraps `get_market_data_service()` in a try, but `_spot` calls it outside any try. `process()` calls `_spot` for each BUY fill (line 570), so an exception there ends the loop, and the pending SELL orders later in the same tick are not filled until the next tick. The risk is small (the service getter is a singleton) but the two helpers should behave the same way: return `None` on failure.

## Order-path and risk invariants (reviewed, compliant)

- **Shared risk core.** `services/nifty_algo/` imports nothing from `services/risk/`, and no module under `services/risk`, `services/strategy_module` or the scalping code imports from `services/nifty_algo/`. CLAUDE.md documents `services/nifty_algo/protection.py` as an intentionally isolated, pure Decimal evaluator, and the isolation holds: no third evaluator was added and no NIFTY formula was copied into a shared consumer.
- **Claim under the same lock that checks.** `NiftyStore.admit_order` (`database/nifty_algo_db.py:2208`) takes `_lock` (a no-op `UPDATE` that acquires the SQLite write lock or a PostgreSQL row lock) before it reads the account, positions and pending orders, performs the duplicate-intent check, checks reserved exit quantity, and writes the order, all in one transaction. A unique constraint on `(user_id, intent_id)` backs it and the `IntegrityError` path returns the original order. This is the pattern the invariant asks for.
- **Exit marker before dispatch.** The exit is an admitted `PENDING` order with a deterministic id `exit:{entry_order_id}:{attempts}`; the pending reservation is the marker and is written before any fill. Resolved failed attempts get a new attempt number, so a refused exit does not leave the position skipped.
- **Fill matches the order, not the leg.** `process()` fills by `order["order_id"]` (`store.fill(user_id, order_id, ...)`), and sell coverage comes from confirmed fills (`_remaining_quantity`), not a position counter.
- **No global switch decides the pipe.** The module never calls `place_order_with_auth` and never reads the analyzer toggle, so the `force_live` hazard does not arise. There is no broker order path at all: `trading_mode.LIVE_ADAPTER` is a stub that refuses without transport, and `admit` calls it before any BUY in a non-PAPER mode.
- **No network under the ledger lock.** The `validate_entry` callback runs under the lock but reads only the market-data cache (`get_all_data`) and pure functions. Confirmed by reading `_depth` and `_spot`.
- **Exit protection is independent of entry controls.** `protect` (1 s job) runs reconcile, `monitor_exits` and `process` even when entries are disabled, and `stop`/`kill` only disable entries, as the `attach_runner` docstring says.

## Repository hygiene, tooling and tests

### F-13 (Medium): Generated trader reports are not git-ignored

`NiftyStore` writes report PDFs to `db/nifty_reports` and calendar uploads to `db/nifty_calendar` (`database/nifty_algo_db.py:653-654`). `.gitignore` ignores `*.db`, `db/strategy_encryption.key` and `db/backups/`, but nothing covers these two directories, and `git status` already lists `db/nifty_reports/` as untracked. The PDFs hold a trader's P&L, positions and account figures, so a `git add -A` would commit private trading records.

Fix: add `db/nifty_reports/` and `db/nifty_calendar/` to `.gitignore`. Also confirm that the Docker volume layout persists both directories (the other `db/` files are on the volume; these are new paths), otherwise a container rebuild loses every report and calendar upload while the database rows still point at them. The report download route already returns `REPORT_FILE_UNAVAILABLE` for that case (`blueprints/nifty_algo.py:881`), which is a good fallback but not a substitute for persistence.

### F-14 (Low): Three modified source files fail `ruff format --check`

`uv run ruff check` passes on all NIFTY Python, but `ruff format --check` reports reformatting needed in these working-tree files:

- `services/nifty_algo/analytics_report.py`
- `services/nifty_algo/calendar.py`
- `services/nifty_algo/calendar_import.py`

Twelve test files (`test/test_nifty_algo_analytics*.py`, `_calendar`, `_core`, `_phase1` to `_phase6`, `_safety_center`, `_v2`) also differ from Ruff's output, which suggests the formatter was not run on them in earlier commits either. CLAUDE.md names `uv run ruff format .` as the style gate. Run it once and commit the result separately from functional changes so review diffs stay readable.

Frontend: `npx biome check src/features/nifty-algo` reports 37 files checked and no fixes. Compliant.

### F-15 (Medium): No NIFTY coverage in the gthread or eventlet suites

CLAUDE.md requires every change to be correct under eventlet, gthread and the dev server, and says the `gthread-migration` CI job runs every `test/test_gthread_*.py` file under real gunicorn. None of those files, nor `test/test_eventlet_*.py`, imports or names `nifty_algo`. The 38 `test/test_nifty_algo_*.py` files do include thread-based concurrency tests (seven of them use `Barrier`, `threading.Thread`, `ThreadPoolExecutor` or `contextvars`), which is good, but they run in-process on Windows or Linux with the standard library and say nothing about green threads.

The NIFTY system adds the following runtime surfaces that the existing suites do not exercise:

- APScheduler jobs on the shared `SCHEDULER` doing one-second database work (`protect`), which is where a greenlet-blocking primitive would show up.
- Two CLI worker processes that share the main SQLite file with the web worker.
- The interaction endpoint (F-11) that waits on the write lock inside a request.
- SMTP and PDF generation on the scheduler's worker (`reports.py` header explains the green-thread choice).

Suggested tests (following the style of `test_sqlite_lock_cooperative.py`): an eventlet-subprocess test that holds the write lock from a second connection while `defer_discord_report` runs, and asserts on elapsed time and hub liveness (it fails today, see F-11); and a gthread-marked test that fires `admit_order` for the same intent from many threads behind a barrier and asserts a single order row.

### F-16 (Low): Changelog lives only in the fork's own file

`docs/nifty-algo/CHANGELOG.md` has a 0.6.0 stanza marked unreleased, but `docs/CHANGELOG.md`, the platform changelog that CLAUDE.md requires before anything is published, has no entry for the NIFTY paper system. That is acceptable while the work is on a feature branch, but it must be written before any merge or release, and `docs/INDEX.md` (which already lists the NIFTY documents) is correct. When the entry is written it should say what a reader must act on: new tables created on first start (no migration), the new `/nifty-algo` page, the Discord interaction endpoint and its public URL requirement, the `db/nifty_reports` and `db/nifty_calendar` directories, and that no live order path exists.

### F-17 (Info): Observations that need no change

- File handling in `write_atomic` (`reports.py:88`) closes the descriptor on every error path, writes to a temporary file in the destination directory and uses `os.replace`. Calendar blob writes use exclusive create. No descriptor leak found.
- `NiftyStore` opens every session through `with self.sessions...`, and the new CLI workers dispose their engine in `finally`.
- Edge case worth a test, not a defect: `NiftyStore` calendar upload (`nifty_algo_db.py:719-741`) deletes the blob file when the database insert fails after `created_file = True`. Two concurrent uploads of identical bytes share one blob name; if the first insert fails after the second has already seen `FileExistsError` and committed, the second row would point at a deleted file.
- `start-app.bat` is an untracked Windows convenience script that runs `uv sync` and `uv run app.py`. It follows the uv convention. Decide whether it belongs in the repository.

## Discord integration (reviewed)

### Compliant

- Outbound calls use the shared `utils.httpx_client.get_httpx_client()` with an explicit `timeout=5` and `follow_redirects=False` against a fixed `https://discord.com/api/v10` origin (`services/nifty_algo/discord_bot.py:255-278`). This satisfies the shared-client, explicit-timeout and FD rules.
- Inbound interactions verify Ed25519 over the exact raw bytes before parsing, reject timestamps more than 300 seconds from now, cap the body at 64 KiB, and answer an unknown application id and a bad signature identically (`discord_bot.py:92-104`, `blueprints/nifty_discord.py:183-201`). The CSRF exemption is limited to that one view and registered through `bp.record_once`.
- The bot token is encrypted with the auth_db Fernet, decrypted only on server-side paths, and never returned to the browser.

### F-18 (Low): Outbound User-Agent names a personal GitHub account

`discord_bot.py:273` sends `"OpenAlgoNiftyBot (https://github.com/Yash19815/openalgo, 1)"` to Discord on every request. Discord asks bots to identify themselves with a URL, so a User-Agent is right, but this one hard-codes an individual's fork URL into every self-hosted installation's traffic. Anyone who runs the code (including the upstream project if the feature is merged) would announce that account to Discord. Use the upstream project URL or a neutral constant, and take the version from the platform version file instead of the literal `1`.

### F-19 (Low): Setup validation makes several sequential network calls inside a request

`DiscordREST.validate` issues four GET calls, each with a 5 second timeout, on the web request that handles `/discord/validate` (`discord_bot.py:280-292`). Worst case that is about 20 seconds on one request. It is bounded and runs only when a trader presses a setup button, so it is not a defect, but it holds a worker thread under gthread. Stream admission (`utils/stream_registry.py`) does not apply because the response is not long-lived; consider a lower overall deadline or a single deadline shared across the four calls.

## Shared feed and database placement

### Shared broker feed (reviewed, compliant)

`NiftyRunner._native_feed` (`services/nifty_algo/runner.py:440-540`) borrows the single shared market-data client through `get_websocket_connection`, registers one cache callback, and releases only the subscriptions this runner added (`owned_subscriptions`); borrowed ones are left alone. `close()` unregisters its own callback and does not disconnect the client. A second device logging in therefore cannot be torn down by NIFTY, and NIFTY cannot tear down the feed for others. It also refuses entries when the instrument master's broker differs from the logged-in broker (`INSTRUMENT_MASTER_BROKER_MISMATCH`), which covers a broker switch.

Note, not a defect: `broker_switch.switch_refusal` knows about Live strategy runs, Live OpenScript runs, Python strategies and scalping protection, but not an open NIFTY paper position. Switching brokers while a paper position is open changes the quote source under that position. The position stays protected by the stale-data safety incident, so this is acceptable for a paper system, but it should be documented in `docs/nifty-algo/SAFETY_MODEL.md`.

### F-20 (Medium): About 45 new tables, written every second, live in the main `openalgo.db`

`initialize_nifty(app, main_database_engine)` (`app.py:339`) runs `Base.metadata.create_all` on the main engine, so every `nifty_algo_*` table (state, orders, positions, trades, events, research recordings, reports, Discord outbox, and so on) lives in `openalgo.db`. CLAUDE.md lists six isolated databases and gives sandbox, logs, latency and health each their own file for this reason.

The protection job runs every second per user and each tick calls `claim_runner`, which takes the ledger write lock through an `UPDATE` and renews a lease; the entry and capture jobs add writes every 5 seconds, plus event rows and research recordings that can be large JSON. On SQLite there is one writer at a time, so NIFTY writes compete with the platform's own writes to the same file (auth, settings, strategy and order bookkeeping). With WAL and the cooperative retry in `database/__init__.py` this will not fail, but it adds lock waits to unrelated paths and makes `openalgo.db` grow and checkpoint with research data. Upgrade and backup tooling that targets `openalgo.db` will also now carry trading research data.

Recommendation: give NIFTY its own SQLite file (for example `db/nifty.db`) created through `database.engine_factory.create_db_engine()`, with its own init function, following the `sandbox.db` pattern. This is a design decision rather than a rule breach, because nothing in CLAUDE.md forbids using the main file, but the isolation argument it makes for the other databases applies here, and moving later requires a data migration.

## Test and tool results

| Check | Result |
| --- | --- |
| `uv run pytest test/test_nifty_algo_*.py` (Windows, Python 3.12) | 817 passed in 284.85 s |
| `uv run ruff check` on NIFTY Python and tests | All checks passed |
| `uv run ruff format --check` | 15 files would be reformatted (3 source, 12 test), see F-14 |
| `npx biome check src/features/nifty-algo` | 37 files, no fixes |
| `scripts/gthread_sleep_gate.py` | 0 unreviewed sleeps |
| `test/test_gthread_*.py` under real gunicorn | Not run: needs Linux or WSL, see F-15 |

Note on the first test attempt: the run stopped on `PermissionError` for `C:\Users\hp\AppData\Local\Temp\pytest-of-hp`, an environment problem with the default pytest temp directory, not a code defect. The passing run used `--basetemp` in a writable directory.

## Summary of findings

| ID | Severity | Area | Finding |
| --- | --- | --- | --- |
| F-11 | High | Eventlet safety | `PRAGMA busy_timeout=500` in `defer_discord_report` is a C-served wait on a web request |
| F-01 | Medium | Logging | `print()` in both workers, no logger, no traceback |
| F-02 | Medium | Page registration | `/nifty-algo` missing from `blueprints/react_app.py` |
| F-03 | Medium | Vocabulary | "Paper Trading" tab label and "paper trade" report text |
| F-05 | Medium | Startup | NIFTY runner restore shares a try block with Python strategy init |
| F-06 | Medium | Logging | Seven broad handlers swallow errors with no log entry |
| F-07 | Medium | Secrets | Discord token column missing from Fernet rotation lists |
| F-08 | Medium | Trader messages | Exception class name reaches the trader; several developer-facing messages |
| F-13 | Medium | Repo hygiene | `db/nifty_reports` and `db/nifty_calendar` not git-ignored |
| F-15 | Medium | Test coverage | No gthread or eventlet suite coverage for NIFTY |
| F-20 | Medium | Architecture | About 45 new tables written every second in the main `openalgo.db` |
| F-04 | Low | Vocabulary | "ARMED" and "Paper Trading" in design mockups |
| F-09 | Low | Security | No rate limit on the public interaction endpoint |
| F-12 | Low | Robustness | `_spot` can raise out of the fill loop |
| F-14 | Low | Style | Three source files and twelve tests need `ruff format` |
| F-16 | Low | Docs | No entry in `docs/CHANGELOG.md` yet |
| F-18 | Low | Privacy | Personal GitHub URL in the outbound User-Agent |
| F-19 | Low | Latency | Discord validation makes four sequential 5 s calls in a request |

Recommended order of work: F-11 first (it is the only finding that can freeze the production worker), then F-01, F-02, F-05, F-06 and F-08 together (small, mechanical), then F-07 and F-13 (data-loss and privacy risk), then F-03, F-09, F-12, F-14, F-18, and finally the design and test items F-15, F-20, F-16 before merge.

## What was not covered

The paste that defined this audit ended at "2." with no scope list, so these areas were not reviewed and should be treated as open:

- Line-by-line review of `database/nifty_algo_db.py` (5,252 lines), `services/nifty_algo/execution_replay.py`, `research.py`, `selection_scoring.py` and `native_data.py`. Only the order admission, locking, file-handling and schema parts were read.
- Strategy logic correctness (signal engine, selector scoring, protection formulas). This audit covers platform compliance, not trading logic.
- The `openalgo-docs` diagrams repository, which CLAUDE.md says must be updated for architecture changes. Adding a scheduler job set, two worker processes, a Discord endpoint and about 45 tables is such a change, so the affected diagrams still need checking.
- The `gthread-migration` job on Linux.
- Accessibility and visual checks of the `/nifty-algo` page in a browser.
- Exhaustive review of error-message wording in every frontend panel (F-08 lists the confirmed cases).
