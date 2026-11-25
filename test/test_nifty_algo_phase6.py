"""Phase 6: PDF reports, SMTP attachments, bounded duplicate-safe delivery."""

import ast
import email
import logging
import smtplib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from flask import Flask, jsonify, session
from flask_wtf.csrf import CSRFProtect, generate_csrf
from pypdf import PdfReader
from sqlalchemy import inspect as schema

from blueprints.nifty_algo import initialize_nifty, nifty_algo_bp
from database.engine_factory import create_db_engine
from database.nifty_algo_db import (
    NiftyDecision,
    NiftyEvent,
    NiftyOrder,
    NiftyReport,
    NiftyState,
    NiftyStore,
    NiftyTrade,
)
from services.nifty_algo import calendar as session_calendar
from services.nifty_algo import reports as reports_module
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.reports import (
    MAX_DELIVERY_ATTEMPTS,
    ReportService,
    backoff,
    relative_path,
    render_pdf,
    resolve_report_path,
    user_directory,
)
from services.nifty_algo.runner import NiftyRunner
from test.nifty_calendar_helpers import seed_approved_nfo_calendar
from test.test_nifty_algo_phase1 import Phase1MarketCalendar
from utils import email_utils

USER = "trader"
PASSWORD = "SMTP-SECRET-PASS-123"
RECIPIENT = "trader@example.com"
SETTINGS = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_username": "sender@example.com",
    "smtp_password": PASSWORD,
    "smtp_use_tls": False,
    "smtp_from_email": "sender@example.com",
    "smtp_helo_hostname": None,
}
SESSION = date(2026, 11, 19)  # Thursday
# The fixture market closes at 15:30 IST (10:00 UTC); reports are due 10 minutes later.
BEFORE_CLOSE = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)
AFTER_CLOSE = datetime(2026, 11, 19, 10, 15, tzinfo=UTC)
MONTH_END_HOLIDAY = {
    "date": "2026-11-30",
    "weekday": "Monday",
    "name": "Fixture holiday",
    "ambiguous": False,
    "issue": None,
    "raw": "30-Nov-2026 Monday Fixture holiday",
}


def make_store(tmp_path, name="phase6", holidays=()):
    engine = create_db_engine(f"sqlite:///{tmp_path / f'{name}.db'}")
    value = NiftyStore(
        engine,
        calendar_blob_dir=tmp_path / f"{name}-calendar",
        report_dir=tmp_path / f"{name}-reports",
    )
    value.initialize()
    value.ensure_user(USER)
    seed_approved_nfo_calendar(value, USER, 2026, entries=holidays)
    return value


@pytest.fixture(autouse=True)
def legacy_calendar(monkeypatch):
    monkeypatch.setattr(session_calendar, "_legacy_calendar", lambda: Phase1MarketCalendar())


@pytest.fixture
def store(tmp_path):
    value = make_store(tmp_path, holidays=[MONTH_END_HOLIDAY])
    yield value
    value.engine.dispose()


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def service(store, clock, *, since=SESSION, settings=SETTINGS, recipient=RECIPIENT, send=None):
    return ReportService(
        store,
        USER,
        clock=clock,
        since=since,
        smtp_settings=lambda: settings,
        recipient=lambda: recipient,
        send=send,
    )


def ok_send():
    return Mock(return_value={"success": True, "message": "Email sent successfully"})


def add_trade(store, closed_at, net, *, symbol="NIFTY19NOV2622000CE", order="entry-1"):
    net = Decimal(net)
    with store.sessions.begin() as db:
        db.add(
            NiftyTrade(
                user_id=USER,
                entry_order_id=order,
                exit_order_id=order + "-exit",
                symbol=symbol,
                quantity=75,
                entry_price=Decimal("100"),
                exit_price=Decimal("100") + net / 75,
                gross=net + Decimal("40"),
                fees=Decimal("40"),
                net=net,
                reason="TARGET_HIT",
                opened_at=closed_at - timedelta(minutes=30),
                closed_at=closed_at,
            )
        )


def add_buy(store, at, *, filled=True, order="entry-1"):
    with store.sessions.begin() as db:
        db.add(
            NiftyOrder(
                user_id=USER,
                order_id=order,
                intent_id="entry:" + order,
                side="BUY",
                symbol="NIFTY19NOV2622000CE",
                token="t-1",
                quantity=75,
                status="FILLED" if filled else "EXPIRED",
                reason="",
                price=Decimal("100") if filled else None,
                fees=Decimal("20") if filled else None,
                payload={},
                eligible_at=at,
                expires_at=at + timedelta(seconds=30),
                created_at=at,
            )
        )


def add_decision(store, decision_id, at, *, eligible=True, side="CE", reasons=()):
    with store.sessions.begin() as db:
        db.add(
            NiftyDecision(
                user_id=USER,
                decision_id=decision_id,
                payload={"decision_id": decision_id, "eligible": eligible, "side": side,
                         "reasons": list(reasons)},
                created_at=at,
            )
        )


def add_event(store, kind, payload, at):
    with store.sessions.begin() as db:
        db.add(NiftyEvent(user_id=USER, kind=kind, payload=payload, created_at=at))


def rows(store):
    with store.sessions() as db:
        return [
            store._report_dict(row)
            for row in db.query(NiftyReport).order_by(NiftyReport.id).all()
        ]


def only(store, kind, period_key=None):
    found = [r for r in rows(store) if r["kind"] == kind and (period_key in (None, r["period_key"]))]
    assert len(found) == 1, found
    return found[0]


