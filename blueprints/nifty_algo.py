"""Authenticated feature API. Order admission remains closed until ready."""

from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from io import BytesIO
from json import dumps, loads
from re import fullmatch
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request, send_file, session
from flask_socketio import join_room, leave_room
from pydantic import ValidationError
from werkzeug.exceptions import RequestEntityTooLarge

from database.nifty_algo_db import NiftyStore, StateConflict
from extensions import socketio
from services.nifty_algo import calendar as nifty_calendar
from services.nifty_algo.analytics_report import analytics_pdf
from services.nifty_algo.config import StrategyConfig, active_configuration
from services.nifty_algo.ledger_analytics import AnalyticsDataError
from services.nifty_algo.paper_executor import NiftyPaperExecutor
from services.nifty_algo.safe_logging import log_failure
from utils.logging import get_logger
from utils.session import check_session_validity

logger = get_logger(__name__)
nifty_algo_bp = Blueprint("nifty_algo", __name__, url_prefix="/api/nifty-algo")

from blueprints.nifty_discord import register_discord_routes

register_discord_routes(nifty_algo_bp)


def _socket_room():
    from utils.session import is_session_valid

    try:
        user = session.get("user")
        return f"nifty_algo:{user}" if user and is_session_valid() else None
    except Exception as error:
        log_failure(logger, "NIFTY socket session validation", error)
        return None


@socketio.on("nifty_algo_subscribe")
def subscribe_updates(data=None):
    """The signed session determines ownership; caller-supplied users are ignored."""
    room = _socket_room()
    if room is None:
        return {"status": "error", "message": "Not authenticated"}
    join_room(room)
    return {"status": "success"}


@socketio.on("nifty_algo_unsubscribe")
def unsubscribe_updates(data=None):
    room = _socket_room()
    if room is None:
        return {"status": "error", "message": "Not authenticated"}
    leave_room(room)
    return {"status": "success"}


def initialize_nifty(app, engine):
    store = NiftyStore(engine)
    store.initialize()
    app.extensions["nifty_algo_store"] = store


def store():
    return current_app.extensions["nifty_algo_store"]


def _runner_status(user_id):
    local = current_app.extensions.get("nifty_algo_runners", {}).get(user_id)
    restore_failed = current_app.extensions.get(
        "nifty_algo_restore_unavailable"
    ) or user_id in current_app.extensions.get("nifty_algo_restore_failed", ())
    if restore_failed and (local is None or local.closed):
        return {"operational": False, "entries_ready": False, "reason": "RUNNER_RESTORE_FAILED"}
    status = store().runner_status(user_id)
    if local is not None and (local.closed or not local.ready):
        # A manually reattached monitor must warm up even if a previous
        # process's lease still carries fresh entry-readiness evidence.
        return {**status, "entries_ready": False, "reason": local.last_issue}
    return status


def success(data):
    return jsonify(status="success", data=data)


@nifty_algo_bp.errorhandler(StateConflict)
def conflict(error):
    return jsonify(
        status="error",
        code="REVISION_CONFLICT",
        message="Information changed. Reload the page and try again.",
    ), 409


@nifty_algo_bp.errorhandler(ValidationError)
def invalid_configuration(error):
    # Validation errors can contain arbitrary caller input. Return field locations only.
    return jsonify(
        status="error",
        code="INVALID_CONFIGURATION",
        message="Invalid strategy configuration",
        fields=[list(item["loc"]) for item in error.errors()],
    ), 400


@nifty_algo_bp.route("/status")
@check_session_validity
def status():
    state = store().read(session["user"])
    state.pop("configuration")
    runner = _runner_status(session["user"])
    safety = store().safety_status(session["user"])
    ready = bool(
        runner.get("operational")
        and runner.get("entries_ready")
        and runner.get("configuration_id") == state["configuration_id"]
        and not state["killed"]
        and not state["daily_locked"]
        and not safety["entry_blocked"]
    )
    return success(
        {
            **state,
            "mode": "PAPER_ONLY",
            "ready": ready,
            "runner": runner,
            "safety": safety,
            "readiness": NiftyPaperExecutor(store(), session["user"]).readiness(),
        }
    )


@nifty_algo_bp.route("/safety")
@check_session_validity
def safety_status():
    return success(store().safety_status(session["user"]))


@nifty_algo_bp.route("/safety/incidents/<int:incident_id>/acknowledge", methods=["POST"])
@check_session_validity
def acknowledge_incident(incident_id):
    body = request.get_json(silent=True)
    if (
        not isinstance(body, dict)
        or set(body) != {"revision"}
        or type(body["revision"]) is not int
        or body["revision"] < 1
    ):
        return jsonify(status="error", message="Positive integer revision required"), 400
    try:
        result = store().acknowledge_safety_incident(
            session["user"],
            incident_id,
            body["revision"],
            actor=session["user"],
            now=datetime.now(UTC),
        )
    except LookupError:
        return jsonify(status="error", message="Incident not found"), 404
    return success(result)


@nifty_algo_bp.route("/safety/incidents/<int:incident_id>/resolve", methods=["POST"])
@check_session_validity
def resolve_incident(incident_id):
    body = request.get_json(silent=True)
    if (
        not isinstance(body, dict)
        or set(body) != {"revision", "state_revision", "confirm"}
        or body["confirm"] != "RESOLVE_ONLY"
        or any(
            type(body[key]) is not int or body[key] < 1 for key in ("revision", "state_revision")
        )
    ):
        return jsonify(
            status="error", message="Positive revisions and RESOLVE_ONLY confirmation required"
        ), 400
    try:
        result = store().resolve_safety_incident(
            session["user"],
            incident_id,
            body["revision"],
            body["state_revision"],
            actor=session["user"],
            now=datetime.now(UTC),
        )
    except LookupError:
        return jsonify(status="error", message="Incident not found"), 404
    return success(result)


