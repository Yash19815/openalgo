"""Named jobs on OpenAlgo's native IST scheduler; no private worker loops.

Protection and entry jobs are separate so history requests cannot suspend exits.
The database lease fences ownership across application restarts.
"""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo

from utils.keyed_locks import KeyedLocks

from .assessment import assess_current
from .config import StrategyConfig
from .contract_resolver import Resolver
from .native_data import NativeDataAdapter
from .paper_executor import NiftyPaperExecutor, OrderRefused

_ATTACH_LOCKS = KeyedLocks(name="nifty-paper-attach")


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
                except Exception:
                    pass
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
                    else "DATA_PIPELINE_UNAVAILABLE:" + type(exc).__name__
                )
                if issue != self.last_issue:
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
        try:
            decision = (
                self.assessment(config, now)
                if self.assessment
                else assess_current(key, config, now, native=self.native, observation_only=False)
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
            # Technical invalidation uses only fresh, completed indicator states.
            invalidated = set()
            st = decision.get("snapshot", {}).get("supertrend")
            fresh = any(c["rule"] == "R-FRESH" and c["state"] == "PASS" for c in decision["checks"])
            for held in self.store.positions(self.user_id):
                direction = 1 if held["instrument"]["kind"] == "CE" else -1
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
            self.executor.monitor_exits(now, technical_invalidations=invalidated)
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
            market = self.native.get_market()
            spot = market.get("spot")
            if not spot or spot["status"] != "AVAILABLE":
                raise OrderRefused(["SPOT_REFERENCE_UNAVAILABLE"])
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
            candidates = Resolver().candidates(
                instruments, quotes, spot["ltp"], decision["side"], now, config
            )
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
            self.ready = False
            self.last_issue = "DATA_PIPELINE_UNAVAILABLE:" + type(exc).__name__
            self.store.record_event(self.user_id, "data_blocked", {"reason": self.last_issue}, now)
        finally:
            self._lease(self.clock() if now is None else now)
        return None

    def _native_feed(self, config, now):
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
        return key

    def _native_assessment(self, config, now):
        key = self._native_feed(config, now)
        return assess_current(key, config, now, native=self.native, observation_only=False)

    def close(self):
        self.closed = True
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

    prefix = "nifty-paper:" + sha256(user_id.encode()).hexdigest()[:24]
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
    try:
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
    except Exception:
        scheduler.remove_job(prefix + ":protect")
        raise
    runners[user_id] = runner
    return runner


def restore_runners(app, scheduler):
    from sqlalchemy import select

    from database.nifty_algo_db import NiftyState

    store = app.extensions["nifty_algo_store"]
    with store.sessions() as db:
        users = list(db.scalars(select(NiftyState.user_id)))
    for user_id in users:
        attach_runner(app, scheduler, user_id)
    if not app.extensions.get("nifty_algo_shutdown_registered"):
        from utils.shutdown import register_shutdown_hook

        def shutdown():
            for user_id, runner in list(app.extensions.get("nifty_algo_runners", {}).items()):
                prefix = "nifty-paper:" + sha256(user_id.encode()).hexdigest()[:24]
                for suffix in (":entries", ":protect"):
                    if scheduler.get_job(prefix + suffix):
                        scheduler.remove_job(prefix + suffix)
                runner.close()
            app.extensions.get("nifty_algo_runners", {}).clear()

        register_shutdown_hook(shutdown, name="nifty-paper", budget_s=5, early=True)
        app.extensions["nifty_algo_shutdown_registered"] = True
