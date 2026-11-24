"""Comparative views reconcile to existing fills and never write a second ledger."""

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import event, select

from database.nifty_algo_db import NiftyOrder, NiftyShadowPosition, NiftyTrade
from test.test_nifty_algo_analytics_integration import round_trip
from test.test_nifty_algo_paper_executor import NOW, USER
from test.test_nifty_algo_safety_center import client as client
from test.test_nifty_algo_safety_center import login
from test.test_nifty_algo_safety_center import store as store


def test_comparative_ledger_quality_filters_and_mirrors_are_read_only(store):
    trade = round_trip(store)
    with store.sessions.begin() as db:
        entry_id = db.scalars(
            select(NiftyTrade.entry_order_id).where(NiftyTrade.user_id == USER)
        ).one()
        buy = db.get(NiftyOrder, (USER, entry_id))
        for kind, additive, net in (("MIRROR", 0, "-999"), ("INDEPENDENT", 1, "80")):
            db.add(
                NiftyShadowPosition(
                    user_id=USER,
                    shadow_key=kind,
                    kind=kind,
                    status="CLOSED",
                    additive=additive,
                    token=buy.token,
                    symbol=buy.symbol,
                    instrument=buy.payload["instrument"],
                    quantity=buy.quantity,
                    entry_price=buy.price,
                    entry_fees=Decimal("10"),
                    exit_fees=Decimal("10"),
                    gross=Decimal(net) + 20,
                    net=Decimal(net),
                    protection={},
                    session=NOW.date().isoformat(),
                    opened_at=NOW,
                    closed_at=NOW + timedelta(seconds=2),
                    updated_at=NOW,
                )
            )
    account = store.account(USER, NOW)
    writes = []

    def statement(_connection, _cursor, sql, *_):
        if sql.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ")):
            writes.append(sql)

    event.listen(store.engine, "before_cursor_execute", statement)
    try:
        result = store.comparative_analytics(USER, NOW, NOW + timedelta(days=1))
        assert Decimal(result["paper"]["metrics"]["total_net"]) == Decimal(trade["net"])
        assert result["paper"]["quality"]["entry"]["available"] == 1
        assert result["paper"]["quality"]["exit"]["available"] == 1
        assert Decimal(result["independent_shadow"]["metrics"]["total_net"]) == 80
        assert result["mirrors"]["total"] == 1 and not result["mirrors"]["additive"]
        assert result["combined_total"] is None
        assert not result["active_settings_changed"]
        assert (
            store.comparative_analytics(USER, NOW, NOW + timedelta(days=1), side="PE")["paper"][
                "metrics"
            ]["trades"]
            == 0
        )
        assert (
            store.comparative_analytics(
                USER, NOW, NOW + timedelta(days=1), reason="MISSING_REASON"
            )["paper"]["metrics"]["trades"]
            == 0
        )
        assert writes == []
    finally:
        event.remove(store.engine, "before_cursor_execute", statement)
    assert store.account(USER, NOW) == account


def test_missing_quotes_are_unavailable_and_financial_data_still_reconciles(store):
    trade = round_trip(store)
    with store.sessions.begin() as db:
        orders = list(db.scalars(select(NiftyOrder).where(NiftyOrder.user_id == USER)))
        for row in orders:
            row.payload = {k: v for k, v in row.payload.items() if k != "fill_observation"}
    result = store.comparative_analytics(USER, NOW, NOW + timedelta(days=1))
    assert result["paper"]["quality"]["entry"]["available"] == 0
    assert result["paper"]["quality"]["entry"]["quantity_weighted_spread"] is None
    assert Decimal(result["paper"]["metrics"]["total_net"]) == Decimal(trade["net"])


def test_comparative_routes_ownership_validation_and_pdf_reconcile(client, store):
    url = "/api/nifty-algo/analytics/comparison?start=2026-11-19&end=2026-11-20"
    assert client.get(url, headers={"Accept": "application/json"}).status_code == 401
    trade = round_trip(store)
    login(client)
    response = client.get(url)
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert Decimal(response.json["data"]["paper"]["metrics"]["total_net"]) == Decimal(trade["net"])
    pdf = client.get(url + "&format=pdf")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf"
    assert "no-store" in pdf.headers["Cache-Control"]
    text = " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf.data)).pages)
    assert "Recorded execution quality" in text and "PAPER" in text
    assert str(trade["net"]).rstrip("0").rstrip(".") in text
    assert client.get(url + "&side=OTM").status_code == 400
    assert client.get(url + "&user=someone-else").status_code == 400


@pytest.mark.parametrize("bad", ["OTM", "", 2])
def test_comparison_rejects_unsupported_filters(store, bad):
    with pytest.raises(ValueError):
        store.comparative_analytics(USER, NOW, NOW + timedelta(days=1), side=bad)


def test_actual_execution_recording_captures_owned_fill_quotes_and_reasons_without_writes(store):
    from services.nifty_algo.research import recording_batch

    round_trip(store)
    rows = store.execution_observations(USER, NOW, NOW + timedelta(seconds=3))
    normalized = recording_batch(rows, NOW + timedelta(seconds=3))
    assert {r["payload"]["event"] for r in normalized} == {"ENTRY_FILL", "EXIT_FILL"}
    assert all(r["payload"]["mode"] == "PAPER" and r["payload"]["quote"] for r in normalized)
    assert (
        next(r for r in normalized if r["payload"]["event"] == "EXIT_FILL")["payload"]["reason"]
        == "TARGET_HIT"
    )
    assert store.execution_observations("other", NOW, NOW + timedelta(seconds=3)) == []
