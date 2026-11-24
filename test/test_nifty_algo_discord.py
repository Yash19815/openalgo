"""Offline bot, signature, accounting isolation and durable delivery regressions."""

from datetime import UTC, datetime, timedelta
from json import dumps
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import event, select

from database.nifty_algo_db import NiftyDiscordSettings, NiftyState, NiftyStore, StateConflict
from services.nifty_algo.discord_bot import (
    CHANNELS,
    DiscordREST,
    DiscordSettings,
    command_definitions,
    command_response,
    event_projection,
    message_payload,
    verify_interaction,
)
from services.nifty_algo.notification_worker import NotificationWorker
from test.test_nifty_algo_paper_executor import NOW, USER
from test.test_nifty_algo_safety_center import client as client
from test.test_nifty_algo_safety_center import login
from test.test_nifty_algo_safety_center import store as store

APP = "100000000000000001"
GUILD = "100000000000000002"
ACTOR = "100000000000000003"
ROLE = "100000000000000004"
KEY = Ed25519PrivateKey.generate()


def configuration(**updates):
    data = {
        "enabled": True,
        "application_id": APP,
        "guild_id": GUILD,
        "public_key": KEY.public_key().public_bytes_raw().hex(),
        "channels": {name: str(200000000000000000 + index) for index, name in enumerate(CHANNELS)},
        "authorized_users": [ACTOR],
        "authorized_roles": [],
        "critical_role": ROLE,
    }
    return {**data, **updates}


def configured(store):
    saved = store.save_discord_configuration(USER, 0, configuration(), "test-only-bot-token", NOW)
    return store.verify_discord_configuration(
        USER, saved["revision"], {"ready": True, "errors": [], "bot_id": APP}, NOW
    )


def critical(store):
    return store.raise_safety_incident(
        USER, "discord-incident", mode="PAPER", code="STALE_DATA", severity="CRITICAL", now=NOW
    )


def interaction(name="status", **updates):
    return {
        "type": 2,
        "id": "300000000000000001",
        "application_id": APP,
        "guild_id": GUILD,
        "channel_id": configuration()["channels"]["bot-status"],
        "member": {"user": {"id": ACTOR}, "roles": []},
        "data": {"name": name},
        **updates,
    }


def test_credentials_encrypted_and_never_returned_or_audited(store):
    configured(store)
    result = store.discord_configuration(USER)
    assert "token" not in result
    with store.sessions() as db:
        cipher = db.get(NiftyDiscordSettings, USER).token_encrypted
        assert cipher != "test-only-bot-token" and cipher.startswith("gAAAA")
    assert "test-only-bot-token" not in dumps(store.events(USER))
    assert store.discord_configuration("other") is None


def test_rotation_requires_current_revision_and_invalidates_verification(store):
    configured(store)
    with pytest.raises(StateConflict):
        store.save_discord_configuration(USER, 0, configuration(), "replacement-token", NOW)
    result = store.save_discord_configuration(USER, 1, configuration(), "replacement-token", NOW)
    assert result["revision"] == 2 and not result["verified"]
    assert store.discord_configuration(USER, secrets=True)["token"] == "replacement-token"


@pytest.mark.parametrize(
    "update",
    [
        {"preferences": {"CRITICAL": False}},
        {"channels": {}},
        {"guild_id": "channel-name"},
        {"authorized_users": [], "authorized_roles": []},
        {"public_key": "bad"},
        {"channels": dict.fromkeys(CHANNELS, "https://evil.invalid")},
    ],
)
def test_configuration_rejects_invalid_or_unsafe_settings(update):
    with pytest.raises(ValueError):
        DiscordSettings.model_validate(configuration(**update))


def test_projection_is_bounded_idempotent_and_does_not_export_arbitrary_payload(store):
    configured(store)
    critical(store)
    store.record_event(USER, "untrusted", {"token": "secret"}, NOW)
    assert store.project_discord_notifications(USER, NOW) == 1
    assert NiftyStore(store.engine).project_discord_notifications(USER, NOW) == 0
    rows = store.notifications(USER)
    assert rows[0]["destination"] == "critical-alerts"
    assert "secret" not in dumps(rows)
    assert rows[0]["envelope"]["mode"] == "PAPER"