def pdf_text(store, row):
    data = resolve_report_path(store.report_dir, row["path"]).read_bytes()
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)


# Table and paths ---------------------------------------------------------------


def test_report_table_is_additive_with_unique_period(store):
    names = set(schema(store.engine).get_table_names())
    assert {"nifty_algo_report", "nifty_algo_month", "nifty_algo_state"} <= names
    unique = schema(store.engine).get_unique_constraints("nifty_algo_report")
    assert any(set(item["column_names"]) == {"user_id", "kind", "period_key"} for item in unique)
    first, created = store.ensure_report(USER, "DAILY", "2026-11-19", AFTER_CLOSE)
    again, created_again = store.ensure_report(USER, "DAILY", "2026-11-19", AFTER_CLOSE)
    assert created and not created_again and first["id"] == again["id"]


def test_report_paths_are_sanitized_and_confined(tmp_path):
    hostile = "../evil\\..\\user name"
    directory = user_directory(hostile)
    assert "/" not in directory and "\\" not in directory and ".." not in directory
    assert user_directory("a.b") != user_directory("a_b")
    assert relative_path(hostile, "DAILY", "2026-11-19").startswith(directory + "/daily/")
    for kind, key in (
        ("DAILY", "../2026-11-19"),
        ("DAILY", "2026-11"),
        ("MONTH_END", "2026-11/.."),
        ("MILESTONE", "2026-11-OTHER"),
        ("WEEKLY", "2026-11-19"),
    ):
        with pytest.raises(ValueError):
            relative_path(USER, kind, key)
    root = tmp_path / "root"
    root.mkdir()
    for bad in ("../outside.pdf", str(tmp_path / "abs.pdf"), "", "x/../../y.pdf", "a/b.txt"):
        with pytest.raises(ValueError):
            resolve_report_path(root, bad)
    assert resolve_report_path(root, "u/daily/x.pdf").is_relative_to(root.resolve())


# Daily and zero-trade -----------------------------------------------------------


def test_daily_report_generated_after_close_with_trades(store):
    add_buy(store, datetime(2026, 11, 19, 5, 0, tzinfo=UTC))
    add_trade(store, datetime(2026, 11, 19, 6, 0, tzinfo=UTC), "420.50")
    add_decision(store, "d-1", datetime(2026, 11, 19, 5, 0, tzinfo=UTC))
    clock = Clock(BEFORE_CLOSE)
    assert service(store, clock, send=ok_send()).tick(BEFORE_CLOSE)["generated"] == []
    assert rows(store) == []

    clock.now = AFTER_CLOSE
    service(store, clock, send=ok_send()).tick(AFTER_CLOSE)
    row = only(store, "DAILY", "2026-11-19")
    assert row["generation_status"] == "GENERATED" and row["variant"] == "STANDARD"
    path = resolve_report_path(store.report_dir, row["path"])
    data = path.read_bytes()
    assert data.startswith(b"%PDF-")
    assert path.is_relative_to(Path(store.report_dir).resolve())
    assert row["path"] == f"{user_directory(USER)}/daily/2026-11-19.pdf"
    assert sha256(data).hexdigest() == row["sha256"] and len(data) == row["size_bytes"]
    assert row["summary"]["trades"] == 1
    assert Decimal(row["summary"]["realized_net"]) == Decimal("420.50")
    text = pdf_text(store, row)
    assert "Primary trades" in text and "NIFTY19NOV2622000CE" in text
    assert "non-additive" in text and "No orders were placed" in text
    assert not list(path.parent.glob(".report-*.tmp"))


def test_zero_trade_daily_report_states_why(store):
    at = datetime(2026, 11, 19, 6, 0, tzinfo=UTC)
    add_decision(store, "d-1", at, eligible=True)
    add_event(store, "entry_rejected", {"reasons": ["COOLDOWN_ACTIVE"]}, at)
    add_event(store, "entry_rejected", {"reasons": ["COOLDOWN_ACTIVE"]}, at + timedelta(minutes=5))
    service(store, Clock(AFTER_CLOSE), send=ok_send()).tick(AFTER_CLOSE)
    row = only(store, "DAILY", "2026-11-19")
    assert row["variant"] == "ZERO_TRADE"
    assert row["summary"]["zero_trade_reasons"] == ["COOLDOWN_ACTIVE"]
    text = pdf_text(store, row)
    assert "zero-trade session" in text and "Why no primary trade" in text
    assert "COOLDOWN_ACTIVE" in text


def test_zero_trade_without_assessments_or_signals(tmp_path):
    store = make_store(tmp_path, "quiet")
    try:
        add_decision(store, "d-2", datetime(2026, 11, 18, 6, 0, tzinfo=UTC), eligible=False)
        now = datetime(2026, 11, 18, 10, 15, tzinfo=UTC)
        service(store, Clock(now), since=date(2026, 11, 17), send=ok_send()).tick(now)
        quiet = only(store, "DAILY", "2026-11-17")
        unsignalled = only(store, "DAILY", "2026-11-18")
        assert quiet["summary"]["zero_trade_reasons"] == ["NO_ASSESSMENT_RECORDED"]
        assert unsignalled["summary"]["zero_trade_reasons"] == ["NO_ELIGIBLE_SIGNAL"]
    finally:
        store.engine.dispose()


