"""Discord setup uses signed OpenAlgo sessions; interactions use signed raw bodies."""

from datetime import UTC, datetime
from json import loads

from flask import current_app, jsonify, request, session
from werkzeug.exceptions import RequestEntityTooLarge

from database.nifty_algo_db import StateConflict
from services.nifty_algo.discord_bot import (
    DiscordREST,
    DiscordSettings,
    command_definitions,
    command_response,
    private_response,
    verify_interaction,
)
from utils.session import check_session_validity


def register_discord_routes(bp):
    def store():
        return current_app.extensions["nifty_algo_store"]

    def body(limit=8192):
        if request.content_length is not None and request.content_length > limit:
            raise RequestEntityTooLarge
        raw = request.stream.read(limit + 1)
        if len(raw) > limit:
            raise RequestEntityTooLarge
        try:
            result = loads(raw)
            return result if isinstance(result, dict) else None
        except (ValueError, UnicodeError, RecursionError):
            return None

    def success(data):
        return jsonify(status="success", data=data)

    @bp.after_request
    def discord_cache_policy(response):
        if request.path.startswith("/api/nifty-algo/discord"):
            response.headers["Cache-Control"] = "private, no-store"
        return response

    @bp.route("/discord", methods=["GET", "POST"])
    @check_session_validity
    def discord_configuration():
        if request.args:
            return jsonify(status="error", message="Discord controls take no query parameters"), 400
        if request.method == "GET":
            return success(
                {
                    "settings": store().discord_configuration(session["user"]),
                    "health": store().notification_health(session["user"]),
                    "deliveries": store().notifications(session["user"]),
                    "incidents": store().safety_status(session["user"])["incidents"],
                }
            )
        data = body()
        if (
            data is None
            or set(data) - {"revision", "configuration", "token", "confirm"}
            or not {"revision", "configuration", "confirm"}.issubset(data)
            or data.get("confirm") != "SAVE_DISCORD_SETTINGS"
        ):
            return jsonify(status="error", message="Invalid Discord settings controls"), 400
        try:
            result = store().save_discord_configuration(
                session["user"],
                data["revision"],
                data["configuration"],
                data.get("token"),
                datetime.now(UTC),
            )
        except StateConflict:
            raise
        except ValueError:
            return jsonify(status="error", message="Discord settings are invalid"), 400
        return success(result)

    @bp.route("/discord/<action>", methods=["POST"])
    @check_session_validity
    def discord_setup_action(action):
        data = body()
        if (
            action not in ("validate", "register-commands", "test")
            or data is None
            or set(data) != {"revision", "confirm"}
            or type(data.get("revision")) is not int
            or data.get("confirm")
            != {
                "validate": "VALIDATE",
                "register-commands": "REGISTER_READ_ONLY",
                "test": "QUEUE_TEST",
            }.get(action)
        ):
            return jsonify(status="error", message="Invalid Discord setup action"), 400
        configuration = store().discord_configuration(session["user"], secrets=True)
        if configuration is None or data["revision"] != configuration["revision"]:
            return jsonify(status="error", message="Reload current Discord settings"), 409
        settings = DiscordSettings.model_validate(configuration["configuration"])
        if action == "test":
            if not settings.enabled or not configuration["verified"]:
                return jsonify(
                    status="error", message="Enable and verify configuration before testing"
                ), 409
            # Durable intent only. The separate dispatcher owns external delivery.
            store().record_event(session["user"], "discord_test", {}, datetime.now(UTC))
            return success({"state": "REQUESTED", "delivery_verified": False}), 202
        try:
            transport = DiscordREST(configuration["token"])
            if action == "validate":
                result = transport.validate(settings)
                return success(
                    store().verify_discord_configuration(
                        session["user"], configuration["revision"], result, datetime.now(UTC)
                    )
                )
            if not configuration["verified"]:
                return jsonify(
                    status="error", message="Verify bot permissions before registering commands"
                ), 409
            result = transport.request(
                "PUT",
                f"/applications/{settings.application_id}/guilds/{settings.guild_id}/commands",
                json=command_definitions(),
            )
            if result.status_code != 200:
                raise ValueError("Command registration refused")
            store().record_event(
                session["user"],
                "discord_commands_registered",
                {"revision": configuration["revision"]},
                datetime.now(UTC),
            )
            return success({"state": "PROVIDER_ACCEPTED", "human_acknowledged": False})
        except Exception:
            return jsonify(
                status="error",
                message="Discord setup request failed; verify configuration and provider health",
            ), 502

    @bp.route("/discord/interactions/<application_id>", methods=["POST"])
    def discord_interaction(application_id):
        # This route alone is CSRF exempt. Ed25519 is mandatory, even for PING.
        if request.args:
            return jsonify(error="Invalid interaction"), 400
        if request.content_length is not None and request.content_length > 65536:
            raise RequestEntityTooLarge
        raw = request.stream.read(65537)
        owner = store().discord_owner(application_id)
        configuration = store().discord_configuration(owner) if owner else None
        now = datetime.now(UTC)
        if configuration is None or not verify_interaction(
            configuration["configuration"]["public_key"],
            request.headers.get("X-Signature-Timestamp"),
            request.headers.get("X-Signature-Ed25519"),
            raw,
            now,
        ):
            return jsonify(error="Invalid request signature"), 401
        try:
            interaction = loads(raw)
            if not isinstance(interaction, dict):
                raise ValueError
        except (ValueError, UnicodeError, RecursionError):
            return jsonify(error="Invalid interaction"), 400
        if interaction.get("type") == 1:
            return jsonify(type=1)
        if not configuration["configuration"]["enabled"]:
            return jsonify(private_response("Discord monitoring is disabled."))
        try:
            response = command_response(
                store(),
                owner,
                DiscordSettings.model_validate(configuration["configuration"]),
                interaction,
                now,
            )
        except Exception:
            response = private_response(
                "Verified information unavailable. Check OpenAlgo; trading state is unchanged."
            )
        return jsonify(response)

    @bp.record_once
    def exempt_signed_interaction(state):
        csrf = state.app.extensions.get("csrf")
        if csrf is not None:
            csrf.exempt(discord_interaction)
