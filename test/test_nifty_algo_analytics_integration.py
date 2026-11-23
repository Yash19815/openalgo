"""Authoritative analytics read persisted fills without mutating trading state."""

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import event, insert, select

from database.nifty_algo_db import NiftyOrder, NiftyTrade
from services.nifty_algo.config import StrategyConfig
from test.test_nifty_algo_paper_executor import NOW, USER, buy_intent, executor, running
from test.test_nifty_algo_paper_executor import market_calendar as market_calendar
from test.test_nifty_algo_safety_center import client as client
from test.test_nifty_algo_safety_center import login
from test.test_nifty_algo_safety_center import store as store


def round_trip(store):
    running(store)
    paper = executor(store, config=StrategyConfig(latency_ms=1))
    paper.admit(buy_intent())
    paper.process(now=NOW + timedelta(seconds=1))
    paper.admit(buy_intent(intent_id="analytics-exit", side="SELL", exit_reason="TARGET_HIT"))
    paper.process(now=NOW + timedelta(seconds=2))
    return store.trades(USER)[0]


def test_analytics_snapshot_uses_durable_fills_and_separates_unavailable_marks(store):
    trade = round_trip(store)
    result = store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1))
    assert result["mode"] == "PAPER"
    assert result["metrics"]["trades"] == 1
    assert Decimal(result["metrics"]["total_net"]) == Decimal(trade["net"])
    assert Decimal(result["metrics"]["costs"]) == Decimal(trade["fees"])
    assert result["metrics"]["basis"] == "PAPER_FILLS_REALIZED"
    assert result["marked_unrealized"] == {"value": None, "reason": "NO_PERSISTED_MARK_SERIES"}
    assert result["details"]["total"] == 1
    assert result["details"]["items"][0]["net"] == trade["net"]


def test_analytics_snapshot_is_owner_scoped_and_has_no_write_side_effects(store):
    round_trip(store)
    writes = []

    def statement(connection, cursor, sql, parameters, context, many):
        if sql.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(sql)

    event.listen(store.engine, "before_cursor_execute", statement)
    try:
        result = store.analytics_snapshot("absent-user", NOW, NOW + timedelta(days=1))
        assert result["metrics"]["trades"] == 0
        assert result["details"]["items"] == []
        assert writes == []
    finally:
        event.remove(store.engine, "before_cursor_execute", statement)


def test_analytics_period_is_half_open_and_opening_balance_uses_prior_realized_net(store):
    trade = round_trip(store)
    closed = NOW + timedelta(seconds=2)
    before = store.analytics_snapshot(USER, NOW, closed)
    after = store.analytics_snapshot(USER, closed, closed + timedelta(days=1))
    later = store.analytics_snapshot(USER, closed + timedelta(microseconds=1), closed + timedelta(days=1))
    assert before["metrics"]["trades"] == 0
    assert after["metrics"]["trades"] == 1
    assert Decimal(later["opening_realized_equity"]) == Decimal("20000") + Decimal(trade["net"])


@pytest.mark.parametrize(
    "start,end,limit,offset",
    [
        (NOW.replace(tzinfo=None), NOW + timedelta(days=1), 50, 0),
        (NOW, NOW, 50, 0),
        (NOW, NOW + timedelta(days=367), 50, 0),
        (NOW, NOW + timedelta(days=1), 101, 0),
        (NOW, NOW + timedelta(days=1), 50, -1),
        (NOW, NOW + timedelta(days=1), True, 0),
    ],
)
def test_analytics_rejects_invalid_or_unbounded_queries(store, start, end, limit, offset):
    with pytest.raises(ValueError):
        store.analytics_snapshot(USER, start, end, limit=limit, offset=offset)


def test_analytics_rejects_trade_not_backed_by_filled_exit_order(store):
    round_trip(store)
    with store.sessions.begin() as db:
        row = db.scalar(select(NiftyTrade).where(NiftyTrade.user_id == USER))
        row.exit_order_id = "missing-fill"
    with pytest.raises(ValueError, match="fill"):
        store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1))