def test_no_daily_report_for_weekend_holiday_or_unapproved_year(tmp_path):
    store = make_store(tmp_path, "closed", holidays=[MONTH_END_HOLIDAY])
    try:
        now = datetime(2026, 11, 30, 12, 0, tzinfo=UTC)  # Monday holiday
        service(store, Clock(now), since=date(2026, 11, 28), send=ok_send()).tick(now)
        assert [r["period_key"] for r in rows(store) if r["kind"] == "DAILY"] == []
        later = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)  # 2027 calendar not approved
        service(store, Clock(later), since=date(2027, 1, 1), send=ok_send()).tick(later)
        assert not [r for r in rows(store) if r["period_key"].startswith("2027")]
    finally:
        store.engine.dispose()


def test_report_backlog_scans_old_days_and_intermediate_months(tmp_path):
    """A long outage cannot silently discard reports more than 7 days old."""
    value = make_store(tmp_path, "long_outage", holidays=[MONTH_END_HOLIDAY])
    try:
        now = datetime(2026, 12, 15, 10, 20, tzinfo=UTC)
        for _ in range(7):
            service(value, Clock(now), since=date(2026, 10, 1), send=ok_send()).tick(now)
        all_rows = rows(value)
        month_keys = {row["period_key"] for row in all_rows if row["kind"] == "MONTH_END"}
        day_keys = {row["period_key"] for row in all_rows if row["kind"] == "DAILY"}
        assert {"2026-10", "2026-11"} <= month_keys
        assert "2026-10-01" in day_keys
        assert "2026-11-16" in day_keys
        assert value.report_scan_cursor(USER, date(2026, 10, 1)) > "2026-12-15"
    finally:
        value.engine.dispose()


@pytest.mark.parametrize(
    ("status", "window"),
    [
        # Native hours that cannot describe this IST day (end not after start).
        ("SESSION_WINDOW_UNAVAILABLE", lambda day: {"start_ms": 2.0, "end_ms": 1.0}),
        # Native calendar closed while the approved NIFTY calendar says trading.
        ("CALENDAR_DISAGREEMENT", lambda day: None),
    ],
)
def test_unknown_session_window_is_recorded_and_retried(store, monkeypatch, status, window):
    class MissingMarketHours(Phase1MarketCalendar):
        @staticmethod
        def get_effective_session_window(day, exchange):
            return window(day)

    monkeypatch.setattr(session_calendar, "_legacy_calendar", lambda: MissingMarketHours())
    assert session_calendar.nifty_session(USER, SESSION, store=store)["status"] == status
    service(store, Clock(AFTER_CLOSE), send=ok_send()).tick(AFTER_CLOSE)
    assert not [item for item in rows(store) if item["kind"] == "DAILY"]
    # Forward scanning may advance, but the undecidable session is retained.
    assert store.report_scan_cursor(USER, SESSION) == (
        SESSION + timedelta(days=1)
    ).isoformat()
    blocked = store.report_scan_status(USER)
    assert blocked["blocked_count"] == 1
    assert blocked["blocked_examples"] == [{
        "day": SESSION.isoformat(), "reason": status
    }]

    # When authoritative market hours recover, the day must be reconsidered.
    monkeypatch.setattr(session_calendar, "_legacy_calendar", lambda: Phase1MarketCalendar())
    service(store, Clock(AFTER_CLOSE), send=ok_send()).tick(AFTER_CLOSE)
    assert store.report_scan_status(USER)["blocked_count"] == 0
    assert only(store, "DAILY", SESSION.isoformat())["generation_status"] == "GENERATED"


def test_report_scan_does_not_starve_later_year_on_unapproved_earlier_year(tmp_path):
    value = make_store(tmp_path, "scan_blocked_year", holidays=[MONTH_END_HOLIDAY])
    try:
        now = datetime(2026, 1, 20, 10, 15, tzinfo=UTC)
        for _ in range(4):
            service(value, Clock(now), since=date(2025, 12, 29), send=ok_send()).tick(now)
        status = value.report_scan_status(USER)
        assert status["blocked_count"] >= 3
        assert "2025-12-29" in {x["day"] for x in status["blocked_examples"]}
        assert value.report_scan_cursor(USER, date(2025, 12, 29)) > "2026-01-10"
        assert any(x["kind"] == "DAILY" and x["period_key"] == "2026-01-05"
                   for x in rows(value))
    finally:
        value.engine.dispose()


def test_report_generation_manual_retry_owned_and_csrf(client, store):
    from services.nifty_algo.reports import MAX_GENERATION_ATTEMPTS
    now = AFTER_CLOSE
    report, _ = store.ensure_report(USER, "DAILY", SESSION.isoformat(), now)
    for _ in range(MAX_GENERATION_ATTEMPTS - 1):
        store.fail_report_generation(USER, report["id"], "ValueError", now)
    url = f"/api/nifty-algo/reports/{report['id']}/retry-generation"
    assert client.post(url).status_code == 400  # CSRF prevents unauthenticated POST
    headers = _login(client)
    assert client.post(url).status_code == 400  # CSRF
    assert client.post(url, headers=headers).status_code == 409
    store.fail_report_generation(USER, report["id"], "ValueError", now)
    accepted = client.post(url, headers=headers)
    assert accepted.status_code == 200
    assert accepted.json["data"]["generation_status"] == "PENDING"
    assert store.report(USER, report["id"])["generation_attempts"] == 0
    assert client.post(url, headers=headers).status_code == 409
    assert client.post("/api/nifty-algo/reports/999/retry-generation", headers=headers).status_code == 404
    _login(client, "someone-else")
    assert client.post(url, headers=_login(client, "someone-else")).status_code == 404
    assert any(e["kind"] == "report_generation_retry_requested" for e in store.events(USER))