@nifty_algo_bp.route("/configuration", methods=["GET", "PUT"])
@check_session_validity
def configuration():
    if request.method == "GET":
        return success(store().read(session["user"]))
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"revision", "configuration"}:
        return jsonify(status="error", message="Provide revision and configuration"), 400
    if type(body["revision"]) is not int or body["revision"] < 1:
        return jsonify(status="error", message="Positive integer revision required"), 400
    config = active_configuration(body["configuration"])
    return success(store().change(session["user"], body["revision"], configuration=config))


@nifty_algo_bp.route("/strategy/<action>", methods=["POST"])
@check_session_validity
def control(action):
    if action == "start":
        state = store().read(session["user"])
        runner = _runner_status(session["user"])
        if not (
            runner.get("operational")
            and runner.get("entries_ready")
            and runner.get("configuration_id") == state["configuration_id"]
            and not state["killed"]
            and not state["daily_locked"]
        ):
            return jsonify(
                status="error",
                code="PAPER_NOT_READY",
                message="Automation requires verified native paper execution and recovery.",
                readiness=NiftyPaperExecutor(store(), session["user"]).readiness(),
            ), 409
    if action not in {"start", "pause", "stop", "kill-switch"}:
        return jsonify(status="error", message="Unknown strategy control"), 404
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"revision"} or type(body["revision"]) is not int:
        return jsonify(status="error", message="Integer revision required"), 400
    return success(store().change(session["user"], body["revision"], action=action))


@nifty_algo_bp.route("/runner", methods=["POST"])
@check_session_validity
def prepare_runner():
    from blueprints.python_strategy import SCHEDULER
    from services.nifty_algo.runner import attach_runner

    if SCHEDULER is None or not SCHEDULER.running:
        return jsonify(
            status="error",
            code="SCHEDULER_UNAVAILABLE",
            message="Native Python strategy scheduler is unavailable.",
        ), 409
    store().read(session["user"])
    attach_runner(current_app._get_current_object(), SCHEDULER, session["user"])
    return success({"state": "MONITOR_ATTACHED", "mode": "PAPER_ONLY"})


@nifty_algo_bp.route("/signals")
@check_session_validity
def signals():
    return success(store().decisions(session["user"]))


@nifty_algo_bp.route("/selector")
@check_session_validity
def selector():
    """Read recorded selector evidence without fetching data or admitting orders."""
    mode = request.args.get("mode", "PAPER")
    if mode not in {"PAPER", "SHADOW"}:
        return jsonify(status="error", message="Selector mode must be PAPER or SHADOW"), 400
    rows = store().events(session["user"], kind=f"contract_selector:{mode}", limit=1)
    if rows:
        if mode == "SHADOW":
            quantities = store().shadow_selection(
                session["user"],
                rows[0]["payload"].get("decision_id"),
                rows[0]["payload"].get("configuration_id"),
            )
            if quantities:
                rows[0]["payload"]["quantity_ranking"] = quantities
            return success(rows[0])
        quantities = store().events(session["user"], kind=f"contract_quantities:{mode}", limit=1)
        if quantities and all(
            quantities[0]["payload"].get(key) == rows[0]["payload"].get(key)
            for key in ("decision_id", "configuration_id")
        ):
            rows[0]["payload"]["quantity_ranking"] = quantities[0]["payload"]
    return success(rows[0] if rows else None)


@nifty_algo_bp.route("/assessment", methods=["POST"])
@check_session_validity
def assessment():
    """Record an observed-history assessment without order authority."""
    from database.auth_db import get_api_key_for_tradingview
    from services.nifty_algo.assessment import assess_current

    key = get_api_key_for_tradingview(session["user"])
    if not key:
        return jsonify(
            status="error",
            code="DATA_AUTH_UNAVAILABLE",
            message="Configure the native OpenAlgo market-data session first.",
        ), 409
    state = store().read(session["user"])
    config = active_configuration(state["configuration"])
    try:
        decision = assess_current(key, config)
    except ValueError:
        return jsonify(
            status="error",
            code="HISTORY_INVALID",
            message="Market history could not be verified. Check the broker connection and try again.",
        ), 422
    return success(store().record_decision(session["user"], decision))


@nifty_algo_bp.route("/signals/<decision_id>")
@check_session_validity
def signal(decision_id):
    rows = store().decisions(session["user"], decision_id)
    if not rows:
        return jsonify(status="error", message="Decision not found"), 404
    return success(rows[0])


@nifty_algo_bp.route("/indicators")
@check_session_validity
def indicators():
    decisions = store().decisions(session["user"])
    if not decisions:
        return success({"available": False, "reason": "No recorded strategy assessment"})
    return success(
        {
            "available": True,
            "snapshot": decisions[0].get("snapshot"),
            "config_id": decisions[0].get("config_id"),
            "effective_configuration": decisions[0].get("effective_configuration"),
            "charge_model": decisions[0].get("charge_model"),
            "timestamp": decisions[0].get("timestamp"),
            "pcr": decisions[0].get("pcr"),
            "confidence": decisions[0].get("confidence"),
            "indicator_states": decisions[0].get("indicator_states"),
            "checks": decisions[0].get("checks"),
            "pcr_readiness": decisions[0].get("pcr_readiness"),
        }
    )


