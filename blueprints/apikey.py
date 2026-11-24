import os
import secrets
from pathlib import Path

from argon2 import PasswordHasher
from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from database.auth_db import (
    get_api_key,
    get_api_key_for_tradingview,
    get_order_mode,
    update_order_mode,
    upsert_api_key,
    verify_api_key,
)
from utils.logging import get_logger
from utils.session import check_session_validity

# Path to React frontend
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

logger = get_logger(__name__)

api_key_bp = Blueprint("api_key_bp", __name__, url_prefix="/")

# Initialize Argon2 hasher
ph = PasswordHasher()


def generate_api_key():
    """Generate a secure random API key"""
    # Generate 32 bytes of random data and encode as hex
    return secrets.token_hex(32)


def _json_body():
    """The request's JSON object, or an empty one for a missing or non-object body."""
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _session_owner_target(body):
    """Return the account a key or mode write may change, or a refusal.

    The target is always the signed-in user. A body ``user_id`` is accepted
    only as a restatement of that user, because the page sends it; any other
    value is refused, so a request can never rotate another account's key,
    change its order mode or create a key for an account that does not exist.
    """
    owner = session.get("user")
    if not owner:
        return None, (jsonify({"error": "Sign in again to continue."}), 401)
    requested = body.get("user_id")
    if requested is not None and requested != owner:
        logger.warning("Refused an API key change for an account other than the signed-in user")
        return None, (
            jsonify(
                {"error": "You can only change the API key of the account you are signed in to."}
            ),
            403,
        )
    return owner, None


@api_key_bp.route("/apikey", methods=["GET", "POST"])
@check_session_validity
def manage_api_key():
    if request.method == "GET":
        login_username = session["user"]
        # Get the decrypted API key if it exists
        api_key = get_api_key_for_tradingview(login_username)
        has_api_key = api_key is not None
        # Get order mode (default to 'auto' if not set)
        order_mode = get_order_mode(login_username) or "auto"
        logger.info(f"Checking API key status for user: {login_username}, order_mode: {order_mode}")

        # Return JSON if Accept header requests it (for React frontend)
        if request.headers.get("Accept") == "application/json":
            return jsonify(
                {
                    "login_username": login_username,
                    "has_api_key": has_api_key,
                    "api_key": api_key,
                    "order_mode": order_mode,
                }
            )

        # Serve React app for browser navigation
        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return send_file(index_path, mimetype="text/html")

        # Fallback to old template if React build not available
        return render_template(
            "apikey.html",
            login_username=login_username,
            has_api_key=has_api_key,
            api_key=api_key,
            order_mode=order_mode,
        )
    else:
        user_id, refusal = _session_owner_target(_json_body())
        if refusal is not None:
            return refusal

        # Generate new API key
        api_key = generate_api_key()

        # Store the API key (auth_db will handle both hashing and encryption)
        key_id = upsert_api_key(user_id, api_key)

        if key_id is not None:
            logger.info(f"API key updated successfully for user: {user_id}")
            return jsonify(
                {"message": "API key updated successfully.", "api_key": api_key, "key_id": key_id}
            )
        else:
            logger.error(f"Failed to update API key for user: {user_id}")
            return jsonify({"error": "Failed to update API key"}), 500


@api_key_bp.route("/apikey/mode", methods=["POST"])
@check_session_validity
def update_api_key_mode():
    """Update order mode (auto/semi_auto) for a user"""
    try:
        body = _json_body()
        user_id, refusal = _session_owner_target(body)
        if refusal is not None:
            return refusal
        mode = body.get("mode")

        if not mode or mode not in ["auto", "semi_auto"]:
            logger.error(f"Invalid order mode: {mode}")
            return jsonify({"error": 'Invalid mode. Must be "auto" or "semi_auto"'}), 400

        # Update the order mode
        success = update_order_mode(user_id, mode)

        if success:
            logger.info(f"Order mode updated successfully for user: {user_id}, new mode: {mode}")
            return jsonify({"message": f"Order mode updated to {mode}", "mode": mode})
        else:
            logger.error(f"Failed to update order mode for user: {user_id}")
            return jsonify({"error": "Failed to update order mode"}), 500

    except Exception as e:
        logger.exception(f"Error updating order mode: {e}")
        return jsonify({"error": "An error occurred while updating order mode"}), 500
