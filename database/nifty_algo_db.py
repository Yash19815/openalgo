"""Additive feature state in OpenAlgo's configured database.

Sessions are short lived. Revisions use compare-and-set updates so a delayed
browser save cannot overwrite another control or configuration change. The
paper ledger keeps funds, order intents, positions and closed trades inside
this feature only; it never shares the shared Sandbox balance.
"""

from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class NiftyState(Base):
    __tablename__ = "nifty_algo_state"
    user_id = Column(String(255), primary_key=True)
    revision = Column(Integer, nullable=False, default=1)
    state = Column(String(30), nullable=False, default="PAUSED")
    killed = Column(Integer, nullable=False, default=0)
    daily_locked = Column(Integer, nullable=False, default=0)
    configuration = Column(JSON, nullable=False)
    configuration_id = Column(String(64), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class NiftyConfiguration(Base):
    __tablename__ = "nifty_algo_configuration"
    user_id = Column(String(255), primary_key=True)
    revision = Column(Integer, primary_key=True)
    configuration_id = Column(String(64), nullable=False)
    configuration = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class NiftyEvent(Base):
    __tablename__ = "nifty_algo_event"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    kind = Column(String(40), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class NiftyDecision(Base):
    __tablename__ = "nifty_algo_decision"
    user_id = Column(String(255), primary_key=True)
    decision_id = Column(String(64), primary_key=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)


class NiftyAccount(Base):
    """Isolated feature ledger. Never shares the shared Sandbox balance."""

    __tablename__ = "nifty_algo_account"
    user_id = Column(String(255), primary_key=True)
    equity = Column(Numeric(18, 4), nullable=False)
    available = Column(Numeric(18, 4), nullable=False)
    starting_day_equity = Column(Numeric(18, 4), nullable=False)
    realized_day = Column(Numeric(18, 4), nullable=False, default=0)
    day = Column(String(10), nullable=False)
    daily_entries = Column(Integer, nullable=False, default=0)
    reconciled = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class NiftyOrder(Base):
    """Durable order intent. ``intent_id`` makes admission idempotent."""

    __tablename__ = "nifty_algo_order"
    __table_args__ = (UniqueConstraint("user_id", "intent_id"),)
    user_id = Column(String(255), primary_key=True)
    order_id = Column(String(64), primary_key=True)
    intent_id = Column(String(128), nullable=False)
    side = Column(String(4), nullable=False)
    symbol = Column(String(64), nullable=False)
    token = Column(String(32), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(12), nullable=False)
    reason = Column(String(64), nullable=False, default="")
    price = Column(Numeric(18, 4))
    fees = Column(Numeric(18, 4))
    payload = Column(JSON, nullable=False)
    eligible_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True))


class NiftyPosition(Base):
    __tablename__ = "nifty_algo_position"
    user_id = Column(String(255), primary_key=True)
    token = Column(String(32), primary_key=True)
    symbol = Column(String(64), nullable=False)
    instrument = Column(JSON, nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Numeric(18, 4), nullable=False)
    entry_order_id = Column(String(64), nullable=False)
    highest = Column(Numeric(18, 4), nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=False)


class NiftyTrade(Base):
    __tablename__ = "nifty_algo_trade"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    entry_order_id = Column(String(64), nullable=False)
    exit_order_id = Column(String(64), nullable=False)
    symbol = Column(String(64), nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Numeric(18, 4), nullable=False)
    exit_price = Column(Numeric(18, 4), nullable=False)
    gross = Column(Numeric(18, 4), nullable=False)
    fees = Column(Numeric(18, 4), nullable=False)
    net = Column(Numeric(18, 4), nullable=False)
    reason = Column(String(64), nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=False)


class StateConflict(ValueError):
    """The caller used an obsolete state revision."""


def _instant(value):
    # SQLite drops timezone metadata from UTC timestamps on read.
    return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.isoformat()


