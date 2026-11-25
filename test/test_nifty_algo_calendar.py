from datetime import date, datetime, time, timedelta
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from flask import Flask
from flask_wtf import CSRFProtect
from reportlab.pdfgen import canvas

from blueprints.nifty_algo import initialize_nifty, nifty_algo_bp
from database.engine_factory import create_db_engine
from database.nifty_algo_db import NiftyStore
from services.nifty_algo import calendar as authority
from services.nifty_algo.calendar_import import (
    CalendarImportError,
    parse_holiday_csv,
    parse_holiday_pdf,
)

IST = ZoneInfo("Asia/Kolkata")


def pdf(*pages):
    output = BytesIO()
    document = canvas.Canvas(output)
    for lines in pages:
        for index, line in enumerate(lines.splitlines()):
            document.drawString(40, 800 - 18 * index, line)
        document.showPage()
    document.save()
    return output.getvalue()


@pytest.fixture
def store(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'calendar.db'}")
    result = NiftyStore(engine, calendar_blob_dir=tmp_path / "calendar_blobs")
    result.initialize()
    yield result
    engine.dispose()


def draft(store, user, entries, year=2026, segment="NFO", *, ambiguous=False):
    data = f"{user}-{year}-{len(store.calendar_versions(user))}".encode()
    return store.create_calendar_draft(
        user,
        year=year,
        segment=segment,
        source_filename="holiday-calendar.csv",
        sha256=sha256(data).hexdigest(),
        uploader=user,
        entries=entries,
        issues=["DATE_INVALID"] if ambiguous else [],
        data=data,
        extension="csv",
    )


def approve(store, version, user="alice"):
    return store.approve_calendar(
        user,
        version["id"],
        confirmed_year=version["year"],
        confirmed_segment=version["segment"],
        actor=user,
    )


def test_pdf_parser_single_and_multiple_pages():
    parsed = parse_holiday_pdf(
        pdf(
            "NSE Equity Derivatives holidays 2026\nMonday 26-Jan-2026 Republic Day",
            "Equity Derivatives\nFriday 03-Apr-2026 Good Friday",
        )
    )
    assert parsed.year == 2026
    assert parsed.segment == "NFO"
    assert [row["date"] for row in parsed.entries] == ["2026-01-26", "2026-04-03"]
    assert not any(row["ambiguous"] for row in parsed.entries)


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ("Tuesday 26-Jan-2026 Republic Day", "WEEKDAY_MISMATCH"),
        ("Monday 26-Jan-2027 Republic Day", "DATE_OUTSIDE_CIRCULAR_YEAR"),
        ("Monday 26-Jan-2026 Republic Day\nMonday 26-Jan-2026 Duplicate", "DUPLICATE_DATE"),
        ("01/02/2026 Ambiguous date", "DATE_FORMAT_UNCLEAR"),
    ],
)
def test_pdf_parser_marks_ambiguous_rows(row, expected):
    parsed = parse_holiday_pdf(pdf(f"NFO holidays 2026\n{row}"))
    assert expected in parsed.issues
    assert any(entry["ambiguous"] for entry in parsed.entries)


def test_pdf_parser_flags_year_conflict_weekends_and_unreadable_documents():
    multiple = parse_holiday_pdf(
        pdf("NFO holidays 2026\nMonday 26-Jan-2026 Republic Day\nSaturday 01-Aug-2027 Extra")
    )
    assert "MULTIPLE_YEARS" in multiple.issues
    assert "DATE_OUTSIDE_CIRCULAR_YEAR" in multiple.issues
    assert "WEEKEND_HOLIDAY" in multiple.issues
    assert all(entry["ambiguous"] for entry in multiple.entries)
    assert "SCANNED_OR_UNREADABLE" in parse_holiday_pdf(pdf("")).issues
    assert parse_holiday_pdf(pdf("2026 holidays\nMonday 26-Jan-2026")).segment == "UNKNOWN"