def test_discord_failure_and_email_acceptance_remain_independent(store):
    configured(store)
    critical(store)
    transport = Mock()
    transport.send.return_value = {"outcome": "AMBIGUOUS", "code": "TRANSPORT_OUTCOME_UNKNOWN"}
    email = Mock(return_value={"outcome": "DELIVERED", "code": "SMTP_ACCEPTED"})
    worker = NotificationWorker(store, USER, transport=transport, email=email, clock=lambda: NOW)
    assert worker.tick()["status"] == "AMBIGUOUS"
    assert worker.tick()["status"] == "DELIVERED"
    assert transport.send.call_count == email.call_count == 1
    rows = store.notifications(USER)
    assert {r["status"] for r in rows} == {"AMBIGUOUS", "DELIVERED"}
    assert store.safety_status(USER)["entry_blocked"]
    assert not store.notification_health(USER)["acceptance_is_acknowledgement"]


def test_429_cooldown_survives_restart_and_does_not_block_fallback(store):
    configured(store)
    critical(store)
    transport = Mock()
    transport.send.return_value = {"outcome": "RETRY", "code": "HTTP_429", "retry_after": 12}
    email = Mock(return_value={"outcome": "DELIVERED", "code": "SMTP_ACCEPTED"})
    worker = NotificationWorker(store, USER, transport=transport, email=email, clock=lambda: NOW)
    assert worker.tick()["status"] == "RETRY"
    restarted = NotificationWorker(
        NiftyStore(store.engine),
        USER,
        transport=transport,
        email=email,
        clock=lambda: NOW + timedelta(seconds=1),
    )
    assert restarted.tick()["status"] == "DELIVERED"
    assert restarted.tick()["status"] == "IDLE"
    assert transport.send.call_count == 1


def test_reminders_are_durable_deduplicated_and_acknowledgement_does_not_resolve(store):
    configured(store)
    incident = critical(store)
    store.project_discord_notifications(USER, NOW)
    assert store.schedule_incident_reminders(USER, NOW + timedelta(seconds=119)) == 0
    assert store.schedule_incident_reminders(USER, NOW + timedelta(seconds=120)) == 1
    assert store.schedule_incident_reminders(USER, NOW + timedelta(seconds=121)) == 0
    response = store.discord_acknowledge(USER, incident["id"], ACTOR, "300000000000000001", NOW)
    assert response["data"]["flags"] == 64
    assert (
        store.discord_acknowledge(USER, incident["id"], ACTOR, "300000000000000001", NOW)
        == response
    )
    assert store.safety_status(USER)["incidents"][0]["status"] == "ACKNOWLEDGED"
    assert store.schedule_incident_reminders(USER, NOW + timedelta(seconds=300)) == 1
    assert store.safety_status(USER)["entry_blocked"]


def test_mentions_allow_only_configured_role_on_incident_creation_or_reminder():
    settings = DiscordSettings.model_validate(configuration())
    envelope = {
        "severity": "CRITICAL",
        "mode": "PAPER",
        "kind": "safety_incident",
        "code": "@everyone @here <@123>",
    }
    payload = message_payload(envelope, settings, 7)
    assert payload["allowed_mentions"]["parse"] == []
    assert payload["allowed_mentions"]["roles"] == [ROLE]
    assert payload["content"] == f"<@&{ROLE}>"
    acknowledged = message_payload({**envelope, "kind": "safety_acknowledged"}, settings, 8)
    assert not acknowledged["content"] and not acknowledged["allowed_mentions"]["roles"]


@pytest.mark.parametrize(
    "status,outcome",
    [(200, "DELIVERED"), (429, "RETRY"), (403, "DEAD"), (500, "AMBIGUOUS"), (302, "AMBIGUOUS")],
)
def test_official_transport_result_and_rate_limit_policy(status, outcome):
    def respond(request):
        assert request.url.host == "discord.com"
        assert request.headers["Authorization"] == "Bot test-only-token"
        return httpx.Response(status, json={"id": "400000000000000001", "retry_after": 2.2})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        result = DiscordREST("test-only-token", http).send("200000000000000001", {})
    assert result["outcome"] == outcome
    if status == 429:
        assert result["retry_after"] == 3
    assert "test-only-token" not in dumps(result)


def test_transport_timeout_is_not_assumed_rejected():
    def fail(request):
        raise httpx.ReadTimeout("untrusted secret provider error")

    with httpx.Client(transport=httpx.MockTransport(fail)) as http:
        result = DiscordREST("test-only-token", http).send("200000000000000001", {})
    assert result == {"outcome": "AMBIGUOUS", "code": "TRANSPORT_OUTCOME_UNKNOWN"}


def test_signature_checks_exact_bytes_age_and_key():
    stamp = str(int(NOW.timestamp()))
    raw = b'{"type":1}'
    signature = KEY.sign(stamp.encode() + raw).hex()
    public = configuration()["public_key"]
    assert verify_interaction(public, stamp, signature, raw, NOW)
    assert not verify_interaction(public, stamp, signature, raw + b" ", NOW)
    assert not verify_interaction(public, stamp, signature, raw, NOW + timedelta(seconds=301))
    assert not verify_interaction(public, None, None, raw, NOW)


