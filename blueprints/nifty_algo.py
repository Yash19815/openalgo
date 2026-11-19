"""Authenticated feature API. Order admission remains closed until ready."""

from flask import Blueprint, current_app, jsonify, request, session
from pydantic import ValidationError

from database.nifty_algo_db import NiftyStore, StateConflict
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.paper_executor import NiftyPaperExecutor
from utils.session import check_session_validity

nifty_algo_bp = Blueprint("nifty_algo", __name__, url_prefix="/api/nifty-algo")


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
    return success(
        {
            **state,
            "mode": "PAPER_ONLY",
            "ready": False,
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
        return jsonify(
            status="error",
            code="PAPER_NOT_READY",
            message="Automation requires verified native paper execution and recovery.",
            readiness=NiftyPaperExecutor(store(), session["user"]).readiness(),
        ), 409
    if action not in {"pause", "stop", "kill-switch"}:
        return jsonify(status="error", message="Unknown strategy control"), 404
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"revision"} or type(body["revision"]) is not int:
        return jsonify(status="error", message="Integer revision required"), 400
    return success(store().change(session["user"], body["revision"], action=action))


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