def test_analytics_api_requires_session_and_valid_period(client, store):
    url = "/api/nifty-algo/analytics"
    assert client.get(url, headers={"Accept": "application/json"}).status_code == 401
    login(client)
    assert client.get(url + "?start=invalid&end=invalid").status_code == 400
    assert client.get(url + "?mode=SHADOW").status_code == 400
    response = client.get(url + "?start=2026-11-19&end=2026-11-20&user=another-user")
    assert response.status_code == 200
    assert response.json["data"]["mode"] == "PAPER"


def append_fills(store, count):
    """Seed immutable copies of a genuine fill pair for full-history read tests."""
    with store.sessions.begin() as db:
        trade = db.scalar(select(NiftyTrade).where(NiftyTrade.user_id == USER))
        entry = db.get(NiftyOrder, (USER, trade.entry_order_id))
        exit_order = db.get(NiftyOrder, (USER, trade.exit_order_id))
        orders, trades = [], []
        for index in range(count):
            entry_id, exit_id = f"analytics-entry-{index}", f"analytics-exit-{index}"
            for source, identity in ((entry, entry_id), (exit_order, exit_id)):
                payload = dict(source.payload)
                if source is exit_order:
                    payload["entry_order_id"] = entry_id
                orders.append({
                    **{column.name: getattr(source, column.name) for column in NiftyOrder.__table__.columns},
                    "order_id": identity, "intent_id": identity, "payload": payload,
                })
            trades.append({
                **{column.name: getattr(trade, column.name) for column in NiftyTrade.__table__.columns
                   if column.name != "id"},
                "entry_order_id": entry_id, "exit_order_id": exit_id,
            })
        db.execute(insert(NiftyOrder), orders)
        db.execute(insert(NiftyTrade), trades)


def test_analytics_totals_cover_more_than_journal_limit_and_ignore_detail_paging(store):
    trade = round_trip(store)
    append_fills(store, 204)
    first = store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1), limit=1)
    last = store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1), limit=1, offset=204)
    assert len(store.trades(USER)) == 200
    assert first["metrics"]["trades"] == 205
    assert Decimal(first["metrics"]["total_net"]) == Decimal(trade["net"]) * 205
    assert len(first["metrics"]["equity_curve"]) == 205
    assert first["metrics"] == last["metrics"]
    assert first["details"]["total"] == 205
    assert len(first["details"]["items"]) == len(last["details"]["items"]) == 1
    assert first["details"]["items"][0]["id"] != last["details"]["items"][0]["id"]


def test_analytics_fences_fills_committed_after_its_watermark(store):
    round_trip(store)
    appended = False

    def interleave(connection, cursor, sql, parameters, context, many):
        nonlocal appended
        if not appended and "sum(nifty_algo_trade.net)" in sql:
            appended = True
            append_fills(store, 1)

    event.listen(store.engine, "before_cursor_execute", interleave)
    try:
        snapshot = store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1))
    finally:
        event.remove(store.engine, "before_cursor_execute", interleave)
    assert appended
    assert snapshot["metrics"]["trades"] == snapshot["details"]["total"] == 1
    assert store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1))["metrics"]["trades"] == 2


def test_analytics_consolidates_partial_exits_but_keeps_both_fill_events(store):
    round_trip(store)
    append_fills(store, 1)
    with store.sessions.begin() as db:
        original, partial = db.scalars(select(NiftyTrade).order_by(NiftyTrade.id)).all()
        entry = db.get(NiftyOrder, (USER, original.entry_order_id))
        entry.quantity *= 2
        entry.fees *= 2
        partial.entry_order_id = entry.order_id
        partial.opened_at = original.opened_at
        partial_exit = db.get(NiftyOrder, (USER, partial.exit_order_id))
        partial_exit.payload = {**partial_exit.payload, "entry_order_id": entry.order_id}
    result = store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1))
    assert result["metrics"]["trades"] == 1
    assert len(result["metrics"]["equity_curve"]) == result["details"]["total"] == 2
    assert result["metrics"]["risk_coverage"] == {"available": 1, "total": 1, "reason": None}