def test_report_pagination_and_scan_status_are_user_scoped(client, store):
    now = AFTER_CLOSE
    for i in range(5):
        store.ensure_report(USER, "DAILY", f"2026-11-{10+i:02d}", now + timedelta(seconds=i))
    _login(client)
    page1 = client.get("/api/nifty-algo/reports?limit=2&offset=0")
    assert page1.status_code == 200
    p1 = page1.json["data"]
    assert [r["period_key"] for r in p1["reports"]] == ["2026-11-14", "2026-11-13"]
    assert p1["pagination"]["next_offset"] == 2
    page2 = client.get("/api/nifty-algo/reports?limit=2&offset=2").json["data"]
    assert [r["period_key"] for r in page2["reports"]] == ["2026-11-12", "2026-11-11"]
    assert client.get("/api/nifty-algo/reports?limit=0").status_code == 400
    assert client.get("/api/nifty-algo/reports?offset=-1").status_code == 400
    scan = client.get("/api/nifty-algo/reports/scan-status")
    assert scan.status_code == 200 and scan.json["data"]["blocked_count"] == 0
    _login(client, "someone-else")
    assert client.get("/api/nifty-algo/reports").json["data"]["reports"] == []


def test_report_session_cache_reloads_after_a_new_tick(store):
    now = AFTER_CLOSE
    runner = service(store, Clock(now), since=SESSION, send=ok_send())
    runner._sessions[SESSION] = {"status": "UNAVAILABLE", "window": None}
    found = runner.due_periods(now)
    assert ("DAILY", SESSION.isoformat()) in found
    assert runner._sessions[SESSION]["status"] == "TRADING"


# Milestones ---------------------------------------------------------------------


def _latch(store, config, at):
    with store.sessions.begin() as db:
        state = db.get(NiftyState, USER)
        state.configuration = config.model_dump(mode="json")
        state.configuration_id = config.version_id
    return store.entry_locks(USER, at, config)


def test_milestone_report_on_monthly_loss_lock(store):
    at = datetime(2026, 11, 19, 6, 0, tzinfo=UTC)
    add_trade(store, at, "-2100")
    assert "MONTHLY_LOSS_LOCK" in _latch(store, StrategyConfig(), at + timedelta(minutes=1))
    now = at + timedelta(minutes=2)
    service(store, Clock(now), send=ok_send()).tick(now)
    row = only(store, "MILESTONE", "2026-11-LOSS_LOCK")
    assert row["generation_status"] == "GENERATED"
    assert row["summary"]["lock"] == "MONTHLY_LOSS_LOCK"
    assert Decimal(row["summary"]["realized_net"]) == Decimal("-2100")
    month = next(m for m in store.report_months(USER) if m["month"] == "2026-11")
    assert month["milestone_report_ids"] == [row["id"]]
    assert "MONTHLY_LOSS_LOCK" in pdf_text(store, row)
    service(store, Clock(now), send=ok_send()).tick(now + timedelta(minutes=1))
    assert next(m for m in store.report_months(USER) if m["month"] == "2026-11")[
        "milestone_report_ids"
    ] == [row["id"]]
    assert not [r for r in rows(store) if r["kind"] == "DAILY"]  # session not closed yet


def test_milestone_report_on_monthly_profit_lock(store):
    at = datetime(2026, 11, 19, 6, 0, tzinfo=UTC)
    add_trade(store, at, "1200")
    config = StrategyConfig(monthly_profit_target=Decimal("1000"))
    assert "MONTHLY_PROFIT_LOCK" in _latch(store, config, at + timedelta(minutes=1))
    now = at + timedelta(minutes=2)
    service(store, Clock(now), send=ok_send()).tick(now)
    row = only(store, "MILESTONE", "2026-11-PROFIT_LOCK")
    assert row["summary"]["lock"] == "MONTHLY_PROFIT_LOCK"
    assert not [r for r in rows(store) if r["period_key"] == "2026-11-LOSS_LOCK"]
    month = next(m for m in store.report_months(USER) if m["month"] == "2026-11")
    assert month["milestone_report_ids"] == [row["id"]]


# Month end ----------------------------------------------------------------------


def test_month_end_after_last_eligible_session_with_month_end_holiday(store):
    add_trade(store, datetime(2026, 11, 27, 6, 0, tzinfo=UTC), "150")
    since = date(2026, 11, 27)
    before = datetime(2026, 11, 27, 10, 5, tzinfo=UTC)
    service(store, Clock(before), since=since, send=ok_send()).tick(before)
    assert not [r for r in rows(store) if r["kind"] == "MONTH_END"]
    after = datetime(2026, 11, 27, 10, 15, tzinfo=UTC)  # Friday; Monday 30th is a holiday
    service(store, Clock(after), since=since, send=ok_send()).tick(after)
    row = only(store, "MONTH_END", "2026-11")
    assert row["generation_status"] == "GENERATED"
    # 21 weekdays in November 2026 less the approved holiday on the 30th.
    assert row["summary"]["sessions"] == 20 and row["summary"]["trades"] == 1
    text = pdf_text(store, row)
    assert "month-end report 2026-11" in text and "2026-11-27" in text
    assert "2026-11-30" not in text


def test_month_end_waits_for_the_real_last_session_without_a_holiday(tmp_path):
    store = make_store(tmp_path, "plain")
    try:
        friday = datetime(2026, 11, 27, 10, 15, tzinfo=UTC)
        service(store, Clock(friday), since=date(2026, 11, 27), send=ok_send()).tick(friday)
        assert not [r for r in rows(store) if r["kind"] == "MONTH_END"]
        monday = datetime(2026, 11, 30, 10, 15, tzinfo=UTC)
        service(store, Clock(monday), since=date(2026, 11, 27), send=ok_send()).tick(monday)
        assert only(store, "MONTH_END", "2026-11")["summary"]["sessions"] == 21
    finally:
        store.engine.dispose()


