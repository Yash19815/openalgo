"""Execution research uses causal fixtures, never a broker or production ledger."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyStore
from services.nifty_algo import execution_replay as replay
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.models import Candle
from services.nifty_algo.selection_scoring import POLICY
from test.test_nifty_algo_paper_executor import instrument
from test.test_nifty_algo_recording_replay import cursor, sealed

NOW = datetime(2026, 11, 19, 5, tzinfo=UTC)
CONFIG = StrategyConfig()
OWNER = "recorder-owner"


@pytest.fixture
def store(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'completion.db'}")
    value = NiftyStore(engine, report_dir=tmp_path / "reports")
    value.initialize()
    value.ensure_user(OWNER)
    yield value
    engine.dispose()


def quote(at, *, bid="164", ask="165", token="token-ce"):
    return {
        "token": token,
        "source_time": at.isoformat(),
        "received_time": at.isoformat(),
        "bid": bid,
        "ask": ask,
        "bid_size": 100,
        "ask_size": 100,
        "volume": 5000,
        "oi": 5000,
        "provider": "DETERMINISTIC_FIXTURE",
    }


def frame(at):
    option = instrument().model_copy(
        update={"master_date": at.date(), "expiry": datetime(2026, 12, 1).date()}
    )
    future = option.model_copy(
        update={"token": "future", "symbol": "NIFTY_FUT", "kind": "FUT", "strike": None}
    )
    calendar = {
        "year": 2026,
        "segment": "NFO",
        "status": "APPROVED",
        "sha256": "a" * 64,
        "approved_at": (at - timedelta(days=20)).isoformat(),
        "entries": [],
    }
    sessions = []
    for i in range(-10, 15):
        day = at.date() + timedelta(days=i)
        start = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=3, minutes=45)
        sessions.append(
            {
                "date": day.isoformat(),
                "status": "TRADING" if day.weekday() < 5 else "WEEKEND",
                "start": start.isoformat(),
                "end": (start + timedelta(hours=6, minutes=15)).isoformat(),
                "calendar_sha256": "a" * 64,
            }
        )
    start = at.replace(hour=3, minute=45, second=0)
    candle = Candle(
        token="future",
        start=start,
        end=start + timedelta(minutes=1),
        timeframe=1,
        open=22000,
        high=22001,
        low=21999,
        close=22000,
        volume=100,
        provenance="TEST_FIXTURE",
    )
    payload = {
        "analysis_instrument": future.model_dump(mode="json"),
        "minute_bars": [candle.model_dump(mode="json")],
        "pcr": {
            "value": 2,
            "kind": "OI",
            "scope": "NIFTY:NFO:2026-12-01:ALL_LISTED_STRIKES",
            "source_time": at.isoformat(),
            "coverage": 1,
            "verified": True,
        },
        "pcr_available_at": at.isoformat(),
        "spot_instrument": {"token": "index", "symbol": "NIFTY", "exchange": "NSE_INDEX"},
        "spot": {
            "token": "index",
            "source_time": at.isoformat(),
            "received_time": at.isoformat(),
            "ltp": "22000",
            "provider": "TEST_FIXTURE",
        },
        "instruments": [option.model_dump(mode="json")],
        "quotes": [quote(at)],
        "sessions": sessions,
        "calendars": [calendar],
        "decision": {"eligible": True},
        "configuration_id": CONFIG.version_id,
        "selector_policy": POLICY,
    }
    return {
        "kind": "FRAME",
        "source_time": at.isoformat(),
        "available_at": at.isoformat(),
        "source": "IMPORT",
        "payload": payload,
    }


def tape(at=NOW, *, loss=False):
    rows = [frame(at)]
    for seconds in (1, 2, 3):
        stamp = at + timedelta(seconds=seconds)
        q = quote(
            stamp,
            bid="80" if loss and seconds >= 2 else "190" if seconds >= 2 else "164",
            ask="81" if loss and seconds >= 2 else "191" if seconds >= 2 else "165",
        )
        rows.append(
            {
                "kind": "QUOTE",
                "source_time": stamp.isoformat(),
                "available_at": stamp.isoformat(),
                "source": "IMPORT",
                "payload": q,
            }
        )
    return rows


def qualifying(frame, now, config):
    return {
        "decision_id": now.isoformat(),
        "eligible": True,
        "side": "CE",
        "confidence": {"score": 100, "method": config.confidence_method},
        "snapshot": {
            "price": 22000,
            "end": now.isoformat(),
            "supertrend": {"direction": 1, "atr": 5},
        },
        "checks": [{"rule": "R-FRESH", "state": "PASS"}],
        "reasons": [],
    }


def splits():
    points = [
        NOW,
        NOW + timedelta(days=1),
        NOW + timedelta(days=4),
        NOW + timedelta(days=4, minutes=1),
    ]
    return [
        {"kind": k, "start": a.isoformat(), "end": b.isoformat()}
        for k, a, b in zip(("TRAIN", "VALIDATION", "TEST"), points, points[1:], strict=False)
    ]


def warmed_frame(at=NOW):
    row = frame(at)
    history = []
    previous_close = 22000.0
    for offset in (-3, -2, -1, 0):
        start = (at + timedelta(days=offset)).replace(hour=3, minute=45, second=0)
        for minute in range(375 if offset else 75):
            if offset:
                close = 22000 + len(history) * 0.02
            elif minute < 60:
                close = 22022.5 - minute * 0.15
            else:
                close = 22013.5 + (minute - 59) * 0.8
            history.append(
                Candle(
                    token="future",
                    start=start + timedelta(minutes=minute),
                    end=start + timedelta(minutes=minute + 1),
                    timeframe=1,
                    open=previous_close,
                    high=max(previous_close, close) + 0.5,
                    low=min(previous_close, close) - 0.5,
                    close=close,
                    volume=1000,
                    provenance="DETERMINISTIC_FIXTURE",
                ).model_dump(mode="json")
            )
            previous_close = close
    row["payload"]["minute_bars"] = history
    put = {
        **row["payload"]["instruments"][0],
        "kind": "PE",
        "token": "token-pe",
        "symbol": "TEST_PE",
    }
    row["payload"]["instruments"].append(put)
    row["payload"]["quotes"].append({**quote(at, token="token-pe"), "oi": 10000})
    return row


def test_actual_five_indicator_pipeline_has_execution_grade_fixture():
    row = warmed_frame()
    parsed = replay.MarketFrame.model_validate(replay.validate_frame(row["payload"], NOW))
    decision = replay.decision_at(parsed, NOW, CONFIG)
    assert decision["eligible"], (decision["checks"], decision["snapshot"], decision["higher"])
    events = [row, *tape()[1:]]
    result = replay.compare(events, CONFIG.model_dump(), CONFIG.model_dump(), splits())
    assert result["variants"][1]["splits"][0]["performance"]["trades"] == 1


def test_replay_rejects_changed_costs_or_risk_without_modifying_config():
    changed = CONFIG.model_copy(update={"brokerage": Decimal("0")})
    with pytest.raises(ValueError, match="risk, cost"):
        replay.compare(tape(), CONFIG.model_dump(), changed.model_dump(), splits())


def test_monthly_loss_and_next_session_cooldown_are_enforced(monkeypatch):
    monkeypatch.setattr(replay, "decision_at", qualifying)
    rows = tape(loss=True) + tape(NOW + timedelta(days=1)) + tape(NOW + timedelta(days=4))
    result = replay._run(rows, CONFIG, True, NOW, NOW + timedelta(days=5))
    assert result["performance"]["trades"] == 1
    assert {r["code"] for r in result["rejections"]} >= {"COOLDOWN_ACTIVE", "MONTHLY_RISK_LOCK"}


def test_entry_cutoff_prevents_a_latency_delayed_fill(monkeypatch):
    monkeypatch.setattr(replay, "decision_at", qualifying)
    at = NOW.replace(hour=9, minute=14, second=59, microsecond=900000)  # 14:44:59.9 IST
    result = replay._run(tape(at), CONFIG, True, at, at + timedelta(minutes=1))
    assert result["performance"]["trades"] == 0
    assert any(r["code"] == "ENTRY_EXPIRED" for r in result["rejections"])


def test_financial_comparison_is_reproducible_and_risk_gated(monkeypatch):
    # Isolate the execution unit from indicator calibration; production Rules are
    # exercised independently below and in the existing strategy regression suite.
    monkeypatch.setattr(replay, "decision_at", qualifying)
    events = tape() + tape(NOW + timedelta(days=1)) + tape(NOW + timedelta(days=4))
    before = deepcopy(events)
    result = replay.compare(events, CONFIG.model_dump(), CONFIG.model_dump(), splits())
    assert result == replay.compare(events, CONFIG.model_dump(), CONFIG.model_dump(), splits())
    assert events == before
    for variant in result["variants"]:
        for split in variant["splits"]:
            assert split["status"] == "MODELED_EXECUTION"
            assert split["performance"]["trades"] == 1
            trade = split["trades"][0]
            assert Decimal(trade["planned_risk"]) <= 400
            assert trade["quantity"] in (25, 50, 75)
            assert Decimal(trade["net"]) == Decimal(trade["gross"]) - Decimal(trade["charges"])
    assert not result["active_settings_changed"]


def test_real_rules_refuse_unwarmed_frames_instead_of_inventing_performance():
    result = replay.compare(tape(), CONFIG.model_dump(), CONFIG.model_dump(), splits())
    assert all(v["status"] == "REFUSED_MISSING_EVIDENCE" for v in result["variants"])
    assert "INCOMPLETE_SIGNAL_INPUTS" in result["variants"][0]["splits"][0]["missing"]


def test_future_pcr_candles_and_reordered_arrivals_are_rejected():
    row = frame(NOW)
    row["payload"]["pcr_available_at"] = (NOW + timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):
        replay.validate_frame(row["payload"], NOW)
    row = frame(NOW)
    row["payload"]["minute_bars"][0]["end"] = (NOW + timedelta(minutes=1)).isoformat()
    with pytest.raises(ValueError):
        replay.validate_frame(row["payload"], NOW)
    with pytest.raises(ValueError, match="Out-of-order"):
        replay.compare(list(reversed(tape())), CONFIG.model_dump(), CONFIG.model_dump(), splits())


def test_protection_gap_withholds_all_financial_results(monkeypatch):
    monkeypatch.setattr(replay, "decision_at", qualifying)
    events = tape()
    events[-2:] = [
        {
            **r,
            "available_at": (replay.instant(r["available_at"]) + timedelta(seconds=10)).isoformat(),
        }
        for r in events[-2:]
    ]
    result = replay.compare(events, CONFIG.model_dump(), CONFIG.model_dump(), splits())
    assert result["variants"][1]["splits"][0]["performance"] is None
    assert "PROTECTION_QUOTE_GAP" in result["variants"][1]["splits"][0]["missing"]


def test_archive_restore_preserves_recording_identity_and_experiment_evidence(store):
    manifest = sealed(store)
    before = cursor(store, manifest).advance(NOW + timedelta(hours=1))
    store.account(OWNER)
    account = store.account(OWNER)  # Compare persisted Numeric values after seed commit.
    store.archive_recording(OWNER, manifest["id"], NOW + timedelta(hours=1))
    assert cursor(store, manifest).advance(NOW + timedelta(hours=1)) == before
    assert store.recording_page(OWNER, manifest["id"])["manifest"] == manifest
    store.restore_recording(OWNER, manifest["id"], NOW + timedelta(hours=1))
    assert cursor(store, manifest).advance(NOW + timedelta(hours=1)) == before
    assert store.account(OWNER) == account


def test_archive_corruption_and_cross_owner_restore_fail_closed(store):
    manifest = sealed(store)
    store.archive_recording(OWNER, manifest["id"], NOW + timedelta(hours=1))
    assert store.load_archived_recording("other", manifest["id"]) is None
    store._archive_path(OWNER, manifest["id"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        store.restore_recording(OWNER, manifest["id"], NOW)


def test_oi_caps_volume_without_changing_weights_or_risk():
    from services.nifty_algo.risk_manager import plan_entry
    from test.test_nifty_algo_phase1 import NOW as at
    from test.test_nifty_algo_phase1 import account, candidate, no_charges

    item, q = candidate()
    rows = [
        plan_entry(
            account(), [(item, q.model_copy(update={"oi": oi}))], CONFIG, 100, no_charges, now=at
        )
        for oi in (None, 0, 1000, 100000)
    ]
    assert all(plan.quantity > 0 and plan.planned_loss <= 400 for plan in rows)
    scores = [Decimal(plan.ranking[0]["scores"]["liquidity"]) for plan in rows]
    assert scores[0] == scores[1] <= scores[2] <= scores[3]
    assert rows[0].ranking[0]["coverage"]["open_interest"] is False
    assert rows[-1].ranking[0]["weights"] == dict(
        zip(
            ("liquidity", "spread", "delta", "reward_risk", "capital_efficiency"),
            map(str, CONFIG.selector_weights),
            strict=True,
        )
    )


def comparison_definition(store):
    sources = []
    for offset in (0, 1, 4):
        at = NOW + timedelta(days=offset)
        recording = store.create_recording(OWNER, at, at + timedelta(hours=1), at)
        store.append_recording(
            OWNER, recording["id"], tape(at), at + timedelta(seconds=4), expected_count=0
        )
        sealed = store.seal_recording(
            OWNER, recording["id"], at + timedelta(minutes=1), expected_count=4
        )
        sources.append({k: sealed[k] for k in ("id", "count", "content_sha256")})
    return store.create_execution_comparison(
        OWNER,
        sources,
        CONFIG.model_dump(mode="json"),
        NOW + timedelta(days=1),
        NOW + timedelta(days=4),
        NOW + timedelta(days=5),
    )


def test_recording_bundle_worker_restart_and_archives_preserve_identical_results(
    store, monkeypatch
):
    from services.nifty_algo.replay_worker import ReplayWorker, run_experiment

    monkeypatch.setattr(replay, "decision_at", qualifying)
    definition = comparison_definition(store)
    assert "EXECUTION_REQUIRES_VALIDATED_EVIDENCE" in definition["limitations"]
    assert "OPTION_REPLAY_UNAVAILABLE" not in definition["limitations"]
    before = store.account(OWNER)
    before = store.account(OWNER)
    at = NOW + timedelta(days=5)
    first = run_experiment(store, OWNER, definition["id"])
    assert first["variants"][1]["splits"][2]["performance"]["trades"] == 1
    store.queue_execution_research(OWNER, definition["id"], at)
    abandoned = store.claim_execution_research(OWNER, at)
    assert store.claim_execution_research(OWNER, at) is None
    later = at + timedelta(minutes=16)
    assert (
        ReplayWorker(NiftyStore(store.engine), OWNER, lambda: later).tick()["status"] == "COMPLETE"
    )
    assert store.execution_research(OWNER, definition["id"])["result"] == first
    from database.nifty_algo_db import StateConflict

    with pytest.raises(StateConflict):
        store.finish_execution_research(OWNER, abandoned, first, later)
    for manifest in definition["snapshot"]["dataset"]["recordings"]:
        store.archive_recording(OWNER, manifest["id"], later)
    assert run_experiment(store, OWNER, definition["id"]) == first
    assert store.account(OWNER) == before
    assert store.execution_research("other", definition["id"]) is None
    assert ReplayWorker(store, OWNER, lambda: later).tick()["status"] == "IDLE"


def test_interrupted_archive_keeps_original_evidence(store, monkeypatch):
    from services.nifty_algo import reports

    manifest = sealed(store)
    before = cursor(store, manifest).advance(NOW + timedelta(hours=1))
    monkeypatch.setattr(reports, "write_atomic", MockWriteFailure())
    with pytest.raises(OSError):
        store.archive_recording(OWNER, manifest["id"], NOW + timedelta(hours=1))
    assert cursor(store, manifest).advance(NOW + timedelta(hours=1)) == before
    assert store.archived_recordings(OWNER) == []


class MockWriteFailure:
    def __call__(self, path, data):
        raise OSError("controlled interrupted write")


def test_frame_identity_split_and_protection_coverage_fail_closed(monkeypatch):
    row = frame(NOW)
    row["payload"]["configuration_id"] = "0" * 64
    with pytest.raises(ValueError, match="CONFIGURATION"):
        replay.compare([row], CONFIG.model_dump(), CONFIG.model_dump(), splits())
    parts = splits()
    parts[0]["end"] = parts[1]["start"] = (NOW + timedelta(minutes=10)).isoformat()
    with pytest.raises(ValueError, match="divide"):
        replay.compare(tape(), CONFIG.model_dump(), CONFIG.model_dump(), parts)
    monkeypatch.setattr(replay, "decision_at", qualifying)
    rows = tape()[:2]
    for seconds in range(2, 335):
        at = NOW + timedelta(seconds=seconds)
        rows.append(
            {
                "kind": "QUOTE",
                "source_time": at.isoformat(),
                "available_at": at.isoformat(),
                "source": "IMPORT",
                "payload": quote(at),
            }
        )
    result = replay._run(rows, CONFIG, True, NOW, NOW + timedelta(minutes=6))
    assert result["performance"] is None
    assert "FUTURES_PROTECTION_FRAME_MISSING" in result["missing"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["spot_instrument"].update(api_key="must-not-persist"),
        lambda p: p["calendars"][0].update(approved_at=(NOW + timedelta(seconds=1)).isoformat()),
        lambda p: p["analysis_instrument"].update(expiry="2026-11-18"),
    ],
)
def test_invalid_analysis_and_secret_payloads_are_not_research_evidence(mutate):
    row = frame(NOW)
    mutate(row["payload"])
    with pytest.raises(ValueError):
        replay.validate_frame(row["payload"], NOW)


def test_execution_queue_and_retention_routes_require_owner_session_csrf_and_confirmation(
    store, monkeypatch
):
    from flask import Flask, jsonify, session
    from flask_wtf.csrf import CSRFProtect, generate_csrf

    import utils.session
    from blueprints.nifty_algo import nifty_algo_bp

    monkeypatch.setattr(utils.session, "is_session_valid", lambda: bool(session.get("user")))
    app = Flask(__name__)
    app.secret_key = "completion-test-only"
    app.extensions["nifty_algo_store"] = store
    CSRFProtect(app)
    app.register_blueprint(nifty_algo_bp)

    @app.get("/csrf-fixture")
    def csrf():
        return jsonify(token=generate_csrf())

    client = app.test_client()
    definition = comparison_definition(store)
    url = f"/api/nifty-algo/research/experiments/{definition['id']}/execution"
    assert client.get(url, headers={"Accept": "application/json"}).status_code == 401
    with client.session_transaction() as browser:
        browser["user"] = OWNER
    headers = {"X-CSRFToken": client.get("/csrf-fixture").json["token"]}
    assert client.post(url, json={"confirm": "REPLAY_RESEARCH_ONLY"}).status_code == 400
    assert client.post(url, json={"confirm": "wrong"}, headers=headers).status_code == 400
    assert (
        client.post(url, json={"confirm": "REPLAY_RESEARCH_ONLY"}, headers=headers).json["data"][
            "status"
        ]
        == "PENDING"
    )
    assert (
        client.post(url, json={"confirm": "REPLAY_RESEARCH_ONLY"}, headers=headers).json["data"][
            "status"
        ]
        == "PENDING"
    )
    manifest = definition["snapshot"]["dataset"]["recordings"][0]
    archive = f"/api/nifty-algo/research/recordings/{manifest['id']}/archive"
    assert client.post(archive, json={"confirm": "wrong"}, headers=headers).status_code == 400
    assert (
        client.post(
            archive, json={"confirm": "ARCHIVE_SEALED_EVIDENCE"}, headers=headers
        ).status_code
        == 200
    )
    downloaded = client.get(archive)
    assert downloaded.status_code == 200 and "no-store" in downloaded.headers["Cache-Control"]
    with client.session_transaction() as browser:
        browser["user"] = "different-owner"
    assert client.get(url).status_code == 404
    assert client.get(archive).status_code == 404