@nifty_algo_bp.route("/risk")
@check_session_validity
def risk():
    from datetime import datetime

    from services.nifty_algo.trading_mode import mode_overview

    state = store().read(session["user"])
    executor = NiftyPaperExecutor(store(), session["user"])
    overview = mode_overview(store(), session["user"])
    # Read-only: entries are refused with CALENDAR_UNAPPROVED until the current
    # IST year has an approved NFO calendar version.
    year = datetime.now(nifty_calendar.IST).year
    approved = store().approved_calendar_version(session["user"], year)
    return success(
        {
            "mode": "PAPER_ONLY",
            "killed": state["killed"],
            "daily_locked": state["daily_locked"],
            "configuration": state["configuration"],
            "account": store().account(session["user"]),
            "account_reconciled": store().account(session["user"])["reconciled"],
            "entry_locks": store().risk_locks(session["user"]),
            "calendar": {
                "year": year,
                "status": "APPROVED" if approved else "CALENDAR_UNAPPROVED",
                "approved_version_id": approved["id"] if approved else None,
            },
            "readiness": executor.readiness(),
            "trading_mode": {
                "mode": overview["mode"],
                "revision": overview["revision"],
                "live_available": overview["live_available"],
                "live_readiness": overview["readiness"],
            },
        }
    )


@nifty_algo_bp.route("/mode", methods=["GET", "POST"])
@check_session_validity
def trading_mode():
    """Paper/Live mode. Live readiness is reported; Live cannot activate in this release."""
    from services.nifty_algo.trading_mode import MODES, mode_overview, request_mode

    user = session["user"]
    if request.method == "GET":
        return success(mode_overview(store(), user))
    body = request.get_json(silent=True)
    if (
        not isinstance(body, dict)
        or not {"mode", "revision"} <= set(body) <= {"mode", "revision", "acknowledged"}
        or body["mode"] not in MODES
        or type(body["revision"]) is not int
        or body["revision"] < 1
        or type(body.get("acknowledged", False)) is not bool
    ):
        return jsonify(
            status="error",
            code="MODE_REQUEST_INVALID",
            message="Provide mode (PAPER or LIVE), integer revision and optional boolean acknowledged",
        ), 400
    mode, codes, changed = request_mode(
        store(),
        user,
        body["revision"],
        body["mode"],
        acknowledged=body.get("acknowledged", False),
        actor=user,
    )
    if codes:
        return jsonify(
            status="error",
            code="MODE_CHANGE_REFUSED",
            message="Trading mode change refused.",
            reasons=codes,
            data=mode,
        ), 409
    return success({**mode, "changed": changed})


@nifty_algo_bp.route("/shadow")
@check_session_validity
def shadow():
    """Hypothetical shadow state. Read-only; mirror P&L is never additive."""
    return success(store().shadow_status(session["user"]))


@nifty_algo_bp.route("/analytics/trades/<int:trade_id>")
@check_session_validity
def analytics_trade_detail(trade_id):
    if request.args:
        return jsonify(status="error", message="Trade details take no query parameters"), 400
    try:
        detail = store().trade_detail(session["user"], trade_id)
    except AnalyticsDataError:
        return jsonify(status="error", message="Trade evidence failed reconciliation"), 409
    if detail is None:
        return jsonify(status="error", message="Trade not found"), 404
    return success(detail)


@nifty_algo_bp.route("/research/opportunities")
@check_session_validity
def opportunities():
    """Research-only signal observations; never order authority."""
    return success(store().opportunities(session["user"]))


@nifty_algo_bp.after_request
def recording_cache_policy(response):
    if request.path.startswith(
        (
            "/api/nifty-algo/research/recordings",
            "/api/nifty-algo/research/experiments",
            "/api/nifty-algo/research/comparisons",
            "/api/nifty-algo/analytics/comparison",
        )
    ):
        response.headers["Cache-Control"] = "private, no-store"
    return response


@nifty_algo_bp.errorhandler(RequestEntityTooLarge)
def oversized_request(error):
    message = (
        "Recording request too large"
        if request.endpoint
        in {"nifty_algo.research_recordings", "nifty_algo.research_recording_seal"}
        else "Request too large"
    )
    return jsonify(status="error", message=message), 413


def _recording_body():
    """Read bounded control JSON even when CSRF already initialized request.stream."""
    if request.content_length is not None and request.content_length > 2048:
        raise RequestEntityTooLarge
    if not request.is_json:
        return None
    body = request.stream.read(2049)
    if len(body) > 2048:
        raise RequestEntityTooLarge
    try:
        return loads(body)
    except (ValueError, UnicodeError, RecursionError):
        return None


@nifty_algo_bp.route("/research/recordings", methods=["GET", "POST"])
@check_session_validity
def research_recordings():
    if request.method == "GET":
        if request.args:
            return jsonify(status="error", message="Recording list takes no parameters"), 400
        items = store().recordings(session["user"])
        # This reports opt-in, not feed health or complete quote coverage.
        requested = any(row["capture"] is not None for row in items)
        return success(
            {
                "items": items,
                "capture_status": "NATIVE_CAPTURE_REQUESTED" if requested else "NOT_CONNECTED",
            }
        )
    body = _recording_body()
    if (
        not isinstance(body, dict)
        or set(body) - {"duration_minutes", "max_observations", "confirm", "native_capture"}
        or not {"duration_minutes", "max_observations", "confirm"} <= set(body)
        or body["confirm"] != "RESEARCH_ONLY"
        or type(body.get("native_capture", False)) is not bool
        or type(body["duration_minutes"]) is not int
        or not 1 <= body["duration_minutes"] <= 1440
        or type(body["max_observations"]) is not int
        or not 1 <= body["max_observations"] <= 10000
    ):
        return jsonify(status="error", message="Invalid research recording request"), 400
    now = datetime.now(UTC)
    try:
        data = store().create_recording(
            session["user"],
            now,
            now + timedelta(minutes=body["duration_minutes"]),
            now,
            max_observations=body["max_observations"],
            native_capture=body.get("native_capture", False),
        )
    except ValueError:
        return jsonify(status="error", message="Research recording limit reached"), 400
    return success(data), 201