@pytest.mark.parametrize(
    "update",
    [
        {"guild_id": "100000000000000009"},
        {"channel_id": "100000000000000009"},
        {"member": {"user": {"id": "100000000000000009"}, "roles": []}},
        {"data": {"name": "buy"}},
        {"data": {"name": "resume"}},
    ],
)
def test_command_authorization_refuses_wrong_scope_and_trading_commands(store, update):
    result = command_response(
        store, USER, DiscordSettings.model_validate(configuration()), interaction(**update), NOW
    )
    assert result["data"]["flags"] == 64 and "Not authorized" in result["data"]["content"]


def test_commands_never_expose_trading_actions_and_ack_changes_only_incident(store):
    configured(store)
    incident = critical(store)
    before = store.read(USER)
    request = interaction(
        "ack",
        data={"name": "ack", "options": [{"name": "incident-id", "value": str(incident["id"])}]},
    )
    response = command_response(
        store, USER, DiscordSettings.model_validate(configuration()), request, NOW
    )
    assert "ACKNOWLEDGED" in response["data"]["content"]
    assert store.read(USER) == before
    assert {item["name"] for item in command_definitions()} == {
        "status",
        "health",
        "position",
        "today",
        "month",
        "report",
        "ack",
    }


def test_settings_api_session_csrf_unknown_fields_and_token_masking(client, store):
    assert (
        client.get("/api/nifty-algo/discord", headers={"Accept": "application/json"}).status_code
        == 401
    )
    headers = login(client)
    data = {
        "revision": 0,
        "configuration": configuration(),
        "token": "test-only-token",
        "confirm": "SAVE_DISCORD_SETTINGS",
    }
    assert client.post("/api/nifty-algo/discord", json=data).status_code == 400
    result = client.post("/api/nifty-algo/discord", json=data, headers=headers)
    assert result.status_code == 200 and "test-only-token" not in result.text
    assert client.get("/api/nifty-algo/discord").headers["Cache-Control"] == "private, no-store"
    assert (
        client.post(
            "/api/nifty-algo/discord", json={**data, "place_order": True}, headers=headers
        ).status_code
        == 400
    )


def test_interaction_endpoint_signature_instead_of_cookie_csrf(client, store):
    configured(store)
    now = datetime.now(UTC)
    stamp = str(int(now.timestamp()))
    raw = b'{"type":1}'
    url = f"/api/nifty-algo/discord/interactions/{APP}"
    assert client.post(url, data=raw).status_code == 401
    result = client.post(
        url,
        data=raw,
        headers={
            "X-Signature-Timestamp": stamp,
            "X-Signature-Ed25519": KEY.sign(stamp.encode() + raw).hex(),
        },
    )
    assert result.status_code == 200 and result.json == {"type": 1}


def test_additive_migration_and_notification_failures_preserve_account_and_release_connections(
    store,
):
    configured(store)
    before = store.read(USER)
    store.initialize()
    opened, closed = [], []

    def connect(*args):
        opened.append(1)

    def close(*args):
        closed.append(1)

    event.listen(store.engine, "connect", connect)
    event.listen(store.engine, "close", close)
    try:
        for _ in range(100):
            store.discord_configuration(USER)
            store.notification_health(USER)
            with pytest.raises(StateConflict):
                store.save_discord_configuration(USER, 0, configuration(), None, NOW)
            assert len(opened) == len(closed)
    finally:
        event.remove(store.engine, "connect", connect)
        event.remove(store.engine, "close", close)
    assert len(opened) == 300
    assert store.read(USER) == before


def test_competing_configuration_writers_have_one_winner(store):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    configured(store)
    barrier = Barrier(2)

    def save():
        barrier.wait(timeout=10)
        try:
            return NiftyStore(store.engine).save_discord_configuration(
                USER, 1, configuration(), None, NOW
            )["revision"]
        except StateConflict:
            return "CONFLICT"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=15) for future in [pool.submit(save), pool.submit(save)]]
    assert sorted(map(str, results)) == ["2", "CONFLICT"]


