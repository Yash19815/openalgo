"""Authenticated feature API. Order admission remains closed until ready."""

from hashlib import sha256

from flask import Blueprint, current_app, jsonify, request, session
from flask_socketio import join_room, leave_room
from pydantic import ValidationError

from database.nifty_algo_db import NiftyStore, StateConflict
from extensions import socketio
from services.nifty_algo import calendar as nifty_calendar
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.paper_executor import NiftyPaperExecutor
from utils.session import check_session_validity

nifty_algo_bp = Blueprint("nifty_algo", __name__, url_prefix="/api/nifty-algo")


def _socket_room():
    from utils.session import is_session_valid

    try:
        user = session.get("user")
        return f"nifty_algo:{user}" if user and is_session_valid() else None
    except Exception:
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


def success(data):
    return jsonify(status="success", data=data)


@nifty_algo_bp.errorhandler(StateConflict)
def conflict(error):
    return jsonify(status="error", code="REVISION_CONFLICT", message=str(error)), 409


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
    runner = store().runner_status(session["user"])
    ready = bool(
        runner.get("operational")
        and runner.get("entries_ready")
        and runner.get("configuration_id") == state["configuration_id"]
        and not state["killed"]
        and not state["daily_locked"]
    )
    return success(
        {
            **state,
            "mode": "PAPER_ONLY",
            "ready": ready,
            "runner": runner,
            "readiness": NiftyPaperExecutor(store(), session["user"]).readiness(),
        }
    )


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
    config = StrategyConfig.model_validate(body["configuration"])
    return success(store().change(session["user"], body["revision"], configuration=config))


@nifty_algo_bp.route("/strategy/<action>", methods=["POST"])
@check_session_validity
def control(action):
    if action == "start":
        state = store().read(session["user"])
        runner = store().runner_status(session["user"])
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
    config = StrategyConfig.model_validate(state["configuration"])
    try:
        decision = assess_current(key, config)
    except ValueError:
        return jsonify(
            status="error",
            code="HISTORY_INVALID",
            message="Native history failed input validation.",
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
    state = store().read(session["user"])
    executor = NiftyPaperExecutor(store(), session["user"])
    return success(
        {
            "mode": "PAPER_ONLY",
            "killed": state["killed"],
            "daily_locked": state["daily_locked"],
            "configuration": state["configuration"],
            "account": store().account(session["user"]),
            "account_reconciled": store().account(session["user"])["reconciled"],
            "entry_locks": store().risk_locks(session["user"]),
            "readiness": executor.readiness(),
        }
    )


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
    if not isinstance(body, dict) or set(body) != {"entries"} or not isinstance(body["entries"], list):
        return jsonify(status="error", code="ENTRIES_INVALID", message="Provide an entries list"), 400
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
        return jsonify(status="error", code="REQUEST_INVALID", message="Invalid reject request"), 400
    try:
        version = store().reject_calendar(
            session["user"], version_id, session["user"], body.get("detail")
        )
    except ValueError as error:
        return jsonify(status="error", code="CALENDAR_REJECT_REFUSED", message=str(error)), 409
    return success(_calendar_response(version))
