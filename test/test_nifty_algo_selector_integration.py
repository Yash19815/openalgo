"""Selector audit reads remain owner-scoped and separate from order authority."""

from datetime import timedelta

import pytest

from database.nifty_algo_db import NiftyOrder, NiftyStore
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.paper_executor import NiftyPaperExecutor, OrderRefused
from services.nifty_algo.runner import NiftyRunner
from test.test_nifty_algo_paper_executor import (
    NOW,
    USER,
    FakeMarket,
    buy_intent,
    executor,
    instrument,
    running,
)
from test.test_nifty_algo_pipeline import pipeline
from test.test_nifty_algo_safety_center import client as client
from test.test_nifty_algo_safety_center import login
from test.test_nifty_algo_safety_center import store as store


def test_selector_event_query_filters_before_limit_and_survives_restart(store):
    store.record_event(USER, "contract_selector:PAPER", {"decision_id": "own"}, NOW)
    for _ in range(101):
        store.record_event(USER, "other", {}, NOW)
    store.record_event("another-user", "contract_selector:PAPER", {"decision_id": "private"}, NOW)
    store.record_event(USER, "contract_selector:SHADOW", {"decision_id": "shadow"}, NOW)
    reopened = NiftyStore(store.engine)
    rows = reopened.events(USER, kind="contract_selector:PAPER", limit=1)
    assert [row["payload"]["decision_id"] for row in rows] == ["own"]
    assert len(reopened.events(USER)) == 100


@pytest.mark.parametrize("limit", [0, 101, True, -1])
def test_event_queries_reject_unbounded_or_invalid_limits(store, limit):
    with pytest.raises(ValueError, match="Event limit"):
        store.events(USER, limit=limit)


def test_selector_api_requires_session_and_never_reads_another_owner(client, store):
    url = "/api/nifty-algo/selector"
    assert client.get(url, headers={"Accept": "application/json"}).status_code == 401
    login(client)
    assert client.get(url).json["data"] is None
    store.record_event(USER, "contract_selector:PAPER", {"decision_id": "own"}, NOW)
    store.record_event("another-user", "contract_selector:PAPER", {"decision_id": "private"}, NOW)
    store.record_event(USER, "contract_selector:SHADOW", {"decision_id": "shadow"}, NOW)
    assert client.get(url + "?user=another-user").json["data"]["payload"]["decision_id"] == "own"
    assert client.get(url + "?mode=SHADOW").json["data"]["payload"]["decision_id"] == "shadow"
    assert client.get(url + "?mode=LIVE").status_code == 400


@pytest.mark.parametrize("mode", ["PAPER", "SHADOW"])
@pytest.mark.parametrize("liquid", [True, False])
def test_runner_records_selection_or_rejections_without_order_authority(store, mode, liquid):
    native = pipeline()
    if not liquid:
        native.market_data.bid_size = native.market_data.ask_size = 0
    executor = NiftyPaperExecutor(store, USER, market_data=native.market_data)
    runner = NiftyRunner(store, USER, native=native, executor=executor, clock=lambda: NOW)
    decision = {"side": "CE", "decision_id": "offline-selector"}
    try:
        if liquid:
            candidates, _ = runner._entry_candidates(decision, StrategyConfig(), NOW, mode=mode)
            assert [item.token for item in candidates] == ["ce"]
        else:
            with pytest.raises(OrderRefused, match="CONTRACT_LIQUIDITY_UNAVAILABLE"):
                runner._entry_candidates(decision, StrategyConfig(), NOW, mode=mode)
        rows = store.events(USER, kind=f"contract_selector:{mode}", limit=1)
        evidence = rows[0]["payload"]
        assert evidence["decision_id"] == decision["decision_id"]
        assert evidence["mode"] == mode
        assert evidence["ranked_tokens"] == (["ce"] if liquid else [])
        assert evidence["candidates"][0]["reasons"] == ([] if liquid else ["DEPTH_INSUFFICIENT"])
        assert store.pending_orders(USER) == []
    finally:
        runner.close()


def test_admission_rejects_conflicting_full_identity_not_just_token_and_symbol(store):
    running(store)
    contract = instrument()
    conflicting = contract.model_copy(update={"strike": contract.strike - 50})
    with pytest.raises(OrderRefused, match="INSTRUMENT_IDENTITY_MISMATCH"):
        executor(store).admit(buy_intent(instrument=contract, candidates=[conflicting]))
    assert store.pending_orders(USER) == []


def test_admission_rejects_conflicting_identity_in_fallback_candidates(store):
    running(store)
    contract = instrument()
    conflicting = contract.model_copy(update={"lot_size": contract.lot_size * 2})
    with pytest.raises(OrderRefused, match="INSTRUMENT_IDENTITY_MISMATCH"):
        executor(store).admit(buy_intent(candidates=[contract, conflicting]))
    assert store.pending_orders(USER) == []


def test_admission_preserves_candidate_evidence_for_fill_revalidation(store):
    running(store)
    intent = buy_intent()
    order, created = executor(store).admit(intent)
    assert created
    assert order["payload"]["candidate_metadata"] == intent["candidate_metadata"]