@pytest.mark.parametrize("failure", [False, True])
def test_fallback_releases_scoped_sessions_before_smtp_and_on_lookup_failure(
    store, monkeypatch, failure
):
    from services.nifty_algo import reports
    from utils import db_sessions

    events = []
    monkeypatch.setattr(db_sessions, "remove_all_scoped_sessions", lambda: events.append("CLEANUP"))

    def settings():
        if failure:
            raise OSError("private provider error")
        return dict.fromkeys(reports.SMTP_REQUIRED, "fixture")

    monkeypatch.setattr(reports, "_default_smtp_settings", settings)
    monkeypatch.setattr(reports, "_default_recipient", lambda _: "fixture@example.invalid")

    def send(*args, **kwargs):
        assert events == ["CLEANUP"]
        events.append("SMTP")
        return True

    monkeypatch.setattr(reports, "_default_send", send)
    result = NotificationWorker(store, USER)._email({"envelope": {"code": "STALE_DATA"}})
    assert events[0] == "CLEANUP"
    assert result["outcome"] == ("AMBIGUOUS" if failure else "DELIVERED")


def test_all_read_only_commands_issue_no_writes(store):
    configured(store)
    statements = []

    def statement(_c, _u, sql, *_a):
        if sql.split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            statements.append(sql)

    event.listen(store.engine, "before_cursor_execute", statement)
    try:
        for name in ("status", "health", "position", "today", "month"):
            response = command_response(
                store, USER, DiscordSettings.model_validate(configuration()), interaction(name), NOW
            )
            assert response["data"]["flags"] == 64
        assert not statements
    finally:
        event.remove(store.engine, "before_cursor_execute", statement)


def test_shadow_digest_has_own_checkpoint_and_never_writes_primary_events(store):
    from sqlalchemy import func

    from database.nifty_algo_db import NiftyEvent, NiftyShadowEvent

    configured(store)
    with store.sessions.begin() as db:
        db.add_all(
            [
                NiftyShadowEvent(
                    user_id=USER, shadow_id=index, kind=kind, payload={"net": "100"}, created_at=NOW
                )
                for index, kind in enumerate(("SHADOW_OPENED", "SHADOW_MIRROR_CLOSED"), start=1)
            ]
        )
    with store.sessions() as db:
        before = db.scalar(select(func.count()).select_from(NiftyEvent))
    assert store.project_shadow_notifications(USER, NOW) == 1
    assert (
        NiftyStore(store.engine).project_shadow_notifications(USER, NOW + timedelta(seconds=30))
        == 0
    )
    rows = store.notifications(USER)
    assert len(rows) == 1 and rows[0]["event_id"] < 0
    assert rows[0]["envelope"]["mirror_events_non_additive"] == 1
    assert rows[0]["envelope"]["mode"] == "SHADOW"
    with store.sessions() as db:
        assert db.scalar(select(func.count()).select_from(NiftyEvent)) == before


@pytest.mark.parametrize("denied", [False, True])
def test_permission_validation_applies_channel_overwrites(denied):
    required = (1 << 10) | (1 << 11) | (1 << 14) | (1 << 15)

    def respond(request):
        path = request.url.path
        if path.endswith("/users/@me"):
            value = {"id": APP}
        elif "/members/" in path:
            value = {"roles": []}
        elif path.endswith("/roles"):
            value = [
                {"id": GUILD, "permissions": str(required)},
                {"id": ROLE, "permissions": "0", "mentionable": True},
            ]
        else:
            value = [
                {
                    "id": channel,
                    "type": 0,
                    "permission_overwrites": [
                        {"id": GUILD, "type": 0, "deny": str(1 << 11), "allow": "0"}
                    ]
                    if denied
                    else [],
                }
                for channel in configuration()["channels"].values()
            ]
        return httpx.Response(200, json=value)

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        result = DiscordREST("test-only-token", http).validate(
            DiscordSettings.model_validate(configuration())
        )
    assert result["ready"] is not denied
    assert len(result["errors"]) == (10 if denied else 0)


def test_report_attachment_is_owned_bounded_and_hash_verified(store, tmp_path, monkeypatch):
    from hashlib import sha256

    store.report_dir = tmp_path / "reports"
    store.report_dir.mkdir()
    path = store.report_dir / "fixture.pdf"
    path.write_bytes(b"%PDF-1.4 isolated-test")
    row = {
        "generation_status": "GENERATED",
        "path": "fixture.pdf",
        "filename": "fixture.pdf",
        "sha256": sha256(path.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(
        store, "report", lambda owner, report_id: row if owner == USER and report_id == 1 else None
    )
    worker = NotificationWorker(store, USER)
    assert worker._attachment(1)[2] == "application/pdf"
    with pytest.raises(LookupError):
        worker._attachment(2)
    path.write_bytes(b"modified")
    with pytest.raises(ValueError):
        worker._attachment(1)
