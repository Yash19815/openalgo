"""Recording controls never accept caller-supplied feed evidence or trading authority."""

from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import Mock

import pytest
from sqlalchemy import event

from test.test_nifty_algo_paper_executor import USER
from test.test_nifty_algo_recording import quote
from test.test_nifty_algo_safety_center import client as client
from test.test_nifty_algo_safety_center import login
from test.test_nifty_algo_safety_center import store as store

URL = "/api/nifty-algo/research/recordings"
BODY = {"duration_minutes": 60, "max_observations": 500, "confirm": "RESEARCH_ONLY"}


def create(client, headers):
    response = client.post(URL, json=BODY, headers=headers)
    assert response.status_code == 201
    return response.json["data"]


def test_recording_controls_require_signed_session_and_csrf(client):
    assert client.get(URL, headers={"Accept": "application/json"}).status_code == 401
    headers = login(client)
    assert client.post(URL, json=BODY).status_code == 400
    dataset = create(client, headers)
    seal = f"{URL}/{dataset['id']}/seal"
    assert client.post(seal, json={"expected_count": 0, "confirm": "SEAL_ONLY"}).status_code == 400


def test_recording_creation_freezes_configuration_without_changing_paper_state(client, store):
    headers = login(client)
    before = store.read(USER)
    dataset = create(client, headers)
    assert dataset["mode"] == "RESEARCH"
    assert dataset["execution_eligible"] is False
    assert dataset["configuration_id"] == before["configuration_id"]
    assert dataset["max_observations"] == 500
    assert dataset["count"] == 0
    assert datetime.fromisoformat(dataset["ends_at"]) - datetime.fromisoformat(
        dataset["starts_at"]
    ) == timedelta(hours=1)
    assert store.read(USER) == before
    listing = client.get(URL)
    assert listing.json["data"]["items"] == [dataset]
    assert listing.json["data"]["capture_status"] == "NOT_CONNECTED"
    assert listing.headers["Cache-Control"] == "private, no-store"
    assert client.get(f"{URL}/{dataset['id']}").json["data"]["items"] == []


def test_native_recording_opt_in_never_starts_feed_or_changes_trading_state(
    client, store, monkeypatch
):
    import services.market_data_service as cache
    import services.websocket_service as sockets

    connection = Mock(side_effect=AssertionError("recording controls must not connect"))
    market = Mock(side_effect=AssertionError("recording controls must not initialize cache"))
    monkeypatch.setattr(sockets, "get_websocket_connection", connection)
    monkeypatch.setattr(cache, "get_market_data_service", market)
    headers = login(client)
    before = store.read(USER)
    assert client.post(URL, json={**BODY, "native_capture": True}).status_code == 400
    response = client.post(URL, json={**BODY, "native_capture": True}, headers=headers)
    assert response.status_code == 201
    manifest = response.json["data"]
    assert manifest["capture"] == {"scope": None, "scope_sha256": None}
    assert manifest["execution_eligible"] is False
    assert manifest["count"] == 0
    assert store.read(USER) == before
    listing = client.get(URL).json["data"]
    assert listing["capture_status"] == "NATIVE_CAPTURE_REQUESTED"
    assert listing["items"] == [manifest]
    assert not connection.called and not market.called
    assert "nifty_algo_runners" not in client.application.extensions


def test_explicit_false_keeps_legacy_recording_unadopted(client):
    headers = login(client)
    response = client.post(URL, json={**BODY, "native_capture": False}, headers=headers)
    assert response.status_code == 201
    assert response.json["data"]["capture"] is None
    assert client.get(URL).json["data"]["capture_status"] == "NOT_CONNECTED"


@pytest.mark.parametrize("value", [None, 0, 1, "true", "false", [], {}])
def test_native_capture_flag_requires_json_boolean(client, value):
    headers = login(client)
    assert (
        client.post(URL, json={**BODY, "native_capture": value}, headers=headers).status_code == 400
    )
    assert client.get(URL).json["data"]["items"] == []


