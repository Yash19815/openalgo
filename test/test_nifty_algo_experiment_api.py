"""Authenticated, definition-only research controls never alter trading state."""

from datetime import timedelta
from io import BytesIO

import pytest
from sqlalchemy import event, update

from database.nifty_algo_db import NiftyResearchExperiment, NiftyState
from services.nifty_algo.config import StrategyConfig
from test.test_nifty_algo_paper_executor import USER
from test.test_nifty_algo_recording import NOW, quote
from test.test_nifty_algo_safety_center import client as client
from test.test_nifty_algo_safety_center import login
from test.test_nifty_algo_safety_center import store as store

URL = "/api/nifty-algo/research/experiments"


def sealed(store):
    before = store.read(USER)
    store.change(USER, before["revision"], configuration=StrategyConfig(adx_min=31))
    manifest = store.create_recording(
        USER, NOW - timedelta(minutes=1), NOW + timedelta(minutes=1), NOW
    )
    store.append_recording(USER, manifest["id"], [quote()], NOW, expected_count=0)
    return store.seal_recording(USER, manifest["id"], NOW, expected_count=1)


def body(manifest):
    return {
        "recording_id": manifest["id"],
        "expected_count": manifest["count"],
        "expected_sha256": manifest["content_sha256"],
        "train_end": (NOW - timedelta(seconds=40)).isoformat(),
        "validation_end": (NOW - timedelta(seconds=20)).isoformat(),
        "configuration_overrides": {"adx_min": 35},
        "confirm": "DEFINE_ONLY",
    }


def test_experiment_controls_freeze_recording_settings_not_active_settings(client, store):
    headers = login(client)
    manifest = sealed(store)
    state = store.read(USER)
    store.change(USER, state["revision"], configuration=StrategyConfig(adx_min=40, atr_period=20))
    before = store.read(USER)
    response = client.post(URL, json=body(manifest), headers=headers)
    assert response.status_code == 201
    result = response.json["data"]
    assert result["status"] == "DEFINED"
    assert result["execution_eligible"] is False
    assert result["performance"] is None
    assert result["snapshot"]["configuration"]["adx_min"] == 35
    assert (
        result["snapshot"]["configuration"]["atr_period"] == manifest["configuration"]["atr_period"]
    )
    assert result["snapshot"]["dataset"] == manifest
    assert store.read(USER) == before
    assert response.headers["Cache-Control"] == "private, no-store"
    detail = client.get(f"{URL}/{result['id']}")
    assert detail.status_code == 200
    assert detail.json["data"] == result
    listing = client.get(URL)
    assert listing.status_code == 200
    assert listing.json["data"]["items"] == [
        {key: result[key] for key in ("id", "sha256", "created_at", "status", "execution_eligible")}
    ]
    assert "snapshot" not in listing.json["data"]["items"][0]


def test_experiment_controls_require_signed_session_and_csrf(client, store):
    assert client.get(URL, headers={"Accept": "application/json"}).status_code == 401
    assert (
        client.get(f"{URL}/{'a' * 32}", headers={"Accept": "application/json"}).status_code == 401
    )
    headers = login(client)
    request = body(sealed(store))
    assert client.post(URL, json=request).status_code == 400
    assert store.experiments(USER) == []
    assert client.post(URL, json=request, headers=headers).status_code == 201


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("confirm", "RUN"),
        ("expected_count", True),
        ("expected_count", -1),
        ("expected_count", 10001),
        ("expected_count", "1"),
        ("expected_sha256", "not-a-hash"),
        ("expected_sha256", None),
        ("recording_id", []),
        ("recording_id", "a" * 33),
        ("configuration_overrides", []),
        ("configuration_overrides", {"broker": "angel"}),
        ("configuration_overrides", {"max_lots": 4}),
        ("configuration_overrides", {"adx_min": "NaN"}),
        ("train_end", NOW.replace(tzinfo=None).isoformat()),
        ("validation_end", "bad-date"),
        ("validation_end", NOW.isoformat()),
        ("user", "other-owner"),
        ("observations", []),
        ("provenance", "verified"),
        ("execution_eligible", True),
    ],
)
def test_invalid_experiment_controls_write_nothing(client, store, field, value):
    headers = login(client)
    request = {**body(sealed(store)), field: value}
    before = store.read(USER)
    assert client.post(URL, json=request, headers=headers).status_code == 400
    assert store.experiments(USER) == []
    assert store.read(USER) == before