@nifty_algo_bp.route("/research/recordings/<recording_id>")
@check_session_validity
def research_recording_page(recording_id):
    args = request.args
    if set(args) - {"after", "limit", "as_of"} or any(len(args.getlist(key)) != 1 for key in args):
        return jsonify(status="error", message="Invalid recording query"), 400
    try:
        after, limit = args.get("after", "0"), args.get("limit", "100")
        if any(
            len(value) > 5 or not value.isascii() or not value.isdecimal()
            for value in (after, limit)
        ):
            raise ValueError
        as_of = None
        if "as_of" in args:
            value = args["as_of"]
            if not value or len(value) > 64:
                raise ValueError
            as_of = datetime.fromisoformat(value)
        data = store().recording_page(
            session["user"], recording_id, after=int(after), limit=int(limit), as_of=as_of
        )
    except ValueError:
        return jsonify(status="error", message="Invalid recording query"), 400
    if data is None:
        return jsonify(status="error", message="Recording not found"), 404
    return success(data)


@nifty_algo_bp.route("/research/recordings/<recording_id>/seal", methods=["POST"])
@check_session_validity
def research_recording_seal(recording_id):
    body = _recording_body()
    if (
        not isinstance(body, dict)
        or set(body) != {"expected_count", "confirm"}
        or body["confirm"] != "SEAL_ONLY"
        or type(body["expected_count"]) is not int
        or not 0 <= body["expected_count"] <= 10000
    ):
        return jsonify(
            status="error", message="Refresh the recording and confirm that you want to seal it."
        ), 400
    if store().recording_page(session["user"], recording_id, limit=1) is None:
        return jsonify(status="error", message="Recording not found"), 404
    try:
        data = store().seal_recording(
            session["user"],
            recording_id,
            datetime.now(UTC),
            expected_count=body["expected_count"],
        )
    except StateConflict:
        raise
    except ValueError:
        return jsonify(status="error", message="Recording cannot be sealed at this time"), 400
    return success(data)


@nifty_algo_bp.route("/research/experiments", methods=["GET", "POST"])
@check_session_validity
def research_experiments():
    """Freeze research settings against owned sealed evidence, never active settings."""
    if request.args:
        return jsonify(status="error", message="Experiment controls take no query parameters"), 400
    if request.method == "GET":
        return success({"items": store().experiment_summaries(session["user"])})
    body = _recording_body()
    required = {
        "recording_id",
        "expected_count",
        "expected_sha256",
        "train_end",
        "validation_end",
        "confirm",
    }
    if (
        not isinstance(body, dict)
        or not required <= set(body)
        or set(body) - required - {"configuration_overrides"}
        or body["confirm"] != "DEFINE_ONLY"
        or not isinstance(body["recording_id"], str)
        or fullmatch(r"[a-f0-9]{32}", body["recording_id"]) is None
        or type(body["expected_count"]) is not int
        or not 0 <= body["expected_count"] <= 10000
        or not isinstance(body["expected_sha256"], str)
        or fullmatch(r"[a-f0-9]{64}", body["expected_sha256"]) is None
        or not isinstance(body.get("configuration_overrides", {}), dict)
        or set(body.get("configuration_overrides", {})) - StrategyConfig.model_fields.keys()
        or any(
            not isinstance(body[key], str) or not 1 <= len(body[key]) <= 64
            for key in ("train_end", "validation_end")
        )
    ):
        return jsonify(status="error", message="Invalid experiment definition"), 400
    try:
        train_end = datetime.fromisoformat(body["train_end"])
        validation_end = datetime.fromisoformat(body["validation_end"])
        if train_end.tzinfo is None or validation_end.tzinfo is None:
            raise ValueError
    except ValueError:
        return jsonify(
            status="error", message="Provide dated experiment boundaries with timezones"
        ), 400
    source = store().recording_page(session["user"], body["recording_id"], limit=1)
    if source is None:
        return jsonify(status="error", message="Recording not found"), 404
    configuration = {
        **source["manifest"]["configuration"],
        **body.get("configuration_overrides", {}),
    }
    try:
        data = store().create_experiment(
            session["user"],
            body["recording_id"],
            datetime.now(UTC),
            expected_count=body["expected_count"],
            expected_sha256=body["expected_sha256"],
            configuration=configuration,
            train_end=train_end,
            validation_end=validation_end,
        )
    except StateConflict:
        raise
    except ValueError:
        return jsonify(
            status="error",
            message="Experiment cannot be defined. Check sealed evidence, settings, splits and limits.",
        ), 400
    return success(data), 201


@nifty_algo_bp.route("/research/experiments/<experiment_id>")
@check_session_validity
def research_experiment(experiment_id):
    if request.args:
        return jsonify(status="error", message="Experiment reads take no query parameters"), 400
    if fullmatch(r"[a-f0-9]{32}", experiment_id) is None:
        return jsonify(status="error", message="Experiment not found"), 404
    try:
        data = store().experiment(session["user"], experiment_id)
    except ValueError:
        return jsonify(status="error", message="Stored experiment failed verification"), 409
    if data is None:
        return jsonify(status="error", message="Experiment not found"), 404
    return success(data)