@pytest.mark.parametrize(
    "change",
    [
        {"duration_minutes": True},
        {"duration_minutes": 0},
        {"duration_minutes": 1441},
        {"duration_minutes": "60"},
        {"max_observations": False},
        {"max_observations": 10001},
        {"confirm": "LIVE"},
        {"user_id": USER},
        {"source": "NATIVE_FEED"},
        {"observations": [quote()]},
    ],
)
def test_recording_creation_rejects_unknown_fields_and_invalid_limits(client, change):
    headers = login(client)
    assert client.post(URL, json={**BODY, **change}, headers=headers).status_code == 400
    assert client.get(URL).json["data"]["items"] == []


def test_recording_reads_and_seal_are_owner_scoped(client, store):
    headers = login(client)
    dataset = create(client, headers)
    login(client, "other-owner")
    assert client.get(URL).json["data"]["items"] == []
    assert client.get(f"{URL}/{dataset['id']}").status_code == 404
    headers = login(client, "other-owner")
    assert (
        client.post(
            f"{URL}/{dataset['id']}/seal",
            json={"expected_count": 0, "confirm": "SEAL_ONLY"},
            headers=headers,
        ).status_code
        == 404
    )
    assert store.recording_page(USER, dataset["id"])["manifest"]["status"] == "RECORDING"


@pytest.mark.parametrize(
    "query",
    [
        "limit=101",
        "limit=0",
        "limit=true",
        "after=-1",
        "after=10001",
        "as_of=2026-01-01T00:00:00",
        "as_of=invalid",
        "user_id=other",
        "limit=1&limit=100",
        "as_of=",
    ],
)
def test_recording_page_refuses_unbounded_ambiguous_or_naive_queries(client, query):
    headers = login(client)
    dataset = create(client, headers)
    assert client.get(f"{URL}/{dataset['id']}?{query}").status_code == 400


def test_recording_api_pages_preserve_as_of_and_seal_fences_append_count(client, store):
    headers = login(client)
    now = datetime.now(UTC)
    dataset = store.create_recording(
        USER, now - timedelta(minutes=1), now + timedelta(minutes=1), now
    )
    rows = [
        quote(source=now - timedelta(seconds=10), available=now - timedelta(seconds=8)),
        quote(source=now - timedelta(seconds=12), available=now - timedelta(seconds=2)),
    ]
    store.append_recording(USER, dataset["id"], rows, now, expected_count=0)
    page = client.get(
        f"{URL}/{dataset['id']}",
        query_string={"as_of": (now - timedelta(seconds=5)).isoformat(), "limit": 1},
    )
    assert [row["sequence"] for row in page.json["data"]["items"]] == [1]
    assert page.json["data"]["next_after"] == 1
    assert page.json["data"]["manifest"]["execution_eligible"] is False
    seal = f"{URL}/{dataset['id']}/seal"
    assert (
        client.post(
            seal, json={"expected_count": 0, "confirm": "SEAL_ONLY"}, headers=headers
        ).status_code
        == 409
    )
    result = client.post(seal, json={"expected_count": 2, "confirm": "SEAL_ONLY"}, headers=headers)
    assert result.status_code == 200
    assert result.json["data"]["status"] == "SEALED"
    again = client.post(seal, json={"expected_count": 2, "confirm": "SEAL_ONLY"}, headers=headers)
    assert again.json == result.json


def test_recording_reads_do_not_write_or_leak_connections(client, store):
    headers = login(client)
    dataset = create(client, headers)
    statements, connections = [], set()

    def statement(connection, cursor, sql, parameters, context, many):
        if sql.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            statements.append(sql)

    def checkout(connection, record, proxy):
        connections.add(id(connection))

    def checkin(connection, record):
        connections.discard(id(connection))

    event.listen(store.engine, "before_cursor_execute", statement)
    event.listen(store.engine, "checkout", checkout)
    event.listen(store.engine, "checkin", checkin)
    try:
        for _ in range(100):
            assert client.get(URL).status_code == 200
            assert client.get(f"{URL}/{dataset['id']}?limit=1").status_code == 200
            assert client.get(f"{URL}/absent").status_code == 404
            assert connections == set()
        assert statements == []
    finally:
        event.remove(store.engine, "before_cursor_execute", statement)
        event.remove(store.engine, "checkout", checkout)
        event.remove(store.engine, "checkin", checkin)


