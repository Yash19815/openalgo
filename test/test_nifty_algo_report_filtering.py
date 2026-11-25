"""Large deterministic selector payloads must not inflate report memory."""

import tracemalloc
from datetime import timedelta

import pytest
from sqlalchemy import select

from database.nifty_algo_db import NiftyEvent
from services.nifty_algo import reports
from test.test_nifty_algo_phase6 import (
    BEFORE_CLOSE,
    SESSION,
    USER,
    legacy_calendar,
)
from test.test_nifty_algo_phase6 import store as report_store


@pytest.fixture
def store(request):
    return request.getfixturevalue("report_store")


def test_report_ignores_large_unused_payloads_without_changing_content(
    store, monkeypatch, record_property
):
    now = BEFORE_CLOSE
    kinds = (
        "entry_rejected",
        "data_blocked",
        "kill-switch",
        "start",
        "pause",
        "stop",
        *reports.LOCK_EVENTS,
        "safety_incident",
        "safety_acknowledged",
        "safety_resolved",
        "PROFIT_LOCK_ACTIVATED",
        "PROFIT_FLOOR_UNREPRESENTABLE",
        "paper_fill_verified",
    )
    with store.sessions.begin() as db:
        db.add_all(
            [
                NiftyEvent(
                    user_id=USER,
                    kind="contract_selector:ranked",
                    payload={"large_unused": "x" * 16384},
                    created_at=now,
                )
                for _ in range(2500)
            ]
        )
        db.add_all(
            [
                NiftyEvent(
                    user_id=USER,
                    kind=kind,
                    payload={"reason": "OFFLINE", "reasons": ["OFFLINE"]},
                    created_at=now,
                )
                for kind in kinds
            ]
        )
    tracemalloc.start()
    filtered = store.report_inputs(USER, now - timedelta(hours=12), now + timedelta(hours=12))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    record_property("filtered_peak_bytes", peak)
    assert [e["kind"] for e in filtered["events"]] == list(kinds)
    assert peak < 8 * 1024 * 1024
    actual = reports.daily_content(store, USER, SESSION.isoformat())
    original = store.report_inputs
    tracemalloc.start()
    with store.sessions() as db:
        all_events = [
            {"kind": e.kind, "payload": e.payload}
            for e in db.scalars(
                select(NiftyEvent).where(NiftyEvent.user_id == USER).order_by(NiftyEvent.id)
            )
        ]
    _, baseline_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    record_property("historical_event_query_peak_bytes", baseline_peak)
    record_property("ignored_selector_payload_rows", 2500)
    assert baseline_peak > peak * 5

    def historical_inputs(*args, **kwargs):
        return original(*args, **kwargs) | {"events": all_events}

    monkeypatch.setattr(store, "report_inputs", historical_inputs)
    assert reports.daily_content(store, USER, SESSION.isoformat()) == actual


def test_report_event_policy_covers_every_kind_the_report_reads():
    from services.nifty_algo.report_policy import REPORT_EVENT_KINDS

    consumed = {"entry_rejected", "data_blocked", "kill-switch"}
    consumed |= set(reports.LOCK_EVENTS) | set(reports.CONTROL_EVENTS)
    consumed |= {
        "safety_incident",
        "safety_acknowledged",
        "safety_resolved",
        "PROFIT_LOCK_ACTIVATED",
        "PROFIT_FLOOR_UNREPRESENTABLE",
        "paper_fill_verified",
    }
    assert consumed <= set(REPORT_EVENT_KINDS)