@nifty_algo_bp.route("/research/experiments/<experiment_id>/inspection", methods=["GET", "POST"])
@check_session_validity
def experiment_inspection(experiment_id):
    if fullmatch(r"[a-f0-9]{32}", experiment_id) is None or request.args:
        return jsonify(status="error", message="Invalid experiment inspection"), 400
    try:
        if request.method == "POST":
            if _recording_body() != {"confirm": "INSPECT_EVIDENCE_ONLY"}:
                return jsonify(status="error", message="Confirm evidence-only inspection"), 400
            data = store().save_research_inspection(
                session["user"], experiment_id, datetime.now(UTC)
            )
        else:
            data = store().research_inspection(session["user"], experiment_id)
    except StateConflict:
        raise
    except LookupError:
        return jsonify(status="error", message="Experiment not found"), 404
    except ValueError:
        return jsonify(status="error", message="Experiment evidence failed verification"), 409
    return success(data)


@nifty_algo_bp.route("/research/experiments/<experiment_id>/replay")
@check_session_validity
def experiment_replay(experiment_id):
    from services.nifty_algo.replay_lab import replay_page

    if fullmatch(r"[a-f0-9]{32}", experiment_id) is None or set(request.args) != {"as_of", "after"}:
        return jsonify(
            status="error",
            message="Choose a valid replay time and refresh the recording before continuing.",
        ), 400
    if len(request.args["as_of"]) > 64 or fullmatch(r"[0-9]{1,5}", request.args["after"]) is None:
        return jsonify(status="error", message="Invalid replay controls"), 400
    try:
        data = replay_page(
            store(),
            session["user"],
            experiment_id,
            as_of=datetime.fromisoformat(request.args["as_of"]),
            after=int(request.args["after"]),
        )
    except LookupError:
        return jsonify(status="error", message="Experiment not found"), 404
    except ValueError:
        return jsonify(status="error", message="Replay evidence or clock failed verification"), 409
    return success(data)


@nifty_algo_bp.route("/research/comparisons", methods=["POST"])
@check_session_validity
def create_execution_comparison():
    body = _recording_body()
    if (
        not isinstance(body, dict)
        or set(body) != {"confirm", "sources", "configuration", "train_end", "validation_end"}
        or body["confirm"] != "DEFINE_RESEARCH_ONLY"
    ):
        return jsonify(status="error", message="Confirm a pinned research-only comparison"), 400
    try:
        result = store().create_execution_comparison(
            session["user"],
            body["sources"],
            body["configuration"],
            datetime.fromisoformat(body["train_end"]),
            datetime.fromisoformat(body["validation_end"]),
            datetime.now(UTC),
        )
    except (ValueError, KeyError, TypeError):
        return jsonify(
            status="error", message="Invalid sealed evidence or comparison boundaries"
        ), 400
    return success(result), 201


@nifty_algo_bp.route("/research/experiments/<experiment_id>/execution", methods=["GET", "POST"])
@check_session_validity
def execution_comparison(experiment_id):
    if fullmatch(r"[a-f0-9]{32}", experiment_id) is None or request.args:
        return jsonify(status="error", message="Invalid experiment identity"), 400
    try:
        if store().experiment(session["user"], experiment_id) is None:
            return jsonify(status="error", message="Experiment not found"), 404
        if request.method == "POST":
            if _recording_body() != {"confirm": "REPLAY_RESEARCH_ONLY"}:
                return jsonify(status="error", message="Confirm research-only replay"), 400
            result = store().queue_execution_research(
                session["user"], experiment_id, datetime.now(UTC)
            )
        else:
            result = store().execution_research(session["user"], experiment_id)
    except ValueError:
        return jsonify(status="error", message="Research result failed verification"), 409
    return success(result)


@nifty_algo_bp.route("/research/recordings/<recording_id>/<action>", methods=["POST"])
@check_session_validity
def recording_retention(recording_id, action):
    if fullmatch(r"[a-f0-9]{32}", recording_id) is None or action not in ("archive", "restore"):
        return jsonify(status="error", message="Invalid recording retention action"), 400
    expected = "ARCHIVE_SEALED_EVIDENCE" if action == "archive" else "RESTORE_ARCHIVED_EVIDENCE"
    if _recording_body() != {"confirm": expected}:
        return jsonify(
            status="error", message="Explicit evidence-retention confirmation required"
        ), 400
    try:
        method = store().archive_recording if action == "archive" else store().restore_recording
        result = method(session["user"], recording_id, datetime.now(UTC))
    except LookupError:
        return jsonify(status="error", message="Recording not found"), 404
    except (ValueError, OSError):
        return jsonify(status="error", message="Sealed archive evidence failed verification"), 409
    return success(result)


@nifty_algo_bp.route("/research/recordings/archives")
@check_session_validity
def recording_archives():
    return success({"items": store().archived_recordings(session["user"]), "storage": "ARCHIVED"})


@nifty_algo_bp.route("/research/recordings/<recording_id>/archive")
@check_session_validity
def recording_archive_download(recording_id):
    if fullmatch(r"[a-f0-9]{32}", recording_id) is None:
        return jsonify(status="error", message="Invalid archive identity"), 400
    try:
        bundle = store().load_archived_recording(session["user"], recording_id)
        if bundle is None:
            return jsonify(status="error", message="Archive not found"), 404
        return send_file(
            BytesIO(dumps(bundle, sort_keys=True, separators=(",", ":")).encode()),
            mimetype="application/json",
            as_attachment=True,
            download_name=f"nifty-recording-{recording_id}.json",
        )
    except (ValueError, OSError):
        return jsonify(status="error", message="Archive failed integrity verification"), 409