@pytest.mark.parametrize("endpoint", ["", "/seal"])
def test_recording_control_body_has_small_request_bound(client, endpoint):
    headers = login(client)
    dataset = create(client, headers)
    url = URL if not endpoint else f"{URL}/{dataset['id']}{endpoint}"
    response = client.post(
        url,
        data='{"untrusted":"' + "x" * 4096 + '"}',
        content_type="application/json",
        headers=headers,
    )
    assert response.status_code == 413
    assert response.json == {"status": "error", "message": "Recording request too large"}
    assert response.headers["Cache-Control"] == "private, no-store"


def test_recording_control_bounds_unknown_length_stream_after_csrf(client):
    headers = login(client)
    stream = BytesIO(b'{"untrusted":"' + b"x" * 4096 + b'"}')
    response = client.post(
        URL,
        content_type="application/json",
        headers=headers,
        environ_overrides={
            "CONTENT_LENGTH": "",
            "wsgi.input_terminated": True,
            "wsgi.input": stream,
        },
    )
    assert response.status_code == 413
    assert stream.tell() <= 2049
    assert client.get(URL).json["data"]["items"] == []


@pytest.mark.parametrize("body", [b"", b"{", b"\xff", b"[" * 1200])
def test_recording_control_rejects_malformed_or_deep_json(client, body):
    headers = login(client)
    response = client.post(URL, data=body, content_type="application/json", headers=headers)
    assert response.status_code == 400
    assert client.get(URL).json["data"]["items"] == []


def test_recording_page_refuses_timezone_conversion_overflow(client):
    headers = login(client)
    dataset = create(client, headers)
    response = client.get(
        f"{URL}/{dataset['id']}", query_string={"as_of": "0001-01-01T00:00:00+14:00"}
    )
    assert response.status_code == 400
    assert response.json["message"] == "Invalid recording query"


@pytest.mark.parametrize(
    "body",
    [
        {},
        None,
        [],
        {"expected_count": 0},
        {"expected_count": 0, "confirm": "RESUME"},
        {"expected_count": True, "confirm": "SEAL_ONLY"},
        {"expected_count": -1, "confirm": "SEAL_ONLY"},
        {"expected_count": 10001, "confirm": "SEAL_ONLY"},
        {"expected_count": 0, "confirm": "SEAL_ONLY", "user_id": USER},
    ],
)
def test_recording_seal_rejects_malformed_or_untrusted_fields(client, body):
    headers = login(client)
    dataset = create(client, headers)
    response = client.post(f"{URL}/{dataset['id']}/seal", json=body, headers=headers)
    assert response.status_code == 400
    assert client.get(f"{URL}/{dataset['id']}").json["data"]["manifest"]["status"] == "RECORDING"


def test_recording_quota_is_reported_without_echoing_validation_details(client):
    headers = login(client)
    identifiers = {create(client, headers)["id"] for _ in range(20)}
    rejected = client.post(URL, json=BODY, headers=headers)
    assert rejected.status_code == 400
    assert rejected.json["message"] == "Research recording limit reached"
    assert {row["id"] for row in client.get(URL).json["data"]["items"]} == identifiers


def test_recording_http_api_does_not_accept_external_evidence(client):
    headers = login(client)
    dataset = create(client, headers)
    response = client.post(
        f"{URL}/{dataset['id']}",
        json={"observations": [quote()], "expected_count": 0},
        headers=headers,
    )
    assert response.status_code == 405
    assert client.get(f"{URL}/{dataset['id']}").json["data"]["manifest"]["count"] == 0
