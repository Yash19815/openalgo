"""Focused Windows-safe compliance regressions; no provider or worker runtime."""

import ast
import copy
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from json import dumps
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Blueprint, Flask
from flask_limiter import Limiter
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

import database
from database.nifty_algo_db import NiftyDiscordReportRequest
from services.nifty_algo.discord_bot import DiscordSettings, command_response
from services.nifty_algo.runner import NiftyRunner, restore_runners
from services.nifty_algo.safe_logging import log_failure
from test.test_nifty_algo_discord import APP, KEY, configuration, configured
from test.test_nifty_algo_notification_completion import report_interaction
from test.test_nifty_algo_paper_executor import NOW, USER, buy_intent, executor, running
from test.test_nifty_algo_safety_center import store as store


def test_report_lock_deadline_rolls_back_then_retry_deduplicates(store):
    configured(store)
    settings = DiscordSettings.model_validate(configuration())
    interaction = report_interaction()
    # A second connection owns the writer. The request must yield/retry within
    # its budget, rather than silently reduce the normal ledger lock budget.
    import time

    before = time.monotonic()
    with store.engine.begin() as holder:
        holder.exec_driver_sql("UPDATE nifty_algo_state SET revision=revision")
        with pytest.raises(OperationalError):
            store.defer_discord_report(USER, settings, interaction, "daily", NOW)
    assert time.monotonic() - before < 2.5
    assert database.LOCK_RETRY_BUDGET_S == 15.0
    for _ in range(2):
        assert store.defer_discord_report(USER, settings, interaction, "daily", NOW) == {
            "type": 5,
            "data": {"flags": 64},
        }
    with store.sessions() as db:
        assert db.scalar(select(func.count()).select_from(NiftyDiscordReportRequest)) == 1