_REPORT_FIELDS = (
    "id",
    "kind",
    "variant",
    "period_key",
    "filename",
    "sha256",
    "size_bytes",
    "generation_status",
    "generation_attempts",
    "generation_error_type",
    "delivery_status",
    "attempts",
    "next_attempt_at",
    "last_error_type",
    "summary",
    "generated_at",
    "sent_at",
    "created_at",
)


def _masked_report(row):
    """Only these fields leave the server: never the stored path or the claim token."""
    return {key: row[key] for key in _REPORT_FIELDS}


@nifty_algo_bp.route("/reports")
@check_session_validity
def reports():
    from services.nifty_algo.reports import MAX_DELIVERY_ATTEMPTS, smtp_ready

    try:
        from database.settings_db import get_smtp_settings

        smtp_configured = smtp_ready(get_smtp_settings())
    except Exception as exc:
        logger.warning("NIFTY report SMTP status unavailable: %s", type(exc).__name__)
        smtp_configured = None
    try:
        limit = int(request.args.get("limit", "100"))
        offset = int(request.args.get("offset", "0"))
    except (TypeError, ValueError):
        return jsonify(status="error", code="INVALID_PAGE"), 400
    if not 1 <= limit <= 100 or not 0 <= offset <= 1000000:
        return jsonify(status="error", code="INVALID_PAGE"), 400
    fetched = store().reports(session["user"], limit=limit + 1, offset=offset)
    more = len(fetched) > limit
    return success(
        {
            "reports": [_masked_report(row) for row in fetched[:limit]],
            "pagination": {
                "limit": limit,
                "offset": offset,
                "next_offset": offset + limit if more else None,
            },
            "smtp_configured": smtp_configured,
            "max_attempts": MAX_DELIVERY_ATTEMPTS,
        }
    )


@nifty_algo_bp.route("/reports/<int:report_id>/pdf")
@check_session_validity
def report_pdf(report_id):
    from io import BytesIO

    from flask import send_file

    from services.nifty_algo.reports import resolve_report_path

    row = store().report(session["user"], report_id)
    if row is None or row["generation_status"] != "GENERATED" or not row["path"]:
        return jsonify(status="error", code="REPORT_NOT_FOUND", message="Report not found"), 404
    try:
        # The path comes only from the owned row and must stay inside the reports root.
        data = resolve_report_path(store().report_dir, row["path"]).read_bytes()
    except (OSError, ValueError):
        return jsonify(
            status="error", code="REPORT_FILE_UNAVAILABLE", message="Report file unavailable"
        ), 404
    if sha256(data).hexdigest() != row["sha256"]:
        return jsonify(
            status="error", code="REPORT_FILE_MODIFIED", message="Report file does not match"
        ), 409
    return send_file(
        BytesIO(data),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=row["filename"],
    )


@nifty_algo_bp.route("/reports/<int:report_id>/resend", methods=["POST"])
@check_session_validity
def resend_report(report_id):
    from datetime import UTC, datetime

    if store().report(session["user"], report_id) is None:
        return jsonify(status="error", code="REPORT_NOT_FOUND", message="Report not found"), 404
    row = store().resend_report(session["user"], report_id, datetime.now(UTC))
    if row is None:
        return jsonify(
            status="error",
            code="RESEND_REFUSED",
            message="Only a failed or skipped delivery can be resent.",
        ), 409
    return success(_masked_report(row))


@nifty_algo_bp.route("/reports/<int:report_id>/retry-generation", methods=["POST"])
@check_session_validity
def retry_report_generation(report_id):
    from services.nifty_algo.reports import MAX_GENERATION_ATTEMPTS

    if store().report(session["user"], report_id) is None:
        return jsonify(status="error", code="REPORT_NOT_FOUND", message="Report not found"), 404
    row = store().retry_report_generation(
        session["user"],
        report_id,
        datetime.now(UTC),
        max_attempts=MAX_GENERATION_ATTEMPTS,
    )
    if row is None:
        return jsonify(
            status="error",
            code="GENERATION_RETRY_REFUSED",
            message="Only a failed report with exhausted generation attempts can be retried.",
        ), 409
    return success(_masked_report(row))


@nifty_algo_bp.route("/reports/scan-status")
@check_session_validity
def report_scan_status():
    """Read-only visibility into unresolved historical report periods."""
    return success(store().report_scan_status(session["user"]))


@nifty_algo_bp.route("/activity")
@check_session_validity
def activity():
    return success(store().events(session["user"]))


@nifty_algo_bp.route("/market")
@check_session_validity
def market():
    from services.nifty_algo.native_data import get_market

    return success(get_market())


@nifty_algo_bp.route("/contracts")
@check_session_validity
def contracts():
    from services.nifty_algo.native_data import get_contracts

    return success(get_contracts())


@nifty_algo_bp.route("/positions")
@check_session_validity
def positions():
    return success(store().positions(session["user"]))