def test_experiment_source_identity_and_owner_are_checked(client, store):
    headers = login(client)
    manifest = sealed(store)
    request = body(manifest)
    assert (
        client.post(URL, json={**request, "expected_sha256": "0" * 64}, headers=headers).status_code
        == 400
    )
    assert (
        client.post(URL, json={**request, "expected_count": 0}, headers=headers).status_code == 400
    )
    first = client.post(URL, json=request, headers=headers).json["data"]
    headers = login(client, "other-owner")
    assert client.post(URL, json=request, headers=headers).status_code == 404
    assert client.get(f"{URL}/{first['id']}").status_code == 404
    assert client.get(URL).json["data"]["items"] == []
    with store.sessions() as db:
        assert db.get(NiftyState, "other-owner") is None


@pytest.mark.parametrize("query", ["user=other", "limit=100", "after=0&after=1"])
def test_experiment_queries_are_not_authority(client, store, query):
    headers = login(client)
    request = body(sealed(store))
    result = client.post(URL, json=request, headers=headers).json["data"]
    assert client.get(f"{URL}?{query}").status_code == 400
    assert client.get(f"{URL}/{result['id']}?{query}").status_code == 400
    assert client.post(f"{URL}?{query}", json=request, headers=headers).status_code == 400
    assert len(store.experiments(USER)) == 1


def test_experiment_reads_select_only_and_list_does_not_load_snapshots(client, store):
    headers = login(client)
    result = client.post(URL, json=body(sealed(store)), headers=headers).json["data"]
    statements = []

    def observe(_connection, _cursor, statement, *_):
        statements.append(statement.upper())

    event.listen(store.engine, "before_cursor_execute", observe)
    try:
        listing = client.get(URL)
        assert all("SNAPSHOT" not in statement for statement in statements)
        detail = client.get(f"{URL}/{result['id']}")
    finally:
        event.remove(store.engine, "before_cursor_execute", observe)
    assert listing.status_code == detail.status_code == 200
    assert all(statement.lstrip().startswith("SELECT") for statement in statements)
    assert (
        listing.headers["Cache-Control"] == detail.headers["Cache-Control"] == "private, no-store"
    )
    assert "nifty_algo_runners" not in client.application.extensions


def test_experiment_definition_has_no_mutation_or_execution_routes(client, store):
    headers = login(client)
    result = client.post(URL, json=body(sealed(store)), headers=headers).json["data"]
    for method in (client.put, client.patch, client.delete):
        assert method(f"{URL}/{result['id']}", json={}, headers=headers).status_code == 405
    assert client.post(f"{URL}/{result['id']}/run", json={}, headers=headers).status_code == 404
    assert store.experiment(USER, result["id"]) == result


def test_corrupt_experiment_read_fails_closed_without_returning_snapshot(client, store):
    headers = login(client)
    result = client.post(URL, json=body(sealed(store)), headers=headers).json["data"]
    with store.sessions.begin() as db:
        db.execute(
            update(NiftyResearchExperiment)
            .where(
                NiftyResearchExperiment.user_id == USER, NiftyResearchExperiment.id == result["id"]
            )
            .values(sha256="0" * 64)
        )
    response = client.get(f"{URL}/{result['id']}")
    assert response.status_code == 409
    assert "data" not in response.json
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.parametrize("unknown_length", [False, True])
def test_experiment_control_body_is_bounded_before_decode(client, store, unknown_length):
    headers = login(client)
    arguments = {
        "content_type": "application/json",
        "headers": headers,
        "environ_overrides": {},
    }
    payload = b'{"oversized":"' + b"x" * 2048 + b'"}'
    if unknown_length:
        arguments["environ_overrides"] = {
            "wsgi.input": BytesIO(payload),
            "wsgi.input_terminated": True,
            "CONTENT_LENGTH": "",
        }
    else:
        arguments["data"] = payload
    response = client.post(URL, **arguments)
    assert response.status_code == 413
    assert store.experiments(USER) == []
