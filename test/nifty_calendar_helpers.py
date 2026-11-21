from hashlib import sha256


def seed_market_timing():
    from database import market_calendar_db

    market_calendar_db.MarketTiming.__table__.create(
        market_calendar_db.engine, checkfirst=True
    )
    session = market_calendar_db.db_session()
    try:
        timing = (
            session.query(market_calendar_db.MarketTiming)
            .filter_by(exchange_code="NFO")
            .first()
        )
        if timing is None:
            timing = market_calendar_db.MarketTiming(exchange_code="NFO")
        timing.start_time = "09:15"
        timing.end_time = "15:40"
        timing.start_offset = 33_300_000
        timing.end_offset = 56_400_000
        session.add(timing)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        market_calendar_db.db_session.remove()
    market_calendar_db.clear_market_calendar_cache()


def seed_approved_nfo_calendar(store, user_id, year, entries=()):
    store.ensure_user(user_id)
    calendar = store.approved_calendar_version(user_id, year)
    if calendar is not None:
        return calendar

    # Use a genuine known holiday as the empty-fixture default; never
    # approve a blank production calendar just to satisfy unit tests.
    entries = list(entries) or [
        {"date": f"{year}-01-26", "name": "Republic Day (test fixture)"}
    ]
    data = ("date,name\n" + "".join(
        f"{entry['date']},{entry.get('name') or 'Test holiday'}\n"
        for entry in entries
    )).encode("utf-8")
    draft = store.create_calendar_draft(
        user_id,
        year=year,
        segment="NFO",
        source_filename="fixture.csv",
        sha256=sha256(data).hexdigest(),
        uploader=user_id,
        entries=[dict(entry) for entry in entries],
        issues=[],
        data=data,
        extension="csv",
    )
    return store.approve_calendar(
        user_id,
        draft["id"],
        confirmed_year=year,
        confirmed_segment="NFO",
        actor=user_id,
    )


def seed_nifty_calendar_dependencies(store, user_id, year):
    seed_market_timing()
    seed_approved_nfo_calendar(store, user_id, year)