@nifty_algo_bp.route("/positions/<token>/close", methods=["POST"])
@check_session_validity
def close_position(token):
    from services.nifty_algo.paper_executor import OrderRefused

    held = next((p for p in store().positions(session["user"]) if p["token"] == token), None)
    if held is None:
        return jsonify(status="error", message="Owned paper position not found"), 404
    executor = NiftyPaperExecutor(store(), session["user"])
    executor.reconcile()
    from datetime import UTC, datetime

    store().observe_position(session["user"], token, None, datetime.now(UTC), "OPERATOR_CLOSE")
    try:
        order, created = executor.admit(
            {
                "intent_id": "operator-close:" + held["entry_order_id"],
                "side": "SELL",
                "symbol": held["symbol"],
                "token": token,
                "instrument": held["instrument"],
                "exit_reason": "OPERATOR_CLOSE",
            }
        )
    except OrderRefused as error:
        return jsonify(status="error", code="EXIT_NOT_ADMITTED", reasons=error.reasons), 409
    return success(
        {
            "order": order,
            "created": created,
            "message": "Position remains open until a confirmed simulated fill.",
        }
    )


@nifty_algo_bp.route("/orders")
@check_session_validity
def orders():
    return success(store().orders(session["user"]))


@nifty_algo_bp.route("/trades")
@check_session_validity
def trades():
    return success(store().trades(session["user"]))


@nifty_algo_bp.route("/performance")
@check_session_validity
def performance():
    return success(store().performance(session["user"]))


@nifty_algo_bp.route("/analytics")
@nifty_algo_bp.route("/analytics.pdf")
@check_session_validity
def analytics_snapshot():
    if request.args.get("mode", "PAPER") != "PAPER":
        return jsonify(status="error", code="PAPER_ANALYTICS_ONLY"), 400
    try:
        ist = ZoneInfo("Asia/Kolkata")
        today = datetime.now(ist).date()
        start = datetime.combine(
            date.fromisoformat(request.args.get("start", today.replace(day=1).isoformat())),
            time.min,
            tzinfo=ist,
        )
        end = datetime.combine(
            date.fromisoformat(request.args.get("end", (today + timedelta(days=1)).isoformat())),
            time.min,
            tzinfo=ist,
        )
        data = store().analytics_snapshot(
            session["user"],
            start,
            end,
            limit=int(request.args.get("limit", "50")),
            offset=int(request.args.get("offset", "0")),
        )
        if request.path.endswith("/analytics.pdf"):
            response = send_file(
                BytesIO(analytics_pdf(data, datetime.now(UTC))),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"nifty-paper-analytics-{start.date()}-{end.date()}.pdf",
            )
            response.headers["Cache-Control"] = "private, no-store"
            return response
        return success(data)
    except AnalyticsDataError:
        return jsonify(
            status="error",
            code="ANALYTICS_EVIDENCE_UNAVAILABLE",
            message="Paper fill evidence is inconsistent or exceeds 5000 fills; narrow the period.",
        ), 422
    except (ValueError, TypeError, OverflowError):
        return jsonify(
            status="error",
            code="INVALID_ANALYTICS_PERIOD",
            message="Use ISO dates, a period of 1 to 366 days, limit 1 to 100 and offset 0 to 5000.",
        ), 400


@nifty_algo_bp.route("/analytics/comparison")
@check_session_validity
def analytics_comparison():
    from zoneinfo import ZoneInfo

    if set(request.args) - {"start", "end", "side", "reason", "format"}:
        return jsonify(status="error", message="Invalid comparison filters"), 400
    try:
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        start = datetime.combine(
            date.fromisoformat(request.args.get("start", (today - timedelta(days=30)).isoformat())),
            time(),
            ZoneInfo("Asia/Kolkata"),
        )
        end = datetime.combine(
            date.fromisoformat(request.args.get("end", (today + timedelta(days=1)).isoformat())),
            time(),
            ZoneInfo("Asia/Kolkata"),
        )
        data = store().comparative_analytics(
            session["user"],
            start,
            end,
            side=request.args.get("side") or None,
            reason=request.args.get("reason") or None,
        )
        if request.args.get("format") == "pdf":
            from services.nifty_algo.reports import render_pdf

            sections = []
            for mode in ("paper", "independent_shadow"):
                metrics = data[mode]["metrics"]
                sections.append(
                    (
                        mode.replace("_", " ").upper(),
                        [
                            [k, str(metrics[k]) if metrics is not None else "Unavailable"]
                            for k in (
                                "trades",
                                "fills",
                                "total_gross",
                                "costs",
                                "total_net",
                                "maximum_drawdown",
                            )
                        ],
                        "Independent modes; never add mirrors or research returns to PAPER capital.",
                    )
                )
            sections.append(
                (
                    "Evidence and suggestions",
                    [
                        ["Mirrors (non-additive)", str(data["mirrors"]["total"])],
                        [
                            "Shadow outcomes unavailable",
                            str(data["independent_shadow"]["unavailable_outcomes"]),
                        ],
                    ],
                    "Sampled extrema are not continuous extremes. Quotes describe modeled PAPER fills, not broker execution.",
                )
            )
            quality = data["paper"]["quality"]
            sections.append(
                (
                    "Recorded execution quality",
                    [
                        [mode + ": " + key, str(value) if value is not None else "Unavailable"]
                        for mode in ("entry", "exit", "protection")
                        for key, value in quality[mode].items()
                    ],
                    "Recorded PAPER fills only; no broker execution claim.",
                )
            )
            sections.append(
                (
                    "Evidence-based research suggestions",
                    [
                        [s["code"], s["message"], str(s["evidence_count"])]
                        for s in quality["suggestions"]
                    ],
                    "Explicit approval required; no automatic strategy changes.",
                )
            )
            response = send_file(
                BytesIO(render_pdf("NIFTY comparative analytics", sections, datetime.now(UTC))),
                mimetype="application/pdf",
                as_attachment=True,
                download_name="nifty-comparative-analytics.pdf",
            )
            response.headers["Cache-Control"] = "private, no-store"
            return response
        if request.args.get("format") not in (None, "json"):
            raise ValueError("Invalid export format")
        return success(data)
    except AnalyticsDataError:
        return jsonify(status="error", message="Comparative evidence failed reconciliation"), 422
    except (ValueError, TypeError, OverflowError):
        return jsonify(status="error", message="Invalid comparative period or filters"), 400


