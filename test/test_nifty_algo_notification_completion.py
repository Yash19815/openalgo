"""All providers are controlled mocks. No test sends external messages."""

from datetime import timedelta
from json import dumps
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import func, select

from database.nifty_algo_db import (
    NiftyDiscordReportRequest,
    NiftyDiscordSettings,
    NiftyEvent,
    NiftyStore,
    StateConflict,
)
from services.nifty_algo.discord_bot import DiscordREST, DiscordSettings, command_response
from services.nifty_algo.notification_worker import NotificationWorker
from test.test_nifty_algo_discord import APP, configuration, configured, critical, interaction
from test.test_nifty_algo_paper_executor import NOW, USER
from test.test_nifty_algo_phase4 import observe, record
from test.test_nifty_algo_safety_center import client as client
from test.test_nifty_algo_safety_center import store as store


def test_worker_heartbeat_restart_outage_and_shutdown_are_durable_and_do_not_resume(store):
    before = store.read(USER)
    store.heartbeat_notification_worker(USER, "first", NOW)
    assert store.notification_worker_health(USER, NOW)["operational"]
    later = NOW + timedelta(seconds=31)
    assert store.notification_worker_health(USER, later)["status"] == "OUTAGE"
    reopened = NiftyStore(store.engine)
    reopened.heartbeat_notification_worker(USER, "second", later)
    assert len(store.events(USER, kind="notification_worker_outage")) == 1
    reopened.heartbeat_notification_worker(USER, "second", later + timedelta(seconds=1))
    assert len(store.events(USER, kind="notification_worker_outage")) == 1
    assert store.heartbeat_notification_worker(USER, "first", later, "STOPPED") is False
    reopened.heartbeat_notification_worker(USER, "second", later + timedelta(seconds=2), "STOPPED")
    assert not reopened.notification_worker_health(USER, later + timedelta(seconds=2))[
        "operational"
    ]
    assert store.read(USER) == before


def test_bucket_limit_does_not_block_an_unrelated_channel(store):
    configured(store)
    critical(store)
    store.project_discord_notifications(USER, NOW)
    claim = store.claim_notification(USER, now=NOW)
    store.notification_result(
        USER,
        claim,
        {
            "outcome": "DELIVERED",
            "code": "HTTP_ACCEPTED",
            "bucket": "channel-bucket",
            "bucket_retry_after": 20,
        },
        NOW,
    )
    store.raise_safety_incident(
        USER, "new-critical", mode="PAPER", code="STALE_DATA", severity="CRITICAL", now=NOW
    )
    store.record_event(USER, "data_blocked", {"reason": "SECRET_MUST_NOT_LEAK"}, NOW)
    store.project_discord_notifications(USER, NOW)
    other = NiftyStore(store.engine).claim_notification(USER, now=NOW)
    assert other["destination"] == "system-warnings"
    assert "SECRET_MUST_NOT_LEAK" not in dumps(other)
    assert store.claim_notification(USER, now=NOW) is None
    assert (
        store.claim_notification(USER, now=NOW + timedelta(seconds=20))["destination"]
        == "critical-alerts"
    )


def test_provider_bucket_headers_and_global_429_are_interpreted():
    def response(request):
        return httpx.Response(
            200,
            json={"id": "400000000000000001"},
            headers={
                "X-RateLimit-Bucket": "trusted_bucket",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset-After": "1.2",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = DiscordREST("fake-token", client).send("200000000000000001", {})
    assert result["bucket"] == "trusted_bucket" and result["bucket_retry_after"] == 2
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, json={"retry_after": 2, "global": True})
        )
    ) as client:
        result = DiscordREST("fake-token", client).send("200000000000000001", {})
    assert result["global"] is True and result["outcome"] == "RETRY"


@pytest.mark.parametrize("outcome,allowed", [("DEAD", True), ("AMBIGUOUS", False)])
def test_only_definite_dead_letters_can_be_replayed(store, outcome, allowed):
    configured(store)
    critical(store)
    store.project_discord_notifications(USER, NOW)
    claim = store.claim_notification(USER, now=NOW)
    store.notification_result(
        USER, claim, {"outcome": outcome, "code": "HTTP_403" if allowed else "UNKNOWN"}, NOW
    )
    if allowed:
        result = store.replay_dead_notification(USER, claim["id"], 1, NOW)
        assert result["status"] == "PENDING"
        with pytest.raises(StateConflict):
            store.replay_dead_notification(USER, claim["id"], 1, NOW)
        assert len(store.events(USER, kind="notification_replay_requested")) == 1
    else:
        with pytest.raises(StateConflict):
            store.replay_dead_notification(USER, claim["id"], 1, NOW)
    with pytest.raises(LookupError):
        store.replay_dead_notification("other", claim["id"], 1, NOW)