def test_csv_parser_and_upload_rejections():
    parsed = parse_holiday_csv(b"date,name\n2026-01-26,Republic Day\n")
    assert parsed.year == 2026
    assert parsed.entries[0]["weekday"] == "Monday"
    with pytest.raises(CalendarImportError, match="2 MB"):
        parse_holiday_csv(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(CalendarImportError) as corrupt:
        parse_holiday_pdf(b"%PDF-corrupt")
    assert corrupt.value.code == "PDF_INVALID"
    with pytest.raises(CalendarImportError) as unsupported:
        parse_holiday_csv(b"\xff\x00")
    assert unsupported.value.code == "FILE_TYPE_UNSUPPORTED"
    with pytest.raises(CalendarImportError):
        parse_holiday_csv(b'{"date":"2026-01-26"}')
    checked = parse_holiday_csv(
        b"date,name\n2026-01-03,Weekend\n2026-01-26,Republic Day\n2026-01-26,Duplicate\n"
    )
    assert "WEEKEND_HOLIDAY" in checked.issues
    assert "DUPLICATE_DATE" in checked.issues
    assert not checked.entries[0]["ambiguous"]
    assert any(entry["ambiguous"] for entry in checked.entries)


def test_approval_revisions_audit_and_history(store):
    created = draft(store, "alice", [])
    with pytest.raises(ValueError, match="reviewed dated NFO holidays"):
        approve(store, created)
    ambiguous = store.update_draft_entries(
        "alice",
        created["id"],
        [{"date": "2026-01-26", "weekday": "Tuesday", "name": "Republic Day"}],
        "alice",
    )
    with pytest.raises(ValueError, match="ambiguous"):
        approve(store, ambiguous)
    corrected = store.update_draft_entries(
        "alice",
        ambiguous["id"],
        [{"date": "2026-01-26", "weekday": "Monday", "name": "Republic Day"}],
        "alice",
    )
    approve(store, corrected)
    second = approve(store, draft(store, "alice", [{"date": "2026-01-26", "name": "Republic Day"}]))
    assert second["status"] == "APPROVED"
    assert second["supersedes_id"] == corrected["id"]
    assert len(store.calendar_versions("alice", 2026)) == 2
    first = store.calendar_version("alice", corrected["id"])
    assert first["status"] == "SUPERSEDED"
    assert first["audit"][-1]["action"] == "SUPERSEDED"
    assert store.calendar_version("alice", second["id"])["audit"][-1]["action"] == "APPROVED"


class FakeMarketCalendar:
    def __init__(self, special=None, windows=None):
        self.special = special
        self.windows = windows or {}
        self.removed = 0

    @property
    def db_session(self):
        return SimpleNamespace(remove=self.remove)

    def remove(self):
        self.removed += 1

    def get_special_session(self, day, exchange):
        return self.special if self.special == day else None

    def get_effective_session_window(self, day, exchange):
        if day == date(2026, 1, 12):
            return None  # Explicit native holiday in get_holidays_by_year.
        opening = datetime.combine(day, time(9, 15), authority.IST)
        return self.windows.get(
            day,
            {
                "start_ms": opening.timestamp() * 1000,
                "end_ms": (opening + timedelta(hours=6, minutes=25)).timestamp() * 1000,
            },
        )

    def get_market_timing(self, exchange):
        return {
            "start_offset": 9 * 60 * 60 * 1000 + 15 * 60 * 1000,
            "end_offset": 15 * 60 * 60 * 1000 + 40 * 60 * 1000,
        }

    def get_holidays_by_year(self, year):
        return [
            {"date": "2026-01-12", "holiday_type": "TRADING_HOLIDAY", "closed_exchanges": ["NFO"]}
        ]


def approved(store, entries=(), *, year=2026):
    values = list(entries) or [{"date": f"{year}-01-26", "name": "Republic Day"}]
    row = draft(store, "alice", values, year)
    return approve(store, row)


def test_approved_calendar_overrides_legacy_and_disables_special(store, monkeypatch):
    market = FakeMarketCalendar(special=date(2026, 1, 15))
    monkeypatch.setattr(authority, "_legacy_calendar", lambda: market)
    approved(store)
    working_day = authority.nifty_session("alice", date(2026, 1, 12), store=store)
    assert working_day["status"] == "CALENDAR_DISAGREEMENT"
    assert working_day["window"] is None
    assert authority.nifty_session("alice", date(2026, 1, 14), store=store)["window"][
        0
    ].time() == time(9, 15)
    holiday = approved(store, [{"date": "2026-01-13"}])
    assert holiday["status"] == "APPROVED"
    assert authority.nifty_session("alice", date(2026, 1, 13), store=store)["status"] == "HOLIDAY"
    assert (
        authority.nifty_session("alice", date(2026, 1, 15), store=store)["status"]
        == "SPECIAL_SESSION_DISABLED"
    )
    assert authority.nifty_session("alice", date(2026, 1, 17), store=store)["status"] == "WEEKEND"
    diff = authority.preview_diff([{"date": "2026-01-13"}], 2026)
    assert diff == {"legacy_only": ["2026-01-12"], "calendar_only": ["2026-01-13"]}
    assert market.removed >= 4


def test_unapproved_calendar_and_next_eligible_sessions(store, monkeypatch):
    market = FakeMarketCalendar()
    monkeypatch.setattr(authority, "_legacy_calendar", lambda: market)
    assert (
        authority.nifty_session("alice", date(2026, 1, 9), store=store)["status"]
        == "CALENDAR_UNAPPROVED"
    )
    approved(store)
    assert authority.next_eligible_session("alice", date(2026, 1, 9), store=store) == date(
        2026, 1, 13
    )
    approved(store, [{"date": "2026-01-13"}])
    assert authority.next_eligible_session("alice", date(2026, 1, 12), store=store) == date(
        2026, 1, 14
    )
    approved(store, [{"date": "2026-01-12"}])
    assert authority.next_eligible_session("alice", date(2026, 1, 9), store=store) == date(
        2026, 1, 13
    )


def test_calendar_mutation_route_requires_auth_and_csrf(tmp_path, monkeypatch):
    from flask import jsonify, session
    from flask_wtf.csrf import generate_csrf

    import utils.session

    monkeypatch.setattr(utils.session, "is_session_valid", lambda: bool(session.get("user")))
    engine = create_db_engine(f"sqlite:///{tmp_path / 'api.db'}")
    app = Flask(__name__)
    app.secret_key = "calendar-api-test"
    app.config["TESTING"] = True
    CSRFProtect(app)
    app.register_blueprint(nifty_algo_bp)
    initialize_nifty(app, engine)

    @app.get("/fixture-csrf")
    def csrf():
        return jsonify(token=generate_csrf())

    client = app.test_client()
    assert client.post("/api/nifty-algo/calendar/upload").status_code == 400
    with client.session_transaction() as browser:
        browser["user"] = "alice"
    assert client.post("/api/nifty-algo/calendar/upload").status_code == 400
    token = client.get("/fixture-csrf").json["token"]
    response = client.post(
        "/api/nifty-algo/calendar/upload",
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 400
    engine.dispose()


def test_calendar_store_is_additive_and_does_not_create_shared_calendar_tables(store):
    from sqlalchemy import inspect

    tables = set(inspect(store.engine).get_table_names())
    assert "nifty_algo_calendar_version" in tables
    assert "market_holidays" not in tables
    assert "market_holiday_exchanges" not in tables
