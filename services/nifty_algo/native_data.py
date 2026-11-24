"""Read-only views over OpenAlgo's instrument master and existing data cache.

The cache can discard source timestamps. Such observations remain visible for
diagnostics but cannot pass a trading freshness check.
"""

from datetime import UTC, date, datetime, timezone
from decimal import Decimal
from math import isfinite
from zoneinfo import ZoneInfo

from .depth_quote import depth_quote
from .models import Instrument, Quote

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


def _master_status():
    from database.master_contract_status_db import get_last_downloaded_broker, get_status

    broker = get_last_downloaded_broker()
    return get_status(broker) if broker else None


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

    def __init__(
        self, instrument_loader=None, market_data=None, clock=None, max_age=5, master_reader=None
    ):
        if max_age <= 0:
            raise ValueError("Positive maximum quote age required")
        self.instrument_loader = instrument_loader or _load_instruments
        self.market_data = market_data
        self.clock = clock or (lambda: datetime.now(UTC))
        self.max_age = max_age
        self.master_reader = master_reader or (
            _master_status if instrument_loader is None else lambda: None
        )

    def _instruments(self, now):
        before = self.master_reader()
        raw_rows = self.instrument_loader()
        rows = [
            metadata
            for row in raw_rows
            if (metadata := _metadata(row, now.astimezone(IST).date())) is not None
        ]
        master = self.master_reader()
        today = now.astimezone(IST).date().isoformat()
        verified = bool(
            master
            and before == master
            and master.get("is_ready")
            and master.get("download_date") == today
        )
        complete = not any(
            row.get("exchange") == "NFO"
            and row.get("name") == "NIFTY"
            and (
                _expiry(row.get("expiry")) is None
                or _expiry(row.get("expiry")) >= now.astimezone(IST).date()
            )
            and _metadata(row, now.astimezone(IST).date()) is None
            for row in raw_rows
        )
        for row in rows:
            if row["kind"] != "SPOT" and verified:
                row.update(
                    master_date=today,
                    master_freshness="VERIFIED",
                    master_broker=master.get("broker"),
                    master_complete=complete,
                )
        return rows

    def instruments(self, now=None):
        """Validated domain instruments only when master freshness is proven."""
        from .models import Instrument

        return [
            Instrument.model_validate(
                {
                    key: value
                    for key, value in row.items()
                    if key not in ("master_freshness", "master_broker", "master_complete")
                }
            )
            for row in self._instruments(now or self.clock())
            if row["kind"] != "SPOT" and row.get("master_freshness") == "VERIFIED"
        ]

    def recording_quote(self, instrument, now=None):
        """Read only identified mode-3 source evidence; never subscribe or reconnect."""
        if not isinstance(instrument, Instrument) or self.market_data is None:
            return None
        try:
            cached = self.market_data.get_all_data(instrument.symbol, instrument.exchange)
            sources = cached.get("source_observations", {})
            raw = sources.get("3")
            if not isinstance(raw, dict) or (
                raw.get("symbol") != instrument.symbol or raw.get("exchange") != instrument.exchange
            ):
                return None
            depth = raw.get("depth", raw)
            if not isinstance(depth, dict) or any(
                not isinstance(depth[key], (list, tuple)) or len(depth[key]) > 20
                for key in ("buy", "sell", "bids", "asks")
                if depth.get(key) is not None
            ):
                return None
            quote = depth_quote(instrument, raw, now or self.clock(), self.max_age, strict=True)
            if quote is None or quote.bid is None or quote.ask is None:
                return None
            return Quote.model_validate(
                {
                    **quote.model_dump(),
                    "oi": raw.get("oi"),
                    "sequence": raw.get("sequence_number", 0),
                }
            )
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return None

    def recording_spot(self, now):
        """Native source snapshot only; never use the display observation fallback."""
        from .models import Quote

        if self.market_data is None:
            return None, None
        instrument = next((r for r in self._instruments(now) if r["kind"] == "SPOT"), None)
        if instrument is None:
            return None, None
        try:
            raw = self.market_data.get_all_data("NIFTY", "NSE_INDEX").get("source_observations", {})
            raw = raw.get("3") or raw.get("2") or raw.get("1")
            if not isinstance(raw, dict):
                return instrument, None
            source, received = _timestamp(raw.get("ltt")), _timestamp(raw.get("received_time"))
            price = _number(raw.get("ltp"), positive=True)
            if source is None or received is None or price is None or not source <= received <= now:
                return instrument, None
            if not 0 <= (now - source).total_seconds() <= self.max_age:
                return instrument, None
            return instrument, Quote(
                token=instrument["token"],
                source_time=source,
                received_time=received,
                ltp=price,
                provider="NATIVE_SOURCE_CACHE",
            )
        except (TypeError, ValueError, AttributeError):
            return instrument, None

    def quote(self, instrument, now=None, max_age=None):
        """Read causal source fields, never display defaults, for PCR and selection."""
        from .models import Quote

        now = now or self.clock()
        if self.market_data is None:
            from services.market_data_service import get_market_data_service

            self.market_data = get_market_data_service()
        cached = self.market_data.get_all_data(instrument.symbol, instrument.exchange)
        sources = cached.get("source_observations", {})
        raw = sources.get("3") or sources.get("2") or {}
        source, received = _timestamp(raw.get("ltt")), _timestamp(raw.get("received_time"))
        if (
            source is None
            or received is None
            or not source <= received <= now
            or not 0 <= (now - source).total_seconds() <= (max_age or self.max_age)
        ):
            return None
        try:
            price = _number(raw.get("ltp"), positive=True)
            return Quote(
                token=instrument.token,
                source_time=source,
                received_time=received,
                ltp=Decimal(str(price)) if price is not None else None,
                volume=raw.get("volume"),
                oi=raw.get("oi"),
                provider="OPENALGO_SOURCE_CACHE",
            )
        except (ValueError, TypeError, ArithmeticError):
            return None

    def get_pcr(self, config, now=None):
        """Full listed strike universe for one expiry, never the tracker window."""
        from .indicators import pcr

        now = now or self.clock()
        rows = self._instruments(now)
        if not any(row.get("master_freshness") == "VERIFIED" for row in rows):
            return {"pcr": None, "reason": "MASTER_FRESHNESS_UNVERIFIED", "scope": None}
        if any(row.get("master_complete") is False for row in rows):
            return {"pcr": None, "reason": "MASTER_UNIVERSE_INVALID", "scope": None}
        from .models import Instrument

        validated = [
            Instrument.model_validate(
                {
                    key: value
                    for key, value in row.items()
                    if key not in ("master_freshness", "master_broker", "master_complete")
                }
            )
            for row in rows
            if row["kind"] != "SPOT" and row.get("master_freshness") == "VERIFIED"
        ]
        contracts = [
            i
            for i in validated
            if i.kind in ("CE", "PE")
            and (not config.avoid_expiry_day or i.expiry > now.astimezone(IST).date())
        ]
        expiry = config.pcr_expiry or min((i.expiry for i in contracts), default=None)
        contracts = [i for i in contracts if i.expiry == expiry]
        scope = f"NIFTY:NFO:{expiry}:ALL_LISTED_STRIKES"
        quotes = {i.token: self.quote(i, now, config.pcr_max_age) for i in contracts}
        value = pcr(
            contracts, quotes, config.pcr_kind, scope, now, config.pcr_max_age, verified=True
        )
        times = [q.source_time for q in quotes.values() if q is not None]
        skewed = bool(
            times and (max(times) - min(times)).total_seconds() > config.pcr_max_skew_seconds
        )
        if skewed:
            value = None
        return {
            "pcr": value,
            "reason": None
            if value
            else "PCR_TIMESTAMP_SKEW"
            if skewed
            else "COMPLETE_TIMESTAMPED_CHAIN_UNAVAILABLE",
            "scope": scope,
            "expected_contracts": len(contracts),
            "observed_contracts": sum(q is not None for q in quotes.values()),
        }

    def get_contracts(self):
        now = self.clock()
        contracts = [row for row in self._instruments(now) if row["kind"] in ("CE", "PE")]
        return sorted(contracts, key=lambda row: (row["expiry"], row["strike"], row["kind"]))

    def _observation(self, instrument, now):
        if self.market_data is None:
            from services.market_data_service import get_market_data_service

            self.market_data = get_market_data_service()
        cached = self.market_data.get_all_data(instrument["symbol"], instrument["exchange"])
        sources = cached.get("source_observations", {})
        observation = (
            sources.get("3")
            or sources.get("2")
            or sources.get("1")
            or cached.get("quote")
            or cached.get("depth")
            or cached.get("ltp")
            or {}
        )
        source = _timestamp(observation.get("ltt"))
        transport = _timestamp(observation.get("timestamp"))
        received = _timestamp(observation.get("received_time") or cached.get("last_update"))
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
            "master_freshness": future.get("master_freshness", "UNVERIFIED")
            if future
            else "UNVERIFIED",
        }


def get_market():
    return NativeDataAdapter().get_market()


def get_contracts():
    return NativeDataAdapter().get_contracts()