def test_trailing_and_research_digests_are_separate_bounded_and_restart_safe(store):
    configured(store)
    for i in range(12):
        store.record_event(
            USER,
            "trailing_stop_updated",
            {"token": "option", "stop_price": str(100 + i), "secret": "hidden"},
            NOW,
        )
    record(store, NOW)
    observe(store, NOW + timedelta(minutes=5), 24020)
    with store.sessions() as db:
        before = db.scalar(select(func.count()).select_from(NiftyEvent))
    assert store.project_discord_notifications(USER, NOW) == 0
    assert store.project_routine_digests(USER, NOW + timedelta(minutes=5)) == 2
    assert NiftyStore(store.engine).project_routine_digests(USER, NOW + timedelta(minutes=6)) == 0
    rows = store.notifications(USER)
    assert {r["destination"] for r in rows} == {"risk-management", "research-insights"}
    assert "hidden" not in dumps(rows)
    research = next(r for r in rows if r["destination"] == "research-insights")
    assert research["envelope"]["mode"] == "RESEARCH"
    assert "UNDERLYING_ATR_STUDY_NOT_OPTIONS_PNL" in dumps(research)
    with store.sessions() as db:
        assert db.scalar(select(func.count()).select_from(NiftyEvent)) == before


def report_interaction(**updates):
    return interaction(
        "report",
        token="PRIVATE_TOKEN_NOT_FOR_LOGS",
        attachment_size_limit=8 * 1024 * 1024,
        app_permissions=str(1 << 15),
        data={"name": "report", "options": [{"name": "daily", "type": 1}]},
        **updates,
    )


def test_report_command_defers_privately_deduplicates_and_encrypts_token(store):
    configured(store)
    request = report_interaction()
    settings = DiscordSettings.model_validate(configuration())
    assert command_response(store, USER, settings, request, NOW) == {
        "type": 5,
        "data": {"flags": 64},
    }
    assert command_response(store, USER, settings, request, NOW) == {
        "type": 5,
        "data": {"flags": 64},
    }
    with store.sessions() as db:
        rows = list(db.scalars(select(NiftyDiscordReportRequest)))
        assert len(rows) == 1 and "PRIVATE_TOKEN" not in rows[0].token_encrypted
    assert "PRIVATE_TOKEN" not in dumps(store.notifications(USER))
    assert "PRIVATE_TOKEN" not in dumps(store.events(USER))


def test_private_report_missing_file_and_crash_never_send_public_or_duplicate(store):
    configured(store)
    command_response(
        store, USER, DiscordSettings.model_validate(configuration()), report_interaction(), NOW
    )
    transport = Mock()
    transport.edit_private_report.return_value = {
        "outcome": "DELIVERED",
        "code": "PRIVATE_REPORT_ACCEPTED",
    }
    worker = NotificationWorker(store, USER, transport=transport, clock=lambda: NOW)
    worker.tick()
    args = transport.edit_private_report.call_args.args
    assert args[0] == APP and args[3] is None
    assert args[2]["allowed_mentions"]["parse"] == []
    worker.tick()
    assert transport.edit_private_report.call_count == 1
    with store.sessions() as db:
        row = db.get(NiftyDiscordReportRequest, (USER, report_interaction()["id"]))
        assert row.status == "DELIVERED" and row.token_encrypted is None


def test_abandoned_private_report_is_ambiguous_not_replayed(store):
    configured(store)
    command_response(
        store, USER, DiscordSettings.model_validate(configuration()), report_interaction(), NOW
    )
    claim = store.claim_discord_report(USER, NOW)
    assert claim is not None
    assert NiftyStore(store.engine).claim_discord_report(USER, NOW + timedelta(seconds=31)) is None
    with store.sessions() as db:
        row = db.get(NiftyDiscordReportRequest, (USER, claim["id"]))
        assert row.status == "AMBIGUOUS" and row.token_encrypted is None