def test_retry_deadline_is_nested_and_does_not_escape_its_context(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(
        database,
        "time",
        SimpleNamespace(
            monotonic=lambda: clock[0], sleep=lambda delay: clock.__setitem__(0, clock[0] + delay)
        ),
    )

    def locked():
        raise sqlite3.OperationalError("database is locked")

    with database.sqlite_lock_deadline(0.1), database.sqlite_lock_deadline(10):
        with pytest.raises(sqlite3.OperationalError):
            database._retrying(locked)
    assert clock[0] < 0.2
    start = clock[0]
    with pytest.raises(sqlite3.OperationalError):
        database._retrying(locked)
    assert clock[0] - start >= 15


@pytest.mark.parametrize("phase", ["bootstrap", "assessment"])
def test_pipeline_failures_keep_stable_public_code_and_protected_details(store, monkeypatch, phase):
    failure = Mock(side_effect=KeyError("synthetic-private-provider-value"))
    runner = NiftyRunner(
        store, USER, clock=lambda: NOW, assessment=failure if phase == "assessment" else None
    )
    if phase == "bootstrap":
        monkeypatch.setattr(runner, "_native_feed", failure)
    assert runner.evaluate(NOW) is None
    assert runner.last_issue == "DATA_PIPELINE_UNAVAILABLE" and not runner.ready
    events = dumps(store.events(USER))
    assert "KeyError" not in events and "synthetic-private-provider-value" not in events


class Scheduler:
    def __init__(self, fail_user=None):
        self.jobs = {}
        self.fail_prefix = (
            "nifty-paper:" + sha256(fail_user.encode()).hexdigest()[:24] if fail_user else None
        )

    def add_job(self, method, trigger, **kwargs):
        if kwargs["id"] == str(self.fail_prefix) + ":entries":
            raise RuntimeError("synthetic credential must stay private")
        self.jobs[kwargs["id"]] = method

    def remove_job(self, job_id):
        self.jobs.pop(job_id)

    def get_job(self, job_id):
        return self.jobs.get(job_id)


def test_manual_reattach_after_global_restore_failure_requires_fresh_local_readiness(
    store, monkeypatch
):
    from blueprints.nifty_algo import _runner_status

    app = Flask(__name__)
    app.extensions["nifty_algo_store"] = store
    app.extensions["nifty_algo_restore_unavailable"] = True
    monkeypatch.setattr(
        store, "runner_status", lambda _: {"operational": True, "entries_ready": True}
    )
    with app.app_context():
        assert not _runner_status(USER)["entries_ready"]
        local = SimpleNamespace(closed=False, ready=False, last_issue="WARMUP_REQUIRED")
        app.extensions["nifty_algo_runners"] = {USER: local}
        assert _runner_status(USER)["reason"] == "WARMUP_REQUIRED"
        assert not _runner_status(USER)["entries_ready"]
        local.ready = True
        assert _runner_status(USER)["entries_ready"]
        assert not _runner_status("other-owner")["entries_ready"]


def test_partial_restore_keeps_positions_and_other_users_then_recovers_once(store, monkeypatch):
    import utils.shutdown
    from blueprints.nifty_algo import _runner_status

    monkeypatch.setattr(utils.shutdown, "register_shutdown_hook", Mock())
    paper = executor(store)
    running(store)
    paper.admit(buy_intent(), NOW)
    paper.market_data.stamp = NOW + timedelta(seconds=1)
    paper.process(paper.market_data.stamp)
    positions = store.positions(USER)
    assert positions
    store.ensure_user("other-owner")
    app = Flask(__name__)
    app.extensions["nifty_algo_store"] = store
    scheduler = Scheduler(fail_user=USER)
    assert restore_runners(app, scheduler) == {"restored": 1, "failed": 1}
    assert len(scheduler.jobs) == 4
    assert store.positions(USER) == positions and not store.trades(USER)
    with app.app_context():
        assert _runner_status(USER)["entries_ready"] is False
        assert _runner_status(USER)["reason"] == "RUNNER_RESTORE_FAILED"
    scheduler.fail_prefix = None
    assert restore_runners(app, scheduler) == {"restored": 2, "failed": 0}
    restored = app.extensions["nifty_algo_runners"][USER]
    assert not restored.ready and not restored.recovery_complete
    restored.executor = paper
    restored.protect(NOW + timedelta(seconds=2))
    assert restored.recovery_complete and not restored.ready
    assert store.positions(USER) and not store.trades(USER)
    assert restore_runners(app, scheduler) == {"restored": 2, "failed": 0}
    assert app.extensions["nifty_algo_runners"][USER] is restored
    assert len(scheduler.jobs) == 8 and len(store.orders(USER, now=NOW)) == 1


@pytest.mark.parametrize("failed_subsystem", ["python", "nifty"])
def test_actual_startup_blocks_attribute_failures_independently(failed_subsystem):
    # Execute the actual two startup try blocks, with their imports already
    # resolved to controlled dependencies. Importing app would boot real services.
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    blocks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in ("init_python_strategy", "restore_runners")
            for statement in node.body
            for n in ast.walk(statement)
        ):
            blocks.append(node)
    assert len(blocks) == 2
    blocks.sort(key=lambda node: node.lineno)
    blocks = copy.deepcopy(blocks)
    for node in blocks:
        node.body = [n for n in node.body if not isinstance(n, ast.ImportFrom)]
        for handler in node.handlers:
            handler.body = [n for n in handler.body if not isinstance(n, ast.ImportFrom)]
    initialize, restore = Mock(), Mock()
    (initialize if failed_subsystem == "python" else restore).side_effect = RuntimeError("private")
    logger, failure, app = Mock(), Mock(), Flask(__name__)
    exec(
        compile(ast.Module(body=blocks, type_ignores=[]), "app.py", "exec"),
        {
            "init_python_strategy": initialize,
            "restore_runners": restore,
            "nifty_scheduler": SimpleNamespace(running=True),
            "logger": logger,
            "log_failure": failure,
            "app": app,
        },
    )
    assert restore.call_count == 1
    assert failure.call_count == 1
    assert failure.call_args.args[1] == (
        "Python strategy scheduler initialization"
        if failed_subsystem == "python"
        else "NIFTY runner restoration"
    )


