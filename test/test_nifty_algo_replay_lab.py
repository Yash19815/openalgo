"""Evidence playback is causal and cannot manufacture full-execution results."""

from datetime import timedelta

import pytest
from sqlalchemy import update

from database.nifty_algo_db import NiftyResearchResult
from services.nifty_algo import research
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.models import PCR
from services.nifty_algo.replay_lab import inspect_experiment, replay_page
from test.test_nifty_algo_experiments import NOW, dataset, define
from test.test_nifty_algo_experiments import store as store
from test.test_nifty_algo_research import START, bars
from test.test_nifty_algo_safety_center import client as client
from test.test_nifty_algo_safety_center import login

OWNER = "recorder-owner"


def experiment(store):
    return define(store, dataset(store))


def test_inspection_reports_actual_coverage_refuses_all_financial_variants_and_is_immutable(store):
    definition = experiment(store)
    before = store.read(OWNER)
    result = inspect_experiment(store, OWNER, definition["id"])
    assert result["samples"] == 1 and result["performance"] is None
    assert result["fidelity"] == "QUOTE_EVIDENCE_ONLY"
    assert "HISTORICAL_PCR" in result["full_execution_refused"]
    assert len(result["variants"]) == 3
    assert all(row["performance"] is None for row in result["variants"])
    stored = store.save_research_inspection(OWNER, definition["id"], NOW)
    assert store.save_research_inspection(OWNER, definition["id"], NOW) == stored
    assert store.research_inspection(OWNER, definition["id"]) == stored
    assert store.research_inspection("other", definition["id"]) is None
    assert store.read(OWNER) == before


def test_playback_uses_receipt_availability_and_cannot_skip_into_future(store):
    definition = experiment(store)
    early = replay_page(store, OWNER, definition["id"], as_of=NOW - timedelta(seconds=50))
    assert early["items"] == []
    full = replay_page(store, OWNER, definition["id"], as_of=NOW)
    assert len(full["items"]) == 1 and full["execution_eligible"] is False
    with pytest.raises(ValueError, match="ahead"):
        replay_page(store, OWNER, definition["id"], as_of=NOW - timedelta(seconds=50), after=1)
    assert replay_page(store, OWNER, definition["id"], as_of=NOW, after=1)["items"] == []
    with pytest.raises(LookupError):
        replay_page(store, "other", definition["id"], as_of=NOW)


def test_corrupt_result_is_not_exposed(store):
    definition = experiment(store)
    store.save_research_inspection(OWNER, definition["id"], NOW)
    with store.sessions.begin() as db:
        db.execute(update(NiftyResearchResult).values(payload={"performance": "invented"}))
    with pytest.raises(ValueError, match="integrity"):
        store.research_inspection(OWNER, definition["id"])


def test_inspection_and_replay_api_require_session_csrf_and_owner(client, store):
    definition = experiment(store)
    base = f"/api/nifty-algo/research/experiments/{definition['id']}"
    headers = login(client, OWNER)
    assert (
        client.post(base + "/inspection", json={"confirm": "INSPECT_EVIDENCE_ONLY"}).status_code
        == 400
    )
    result = client.post(
        base + "/inspection", json={"confirm": "INSPECT_EVIDENCE_ONLY"}, headers=headers
    )
    assert result.status_code == 200
    assert client.get(base + "/inspection").json["data"]["result"]["performance"] is None
    page = client.get(base + "/replay", query_string={"as_of": NOW.isoformat(), "after": "0"})
    assert page.status_code == 200 and len(page.json["data"]["items"]) == 1
    assert (
        client.get(
            base + "/replay", query_string={"as_of": NOW.isoformat(), "after": "0", "run_live": 1}
        ).status_code
        == 400
    )
    login(client, "other")
    assert (
        client.get(
            base + "/replay", query_string={"as_of": NOW.isoformat(), "after": "0"}
        ).status_code
        == 404
    )


def test_signal_replay_waits_for_pcr_receipt_and_never_uses_future_observation(monkeypatch):
    class SpyRules:
        def evaluate(self, bars, higher, pcr, now, *args):
            return {"at": now, "pcr": pcr.value if pcr else None}

    monkeypatch.setattr(research, "Rules", SpyRules)
    pcr = PCR(
        value=2,
        kind="OI",
        scope="TEST_FIXTURE",
        source_time=START + timedelta(minutes=20),
        coverage=1,
        verified=True,
    )
    kwargs = {
        "session_opens": {START.date(): START},
        "pcr_observations": [{"pcr": pcr, "available_at": START + timedelta(minutes=21)}],
    }
    result = research.signal_study(
        bars(30), StrategyConfig(), START, START + timedelta(minutes=31), **kwargs
    )
    assert all(
        row["pcr"] is None
        for row in result["decisions"]
        if row["at"] <= START + timedelta(minutes=20)
    )
    assert result["decisions"][-1]["pcr"] == 2
    assert not result["indicator_coverage"]["complete_five_indicator_evidence"]
    assert result["performance"] is None


def test_signal_replay_refuses_reordering_and_missing_availability_evidence():
    with pytest.raises(ValueError, match="Out-of-order"):
        research.signal_study(
            list(reversed(bars(30))),
            StrategyConfig(),
            START,
            START + timedelta(minutes=31),
            session_opens={START.date(): START},
        )
    with pytest.raises(ValueError, match="availability"):
        research.signal_study(
            bars(30),
            StrategyConfig(),
            START,
            START + timedelta(minutes=31),
            session_opens={START.date(): START},
            pcr_observations=[{}],
        )