def test_private_report_transport_uses_only_original_ephemeral_response_and_masks_urls():
    from utils.logging import redact_text

    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "400000000000000001"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = DiscordREST("fake-token", client).edit_private_report(
            APP, "PRIVATE_TOKEN", {"content": "test"}
        )
    assert result["outcome"] == "DELIVERED"
    assert seen[0].method == "PATCH" and str(seen[0].url).endswith("/messages/@original")
    assert "PRIVATE_TOKEN" not in redact_text(str(seen[0].url))


@pytest.mark.parametrize(
    "limit,corrupt,revoked,attached",
    [
        (8 * 1024 * 1024, False, False, True),
        (1, False, False, False),
        (8 * 1024 * 1024, True, False, False),
        (8 * 1024 * 1024, False, True, False),
    ],
)
def test_private_owned_pdf_verification_size_and_revoked_authorization(
    store, tmp_path, limit, corrupt, revoked, attached
):
    from hashlib import sha256

    from database.nifty_algo_db import NiftyReport
    from services.nifty_algo.reports import render_pdf

    store.report_dir = tmp_path / "owned-reports"
    configured(store)
    data = render_pdf("PRIVATE OWNER REPORT", [], NOW)
    path = store.report_dir / "private-completion.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    with store.sessions.begin() as db:
        db.add(
            NiftyReport(
                user_id=USER,
                kind="DAILY",
                period_key="2026-11-19",
                path=path.name,
                sha256=sha256(data).hexdigest(),
                size_bytes=len(data),
                generation_status="GENERATED",
                delivery_status="SKIPPED",
                created_at=NOW,
                updated_at=NOW,
                generated_at=NOW,
            )
        )
    request = report_interaction()
    request["attachment_size_limit"] = limit
    assert (
        command_response(
            store, USER, DiscordSettings.model_validate(configuration()), request, NOW
        )["type"]
        == 5
    )
    if corrupt:
        path.write_bytes(b"corrupted")
    if revoked:
        with store.sessions.begin() as db:
            row = db.get(NiftyDiscordSettings, USER)
            row.configuration = {
                **row.configuration,
                "authorized_users": [],
                "authorized_roles": [],
            }
    transport = Mock()
    transport.edit_private_report.return_value = {
        "outcome": "DELIVERED",
        "code": "PRIVATE_REPORT_ACCEPTED",
    }
    NotificationWorker(store, USER, transport=transport, clock=lambda: NOW).tick()
    attachment = transport.edit_private_report.call_args.args[3]
    assert (attachment is not None) is attached
    if attached:
        assert attachment[1] == data and attachment[2] == "application/pdf"
    assert store.report("other", 1) is None
    assert store.notification_health(USER, NOW)["private_report_counts"] == {"DELIVERED": 1}


def test_private_report_429_reschedules_only_until_expiry(store):
    configured(store)
    command_response(
        store, USER, DiscordSettings.model_validate(configuration()), report_interaction(), NOW
    )
    claim = store.claim_discord_report(USER, NOW)
    store.finish_discord_report(
        USER, claim, {"outcome": "RETRY", "code": "RATE_LIMIT", "retry_after": 3}, NOW
    )
    assert store.claim_discord_report(USER, NOW + timedelta(seconds=2)) is None
    retry = store.claim_discord_report(USER, NOW + timedelta(seconds=3))
    assert retry["id"] == claim["id"] and retry["claim_token"] != claim["claim_token"]
    assert not store.finish_discord_report(USER, claim, {"outcome": "DELIVERED"}, NOW)
    store.finish_discord_report(
        USER,
        retry,
        {"outcome": "RETRY", "code": "RATE_LIMIT", "retry_after": 900},
        NOW + timedelta(seconds=3),
    )
    assert store.claim_discord_report(USER, NOW + timedelta(minutes=15)) is None
    assert store.notification_health(USER, NOW)["private_report_counts"] == {"EXPIRED": 1}


@pytest.mark.parametrize(
    "status,outcome", [(429, "RETRY"), (500, "AMBIGUOUS"), (403, "DEAD"), (204, "AMBIGUOUS")]
)
def test_private_transport_never_blindly_retries_unknown_acknowledgements(status, outcome):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json={"retry_after": 1})
        )
    ) as client:
        assert (
            DiscordREST("fake-token", client).edit_private_report(
                APP, "PRIVATE_TOKEN", {"content": "test"}
            )["outcome"]
            == outcome
        )