class NiftyStore:
    def __init__(self, engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def initialize(self):
        Base.metadata.create_all(self.engine)

    def ensure_user(self, user_id):
        from services.nifty_algo.config import StrategyConfig

        config = StrategyConfig()
        now = datetime.now(UTC)
        try:
            with self.sessions.begin() as db:
                if db.get(NiftyState, user_id) is not None:
                    return
                values = config.model_dump(mode="json")
                db.add(
                    NiftyState(
                        user_id=user_id,
                        configuration=values,
                        configuration_id=config.version_id,
                        updated_at=now,
                    )
                )
                db.add(
                    NiftyConfiguration(
                        user_id=user_id,
                        revision=1,
                        configuration_id=config.version_id,
                        configuration=values,
                        created_at=now,
                    )
                )
        except IntegrityError:
            # Another request can initialize the same user concurrently.
            with self.sessions() as db:
                if db.get(NiftyState, user_id) is None:
                    raise

    def read(self, user_id):
        self.ensure_user(user_id)
        with self.sessions() as db:
            row = db.get(NiftyState, user_id)
            return {
                "revision": row.revision,
                "state": row.state,
                "killed": bool(row.killed),
                "daily_locked": bool(row.daily_locked),
                "configuration": row.configuration,
                "configuration_id": row.configuration_id,
                "updated_at": _instant(row.updated_at),
            }

    def change(self, user_id, revision, *, configuration=None, action=None):
        self.ensure_user(user_id)
        now = datetime.now(UTC)
        values = {"revision": revision + 1, "updated_at": now}
        if configuration is not None:
            values.update(
                configuration=configuration.model_dump(mode="json"),
                configuration_id=configuration.version_id,
                state="PAUSED",
            )
        if action in ("pause", "stop"):
            values["state"] = "PAUSED" if action == "pause" else "STOPPED"
        elif action == "kill-switch":
            values.update(state="KILLED", killed=1)
        elif action is not None:
            raise ValueError("Unsupported control")
        with self.sessions.begin() as db:
            # Killing is monotonic. Configuration and pause cannot clear it.
            row = db.get(NiftyState, user_id)
            if row.killed:
                values["state"] = "KILLED"
            changed = db.execute(
                update(NiftyState)
                .where(NiftyState.user_id == user_id, NiftyState.revision == revision)
                .values(**values)
            )
            if changed.rowcount != 1:
                raise StateConflict("State changed. Reload before saving.")
            if configuration is not None:
                db.add(
                    NiftyConfiguration(
                        user_id=user_id,
                        revision=revision + 1,
                        configuration_id=configuration.version_id,
                        configuration=values["configuration"],
                        created_at=now,
                    )
                )
            db.add(
                NiftyEvent(
                    user_id=user_id,
                    kind=action or "configuration",
                    payload={"revision": revision + 1},
                    created_at=now,
                )
            )
        return self.read(user_id)

    def decisions(self, user_id, decision_id=None):
        with self.sessions() as db:
            query = select(NiftyDecision).where(NiftyDecision.user_id == user_id)
            if decision_id:
                query = query.where(NiftyDecision.decision_id == decision_id)
            rows = db.scalars(query.order_by(NiftyDecision.created_at.desc()).limit(100))
            return [row.payload for row in rows]

    def record_decision(self, user_id, decision):
        try:
            with self.sessions.begin() as db:
                db.add(
                    NiftyDecision(
                        user_id=user_id,
                        decision_id=decision["decision_id"],
                        payload=decision,
                        created_at=datetime.now(UTC),
                    )
                )
        except IntegrityError:
            with self.sessions() as db:
                existing = db.get(NiftyDecision, (user_id, decision["decision_id"]))
                if existing is None:
                    raise
                return existing.payload
        return decision

    def events(self, user_id):
        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyEvent)
                .where(NiftyEvent.user_id == user_id)
                .order_by(NiftyEvent.id.desc())
                .limit(100)
            )
            return [
                {
                    "id": row.id,
                    "kind": row.kind,
                    "payload": row.payload,
                    "created_at": _instant(row.created_at),
                }
                for row in rows
            ]

    # Isolated paper ledger -------------------------------------------------

    @staticmethod
    def _account_dict(row):
        return {
            "equity": str(row.equity),
            "available": str(row.available),
            "starting_day_equity": str(row.starting_day_equity),
            "realized_day": str(row.realized_day),
            "day": row.day,
            "daily_entries": row.daily_entries,
            "reconciled": bool(row.reconciled),
            "updated_at": _instant(row.updated_at),
        }

    @staticmethod
    def _order_dict(row):
        return {
            "order_id": row.order_id,
            "intent_id": row.intent_id,
            "side": row.side,
            "symbol": row.symbol,
            "token": row.token,
            "quantity": row.quantity,
            "status": row.status,
            "reason": row.reason,
            "price": None if row.price is None else str(row.price),
            "fees": None if row.fees is None else str(row.fees),
            "payload": row.payload,
            "eligible_at": _instant(row.eligible_at),
            "expires_at": _instant(row.expires_at),
            "created_at": _instant(row.created_at),
            "resolved_at": None if row.resolved_at is None else _instant(row.resolved_at),
        }

    def account(self, user_id, now=None):
        self.ensure_user(user_id)
        now = now or datetime.now(UTC)
        today = now.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()
        with self.sessions.begin() as db:
            row = db.get(NiftyAccount, user_id)
            if row is None:
                capital = Decimal(
                    str(db.get(NiftyState, user_id).configuration["virtual_capital"])
                )
                row = NiftyAccount(
                    user_id=user_id,
                    equity=capital,
                    available=capital,
                    starting_day_equity=capital,
                    realized_day=Decimal("0"),
                    day=today,
                    updated_at=now,
                )
                db.add(row)
                db.flush()
            elif row.day != today:
                # IST day rollover: fresh loss baseline and entry counter.
                row.starting_day_equity = row.equity
                row.realized_day = Decimal("0")
                row.daily_entries = 0
                row.day = today
                row.updated_at = now
            return self._account_dict(row)

    def mark_reconciled(self, user_id, now=None):
        self.account(user_id)
        with self.sessions.begin() as db:
            row = db.get(NiftyAccount, user_id)
            row.reconciled = 1
            row.updated_at = now or datetime.now(UTC)

    def admit_order(self, user_id, order):
        """Persist a pending intent exactly once; a retry reads the original."""
        try:
            with self.sessions.begin() as db:
                db.add(
                    NiftyOrder(
                        user_id=user_id,
                        order_id=order["order_id"],
                        intent_id=order["intent_id"],
                        side=order["side"],
                        symbol=order["symbol"],
                        token=order["token"],
                        quantity=order["quantity"],
                        status="PENDING",
                        payload=order["payload"],
                        eligible_at=order["eligible_at"],
                        expires_at=order["expires_at"],
                        created_at=order["created_at"],
                    )
                )
        except IntegrityError:
            with self.sessions() as db:
                existing = db.scalars(
                    select(NiftyOrder).where(
                        NiftyOrder.user_id == user_id,
                        NiftyOrder.intent_id == order["intent_id"],
                    )
                ).first()
                if existing is None:
                    raise
                return self._order_dict(existing), False
        return order, True

    def order_by_intent(self, user_id, intent_id):
        with self.sessions() as db:
            row = db.scalars(
                select(NiftyOrder).where(
                    NiftyOrder.user_id == user_id,
                    NiftyOrder.intent_id == intent_id,
                )
            ).first()
            return self._order_dict(row) if row is not None else None

    def pending_orders(self, user_id):
        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyOrder).where(
                    NiftyOrder.user_id == user_id, NiftyOrder.status == "PENDING"
                )
            )
            return [self._order_dict(row) for row in rows]

    def expire_pending(self, user_id, now):
        with self.sessions.begin() as db:
            rows = db.scalars(
                select(NiftyOrder).where(
                    NiftyOrder.user_id == user_id,
                    NiftyOrder.status == "PENDING",
                    NiftyOrder.expires_at < now,
                )
            )
            for row in rows:
                row.status = "EXPIRED"
                row.reason = "ORDER_TTL"
                row.resolved_at = now

    def orders(self, user_id, limit=100, now=None):
        self.expire_pending(user_id, now or datetime.now(UTC))
        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyOrder)
                .where(NiftyOrder.user_id == user_id)
                .order_by(NiftyOrder.created_at.desc())
                .limit(limit)
            )
            return [self._order_dict(row) for row in rows]

    def fill(self, user_id, order_id, price, fees, now):
        """Resolve a pending order and move money atomically.

        Idempotent: an already-resolved order returns its stored row without a
        second debit or position mutation. A BUY with insufficient funds or a
        SELL without a held position resolves REJECTED instead of filling.
        """
        price, fees = Decimal(str(price)), Decimal(str(fees))
        with self.sessions.begin() as db:
            order = db.get(NiftyOrder, (user_id, order_id))
            if order.status != "PENDING":
                return self._order_dict(order)
            account = db.get(NiftyAccount, user_id)
            quantity = order.quantity
            if order.side == "BUY":
                cost = price * quantity + fees
                if cost > account.available:
                    order.status, order.reason = "REJECTED", "INSUFFICIENT_FUNDS"
                else:
                    account.available -= cost
                    account.equity -= fees
                    account.daily_entries += 1
                    existing = db.get(NiftyPosition, (user_id, order.token))
                    if existing is None:
                        db.add(
                            NiftyPosition(
                                user_id=user_id,
                                token=order.token,
                                symbol=order.symbol,
                                instrument=order.payload["instrument"],
                                quantity=quantity,
                                entry_price=price,
                                entry_order_id=order.order_id,
                                highest=price,
                                opened_at=now,
                            )
                        )
                    else:
                        total = existing.quantity + quantity
                        existing.entry_price = (
                            existing.entry_price * existing.quantity + price * quantity
                        ) / total
                        existing.quantity = total
                    order.status = "FILLED"
            else:
                position = db.get(NiftyPosition, (user_id, order.token))
                if position is None or position.quantity < quantity:
                    order.status, order.reason = "REJECTED", "UNCOVERED_SELL"
                else:
                    proceeds = price * quantity - fees
                    account.available += proceeds
                    gross = (price - position.entry_price) * quantity
                    entry = db.get(NiftyOrder, (user_id, position.entry_order_id))
                    entry_fees = Decimal("0") if entry is None else Decimal(entry.fees)
                    net = gross - fees - entry_fees
                    account.equity += gross - fees
                    account.realized_day += net
                    db.add(
                        NiftyTrade(
                            user_id=user_id,
                            entry_order_id=position.entry_order_id,
                            exit_order_id=order.order_id,
                            symbol=order.symbol,
                            quantity=quantity,
                            entry_price=position.entry_price,
                            exit_price=price,
                            gross=gross,
                            fees=fees + entry_fees,
                            net=net,
                            reason=order.payload.get("exit_reason", "SIGNAL_EXIT"),
                            opened_at=position.opened_at,
                            closed_at=now,
                        )
                    )
                    position.quantity -= quantity
                    if position.quantity == 0:
                        db.delete(position)
                    order.status = "FILLED"
            if order.status == "FILLED":
                order.price, order.fees = price, fees
            order.resolved_at = now
            account.updated_at = now
            return self._order_dict(order)

    def positions(self, user_id):
        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyPosition).where(NiftyPosition.user_id == user_id)
            )
            return [
                {
                    "symbol": row.symbol,
                    "token": row.token,
                    "instrument": row.instrument,
                    "quantity": row.quantity,
                    "entry_price": str(row.entry_price),
                    "highest": str(row.highest),
                    "opened_at": _instant(row.opened_at),
                }
                for row in rows
            ]

    def mark_highest(self, user_id, token, price):
        with self.sessions.begin() as db:
            row = db.get(NiftyPosition, (user_id, token))
            if row is not None and price > row.highest:
                row.highest = price

    def trades(self, user_id, limit=200):
        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyTrade)
                .where(NiftyTrade.user_id == user_id)
                .order_by(NiftyTrade.closed_at.desc())
                .limit(limit)
            )
            return [
                {
                    "symbol": row.symbol,
                    "quantity": row.quantity,
                    "entry_price": str(row.entry_price),
                    "exit_price": str(row.exit_price),
                    "gross": str(row.gross),
                    "fees": str(row.fees),
                    "net": str(row.net),
                    "reason": row.reason,
                    "opened_at": _instant(row.opened_at),
                    "closed_at": _instant(row.closed_at),
                }
                for row in rows
            ]

    def performance(self, user_id):
        account = self.account(user_id)
        trades = self.trades(user_id)
        nets = [Decimal(row["net"]) for row in trades]
        wins = [row for row in nets if row > 0]
        return {
            "account": account,
            "trades": len(nets),
            "wins": len(wins),
            "win_rate": round(len(wins) / len(nets), 4) if nets else None,
            "realized_total": str(sum(nets, Decimal("0"))),
            "realized_day": account["realized_day"],
            "best": str(max(nets)) if nets else None,
            "worst": str(min(nets)) if nets else None,
        }
