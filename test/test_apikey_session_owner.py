"""API key and order-mode writes change only the signed-in account.

``/apikey`` (POST) and ``/apikey/mode`` used to take the target account from
the request body's ``user_id``. A signed-in session could therefore rotate
another account's key, change its order mode, or mint a key for an account
that does not exist. Both writes are now bound to ``session["user"]``.

Synthetic accounts and an in-memory recorder only: no database, no real key.
"""

import os
import sys

import pytest
from flask import Flask, jsonify
from flask_wtf.csrf import CSRFProtect, generate_csrf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import blueprints.apikey as apikey_module  # noqa: E402
import utils.session as session_module  # noqa: E402

OWNER, OTHER, MISSING = "synthetic-owner-a", "synthetic-owner-b", "synthetic-nobody"


@pytest.fixture
def writes(monkeypatch):
    """Record every key and mode write instead of touching auth_db."""
    calls = []
    monkeypatch.setattr(session_module, "is_session_valid", lambda: True)
    monkeypatch.setattr(
        apikey_module,
        "upsert_api_key",
        lambda user_id, api_key: calls.append(("key", user_id, api_key)) or 7,
    )
    monkeypatch.setattr(
        apikey_module,
        "update_order_mode",
        lambda user_id, mode: calls.append(("mode", user_id, mode)) or True,
    )
    return calls


def _app(csrf=False):
    app = Flask(__name__)
    app.secret_key = "synthetic-test-secret"
    app.config["WTF_CSRF_ENABLED"] = csrf
    CSRFProtect(app)
    app.register_blueprint(apikey_module.api_key_bp)

    @app.route("/_csrf")
    def token():
        return jsonify(token=generate_csrf())

    return app


def _client(app, user=OWNER):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = user
    return client


@pytest.mark.parametrize("target", [OTHER, MISSING])
def test_a_key_cannot_be_rotated_or_issued_for_another_account(writes, target):
    response = _client(_app()).post("/apikey", json={"user_id": target})

    assert response.status_code == 403
    assert "api_key" not in response.get_json()
    assert writes == []


@pytest.mark.parametrize("target", [OTHER, MISSING])
def test_the_order_mode_of_another_account_cannot_be_changed(writes, target):
    response = _client(_app()).post("/apikey/mode", json={"user_id": target, "mode": "semi_auto"})

    assert response.status_code == 403
    assert writes == []


@pytest.mark.parametrize("body", [{"user_id": OWNER}, {}])
def test_the_signed_in_account_still_rotates_its_own_key(writes, body):
    response = _client(_app()).post("/apikey", json=body)

    assert response.status_code == 200
    issued = response.get_json()["api_key"]
    assert writes == [("key", OWNER, issued)]


@pytest.mark.parametrize("body", [{"user_id": OWNER, "mode": "semi_auto"}, {"mode": "auto"}])
def test_the_signed_in_account_still_changes_its_own_mode(writes, body):
    response = _client(_app()).post("/apikey/mode", json=body)

    assert response.status_code == 200
    assert writes == [("mode", OWNER, body["mode"])]


def test_an_invalid_mode_is_still_refused_for_the_owner(writes):
    response = _client(_app()).post("/apikey/mode", json={"user_id": OWNER, "mode": "live"})

    assert response.status_code == 400
    assert writes == []


@pytest.mark.parametrize("path", ["/apikey", "/apikey/mode"])
def test_a_non_object_body_never_targets_another_account(writes, path):
    response = _client(_app()).post(path, json=[OTHER])

    # A list body carries no target, so the key route reaches only the owner
    # and the mode route refuses it for having no mode.
    if path == "/apikey":
        assert response.status_code == 200
        assert [call[1] for call in writes] == [OWNER]
    else:
        assert response.status_code == 400
        assert writes == []


@pytest.mark.parametrize(
    "path,body",
    [("/apikey", {"user_id": OWNER}), ("/apikey/mode", {"user_id": OWNER, "mode": "auto"})],
)
def test_csrf_still_guards_both_writes(writes, path, body):
    app = _app(csrf=True)
    client = _client(app)

    refused = client.post(path, json=body)
    assert refused.status_code == 400
    assert writes == []

    token = client.get("/_csrf").get_json()["token"]
    accepted = client.post(path, json=body, headers={"X-CSRFToken": token})
    assert accepted.status_code == 200
    assert len(writes) == 1 and writes[0][1] == OWNER


def test_the_apikey_views_are_not_csrf_exempt():
    from pathlib import Path

    source = (Path(apikey_module.__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    exemptions = [line for line in source.splitlines() if "csrf.exempt(" in line]
    assert exemptions, "the exemption list moved; point this test at it"
    assert not any("api_key" in line for line in exemptions)
    # The endpoint-name loop exempts only the listed MCP/OAuth endpoints.
    assert '"api_key_bp.' not in source