def test_dead_letter_inspection_pages_all_owned_failures_and_keeps_controls_private(client, store):
    from database.nifty_algo_db import NiftyNotificationDelivery
    from test.test_nifty_algo_safety_center import login

    url = "/api/nifty-algo/discord/failures"
    assert client.get(url, headers={"Accept": "application/json"}).status_code == 401
    with store.sessions.begin() as db:
        for i in range(55):
            db.add(
                NiftyNotificationDelivery(
                    user_id=USER,
                    event_id=1000 + i,
                    destination="critical-alerts",
                    status="DEAD",
                    envelope={"kind": "test_notification"},
                    attempts=0,
                    next_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
    login(client)
    first = client.get(url)
    assert first.status_code == 200 and "no-store" in first.headers["Cache-Control"]
    page = first.json["data"]
    assert len(page["items"]) == 50 and page["next_before"]
    second = client.get(url + f"?before={page['next_before']}").json["data"]
    assert len(second["items"]) == 5 and second["next_before"] is None
    assert not {r["id"] for r in page["items"]} & {r["id"] for r in second["items"]}
    assert client.get(url + "?before=0").status_code == 400
    assert client.get(url + "?user=other").status_code == 400
    assert client.get(url + "?before=1&before=2").status_code == 400
    login(client, "other")
    assert client.get(url).json["data"]["items"] == []


def test_dead_letter_replay_api_requires_csrf_owner_and_exact_failed_revision(client, store):
    from test.test_nifty_algo_safety_center import login

    configured(store)
    critical(store)
    store.project_discord_notifications(USER, NOW)
    claim = store.claim_notification(USER, now=NOW)
    store.notification_result(USER, claim, {"outcome": "DEAD", "code": "HTTP_403"}, NOW)
    url = f"/api/nifty-algo/discord/deliveries/{claim['id']}/replay"
    body = {"confirm": "REPLAY_DEFINITELY_FAILED", "expected_attempts": 1}
    headers = login(client)
    assert client.post(url, json=body).status_code == 400
    assert (
        client.post(url, json={**body, "expected_attempts": 0}, headers=headers).status_code == 409
    )
    assert client.post(url, json=body, headers=headers).json["data"]["status"] == "PENDING"
    assert client.post(url, json=body, headers=headers).status_code == 409
    other = login(client, "other")
    assert client.post(url, json=body, headers=other).status_code == 404


def test_signed_opaque_continuation_token_is_encrypted_and_encoded_as_one_path_segment(store):
    configured(store)
    request = report_interaction()
    request["token"] = "opaque+token/with=padding"
    assert (
        command_response(
            store, USER, DiscordSettings.model_validate(configuration()), request, NOW
        )["type"]
        == 5
    )
    claim = store.claim_discord_report(USER, NOW)
    assert claim["token"] == request["token"]
    seen = []

    def respond(request):
        seen.append(request.url.raw_path)
        return httpx.Response(200, json={"id": "400000000000000001"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        assert (
            DiscordREST("fake-token", transport).edit_private_report(
                APP, claim["token"], {"content": "test"}
            )["outcome"]
            == "DELIVERED"
        )
    assert b"opaque%2Btoken%2Fwith%3Dpadding/messages/@original" in seen[0]
    assert b"opaque+token/with=padding" not in seen[0]


def test_monthly_report_selection_is_not_truncated_by_newer_daily_history(store):
    from database.nifty_algo_db import NiftyReport

    configured(store)
    with store.sessions.begin() as db:
        monthly = NiftyReport(
            user_id=USER,
            kind="MONTH_END",
            period_key="2026-10",
            generation_status="GENERATED",
            generated_at=NOW - timedelta(days=20),
            created_at=NOW - timedelta(days=20),
            updated_at=NOW - timedelta(days=20),
        )
        db.add(monthly)
        db.flush()
        expected = monthly.id
        for i in range(101):
            db.add(
                NiftyReport(
                    user_id=USER,
                    kind="DAILY",
                    period_key=(NOW - timedelta(days=i)).date().isoformat(),
                    generation_status="GENERATED",
                    generated_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
    request = report_interaction()
    request["data"]["options"][0]["name"] = "monthly"
    assert (
        command_response(
            store, USER, DiscordSettings.model_validate(configuration()), request, NOW
        )["type"]
        == 5
    )
    assert store.claim_discord_report(USER, NOW)["payload"]["report_id"] == expected
