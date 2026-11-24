"""Named jobs on OpenAlgo's native IST scheduler; no private worker loops.

Protection and entry jobs are separate so history requests cannot suspend exits.
The database lease fences ownership across application restarts.
"""

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from time import monotonic
from uuid import uuid4
from zoneinfo import ZoneInfo

from utils.keyed_locks import KeyedLocks
from utils.logging import get_logger

from .assessment import assess_current
from .calendar import IST
from .config import StrategyConfig
from .contract_resolver import Resolver, SelectionUnavailable
from .models import Instrument
from .native_data import NativeDataAdapter
from .paper_executor import NiftyPaperExecutor, OrderRefused, _charges
from .protection import early_booking_exit, momentum_weakening
from .research import opportunity_from_decision, recording_scope
from .safe_logging import log_failure
from .shadow import ShadowBook

_ATTACH_LOCKS = KeyedLocks(name="nifty-paper-attach")
logger = get_logger(__name__)


class NiftyRunner:
    def __init__(
        self,
        store,
        user_id,
        *,
        native=None,
        assessment=None,
        executor=None,
        clock=None,
        publish=None,
    ):
        self.store, self.user_id = store, user_id
        self.clock = clock or (lambda: datetime.now(UTC))
        self.native = native or NativeDataAdapter(clock=self.clock)
        self.executor = executor or NiftyPaperExecutor(
            store, user_id, market_data=self.native.market_data
        )
        self.assessment = assessment
        self.shadow = ShadowBook(
            store,
            user_id,
            quote=lambda instrument, now, config: self.executor._depth(instrument, now, config),
        )
        self.publish = publish or (lambda data: None)
        self.owner = uuid4().hex
        self.started_at = self.clock()
        self.last_boundary = None
        self.last_reconnect = None
        self.last_issue = "WARMUP_REQUIRED"
        self.ready = False
        self.reconciled = False
        self.recovery_complete = False
        self.client = None
        self.cache_callback = None
        self.analysis_token = None
        self.assessed_configuration_id = None
        self.owned_subscriptions = set()
        self.last_assessed_at = None
        self.socket_ref = None
        self.closed = False
        self.recording_feed = None

    def _lease(self, now):
        if self.closed:
            return False
        return self.store.claim_runner(
            self.user_id,
            self.owner,
            now,
            payload={
                "entries_ready": self.ready,
                "reason": self.last_issue,
                "started_at": self.started_at.isoformat(),
                "last_boundary": self.last_boundary,
                "configuration_id": self.assessed_configuration_id,
                "assessed_at": (
                    self.last_assessed_at.isoformat() if self.last_assessed_at else None
                ),
            },
        )

    def protect(self, now=None):
        now = now or self.clock()
        if self.last_assessed_at is not None and (now - self.last_assessed_at).total_seconds() > 30:
            self.ready = False
            self.last_issue = "AWAITING_NEXT_COMPLETED_ENTRY_BAR"
        if self.client is not None and (not self.client.connected or not self.client.authenticated):
            self.ready = False
            self.last_issue = "MARKET_DATA_DISCONNECTED"
        if not self._lease(now):
            return {"reason": "RUNNER_OWNED_ELSEWHERE"}
        if not self.recovery_complete or (
            not self.reconciled and not self.store.positions(self.user_id)
        ):
            report = self.executor.reconcile(now)
            self.reconciled = not report["reasons"]
            self.recovery_complete = True
        self.executor.monitor_exits(now)
        fills = self.executor.process(now)
        self._shadow_upkeep(now)
        if fills:
            self.publish({"kind": "paper_fills", "count": len(fills)})
        return fills

    def evaluate(self, now=None):
        now = now or self.clock()
        if not self._lease(now):
            return None
        state = self.store.read(self.user_id)
        try:
            config = StrategyConfig.model_validate(state["configuration"])
        except ValueError:
            self.ready = False
            self.last_issue = "CONFIGURATION_INCOMPATIBLE"
            if self.assessment is None:
                try:
                    # This profile supplies read-only feed parameters only.
                    # Existing exposure keeps its own valid entry configuration.
                    self._native_feed(StrategyConfig(), now)
                except Exception as error:
                    log_failure(logger, "NIFTY protection feed bootstrap", error)
            self._lease(now)
            return None
        if self.assessed_configuration_id != config.version_id:
            self.ready = False
        self.executor.config = config
        key = None
        if self.assessment is None:
            try:
                key = self._native_feed(config, now)
            except Exception as exc:
                issue = (
                    ", ".join(exc.reasons)
                    if isinstance(exc, OrderRefused)
                    else "DATA_PIPELINE_UNAVAILABLE"
                )
                if issue != self.last_issue:
                    log_failure(logger, "NIFTY data pipeline", exc)
                    self.store.record_event(self.user_id, "data_blocked", {"reason": issue}, now)
                self.ready, self.last_issue = False, issue
                self._lease(now)
                return None
        # One source history request per completed five-minute boundary. Startup
        # and reconnect establish a new causal floor; missed signals are not replayed.
        boundary = int(now.timestamp()) // 300
        if boundary == self.last_boundary:
            return None
        self.last_boundary = boundary
        shadow_decision = None
        try:
            decision = (
                self.assessment(config, now)
                if self.assessment
                else assess_current(
                    key,
                    config,
                    now,
                    native=self.native,
                    observation_only=False,
                    evidence_sink=self._record_analysis_frame,
                )
            )
            self.assessed_configuration_id = config.version_id
            self.last_assessed_at = now
            self.ready = not any(
                c["state"] == "UNAVAILABLE"
                or (c["rule"] in ("R-WARMUP", "R-FRESH") and c["state"] != "PASS")
                for c in decision["checks"]
            )
            self.ready = (
                self.ready
                and not any(
                    reason in decision["reasons"]
                    for reason in ("MASTER_FRESHNESS_UNVERIFIED", "SESSION_VWAP_INCOMPLETE")
                )
                and self.reconciled
            )
            self.last_issue = None if self.ready else "; ".join(decision["reasons"])
            decision = self.store.record_decision(self.user_id, decision)
            self.publish({"kind": "decision", "decision_id": decision["decision_id"]})
            self._research(decision, config, now)
            # Data readiness, not primary entry refusals, qualifies a shadow entry.
            shadow_decision = decision if self.ready else None
            # Technical invalidation uses only fresh, completed indicator states.
            invalidated = set()
            discretionary_exits = {}
            st = decision.get("snapshot", {}).get("supertrend")
            fresh = any(c["rule"] == "R-FRESH" and c["state"] == "PASS" for c in decision["checks"])
            snapshot = decision.get("snapshot") or {}
            for held in self.store.positions(self.user_id):
                direction = 1 if held["instrument"]["kind"] == "CE" else -1
                protection = held.get("protection") or {}
                entry_context = (held.get("protection") or {}).get("signal_context") or {}
                same_future = decision.get("analysis_token") == entry_context.get("analysis_token")
                entry_snapshot = entry_context.get("snapshot") or {}
                entry_st = entry_snapshot.get("supertrend") or {}
                entry_config = (
                    StrategyConfig.model_validate(held["protection"]["configuration"])
                    if held.get("protection")
                    else config
                )
                atr_invalid = (
                    same_future
                    and entry_st.get("atr")
                    and entry_snapshot.get("price")
                    and decision.get("snapshot", {}).get("price")
                    and (entry_snapshot["price"] - decision["snapshot"]["price"]) * direction
                    >= entry_st["atr"] * entry_config.atr_exit_multiple
                )
                if fresh and ((st and same_future and st["direction"] != direction) or atr_invalid):
                    invalidated.add(held["token"])
                if fresh and snapshot.get("end") and protection:
                    previous_snapshot = protection.get("last_snapshot")
                    if previous_snapshot:
                        source_time = protection.get("last_source_time")
                        last_bid = protection.get("last_bid")
                        try:
                            quote_age = (now - datetime.fromisoformat(source_time)).total_seconds()
                            if (
                                last_bid is not None
                                and 0 <= quote_age <= entry_config.quote_max_age
                                and momentum_weakening(previous_snapshot, snapshot, direction)
                            ):
                                reason = early_booking_exit(
                                    protection,
                                    held["entry_price"],
                                    last_bid,
                                    held["instrument"]["tick_size"],
                                    entry_config,
                                    quantity=held["quantity"],
                                    entry_fees=protection.get("entry_fees_remaining", "0"),
                                    charges=_charges,
                                    momentum_weak=True,
                                )
                                if reason:
                                    discretionary_exits[held["token"]] = reason
                        except (TypeError, ValueError):
                            pass
                    self.store.update_position_snapshot(
                        self.user_id,
                        held["token"],
                        {key: snapshot[key] for key in ("end", "price", "macd") if key in snapshot},
                    )
            self.executor.monitor_exits(
                now,
                technical_invalidations=invalidated,
                discretionary_exits=discretionary_exits,
            )
            end = decision.get("snapshot", {}).get("end")
            if (
                state["state"] != "RUNNING"
                or state["killed"]
                or not self.ready
                or not decision["eligible"]
                or self.closed
                or not end
                or datetime.fromisoformat(end) <= self.started_at
            ):
                return decision
            if self.store.read(self.user_id)["configuration_id"] != config.version_id:
                raise OrderRefused(["CONFIGURATION_CHANGED"])
            # Loss cooldown and monthly locks gate entry before contract resolution.
            locks = self.executor.entry_lock_reasons(now, config)
            if locks:
                raise OrderRefused(locks)
            candidates, candidate_metadata = self._entry_candidates(decision, config, now)
            instrument = candidates[0]
            self.executor.admit(
                {
                    "intent_id": f"entry:{decision['decision_id']}",
                    "decision_id": decision["decision_id"],
                    "side": "BUY",
                    "symbol": instrument.symbol,
                    "token": instrument.token,
                    "instrument": instrument,
                    "candidates": candidates,
                    "candidate_metadata": candidate_metadata,
                    "runner_owner": self.owner,
                },
                now,
            )
            return decision
        except OrderRefused as exc:
            self.last_issue = ", ".join(exc.reasons)
            self.ready = False
            self.store.record_event(self.user_id, "entry_rejected", {"reasons": exc.reasons}, now)
        except Exception as exc:
            # Never log broker credentials, API bodies or arbitrary error strings.
            log_failure(logger, "NIFTY assessment pipeline", exc)
            self.ready = False
            self.last_issue = "DATA_PIPELINE_UNAVAILABLE"
            self.store.record_event(self.user_id, "data_blocked", {"reason": self.last_issue}, now)
        finally:
            # Shadows follow the primary attempt, so a pending primary BUY takes precedence.
            if shadow_decision is not None:
                self._shadow_entry(shadow_decision, config, now)
            self._lease(self.clock() if now is None else now)
        return None

    def _entry_candidates(self, decision, config, now, *, mode="PAPER"):
        if mode not in {"PAPER", "SHADOW"}:
            raise ValueError("Selector mode must be PAPER or SHADOW")
        spot_reference = None
        try:
            market = self.native.get_market()
            spot = market.get("spot")
            if not spot or spot["status"] != "AVAILABLE":
                raise OrderRefused(["SPOT_REFERENCE_UNAVAILABLE"])
            try:
                spot_reference = Decimal(str(spot["ltp"]))
                if not spot_reference.is_finite() or spot_reference <= 0:
                    raise ValueError("Invalid spot")
            except (ValueError, TypeError, ArithmeticError):
                spot_reference = None
                raise OrderRefused(["SPOT_REFERENCE_UNAVAILABLE"]) from None
            instruments = self.native.instruments(now)
            if config.pcr_expiry:
                instruments = [
                    i for i in instruments if i.kind == "FUT" or i.expiry == config.pcr_expiry
                ]
            quotes = {
                i.token: self.executor._depth(i, now)
                for i in instruments
                if i.kind == decision["side"]
            }
            report = Resolver().assess(
                instruments, quotes, spot_reference, decision["side"], now, config
            )
        except (OrderRefused, ValueError) as exc:
            if isinstance(exc, OrderRefused):
                reasons = exc.reasons
            elif isinstance(exc, SelectionUnavailable):
                reasons = [exc.code]
            else:
                reasons = ["CONTRACT_EVIDENCE_UNAVAILABLE"]
            self.store.record_event(
                self.user_id,
                f"contract_selector:{mode}",
                {
                    "status": "UNAVAILABLE",
                    "reasons": reasons,
                    "policy": "listed-preference-v1",
                    "configuration_id": config.version_id,
                    "decision_id": decision["decision_id"],
                    "mode": mode,
                    "evaluated_at": now.isoformat(),
                    "spot_reference": str(spot_reference) if spot_reference is not None else None,
                    "atm_strike": None,
                    "expiry": None,
                    "ranked_tokens": [],
                    "candidates": [],
                    "omitted_candidates": 0,
                },
                now,
            )
            raise
        self.store.record_event(
            self.user_id,
            f"contract_selector:{mode}",
            {**report, "decision_id": decision["decision_id"], "mode": mode},
            now,
        )
        eligible = [item for item in report["candidates"] if not item["reasons"]]
        if not eligible:
            raise OrderRefused(["CONTRACT_LIQUIDITY_UNAVAILABLE"])
        candidates = [Instrument.model_validate(item["instrument"]) for item in eligible]
        return candidates, [
            {
                "token": item["instrument"]["token"],
                "moneyness": item["moneyness"],
                "spot_reference": report["spot_reference"],
                "atm_strike": report["atm_strike"],
            }
            for item in eligible
        ]

    def _research(self, decision, config, now):
        """Research-only observation step; never admits, fills or transmits orders."""
        try:
            snapshot = decision.get("snapshot") or {}
            if snapshot.get("end") and snapshot.get("price") is not None:
                self.store.observe_opportunities(
                    self.user_id,
                    {
                        "token": decision.get("analysis_token"),
                        "price": snapshot["price"],
                        "at": snapshot["end"],
                    },
                    now,
                )
            opportunity = opportunity_from_decision(decision, config)
            if opportunity is not None:
                self.store.record_opportunity(self.user_id, opportunity, now)
        except Exception as exc:
            logger.warning("NIFTY research observation skipped: %s", type(exc).__name__)

    def _shadow_entry(self, decision, config, now):
        """Hypothetical independent entry; failures never reach the primary path."""
        end = (decision.get("snapshot") or {}).get("end")
        if (
            self.closed
            or not decision.get("eligible")
            or not end
            or datetime.fromisoformat(end) <= self.started_at
        ):
            return None
        try:
            if self.shadow.entry_blocks(now, config):
                return None
            row, _ = self.shadow.open_independent(
                decision,
                now,
                config,
                lambda: self._entry_candidates(decision, config, now, mode="SHADOW")[0],
            )
            return row
        except Exception as exc:
            logger.warning("NIFTY shadow entry skipped: %s", type(exc).__name__)
            return None

    def _shadow_upkeep(self, now):
        """Mirror the primary, protect the shadow and stop expired research steps."""
        try:
            self.shadow.sync_mirrors(now)
            self.shadow.monitor(now)
            self.store.expire_opportunities(self.user_id, now)
        except Exception as exc:
            logger.warning("NIFTY shadow upkeep skipped: %s", type(exc).__name__)

    def _native_feed(self, config, now):
        self.recording_feed = None
        from database.auth_db import get_api_key_for_tradingview, get_broker_name
        from services.websocket_service import get_websocket_connection

        key = get_api_key_for_tradingview(self.user_id)
        if not key:
            raise OrderRefused(["MARKET_DATA_AUTH_UNAVAILABLE"])
        ok, client, _ = get_websocket_connection(self.user_id)
        if not ok:
            raise OrderRefused(["NATIVE_SUBSCRIPTION_UNAVAILABLE"])
        # Register the existing cache callback once through native conventions.
        from services.market_data_service import get_market_data_service

        service = get_market_data_service()
        if self.closed:
            raise OrderRefused(["RUNNER_SHUTDOWN"])
        if self.client is not client:
            if self.client is not None and self.cache_callback is not None:
                self.client.unregister_callback("market_data", self.cache_callback)
            if self.cache_callback is not None:
                # Native client replacement adopts registered callbacks. Remove
                # our adopted callback before registering its replacement.
                client.unregister_callback("market_data", self.cache_callback)
            self.cache_callback = lambda data: service.process_market_data(data)
            client.register_callback("market_data", self.cache_callback)
            self.client = client
            self.owned_subscriptions.clear()
            self.started_at = now
        if self.socket_ref is not client.ws:
            self.socket_ref = client.ws
            self.started_at = now
        self.executor.market_data = self.native.market_data = service
        # Held-contract data remains an independent prerequisite from entry PCR.
        # Attempt these subscriptions even when the current master/PCR is blocked.
        active_before = {
            (row["exchange"], row["symbol"], row["mode"])
            for row in client.get_subscriptions()["subscriptions"]
        }
        held_missing = {
            ("NFO", row["symbol"], "Depth") for row in self.store.positions(self.user_id)
        } - active_before
        if held_missing:
            ack = client.subscribe(
                [{"exchange": e, "symbol": s} for e, s, _ in sorted(held_missing)], "Depth"
            )
            self.owned_subscriptions.update(
                (row["exchange"], row["symbol"], "Depth")
                for row in ack.get("subscriptions", [])
                if row.get("status") == "success"
            )
            if ack.get("status") != "success":
                raise OrderRefused(["PROTECTIVE_SUBSCRIPTION_ACK_FAILED"])
        health = service.health_monitor.get_health()
        reconnect = health.get("reconnect_count")
        if self.last_reconnect is not None and reconnect != self.last_reconnect:
            self.started_at = now
        self.last_reconnect = reconnect
        contracts = self.native.instruments(now)
        broker = get_broker_name(key)
        rows = self.native._instruments(now)
        if not broker or not any(row.get("master_broker") == broker for row in rows):
            raise OrderRefused(["INSTRUMENT_MASTER_BROKER_MISMATCH"])
        options = [
            i
            for i in contracts
            if i.kind in ("CE", "PE")
            and (
                not config.avoid_expiry_day
                or i.expiry > now.astimezone(ZoneInfo("Asia/Kolkata")).date()
            )
        ]
        expiry = config.pcr_expiry or min((i.expiry for i in options), default=None)
        wanted = {(i.exchange, i.symbol, "Depth") for i in options if i.expiry == expiry}
        futures = sorted((i for i in contracts if i.kind == "FUT"), key=lambda i: i.expiry)
        if futures:
            wanted.add(("NFO", futures[0].symbol, "Quote"))
            if self.analysis_token != futures[0].token:
                self.analysis_token = futures[0].token
                self.started_at = now
        wanted.add(("NSE_INDEX", "NIFTY", "Quote"))
        for held in self.store.positions(self.user_id):
            wanted.add(("NFO", held["symbol"], "Depth"))
        active = {
            (i["exchange"], i["symbol"], i["mode"])
            for i in client.get_subscriptions()["subscriptions"]
        }
        missing = wanted - active
        # Release only subscriptions this runner originally added. Pre-existing
        # subscriptions are borrowed and remain untouched.
        for exchange, symbol, mode in sorted(self.owned_subscriptions - wanted):
            ack = client.unsubscribe([{"exchange": exchange, "symbol": symbol}], mode)
            if ack.get("status") == "success":
                self.owned_subscriptions.discard((exchange, symbol, mode))
        # Protection subscriptions take priority even if a full PCR scope exceeds
        # broker capacity. Never let an entry prerequisite suppress exit data.
        held_keys = {("NFO", row["symbol"], "Depth") for row in self.store.positions(self.user_id)}
        protection_missing = missing & held_keys
        if protection_missing:
            ack = client.subscribe(
                [{"exchange": e, "symbol": s} for e, s, _ in sorted(protection_missing)], "Depth"
            )
            self.owned_subscriptions.update(
                (e["exchange"], e["symbol"], "Depth")
                for e in ack.get("subscriptions", [])
                if e.get("status") == "success"
            )
            if ack.get("status") != "success":
                raise OrderRefused(["PROTECTIVE_SUBSCRIPTION_ACK_FAILED"])
            missing -= protection_missing
        if len(active | wanted) > 1000:
            raise OrderRefused(["FULL_PCR_SCOPE_EXCEEDS_NATIVE_SUBSCRIPTION_QUOTA"])
        for mode in ("Quote", "Depth"):
            symbols = [{"exchange": e, "symbol": s} for e, s, m in sorted(missing) if m == mode]
            for index in range(0, len(symbols), 50):
                ack = client.subscribe(symbols[index : index + 50], mode)
                self.owned_subscriptions.update(
                    (e["exchange"], e["symbol"], mode)
                    for e in ack.get("subscriptions", [])
                    if e.get("status") == "success"
                )
                if ack.get("status") != "success":
                    raise OrderRefused(["NATIVE_SUBSCRIPTION_ACK_FAILED"])
        try:
            master = self.native.master_reader()
            scope = recording_scope(
                [
                    item
                    for item in contracts
                    if item.kind in ("CE", "PE") and (item.exchange, item.symbol, "Depth") in wanted
                ],
                broker,
                now,
            )
            scope_rows = [
                row
                for row in rows
                if row["kind"] in ("CE", "PE")
                and (row["exchange"], row["symbol"], "Depth") in wanted
            ]
            if any(
                row.get("master_freshness") != "VERIFIED"
                or row.get("master_broker") != broker
                or not row.get("master_complete")
                for row in scope_rows
            ):
                raise ValueError("Recording master verification changed")
            verified_scope = recording_scope(
                [
                    Instrument.model_validate(
                        {
                            key: value
                            for key, value in row.items()
                            if key not in ("master_freshness", "master_broker", "master_complete")
                        }
                    )
                    for row in scope_rows
                ],
                broker,
                now,
            )
            if verified_scope != scope:
                raise ValueError("Recording master identity changed")
            if (
                master
                and master.get("is_ready")
                and master.get("broker") == broker
                and master.get("download_date") == now.astimezone(IST).date().isoformat()
            ):
                self.recording_feed = {
                    "at": now,
                    "client": client,
                    "socket": client.ws,
                    "reconnect": reconnect,
                    "master": dict(master),
                    "scope": scope,
                }
        except Exception as exc:
            # Research metadata must never block the existing trading feed.
            logger.warning("NIFTY recording context skipped: %s", type(exc).__name__)
        return key

    def _recording_feed_current(self, context, now):
        if (
            context is None
            or self.closed
            or self.recording_feed is not context
            or not 0 <= (now - context["at"]).total_seconds() <= 10
            or self.client is not context["client"]
            or not self.client.connected
            or not self.client.authenticated
            or self.client.ws is not context["socket"]
            or self.native.master_reader() != context["master"]
            or self.native.market_data.health_monitor.get_health().get("reconnect_count")
            != context["reconnect"]
        ):
            return False
        active = {
            (row["exchange"], row["symbol"], row["mode"])
            for row in self.client.get_subscriptions()["subscriptions"]
        }
        return all(
            (item["exchange"], item["symbol"], "Depth") in active
            for item in context["scope"]["instruments"]
        )

    def capture(self, now=None):
        """Bounded cache-only quote sampling; never renews readiness or the lease."""
        now = now or self.clock()
        context = self.recording_feed
        try:
            if not self._recording_feed_current(context, now):
                return None
            self._capture_exit_studies(now)
            manifest = next(
                (
                    row
                    for row in self.store.recordings(self.user_id)
                    if row["capture"] is not None
                    and row["status"] == "RECORDING"
                    and row["count"] < row["max_observations"]
                    and row["size_bytes"] < 16777216
                    and datetime.fromisoformat(row["starts_at"])
                    <= now
                    < datetime.fromisoformat(row["ends_at"])
                ),
                None,
            )
            if manifest is None:
                return None
            scope = context["scope"]
            manifest = self.store.freeze_recording_scope(
                self.user_id,
                manifest["id"],
                now,
                instruments=[Instrument.model_validate(item) for item in scope["instruments"]],
                broker=scope["broker"],
                runner_owner=self.owner,
            )
            frozen = manifest["capture"]["scope"]
            instruments = frozen["instruments"]
            # Wall-clock rotation avoids an unbounded process cursor or sample cache.
            start = (int(now.timestamp()) // 5 * 100) % len(instruments)
            limit = min(100, len(instruments), manifest["max_observations"] - manifest["count"])
            deadline = monotonic() + 0.25
            observations = []
            floor = max(datetime.fromisoformat(frozen["frozen_at"]), self.started_at)
            for offset in range(limit):
                if monotonic() >= deadline:
                    break
                item = Instrument.model_validate(instruments[(start + offset) % len(instruments)])
                quote = self.native.recording_quote(item, now)
                if quote is None or quote.source_time < floor:
                    continue
                observations.append(
                    {
                        "kind": "QUOTE",
                        "source": "NATIVE_FEED",
                        "source_time": quote.source_time.isoformat(),
                        "available_at": now.isoformat(),
                        "payload": quote.model_dump(mode="json"),
                    }
                )
            write_now = self.clock()
            if not self._recording_feed_current(context, write_now):
                return None
            if not observations:
                return self._capture_execution_observations(manifest, context, floor, write_now)
            saved = self.store.append_recording(
                self.user_id,
                manifest["id"],
                observations,
                write_now,
                expected_count=manifest["count"],
                deduplicate_samples=True,
                runner_owner=self.owner,
            )
            return self._capture_execution_observations(saved, context, floor, write_now)
        except Exception as exc:
            logger.warning("NIFTY recording capture skipped: %s", type(exc).__name__)
            return None

    def _capture_execution_observations(self, manifest, context, floor, now):
        tokens = {i["token"] for i in context["scope"]["instruments"]}
        observations = [
            o
            for o in self.store.execution_observations(self.user_id, floor, now)
            if o["payload"]["token"] in tokens
        ]
        remaining = manifest["max_observations"] - manifest["count"]
        if (
            not observations
            or remaining <= 0
            or not self._recording_feed_current(context, self.clock())
        ):
            return manifest
        return self.store.append_recording(
            self.user_id,
            manifest["id"],
            observations[:remaining],
            now,
            expected_count=manifest["count"],
            deduplicate_samples=True,
            runner_owner=self.owner,
        )

    def _record_analysis_frame(self, bars, windows, pcr, decision, assessed_at):
        """Entry-job research snapshot; cache/calendar only beyond existing history call."""
        from datetime import timedelta

        from .calendar import nifty_session
        from .execution_replay import validate_frame
        from .selection_scoring import POLICY

        now = self.clock()
        context = self.recording_feed
        if not self._recording_feed_current(context, now):
            return
        manifest = next(
            (
                r
                for r in self.store.recordings(self.user_id)
                if r["status"] == "RECORDING"
                and r["capture"] is not None
                and datetime.fromisoformat(r["starts_at"])
                <= now
                < datetime.fromisoformat(r["ends_at"])
            ),
            None,
        )
        if manifest is None:
            return
        instruments = [Instrument.model_validate(i) for i in context["scope"]["instruments"]]
        manifest = self.store.freeze_recording_scope(
            self.user_id,
            manifest["id"],
            now,
            instruments=instruments,
            broker=context["scope"]["broker"],
            runner_owner=self.owner,
        )
        today = now.astimezone(IST).date()
        days = sorted(set(windows) | {today + timedelta(days=i) for i in range(11)})
        calendars = [
            c
            for year in sorted({d.year for d in days})
            if (c := self.store.approved_calendar_version(self.user_id, year)) is not None
        ]
        sessions = []
        for day in days:
            session = nifty_session(self.user_id, day, store=self.store)
            calendar = next((c for c in calendars if c["year"] == day.year), None)
            window = session["window"]
            sessions.append(
                {
                    "date": day.isoformat(),
                    "status": session["status"],
                    "start": window[0].isoformat() if window else None,
                    "end": window[1].isoformat() if window else None,
                    "calendar_sha256": calendar["sha256"] if calendar else None,
                }
            )
        spot_instrument, spot = self.native.recording_spot(now)
        deadline = monotonic() + 0.25
        quotes = []
        for instrument in instruments:
            if monotonic() >= deadline:
                break
            quote = self.native.recording_quote(instrument, now)
            if quote is not None:
                quotes.append(quote.model_dump(mode="json"))
        analysis = {
            k: v
            for k, v in decision["analysis_instrument"].items()
            if k not in ("master_freshness", "master_broker", "master_complete")
        }
        available_at = self.clock()
        payload = validate_frame(
            {
                "analysis_instrument": analysis,
                "minute_bars": [b.model_dump(mode="json") for b in bars],
                "pcr": pcr.model_dump(mode="json") if pcr else None,
                "pcr_available_at": now.isoformat() if pcr else None,
                "spot": spot.model_dump(mode="json") if spot else None,
                "spot_instrument": spot_instrument,
                "instruments": [i.model_dump(mode="json") for i in instruments],
                "quotes": quotes,
                "sessions": sessions,
                "calendars": calendars,
                "decision": decision,
                "configuration_id": decision["config_id"],
                "selector_policy": POLICY,
            },
            available_at,
        )
        if not self._recording_feed_current(context, self.clock()):
            return
        self.store.append_recording(
            self.user_id,
            manifest["id"],
            [
                {
                    "kind": "FRAME",
                    "source": "NATIVE_FEED",
                    "source_time": available_at.isoformat(),
                    "available_at": available_at.isoformat(),
                    "payload": payload,
                }
            ],
            self.clock(),
            expected_count=manifest["count"],
            runner_owner=self.owner,
        )

    def _capture_exit_studies(self, now):
        """Cache-only sampled research through the approved effective session close."""
        from .calendar import nifty_session

        day = now.astimezone(ZoneInfo("Asia/Kolkata")).date()
        session = nifty_session(self.user_id, day, store=self.store)
        if (
            session["status"] != "TRADING"
            or not session["window"][0] <= now <= session["window"][1]
        ):
            return
        calendar = self.store.approved_calendar_version(self.user_id, day.year)
        deadline = monotonic() + 0.1
        for trade in self.store.exit_study_targets(self.user_id, *session["window"]):
            if monotonic() >= deadline:
                break
            quote = self.native.recording_quote(Instrument.model_validate(trade["instrument"]), now)
            if quote is not None:
                self.store.observe_exit_study(
                    self.user_id, trade["id"], quote, now, session["window"][1], calendar["id"]
                )

    def reports(self, now=None):
        """Report generation and email delivery on their own job; SMTP never delays exits."""
        if self.closed:
            return None
        from .reports import ReportService

        try:
            return ReportService(self.store, self.user_id, clock=self.clock).tick(
                now or self.clock()
            )
        except Exception as exc:
            logger.warning("NIFTY reports skipped: %s", type(exc).__name__)
            return None

    def _native_assessment(self, config, now):
        key = self._native_feed(config, now)
        return assess_current(key, config, now, native=self.native, observation_only=False)

    def close(self):
        self.closed = True
        self.recording_feed = None
        if self.client is not None and self.cache_callback is not None:
            self.client.unregister_callback("market_data", self.cache_callback)
        self.store.release_runner(self.user_id, self.owner)
        self.owned_subscriptions.clear()


def attach_runner(app, scheduler, user_id):
    """Explicitly attach a named runner; stop/kill disables entries, never protection."""
    with _ATTACH_LOCKS.hold((id(app), user_id)):
        return _attach_runner(app, scheduler, user_id)


def _attach_runner(app, scheduler, user_id):
    runners = app.extensions.setdefault("nifty_algo_runners", {})
    if user_id in runners:
        return runners[user_id]
    from extensions import emit_from_any_thread

    runner = NiftyRunner(
        app.extensions["nifty_algo_store"],
        user_id,
        publish=lambda payload: emit_from_any_thread(
            "nifty_algo_update", payload, room=f"nifty_algo:{user_id}"
        ),
    )

    def scoped(method):
        def job():
            with app.app_context():
                method()

        return job

    def scoped_reports():
        from utils.db_sessions import session_cleanup

        # Reads OpenAlgo's settings and user tables through their scoped sessions.
        with app.app_context(), session_cleanup():
            runner.reports()

    prefix = "nifty-paper:" + sha256(user_id.encode()).hexdigest()[:24]
    added = []
    try:
        scheduler.add_job(
            scoped(runner.protect),
            "interval",
            seconds=1,
            id=prefix + ":protect",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=1,
            replace_existing=True,
        )
        added.append(prefix + ":protect")
        scheduler.add_job(
            scoped(runner.evaluate),
            "interval",
            seconds=5,
            id=prefix + ":entries",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=1,
            replace_existing=True,
        )
        added.append(prefix + ":entries")
        # Reports run on their own job so a slow mail server never delays the
        # protection or entry jobs.
        scheduler.add_job(
            scoped_reports,
            "interval",
            seconds=60,
            id=prefix + ":reports",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
            replace_existing=True,
        )
        added.append(prefix + ":reports")
        scheduler.add_job(
            scoped(runner.capture),
            "interval",
            seconds=5,
            id=prefix + ":capture",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=1,
            replace_existing=True,
        )
    except Exception:
        runner.ready = False
        runner.closed = True
        for job_id in reversed(added):
            try:
                scheduler.remove_job(job_id)
            except Exception as error:
                log_failure(logger, "NIFTY partial job cleanup", error)
        runner.close()
        raise
    runners[user_id] = runner
    app.extensions.get("nifty_algo_restore_failed", set()).discard(user_id)
    return runner


def restore_runners(app, scheduler):
    from sqlalchemy import select

    from database.nifty_algo_db import NiftyState

    store = app.extensions["nifty_algo_store"]
    app.extensions["nifty_algo_restore_unavailable"] = True
    failures = app.extensions["nifty_algo_restore_failed"] = set()
    with store.sessions() as db:
        users = list(db.scalars(select(NiftyState.user_id)))
    for user_id in users:
        try:
            attach_runner(app, scheduler, user_id)
        except Exception as error:
            failures.add(user_id)
            # No account, position or readiness state is cleared on a failed
            # attachment. Other owners must still recover their protection.
            log_failure(logger, "NIFTY owner runner restoration", error)
    if not app.extensions.get("nifty_algo_shutdown_registered"):
        from utils.shutdown import register_shutdown_hook

        def shutdown():
            for user_id, runner in list(app.extensions.get("nifty_algo_runners", {}).items()):
                prefix = "nifty-paper:" + sha256(user_id.encode()).hexdigest()[:24]
                for suffix in (":capture", ":reports", ":entries", ":protect"):
                    if scheduler.get_job(prefix + suffix):
                        scheduler.remove_job(prefix + suffix)
                runner.close()
            app.extensions.get("nifty_algo_runners", {}).clear()

        register_shutdown_hook(shutdown, name="nifty-paper", budget_s=5, early=True)
        app.extensions["nifty_algo_shutdown_registered"] = True
    app.extensions["nifty_algo_restore_unavailable"] = False
    return {"restored": len(users) - len(failures), "failed": len(failures)}
