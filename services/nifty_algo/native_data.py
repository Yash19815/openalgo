"""Read-only views over OpenAlgo's instrument master and existing data cache.

The cache can discard source timestamps. Such observations remain visible for
diagnostics but cannot pass a trading freshness check.
"""

from datetime import UTC, date, datetime, timezone
from math import isfinite
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
FIELDS = (
    "symbol",
    "token",
    "name",
    "exchange",
    "instrumenttype",
    "expiry",
    "strike",
    "lotsize",
    "tick_size",
)


def _load_instruments():
    from database.symbol import SymToken, db_session

    try:
        rows = (
            db_session.query(SymToken)
            .filter(
            SymToken.name.in_(("NIFTY", "Nifty 50", "NIFTY 50")),
                SymToken.exchange.in_(("NFO", "NSE_INDEX")),
            )
            .all()
        )
        return [{field: getattr(row, field) for field in FIELDS} for row in rows]
    finally:
        db_session.remove()


def _timestamp(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else None
    if isinstance(value, bool):
        return None
    try:
        epoch = float(value)
        if not isfinite(epoch) or epoch <= 0:
            return None
        if epoch >= 100_000_000_000:
            epoch /= 1000
        return datetime.fromtimestamp(epoch, UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _number(value, positive=False):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(result) or result < 0 or (positive and result == 0):
        return None
    return result


def _expiry(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for pattern in ("%d-%b-%y", "%d%b%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), pattern).date()
        except ValueError:
            continue
    return None


def _metadata(row, today):
    symbol, token = row.get("symbol"), row.get("token")
    instrument_type = row.get("instrumenttype")
    if not symbol or not token:
        return None
    if (
        row.get("exchange") == "NSE_INDEX"
        and instrument_type == "AMXIDX"
        and row.get("name") in ("NIFTY", "Nifty 50", "NIFTY 50")
        and symbol == "NIFTY"
    ):
        return {"symbol": symbol, "token": str(token), "exchange": "NSE_INDEX", "kind": "SPOT"}
    if row.get("exchange") != "NFO" or row.get("name") != "NIFTY":
        return None
    kind = instrument_type
    if kind in ("FUTIDX", "FUT"):
        kind = "FUT"
    if kind == "OPTIDX":
        kind = next((side for side in ("CE", "PE") if symbol.endswith(side)), None)
    if kind not in ("FUT", "CE", "PE"):
        return None
    expiry = _expiry(row.get("expiry"))
    lot = _number(row.get("lotsize"), positive=True)
    tick = _number(row.get("tick_size"), positive=True)
    strike = _number(row.get("strike"), positive=True)
    if expiry is None or expiry < today or lot is None or int(lot) != lot or tick is None:
        return None
    if kind in ("CE", "PE") and strike is None:
        return None
    return {
        "symbol": symbol,
        "token": str(token),
        "underlying": "NIFTY",
        "exchange": "NFO",
        "kind": kind,
        "expiry": expiry.isoformat(),
        "strike": strike if kind in ("CE", "PE") else None,
        "lot_size": int(lot),
        "tick_size": tick,
        "master_freshness": "UNVERIFIED",
    }


class NativeDataAdapter:
    """Read cached observations without subscribing or creating broker sessions."""

    def __init__(self, instrument_loader=None, market_data=None, clock=None, max_age=5):
        if max_age <= 0:
            raise ValueError("Positive maximum quote age required")
        self.instrument_loader = instrument_loader or _load_instruments
        self.market_data = market_data
        self.clock = clock or (lambda: datetime.now(UTC))
        self.max_age = max_age

    def _instruments(self, now):
        return [
            metadata
            for row in self.instrument_loader()
            if (metadata := _metadata(row, now.astimezone(IST).date())) is not None
        ]

    def get_contracts(self):
        now = self.clock()
        contracts = [row for row in self._instruments(now) if row["kind"] in ("CE", "PE")]
        return sorted(contracts, key=lambda row: (row["expiry"], row["strike"], row["kind"]))

    def _observation(self, instrument, now):
        if self.market_data is None:
            from services.market_data_service import get_market_data_service

            self.market_data = get_market_data_service()
        cached = self.market_data.get_all_data(instrument["symbol"], instrument["exchange"])
        observation = cached.get("quote") or cached.get("depth") or cached.get("ltp") or {}
        source = _timestamp(observation.get("ltt"))
        transport = _timestamp(observation.get("timestamp"))
        received = _timestamp(cached.get("last_update"))
        price = _number(observation.get("ltp", observation.get("value")), positive=True)
        reasons = []
        if price is None:
            reasons.append("PRICE_UNAVAILABLE")
        if source is None:
            reasons.append("SOURCE_TIMESTAMP_UNAVAILABLE")
        if received is None:
            reasons.append("RECEIPT_TIMESTAMP_UNAVAILABLE")
        if source is not None and received is not None:
            if not source <= received <= now:
                reasons.append("TIMESTAMP_ORDER_INVALID")
            if not 0 <= (now - source).total_seconds() <= self.max_age:
                reasons.append("SOURCE_QUOTE_STALE")
            if source.astimezone(IST).date() != now.astimezone(IST).date():
                reasons.append("PREVIOUS_SESSION_QUOTE")
        return {
            "instrument": instrument,
            "ltp": price,
            "volume": None if instrument["kind"] == "SPOT" else _number(observation.get("volume")),
            "oi": _number(observation.get("oi")),
            "source_time": source.isoformat() if source else None,
            "transport_time": transport.isoformat() if transport else None,
            "received_time": received.isoformat() if received else None,
            "feed_latency_ms": (received - source).total_seconds() * 1000
            if source and received and received >= source
            else None,
            "status": "DATA_UNAVAILABLE" if reasons else "AVAILABLE",
            "reasons": reasons,
        }

    def get_market(self):
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("Clock requires timezone")
        instruments = self._instruments(now)
        spot = next((row for row in instruments if row["kind"] == "SPOT"), None)
        futures = sorted(
            (row for row in instruments if row["kind"] == "FUT"),
            key=lambda row: (row["expiry"], row["symbol"]),
        )
        future = futures[0] if futures else None
        return {
            "spot": self._observation(spot, now) if spot else None,
            "future": self._observation(future, now) if future else None,
            "source": "OPENALGO_CACHE",
            "master_freshness": "UNVERIFIED",
        }


def get_market():
    return NativeDataAdapter().get_market()


def get_contracts():
    return NativeDataAdapter().get_contracts()