@pytest.mark.parametrize("corruption", ["duplicate", "quantity", "price", "instrument", "costs"])
def test_analytics_refuses_conflicting_or_duplicate_persisted_fill_evidence(store, corruption):
    round_trip(store)
    with store.sessions.begin() as db:
        trade = db.scalar(select(NiftyTrade))
        exit_order = db.get(NiftyOrder, (USER, trade.exit_order_id))
        if corruption == "duplicate":
            db.add(NiftyTrade(**{
                column.name: getattr(trade, column.name) for column in NiftyTrade.__table__.columns
                if column.name != "id"
            }))
        elif corruption == "quantity":
            trade.quantity += 1
        elif corruption == "price":
            trade.exit_price += 1
        elif corruption == "instrument":
            exit_order.payload = {
                **exit_order.payload, "instrument": {**exit_order.payload["instrument"], "strike": "1"},
            }
        else:
            trade.net += 1
    with pytest.raises(ValueError, match="fill"):
        store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1))


def test_analytics_response_never_exposes_arbitrary_order_context(client, store):
    round_trip(store)
    with store.sessions.begin() as db:
        row = db.scalar(select(NiftyOrder).where(NiftyOrder.side == "BUY"))
        row.payload = {**row.payload, "password": "private-test-secret"}
    login(client)
    response = client.get("/api/nifty-algo/analytics?start=2026-11-19&end=2026-11-20")
    assert response.status_code == 200
    assert "private-test-secret" not in response.text
    assert response.json["data"]["metrics"]["trades"] == 1


def test_analytics_rejects_partial_exits_exceeding_the_filled_entry(store):
    round_trip(store)
    append_fills(store, 1)
    with store.sessions.begin() as db:
        original, partial = db.scalars(select(NiftyTrade).order_by(NiftyTrade.id)).all()
        partial.entry_order_id = original.entry_order_id
        exit_order = db.get(NiftyOrder, (USER, partial.exit_order_id))
        exit_order.payload = {**exit_order.payload, "entry_order_id": original.entry_order_id}
    with pytest.raises(ValueError, match="fill"):
        store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1))


def test_analytics_refuses_oversized_period_instead_of_returning_truncated_metrics(store):
    round_trip(store)
    append_fills(store, 5000)
    with pytest.raises(ValueError, match="5000"):
        store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1))


def test_analytics_sessions_close_on_repeated_success_and_evidence_failure(store):
    round_trip(store)
    checked_out = 0

    def checkout(*args):
        nonlocal checked_out
        checked_out += 1

    def checkin(*args):
        nonlocal checked_out
        checked_out -= 1

    event.listen(store.engine, "checkout", checkout)
    event.listen(store.engine, "checkin", checkin)
    try:
        for _ in range(100):
            store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1))
            assert checked_out == 0
        with store.sessions.begin() as db:
            trade = db.scalar(select(NiftyTrade))
            trade.exit_order_id = "missing-fill"
        for _ in range(100):
            with pytest.raises(ValueError, match="fill"):
                store.analytics_snapshot(USER, NOW, NOW + timedelta(days=1))
            assert checked_out == 0
    finally:
        event.remove(store.engine, "checkout", checkout)
        event.remove(store.engine, "checkin", checkin)


def test_analytics_pdf_requires_session_and_exports_authoritative_period_totals(client, store):
    url = "/api/nifty-algo/analytics.pdf?start=2026-11-19&end=2026-11-20&limit=1"
    assert client.get(url, headers={"Accept": "application/json"}).status_code == 401
    trade = round_trip(store)
    append_fills(store, 204)
    login(client)
    response = client.get(url)
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.headers["Cache-Control"] == "private, no-store"
    with BytesIO(response.data) as buffer:
        document = PdfReader(buffer)
        report_text = "\n".join(page.extract_text() for page in document.pages)
    assert "205" in report_text
    assert str(Decimal(trade["net"]) * 205) in report_text
    assert "not mark-to-market" in report_text
    assert "1 of 205" in report_text
    assert "NO_PERSISTED_MARK_SERIES" in report_text
    assert client.get("/api/nifty-algo/analytics.pdf?start=invalid").status_code == 400