# Idempotence --------------------------------------------------------------------


def test_generation_is_idempotent_and_deterministic(store):
    add_trade(store, datetime(2026, 11, 19, 6, 0, tzinfo=UTC), "75")
    for _ in range(3):
        service(store, Clock(AFTER_CLOSE), send=ok_send()).tick(AFTER_CLOSE)
    later = AFTER_CLOSE + timedelta(hours=2)
    service(store, Clock(later), send=ok_send()).tick(later)
    row = only(store, "DAILY", "2026-11-19")
    report_service = service(store, Clock(later))
    _, title, sections, _ = report_service.content("DAILY", "2026-11-19")
    again = render_pdf(title, sections, datetime.fromisoformat(row["created_at"]))
    assert sha256(again).hexdigest() == row["sha256"]
    other = render_pdf(title, sections, datetime.fromisoformat(row["created_at"]) + timedelta(1))
    assert sha256(other).hexdigest() != row["sha256"]
    events = [e for e in store.events(USER) if e["kind"] == "report_generated"]
    assert len(events) == 1


# Delivery -----------------------------------------------------------------------


class RecordingSMTP:
    instances = []

    def __init__(self, host, port, **kwargs):
        self.kwargs = kwargs
        self.messages = []
        self.closed = False
        RecordingSMTP.instances.append(self)

    def ehlo(self, *args):
        return (250, b"ok")

    def starttls(self, **kwargs):
        return (220, b"ok")

    def login(self, user, password):
        return (235, b"ok")

    def sendmail(self, sender, recipient, message):
        self.messages.append((sender, recipient, message))
        return {}

    def quit(self):
        self.closed = True

    def close(self):
        self.closed = True


def test_send_with_pdf_attachment_through_smtplib(store, monkeypatch):
    RecordingSMTP.instances = []
    monkeypatch.setattr(email_utils.smtplib, "SMTP", RecordingSMTP)
    service(store, Clock(AFTER_CLOSE)).tick(AFTER_CLOSE)
    row = only(store, "DAILY", "2026-11-19")
    assert row["delivery_status"] == "SENT" and row["attempts"] == 1 and row["sent_at"]
    [smtp] = RecordingSMTP.instances
    assert smtp.kwargs == {"timeout": reports_module.SMTP_TIMEOUT_SECONDS}
    [(sender, recipient, raw)] = smtp.messages
    assert recipient == RECIPIENT
    message = email.message_from_string(raw)
    assert message.get_content_type() == "multipart/mixed"
    [attachment] = [part for part in message.walk() if part.get_filename()]
    assert attachment.get_filename() == "2026-11-19.pdf"
    assert attachment.get_content_type() == "application/pdf"
    body = attachment.get_payload(decode=True)
    assert len(body) == row["size_bytes"]
    assert sha256(body).hexdigest() == row["sha256"]
    text = next(p for p in message.walk() if p.get_content_type() == "text/plain")
    assert "2026-11-19" in text.get_payload(decode=True).decode()


def test_attachment_size_limit_is_enforced_before_connecting(monkeypatch):
    connect = Mock()
    monkeypatch.setattr(email_utils.smtplib, "SMTP", connect)
    raw = email_utils.MAX_ATTACHMENT_BYTES * 3 // 4 + 3
    result = email_utils.send_email(
        RECIPIENT, "s", "t", smtp_settings=dict(SETTINGS),
        attachments=[("big.pdf", bytes(raw), "application/pdf")], redact=True,
    )
    assert result["success"] is False and result["error_type"] == "AttachmentTooLarge"
    connect.assert_not_called()
    for bad in (("../x.pdf", b"x", "application/pdf"), ("x.pdf", b"x", "pdf")):
        result = email_utils.send_email(
            RECIPIENT, "s", "t", smtp_settings=dict(SETTINGS), attachments=[bad], redact=True
        )
        assert result["success"] is False and result["error_type"] == "ValueError"
    connect.assert_not_called()


def test_accepted_report_is_not_retried_when_quit_disconnects(store, monkeypatch):
    class DisconnectOnQuit(RecordingSMTP):
        def quit(self):
            raise smtplib.SMTPServerDisconnected("connection closed after acceptance")

    RecordingSMTP.instances = []
    monkeypatch.setattr(email_utils.smtplib, "SMTP", DisconnectOnQuit)
    clock = Clock(AFTER_CLOSE)
    service(store, clock).tick(clock.now)
    clock.now += timedelta(minutes=10)
    service(store, clock).tick(clock.now)
    assert only(store, "DAILY")["delivery_status"] == "SENT"
    assert len(RecordingSMTP.instances) == 1
    assert RecordingSMTP.instances[0].closed


def test_report_with_unknown_smtp_outcome_requires_manual_retry(store, monkeypatch):
    class LostAcknowledgement(RecordingSMTP):
        def sendmail(self, sender, recipient, message):
            super().sendmail(sender, recipient, message)
            raise TimeoutError("final DATA acknowledgement lost")

    RecordingSMTP.instances = []
    monkeypatch.setattr(email_utils.smtplib, "SMTP", LostAcknowledgement)
    clock = Clock(AFTER_CLOSE)
    service(store, clock).tick(clock.now)
    clock.now += timedelta(minutes=10)
    service(store, clock).tick(clock.now)
    row = only(store, "DAILY")
    assert row["delivery_status"] == "FAILED"
    assert row["last_error_type"] == "DELIVERY_OUTCOME_UNKNOWN"
    assert row["next_attempt_at"] is None
    assert len(RecordingSMTP.instances) == 1
    assert RecordingSMTP.instances[0].closed