def test_recorded_atm_hint_cannot_override_current_otm_at_fill(store):
    running(store)
    market = FakeMarket()
    intent = buy_intent()
    exe = executor(store, market=market, config=StrategyConfig(latency_ms=1))
    order, _ = exe.admit(intent)
    with store.sessions.begin() as db:
        row = db.get(NiftyOrder, (USER, order["order_id"]))
        row.payload = {**row.payload, "candidate_metadata": intent["candidate_metadata"]}
    market.index_ltp = "21900"
    fills = exe.process(now=NOW + timedelta(seconds=1))
    assert [(row["status"], row["reason"]) for row in fills] == [("REJECTED", "OTM_PROHIBITED")]
    assert store.positions(USER) == []


@pytest.mark.parametrize(
    ("spot", "reason"),
    [("21900", "OTM_PROHIBITED"), ("0", "SPOT_REFERENCE_UNAVAILABLE")],
)
def test_admission_revalidates_current_spot_at_durable_write(store, monkeypatch, spot, reason):
    running(store)
    market = FakeMarket()
    exe = executor(store, market=market)
    original = store.admit_order

    def competing_update(user, order, **kwargs):
        market.index_ltp = spot
        return original(user, order, **kwargs)

    monkeypatch.setattr(store, "admit_order", competing_update)
    with pytest.raises(OrderRefused, match=reason):
        exe.admit(buy_intent())
    assert store.pending_orders(USER) == []
    assert store.positions(USER) == []


def test_fill_rejects_order_symbol_that_differs_from_frozen_contract(store):
    running(store)
    exe = executor(store, config=StrategyConfig(latency_ms=1))
    order, _ = exe.admit(buy_intent())
    with store.sessions.begin() as db:
        db.get(NiftyOrder, (USER, order["order_id"])).symbol = "DIFFERENT_CONTRACT"
    with pytest.raises(ValueError, match="Final execution instrument failed validation"):
        exe.process(now=NOW + timedelta(seconds=1))
    assert store.positions(USER) == []
    assert store.pending_orders(USER)[0]["status"] == "PENDING"


def test_fill_boundary_requires_current_spot_even_when_caller_omits_it(store, monkeypatch):
    running(store)
    exe = executor(store, config=StrategyConfig(latency_ms=1))
    exe.admit(buy_intent())
    original = store.fill

    def omit_spot(*args, **kwargs):
        kwargs.pop("spot")
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "fill", omit_spot)
    with pytest.raises(ValueError, match="Current spot required for entry fill"):
        exe.process(now=NOW + timedelta(seconds=1))
    assert store.positions(USER) == []
    assert store.pending_orders(USER)[0]["status"] == "PENDING"


@pytest.mark.parametrize("mode", ["PAPER", "SHADOW"])
@pytest.mark.parametrize(
    ("fault", "reason"),
    [
        ("spot", "SPOT_REFERENCE_UNAVAILABLE"),
        ("master", "CONTRACT_METADATA_UNAVAILABLE"),
        ("invalid-master", "CONTRACT_EVIDENCE_UNAVAILABLE"),
        ("greeks", "GREEKS_UNAVAILABLE"),
        ("itm", "ITM_STRIKE_UNAVAILABLE"),
    ],
)
def test_selector_records_failures_before_ranking_without_inventing_candidates(
    store, monkeypatch, mode, fault, reason
):
    native = pipeline()
    config = StrategyConfig()
    if fault == "spot":
        monkeypatch.setattr(native, "get_market", lambda: {})
    elif fault == "master":
        monkeypatch.setattr(native, "instruments", lambda now: [])
    elif fault == "invalid-master":

        def invalid_master(now):
            raise ValueError("Provider detail must not become persisted evidence")

        monkeypatch.setattr(native, "instruments", invalid_master)
    elif fault == "greeks":
        config = StrategyConfig(selection="DELTA")
    elif fault == "itm":
        config = StrategyConfig(selection="ITM")
    exe = NiftyPaperExecutor(store, USER, market_data=native.market_data)
    runner = NiftyRunner(store, USER, native=native, executor=exe, clock=lambda: NOW)
    try:
        with pytest.raises((OrderRefused, ValueError)):
            runner._entry_candidates(
                {"side": "CE", "decision_id": "failed-selector"}, config, NOW, mode=mode
            )
        rows = NiftyStore(store.engine).events(USER, kind=f"contract_selector:{mode}", limit=1)
        assert len(rows) == 1
        report = rows[0]["payload"]
        assert report["status"] == "UNAVAILABLE"
        assert report["reasons"] == [reason]
        assert report["configuration_id"] == config.version_id
        assert report["decision_id"] == "failed-selector"
        assert report["mode"] == mode
        assert report["candidates"] == report["ranked_tokens"] == []
        assert report["atm_strike"] is report["expiry"] is None
        assert store.pending_orders(USER) == []
    finally:
        runner.close()