def test_spot_bootstrap_failure_does_not_stop_pending_protective_exit(store, monkeypatch):
    import services.market_data_service

    paper = executor(store)
    market = paper.market_data
    running(store)
    order, _ = paper.admit(buy_intent(), NOW)
    market.stamp = NOW + timedelta(seconds=1)
    paper.process(market.stamp)
    paper.monitor_exits(market.stamp, operator_close=True)
    sell = next(row for row in store.pending_orders(USER) if row["side"] == "SELL")
    # A stale pending BUY may precede a protective SELL. Reuse its valid payload;
    # failing the spot cache must skip that BUY and still process the real exit.
    pending_buy = {**store.order_by_intent(USER, order["intent_id"]), "side": "BUY"}
    pending_buy["eligible_at"] = NOW.isoformat()
    monkeypatch.setattr(store, "pending_orders", lambda _: [pending_buy, sell])
    paper.market_data = None
    monkeypatch.setattr(
        services.market_data_service,
        "get_market_data_service",
        Mock(side_effect=RuntimeError("private bootstrap failure")),
    )
    original_depth = paper._depth
    monkeypatch.setattr(
        paper, "_depth", lambda *args: _cached_depth(paper, market, original_depth, *args)
    )
    market.stamp = NOW + timedelta(seconds=2)
    paper.process(market.stamp)
    assert not store.positions(USER)
    assert store.trades(USER)[0]["reason"] == "OPERATOR_CLOSE"


def _cached_depth(paper, market, original, *args):
    paper.market_data = market
    try:
        return original(*args)
    finally:
        paper.market_data = None


def test_logs_keep_traceback_locations_without_provider_messages_or_chain(caplog):
    logger = logging.getLogger("nifty-compliance")
    secret = "synthetic-secret-response-header-recipient"
    try:
        try:
            raise ValueError(secret)
        except ValueError as cause:
            raise RuntimeError(secret) from cause
    except RuntimeError as error:
        with caplog.at_level(logging.ERROR, logger=logger.name):
            log_failure(logger, "Mock provider", error)
    assert secret not in caplog.text
    assert "Mock provider failed (RuntimeError)" in caplog.text
    assert "test_logs_keep_traceback_locations" in caplog.text


def interaction_app(store, monkeypatch):
    import blueprints.nifty_discord as module

    app = Flask(__name__)
    rate_limiter = Limiter(key_func=lambda: "test", storage_uri="memory://")
    monkeypatch.setattr(module, "limiter", rate_limiter)
    bp = Blueprint("compliance_discord", __name__, url_prefix="/api/nifty-algo")
    module.register_discord_routes(bp)
    app.extensions["nifty_algo_store"] = store
    rate_limiter.init_app(app)
    app.register_blueprint(bp)
    return app.test_client()


def test_public_interaction_limits_run_before_owner_lookup(store, monkeypatch):
    lookup = Mock(return_value=None)
    monkeypatch.setattr(store, "discord_owner", lookup)
    client = interaction_app(store, monkeypatch)
    for i in range(20):
        response = client.post(f"/api/nifty-algo/discord/interactions/{i}", data=b"{}")
        assert response.status_code == 401
    assert (
        client.post("/api/nifty-algo/discord/interactions/unknown", data=b"{}").status_code == 429
    )
    assert lookup.call_count == 20


def test_rate_limited_surface_still_verifies_signed_ping(store, monkeypatch):
    configured(store)
    client = interaction_app(store, monkeypatch)
    raw = dumps({"type": 1}).encode()
    timestamp = str(int(datetime.now(UTC).timestamp()))
    headers = {
        "X-Signature-Timestamp": timestamp,
        "X-Signature-Ed25519": KEY.sign(timestamp.encode() + raw).hex(),
    }
    url = f"/api/nifty-algo/discord/interactions/{APP}"
    assert client.post(url, data=raw).status_code == 401
    response = client.post(url, data=raw, headers=headers)
    assert response.status_code == 200 and response.json == {"type": 1}


def test_nifty_browser_route_is_registered_without_changing_client_auth(monkeypatch):
    import blueprints.react_app as module

    app = Flask(__name__)
    monkeypatch.setattr(module, "serve_react_app", lambda: "react-shell")
    app.register_blueprint(module.react_bp)
    for path in ("/nifty-algo", "/nifty-algo/"):
        response = app.test_client().get(path)
        assert response.status_code == 200 and response.text == "react-shell"