def test_expired_delivery_claim_cannot_be_automatically_reclaimed(store):
    service(store, Clock(AFTER_CLOSE)).generate_due(AFTER_CLOSE)
    row = only(store, "DAILY")
    assert store.claim_report_delivery(
        USER, row["id"], "crashed", AFTER_CLOSE, lease_seconds=300, max_attempts=5
    ) == 1
    later = AFTER_CLOSE + timedelta(seconds=301)
    assert store.claim_report_delivery(
        USER, row["id"], "new", later, lease_seconds=300, max_attempts=5
    ) is None
    # Missing configuration must not erase an unresolved delivery claim.
    assert not store.skip_report_delivery(USER, row["id"], "SMTP_NOT_CONFIGURED", later)
    sender = ok_send()
    service(store, Clock(later), send=sender).deliver_due(later)
    sender.assert_not_called()
    row = only(store, "DAILY")
    assert row["delivery_status"] == "FAILED"
    assert row["last_error_type"] == "DELIVERY_OUTCOME_UNKNOWN"
    # Expiry is a durable delivery outcome and must have the same audit trail
    # as a sender's acknowledgement, exactly once even across recovery ticks.
    assert store.fail_interrupted_deliveries(USER, later) == 0
    outcomes = [
        event
        for event in store.events(USER)
        if event["kind"] == "report_delivery"
        and event["payload"]["report_id"] == row["id"]
    ]
    assert len(outcomes) == 1
    assert outcomes[0]["payload"]["status"] == "FAILED"
    assert outcomes[0]["payload"]["error_type"] == "DELIVERY_OUTCOME_UNKNOWN"


def test_failure_retries_with_backoff_then_fails(store):
    failing = Mock(return_value={
        "success": False, "message": "x", "error_type": "SMTPServerDisconnected",
        "retry_safe": True,  # Connection failed before message transmission.
    })
    clock = Clock(AFTER_CLOSE)
    service(store, clock, send=failing).tick(AFTER_CLOSE)
    row = only(store, "DAILY")
    assert row["delivery_status"] == "PENDING" and row["attempts"] == 1
    assert datetime.fromisoformat(row["next_attempt_at"]) == AFTER_CLOSE + backoff(1)
    assert [backoff(n).total_seconds() for n in (1, 2, 3, 4)] == [60, 120, 240, 480]
    clock.now = AFTER_CLOSE + timedelta(seconds=30)
    service(store, clock, send=failing).tick(clock.now)
    assert failing.call_count == 1  # Not due yet.
    for _ in range(10):
        due = only(store, "DAILY")["next_attempt_at"]
        if due is None:
            break
        clock.now = datetime.fromisoformat(due)
        service(store, clock, send=failing).tick(clock.now)
    row = only(store, "DAILY")
    assert failing.call_count == MAX_DELIVERY_ATTEMPTS
    assert row["delivery_status"] == "FAILED" and row["attempts"] == MAX_DELIVERY_ATTEMPTS
    assert row["last_error_type"] == "SMTPServerDisconnected" and row["next_attempt_at"] is None
    clock.now += timedelta(hours=2)
    service(store, clock, send=failing).tick(clock.now)
    assert failing.call_count == MAX_DELIVERY_ATTEMPTS
    statuses = [e["payload"]["status"] for e in store.events(USER) if e["kind"] == "report_delivery"]
    assert sorted(statuses) == ["FAILED"] + ["PENDING"] * (MAX_DELIVERY_ATTEMPTS - 1)


def test_double_tick_raced_at_the_claim_write_sends_once(store, monkeypatch):
    send = ok_send()
    clock = Clock(AFTER_CLOSE)
    first = service(store, clock, send=send)
    first.generate_due(AFTER_CLOSE)
    original = store.claim_report_delivery
    raced = []

    def claim_after_competitor(*args, **kwargs):
        if not raced:
            raced.append(True)
            # The competing tick claims and sends between this tick's last read and its write.
            service(store, clock, send=send).deliver_due(AFTER_CLOSE)
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "claim_report_delivery", claim_after_competitor)
    assert first.deliver_due(AFTER_CLOSE) == []
    assert raced and send.call_count == 1
    row = only(store, "DAILY")
    assert row["delivery_status"] == "SENT" and row["attempts"] == 1


def test_restart_does_not_resend_and_interrupted_claim_is_held(store, monkeypatch):
    send = ok_send()
    service(store, Clock(AFTER_CLOSE), send=send).tick(AFTER_CLOSE)
    assert send.call_count == 1
    for offset in (1, 60, 300):  # Same IST session, so no new daily report is due.
        later = AFTER_CLOSE + timedelta(minutes=offset)
        service(store, Clock(later), send=send).tick(later)
    assert send.call_count == 1 and only(store, "DAILY")["delivery_status"] == "SENT"

    # A process may die after SMTP accepts but before the ledger settles.
    report = store.ensure_report(USER, "MONTH_END", "2026-10", AFTER_CLOSE)[0]
    store.complete_report_generation(
        USER, report["id"], path="x/month_end/2026-10.pdf", sha256="0" * 64, size_bytes=1,
        variant="STANDARD", summary={}, now=AFTER_CLOSE,
    )
    assert store.claim_report_delivery(
        USER, report["id"], "dead", AFTER_CLOSE, lease_seconds=300, max_attempts=5
    ) == 1
    assert store.deliverable_reports(USER, AFTER_CLOSE + timedelta(seconds=299), 5) == []
    expired_at = AFTER_CLOSE + timedelta(seconds=300)
    assert store.deliverable_reports(USER, expired_at, 5) == []
    assert store.fail_interrupted_deliveries(USER, expired_at) == 1
    assert store.report(USER, report["id"])["delivery_status"] == "FAILED"