def _calendar_response(version):
    return {
        **version,
        "preview_diff": nifty_calendar.preview_diff(version["entries"], version["year"]),
    }


@nifty_algo_bp.route("/calendar/upload", methods=["POST"])
@check_session_validity
def upload_calendar():
    from services.nifty_algo.calendar_import import (
        MAX_CALENDAR_BYTES,
        CalendarImportError,
        parse_holiday_csv,
        parse_holiday_pdf,
    )

    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify(status="error", code="FILE_REQUIRED", message="Calendar file required"), 400
    data = uploaded.stream.read(MAX_CALENDAR_BYTES + 1)
    try:
        if len(data) > MAX_CALENDAR_BYTES:
            raise CalendarImportError("FILE_TOO_LARGE", "Calendar upload exceeds 2 MB")
        if data.startswith(b"%PDF-"):
            parsed = parse_holiday_pdf(data)
            extension = "pdf"
        else:
            parsed = parse_holiday_csv(data)
            extension = "csv"
    except CalendarImportError as error:
        return jsonify(status="error", code=error.code, message=str(error)), 400
    supplied_year = request.form.get("year")
    try:
        year = int(supplied_year) if supplied_year else parsed.year
        if year is None or year < 2000 or year > 2100:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify(
            status="error",
            code="YEAR_UNCONFIRMED",
            message="Provide the calendar year when it cannot be determined unambiguously.",
        ), 400
    entries = [dict(entry) for entry in parsed.entries]
    issues = list(parsed.issues)
    for entry in entries:
        if entry["date"] and entry["date"][:4] != str(year):
            entry["ambiguous"] = True
            entry["issue"] = ",".join(filter(None, (entry["issue"], "DATE_OUTSIDE_CIRCULAR_YEAR")))
            issues.append("DATE_OUTSIDE_CIRCULAR_YEAR")
    version = store().create_calendar_draft(
        session["user"],
        year=year,
        segment=parsed.segment,
        source_filename=uploaded.filename,
        sha256=sha256(data).hexdigest(),
        uploader=session["user"],
        entries=entries,
        issues=list(dict.fromkeys(issues)),
        data=data,
        extension=extension,
    )
    return success(_calendar_response(version))


@nifty_algo_bp.route("/calendar/versions")
@check_session_validity
def calendar_versions():
    year = request.args.get("year")
    try:
        versions = store().calendar_versions(session["user"], int(year) if year else None)
    except ValueError:
        return jsonify(status="error", code="YEAR_INVALID", message="Year must be an integer"), 400
    return success([_calendar_response(version) for version in versions])


@nifty_algo_bp.route("/calendar/versions/<int:version_id>")
@check_session_validity
def calendar_version(version_id):
    version = store().calendar_version(session["user"], version_id)
    if version is None:
        return jsonify(status="error", code="CALENDAR_NOT_FOUND", message="Calendar not found"), 404
    return success(_calendar_response(version))


@nifty_algo_bp.route("/calendar/versions/<int:version_id>", methods=["PATCH"])
@check_session_validity
def update_calendar(version_id):
    body = request.get_json(silent=True)
    if (
        not isinstance(body, dict)
        or set(body) != {"entries"}
        or not isinstance(body["entries"], list)
    ):
        return jsonify(
            status="error", code="ENTRIES_INVALID", message="Provide an entries list"
        ), 400
    try:
        version = store().update_draft_entries(
            session["user"], version_id, body["entries"], session["user"]
        )
    except ValueError as error:
        return jsonify(status="error", code="CALENDAR_UPDATE_REFUSED", message=str(error)), 409
    return success(_calendar_response(version))


@nifty_algo_bp.route("/calendar/versions/<int:version_id>/approve", methods=["POST"])
@check_session_validity
def approve_calendar(version_id):
    body = request.get_json(silent=True)
    if (
        not isinstance(body, dict)
        or set(body) != {"confirmed_year", "confirmed_segment"}
        or type(body["confirmed_year"]) is not int
        or not isinstance(body["confirmed_segment"], str)
    ):
        return jsonify(
            status="error",
            code="CALENDAR_CONFIRMATION_REQUIRED",
            message="Confirm the calendar year and segment explicitly.",
        ), 400
    try:
        version = store().approve_calendar(
            session["user"],
            version_id,
            confirmed_year=body["confirmed_year"],
            confirmed_segment=body["confirmed_segment"],
            actor=session["user"],
        )
    except ValueError as error:
        return jsonify(status="error", code="CALENDAR_APPROVAL_REFUSED", message=str(error)), 409
    return success(_calendar_response(version))


@nifty_algo_bp.route("/calendar/versions/<int:version_id>/reject", methods=["POST"])
@check_session_validity
def reject_calendar(version_id):
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or set(body) - {"detail"}:
        return jsonify(
            status="error", code="REQUEST_INVALID", message="Invalid reject request"
        ), 400
    try:
        version = store().reject_calendar(
            session["user"], version_id, session["user"], body.get("detail")
        )
    except ValueError as error:
        return jsonify(status="error", code="CALENDAR_REJECT_REFUSED", message=str(error)), 409
    return success(_calendar_response(version))