def test_smtp_not_configured_marks_skipped_but_generates(store):
    send = ok_send()
    service(store, Clock(AFTER_CLOSE), settings=None, send=send).tick(AFTER_CLOSE)
    row = only(store, "DAILY")
    assert row["generation_status"] == "GENERATED"
    assert row["delivery_status"] == "SKIPPED_NO_SMTP"
    assert row["last_error_type"] == "SMTP_NOT_CONFIGURED" and row["attempts"] == 0
    send.assert_not_called()
    assert not store.skip_report_delivery(USER, row["id"], "SMTP_NOT_CONFIGURED", AFTER_CLOSE)
    outcomes = [
        event["payload"]
        for event in store.events(USER)
        if event["kind"] == "report_delivery"
        and event["payload"]["report_id"] == row["id"]
    ]
    assert len(outcomes) == 1
    assert outcomes[0]["status"] == "SKIPPED_NO_SMTP"
    assert outcomes[0]["error_type"] == "SMTP_NOT_CONFIGURED"
    assert outcomes[0]["attempts"] == 0


def test_incomplete_smtp_or_no_recipient_is_skipped(tmp_path):
    for name, settings, recipient, reason in (
        ("partial", {**SETTINGS, "smtp_password": None}, RECIPIENT, "SMTP_NOT_CONFIGURED"),
        ("norecipient", SETTINGS, None, "RECIPIENT_UNAVAILABLE"),
    ):
        store = make_store(tmp_path, name)
        try:
            send = ok_send()
            service(store, Clock(AFTER_CLOSE), settings=settings, recipient=recipient,
                    send=send).tick(AFTER_CLOSE)
            row = only(store, "DAILY")
            assert row["delivery_status"] == "SKIPPED_NO_SMTP" and row["last_error_type"] == reason
            send.assert_not_called()
        finally:
            store.engine.dispose()


def test_no_smtp_secret_in_logs_events_or_rows(store, monkeypatch, caplog):
    class LeakySMTP(RecordingSMTP):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, f"rejected {password} for {user}".encode())

    monkeypatch.setattr(email_utils.smtplib, "SMTP", LeakySMTP)
    with caplog.at_level(logging.DEBUG):
        service(store, Clock(AFTER_CLOSE)).tick(AFTER_CLOSE)

        class Crash(RecordingSMTP):
            def sendmail(self, *args):
                raise RuntimeError(f"socket said {PASSWORD} to {RECIPIENT}")

        monkeypatch.setattr(email_utils.smtplib, "SMTP", Crash)
        retry = AFTER_CLOSE + backoff(1)
        service(store, Clock(retry)).tick(retry)
    row = only(store, "DAILY")
    assert row["attempts"] == 2 and row["last_error_type"] == "DELIVERY_OUTCOME_UNKNOWN"
    assert "SMTPAuthenticationError" in caplog.text  # Failures are logged, by type only.
    stored = repr(rows(store)) + repr(store.events(USER))
    for text in (caplog.text, stored):
        assert PASSWORD not in text
        assert RECIPIENT not in text


def test_send_email_existing_callers_unaffected(monkeypatch):
    RecordingSMTP.instances = []
    monkeypatch.setattr(email_utils.smtplib, "SMTP", RecordingSMTP)
    result = email_utils.send_email("to@example.com", "s", "t", smtp_settings=dict(SETTINGS))
    assert result == {"success": True, "message": "Email sent successfully"}
    [smtp] = RecordingSMTP.instances
    assert smtp.kwargs == {}  # The socket default is kept off gthread, as before.
    message = email.message_from_string(smtp.messages[0][2])
    assert message.get_content_type() == "multipart/alternative"
    assert not [part for part in message.walk() if part.get_filename()]

    class Refuses(RecordingSMTP):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(email_utils.smtplib, "SMTP", Refuses)
    failed = email_utils.send_email("to@example.com", "s", "t", smtp_settings=dict(SETTINGS))
    assert failed == {
        "success": False,
        "message": "SMTP Authentication failed. Please check your username and password.",
    }


# Runner and isolation -----------------------------------------------------------


def test_runner_report_job_never_raises(store, monkeypatch, caplog):
    runner = NiftyRunner(store, USER, native=Mock(), executor=Mock(), clock=lambda: AFTER_CLOSE)

    def broken(self, now=None):
        raise RuntimeError(PASSWORD)

    monkeypatch.setattr(ReportService, "tick", broken)
    with caplog.at_level(logging.WARNING):
        assert runner.reports() is None
    assert "NIFTY reports skipped: RuntimeError" in caplog.text and PASSWORD not in caplog.text
    runner.closed = True
    assert runner.reports() is None


def test_reports_module_never_imports_order_paths():
    tree = ast.parse(Path(reports_module.__file__).read_text(encoding="utf-8"))
    modules = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ] + [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert not any(
        name.startswith(("broker", "sandbox", "services.place_order", "services.place_smart_order"))
        or "paper_executor" in name
        for name in modules
    )


# API ----------------------------------------------------------------------------


@pytest.fixture
def client(store, monkeypatch):
    import database.settings_db
    import utils.session

    monkeypatch.setattr(utils.session, "is_session_valid", lambda: bool(session.get("user")))
    monkeypatch.setattr(database.settings_db, "get_smtp_settings", lambda: None)
    app = Flask(__name__)
    app.secret_key = "test-only-nifty-fixture-key"
    app.config["TESTING"] = True
    CSRFProtect(app)
    app.register_blueprint(nifty_algo_bp)
    initialize_nifty(app, store.engine)
    app.extensions["nifty_algo_store"] = store

    @app.get("/fixture-csrf")
    def csrf():
        return jsonify(token=generate_csrf())

    return app.test_client()


JSON = {"Accept": "application/json"}


def _login(client, user=USER):
    with client.session_transaction() as browser:
        browser["user"] = user
    return {"X-CSRFToken": client.get("/fixture-csrf").json["token"]}


def _generated(store, send=None):
    service(store, Clock(AFTER_CLOSE), send=send or ok_send()).tick(AFTER_CLOSE)
    return only(store, "DAILY")


def test_reports_list_is_masked(client, store):
    assert client.get("/api/nifty-algo/reports", headers=JSON).status_code == 401
    row = _generated(store)
    _login(client)
    response = client.get("/api/nifty-algo/reports")
    assert response.status_code == 200
    data = response.json["data"]
    assert data["smtp_configured"] is False and data["max_attempts"] == MAX_DELIVERY_ATTEMPTS
    [listed] = data["reports"]
    assert listed["id"] == row["id"] and listed["filename"] == "2026-11-19.pdf"
    assert listed["delivery_status"] == "SENT"
    assert "path" not in listed and "claim_token" not in listed and "claimed_until" not in listed
    body = response.get_data(as_text=True)
    assert str(Path(store.report_dir)) not in body and user_directory(USER) not in body


def test_download_endpoint_confines_path(client, store, tmp_path):
    row = _generated(store)
    assert client.get(f"/api/nifty-algo/reports/{row['id']}/pdf", headers=JSON).status_code == 401
    _login(client)
    response = client.get(f"/api/nifty-algo/reports/{row['id']}/pdf")
    assert response.status_code == 200 and response.mimetype == "application/pdf"
    assert sha256(response.data).hexdigest() == row["sha256"]
    assert "2026-11-19.pdf" in response.headers["Content-Disposition"]
    assert client.get("/api/nifty-algo/reports/999/pdf").status_code == 404

    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-outside")
    for hostile in ("../outside.pdf", str(outside), "../../outside.pdf"):
        with store.sessions.begin() as db:
            db.get(NiftyReport, row["id"]).path = hostile
            db.get(NiftyReport, row["id"]).sha256 = sha256(b"%PDF-outside").hexdigest()
        refused = client.get(f"/api/nifty-algo/reports/{row['id']}/pdf")
        assert refused.status_code == 404 and refused.json["code"] == "REPORT_FILE_UNAVAILABLE"
        assert b"outside" not in refused.data

    with store.sessions.begin() as db:
        db.get(NiftyReport, row["id"]).path = row["path"]
        db.get(NiftyReport, row["id"]).sha256 = row["sha256"]
    resolve_report_path(store.report_dir, row["path"]).write_bytes(b"%PDF-tampered")
    assert client.get(f"/api/nifty-algo/reports/{row['id']}/pdf").status_code == 409

    _login(client, user="someone-else")
    assert client.get(f"/api/nifty-algo/reports/{row['id']}/pdf").status_code == 404


def test_resend_is_compare_and_set(client, store, monkeypatch):
    failing = Mock(return_value={
        "success": False, "message": "x", "error_type": "TimeoutError", "retry_safe": True,
    })
    row = _generated(store, send=failing)
    headers = _login(client)
    url = f"/api/nifty-algo/reports/{row['id']}/resend"
    assert client.post(url).status_code == 400  # CSRF token required.
    refused = client.post(url, headers=headers)  # Still PENDING with retries left.
    assert refused.status_code == 409 and refused.json["code"] == "RESEND_REFUSED"
    with store.sessions.begin() as db:
        failed = db.get(NiftyReport, row["id"])
        failed.delivery_status, failed.attempts, failed.next_attempt_at = "FAILED", 5, None
    original = store.resend_report

    def resend_after_competitor(*args, **kwargs):
        # A competing resend lands between the route's lookup and this write.
        assert original(*args, **kwargs) is not None
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "resend_report", resend_after_competitor)
    raced = client.post(url, headers=headers)
    assert raced.status_code == 409 and raced.json["code"] == "RESEND_REFUSED"
    monkeypatch.setattr(store, "resend_report", original)
    current = store.report(USER, row["id"])
    assert current["delivery_status"] == "PENDING" and current["attempts"] == 0
    assert [e for e in store.events(USER) if e["kind"] == "report_resend_requested"]

    with store.sessions.begin() as db:
        db.get(NiftyReport, row["id"]).delivery_status = "SKIPPED_NO_SMTP"
    accepted = client.post(url, headers=headers)
    assert accepted.status_code == 200 and accepted.json["data"]["delivery_status"] == "PENDING"
    assert "path" not in accepted.json["data"]
    with store.sessions.begin() as db:
        db.get(NiftyReport, row["id"]).delivery_status = "SENT"
    assert client.post(url, headers=headers).status_code == 409
    assert client.post("/api/nifty-algo/reports/999/resend", headers=headers).status_code == 404
