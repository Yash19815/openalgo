"""Additive feature state in OpenAlgo's configured database.

Sessions are short lived. Revisions use compare-and-set updates so a delayed
browser save cannot overwrite another control or configuration change. The
paper ledger keeps funds, order intents, positions and closed trades inside
this feature only; it never shares the shared Sandbox balance.
"""

from datetime import UTC, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256 as sha256_bytes
from pathlib import Path
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


class NiftyCalendarVersion(Base):
    __tablename__ = "nifty_algo_calendar_version"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    segment = Column(String(20), nullable=False)
    source_filename = Column(String(255), nullable=False)
    sha256 = Column(String(64), nullable=False)
    uploader = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT")
    entries = Column(JSON, nullable=False)
    issues = Column(JSON, nullable=False)
    audit = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    approved_at = Column(DateTime(timezone=True))
    approved_by = Column(String(255))
    supersedes_id = Column(Integer)


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


class NiftyProtection(Base):
    """Additive protection state; avoids destructive changes to existing ledgers."""

    __tablename__ = "nifty_algo_protection"
    user_id = Column(String(255), primary_key=True)
    token = Column(String(32), primary_key=True)
    payload = Column(JSON, nullable=False)


class NiftyRunnerLease(Base):
    __tablename__ = "nifty_algo_runner"
    user_id = Column(String(255), primary_key=True)
    owner = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSON, nullable=False)


class NiftyDepthUse(Base):
    """A displayed snapshot cannot supply the same side's quantity twice."""

    __tablename__ = "nifty_algo_depth_use"
    user_id = Column(String(255), primary_key=True)
    snapshot_id = Column(String(128), primary_key=True)
    quantity = Column(Integer, nullable=False)


class NiftyCooldown(Base):
    """A losing primary session blocks the next eligible approved NFO session.

    ``cooldown_session`` stays NULL until the approved calendar resolves it;
    admission treats an unresolved row as blocking (fail closed).
    """

    __tablename__ = "nifty_algo_cooldown"
    user_id = Column(String(255), primary_key=True)
    loss_session = Column(String(10), primary_key=True)
    cooldown_session = Column(String(10))
    loss_event_id = Column(Integer, nullable=False)
    entry_order_id = Column(String(64), nullable=False)
    realized_net = Column(Numeric(18, 4), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class NiftyMonth(Base):
    """IST calendar-month realized net and latched monthly entry locks.

    Independent of ``nifty_algo_account``: equity never resets on a new month,
    and nothing that changes equity touches these counters.
    """

    __tablename__ = "nifty_algo_month"
    user_id = Column(String(255), primary_key=True)
    month = Column(String(7), primary_key=True)
    realized_net = Column(Numeric(18, 4), nullable=False, default=0)
    loss_locked_at = Column(DateTime(timezone=True))
    profit_locked_at = Column(DateTime(timezone=True))
    lock_detail = Column(JSON, nullable=False, default=dict)
    milestone_report_ids = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class StateConflict(ValueError):
    """The caller used an obsolete state revision."""


def _instant(value):
    # SQLite drops timezone metadata from UTC timestamps on read.
    return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.isoformat()


_IST = ZoneInfo("Asia/Kolkata")


def _month_key(moment):
    return moment.astimezone(_IST).strftime("%Y-%m")


def _optional_amount(value):
    return None if value is None else Decimal(str(value))


def _month_bounds(key):
    year, month = (int(part) for part in key.split("-"))
    start = datetime(year, month, 1, tzinfo=_IST)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=_IST)
    return start.astimezone(UTC), end.astimezone(UTC)


class NiftyStore:
    def __init__(self, engine, calendar_blob_dir=None):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False)
        self.calendar_blob_dir = Path(calendar_blob_dir or "db/nifty_calendar")

    def initialize(self):
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _calendar_dict(row):
        if row is None:
            return None
        return {
            "id": row.id, "user_id": row.user_id, "year": row.year,
            "segment": row.segment, "source_filename": row.source_filename,
            "sha256": row.sha256, "uploader": row.uploader, "status": row.status,
            "entries": row.entries, "issues": row.issues, "audit": row.audit,
            "created_at": _instant(row.created_at),
            "approved_at": _instant(row.approved_at) if row.approved_at else None,
            "approved_by": row.approved_by, "supersedes_id": row.supersedes_id,
        }

    def create_calendar_draft(
        self, user_id, *, year, segment, source_filename, sha256, uploader,
        entries, issues, data, extension,
    ):
        self.ensure_user(user_id)
        if not year:
            raise ValueError("Calendar year is unconfirmed")
        if extension not in ("pdf", "csv") or sha256_bytes(data).hexdigest() != sha256:
            raise ValueError("Calendar upload metadata does not match its content")
        destination = self.calendar_blob_dir / f"{sha256}.{extension}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        created_file = False
        try:
            with destination.open("xb") as output:
                output.write(data)
            created_file = True
        except FileExistsError:
            if destination.read_bytes() != data:
                raise ValueError("Calendar content hash collision") from None
        now = datetime.now(UTC)
        audit = [{"at": now.isoformat(), "actor": uploader, "action": "DRAFT_CREATED",
                  "detail": {"sha256": sha256}}]
        try:
            with self.sessions.begin() as db:
                self._lock(db, user_id)
                row = NiftyCalendarVersion(
                    user_id=user_id, year=int(year), segment=segment,
                    source_filename=Path(source_filename).name[:255], sha256=sha256,
                    uploader=uploader, status="DRAFT", entries=entries, issues=list(issues),
                    audit=audit, created_at=now,
                )
                db.add(row)
                db.flush()
                result = self._calendar_dict(row)
        except Exception:
            if created_file:
                destination.unlink(missing_ok=True)
            raise
        return result

    def calendar_versions(self, user_id, year=None):
        self.ensure_user(user_id)
        with self.sessions() as db:
            query = select(NiftyCalendarVersion).where(NiftyCalendarVersion.user_id == user_id)
            if year is not None:
                query = query.where(NiftyCalendarVersion.year == int(year))
            rows = db.scalars(query.order_by(NiftyCalendarVersion.created_at.desc())).all()
            return [self._calendar_dict(row) for row in rows]

    def calendar_version(self, user_id, version_id):
        self.ensure_user(user_id)
        with self.sessions() as db:
            row = db.scalar(select(NiftyCalendarVersion).where(
                NiftyCalendarVersion.user_id == user_id,
                NiftyCalendarVersion.id == int(version_id),
            ))
            return self._calendar_dict(row)

    def approved_calendar_version(self, user_id, year):
        self.ensure_user(user_id)
        with self.sessions() as db:
            row = db.scalar(select(NiftyCalendarVersion).where(
                NiftyCalendarVersion.user_id == user_id,
                NiftyCalendarVersion.year == int(year),
                NiftyCalendarVersion.segment == "NFO",
                NiftyCalendarVersion.status == "APPROVED",
            ))
            return self._calendar_dict(row)

    def update_draft_entries(self, user_id, version_id, entries, actor):
        from services.nifty_algo.calendar_import import recompute_entries

        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.scalar(select(NiftyCalendarVersion).where(
                NiftyCalendarVersion.user_id == user_id,
                NiftyCalendarVersion.id == int(version_id),
            ))
            if row is None or row.status != "DRAFT":
                raise ValueError("Calendar version is not an editable draft")
            normalized, issues = recompute_entries(entries, row.year)
            row.entries = normalized
            row.issues = list(issues)
            row.audit = [*row.audit, {
                "at": datetime.now(UTC).isoformat(), "actor": actor,
                "action": "DRAFT_ENTRIES_UPDATED", "detail": {"count": len(normalized)},
            }]
            result = self._calendar_dict(row)
        return result

    def approve_calendar(
        self, user_id, version_id, *, confirmed_year, confirmed_segment, actor, now=None
    ):
        result = self._approve_calendar(
            user_id,
            version_id,
            confirmed_year=confirmed_year,
            confirmed_segment=confirmed_segment,
            actor=actor,
        )
        # A revised calendar recomputes current and future cooldown sessions.
        self.resolve_cooldowns(user_id, now or datetime.now(UTC), recompute=True)
        return result

    def _approve_calendar(self, user_id, version_id, *, confirmed_year, confirmed_segment, actor):
        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.scalar(select(NiftyCalendarVersion).where(
                NiftyCalendarVersion.user_id == user_id,
                NiftyCalendarVersion.id == int(version_id),
            ))
            if row is None or row.status != "DRAFT":
                raise ValueError("Calendar version is not an approvable draft")
            if int(confirmed_year) != row.year or confirmed_segment != row.segment:
                raise ValueError("Calendar year and segment confirmation must match")
            if row.segment != "NFO" or any(item.get("ambiguous") for item in row.entries):
                raise ValueError("Calendar has an unconfirmed segment or ambiguous entries")
            prior = db.scalar(select(NiftyCalendarVersion).where(
                NiftyCalendarVersion.user_id == user_id,
                NiftyCalendarVersion.year == row.year,
                NiftyCalendarVersion.status == "APPROVED",
            ))
            now = datetime.now(UTC)
            if prior:
                prior.status = "SUPERSEDED"
                row.supersedes_id = prior.id
                prior.audit = [*prior.audit, {
                    "at": now.isoformat(), "actor": actor, "action": "SUPERSEDED",
                    "detail": {"by_version": row.id},
                }]
            row.status = "APPROVED"
            row.approved_at = now
            row.approved_by = actor
            row.audit = [*row.audit, {
                "at": now.isoformat(), "actor": actor, "action": "APPROVED",
                "detail": {"year": row.year, "segment": row.segment},
            }]
            result = self._calendar_dict(row)
        return result

    def reject_calendar(self, user_id, version_id, actor, detail=None):
        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.scalar(select(NiftyCalendarVersion).where(
                NiftyCalendarVersion.user_id == user_id,
                NiftyCalendarVersion.id == int(version_id),
            ))
            if row is None or row.status != "DRAFT":
                raise ValueError("Calendar version is not a rejectable draft")
            row.status = "REJECTED"
            row.audit = [*row.audit, {
                "at": datetime.now(UTC).isoformat(), "actor": actor,
                "action": "REJECTED", "detail": detail or {},
            }]
            result = self._calendar_dict(row)
        return result

    def ensure_user(self, user_id):
        from services.nifty_algo.config import StrategyConfig

        config = StrategyConfig()
        now = datetime.now(UTC)
        try:
            with self.sessions.begin() as db:
                existing = db.get(NiftyState, user_id)
                if existing is not None:
                    source_version = existing.configuration.get("strategy_version", "1.0.0")
                    if source_version != config.strategy_version:
                        from services.nifty_algo.config import migrate_configuration

                        self._lock(db, user_id)
                        db.refresh(existing)
                        source_version = existing.configuration.get("strategy_version", "1.0.0")
                        if source_version != config.strategy_version:
                            try:
                                migrated = migrate_configuration(existing.configuration)
                            except ValueError:
                                if existing.state not in ("PAUSED", "KILLED"):
                                    existing.state = "KILLED" if existing.killed else "PAUSED"
                                    existing.revision += 1
                                    db.add(
                                        NiftyEvent(
                                            user_id=user_id,
                                            kind="configuration_incompatible",
                                            payload={"reason": "VALIDATION_REQUIRED"},
                                            created_at=now,
                                        )
                                    )
                                return
                            existing.revision += 1
                            existing.configuration = migrated.model_dump(mode="json")
                            existing.configuration_id = migrated.version_id
                            existing.state = "KILLED" if existing.killed else "PAUSED"
                            existing.updated_at = now
                            db.add(
                                NiftyConfiguration(
                                    user_id=user_id,
                                    revision=existing.revision,
                                    configuration_id=migrated.version_id,
                                    configuration=existing.configuration,
                                    created_at=now,
                                )
                            )
                            db.add(
                                NiftyEvent(
                                    user_id=user_id,
                                    kind="configuration_migration",
                                    payload={
                                        "from": source_version,
                                        "to": migrated.strategy_version,
                                        "revision": existing.revision,
                                    },
                                    created_at=now,
                                )
                            )
                    if existing.configuration.get("strategy_version") == config.strategy_version:
                        try:
                            StrategyConfig.model_validate(existing.configuration)
                        except ValueError:
                            self._lock(db, user_id)
                            if existing.state not in ("PAUSED", "KILLED"):
                                existing.state = "KILLED" if existing.killed else "PAUSED"
                                existing.revision += 1
                                db.add(
                                    NiftyEvent(
                                        user_id=user_id,
                                        kind="configuration_incompatible",
                                        payload={"reason": "VALIDATION_REQUIRED"},
                                        created_at=now,
                                    )
                                )
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
        elif action == "start":
            values["state"] = "RUNNING"
        elif action is not None:
            raise ValueError("Unsupported control")
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            # Killing is monotonic. Configuration and pause cannot clear it.
            row = db.get(NiftyState, user_id)
            if action == "start":
                lease = db.get(NiftyRunnerLease, user_id)
                account = db.get(NiftyAccount, user_id)
                if (
                    row.killed
                    or row.daily_locked
                    or lease is None
                    or account is None
                    or not account.reconciled
                    or datetime.fromisoformat(_instant(lease.expires_at)) <= now
                    or not lease.payload.get("entries_ready")
                    or lease.payload.get("configuration_id") != row.configuration_id
                ):
                    raise StateConflict("Start prerequisites changed. Reload readiness.")
            if row.killed:
                values["state"] = "KILLED"
            previous_target = None
            if configuration is not None:
                previous_target = (row.configuration or {}).get("monthly_profit_target")
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
                new_target = values["configuration"].get("monthly_profit_target")
                if _optional_amount(previous_target) != _optional_amount(new_target):
                    # Audit only. A latched monthly lock is never cleared here.
                    db.add(
                        NiftyEvent(
                            user_id=user_id,
                            kind="monthly_profit_target_changed",
                            payload={
                                "previous": previous_target,
                                "new": new_target,
                                "at": now.isoformat(),
                                "revision": revision + 1,
                            },
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

    @staticmethod
    def _lock(db, user_id):
        # UPDATE acquires a write lock on SQLite and a row lock on PostgreSQL.
        # All ledger writers take this lock before reading mutable account state.
        db.execute(
            update(NiftyState)
            .where(NiftyState.user_id == user_id)
            .values(updated_at=NiftyState.updated_at)
        )

    def claim_runner(self, user_id, owner, now, seconds=30, payload=None):
        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyRunnerLease, user_id)
            if (
                row is not None
                and row.owner != owner
                and datetime.fromisoformat(_instant(row.expires_at)) > now
            ):
                return False
            if row is None:
                row = NiftyRunnerLease(user_id=user_id)
                db.add(row)
            expiry = now + timedelta(seconds=seconds)
            if row.owner == owner and row.expires_at is not None:
                expiry = max(expiry, datetime.fromisoformat(_instant(row.expires_at)))
            row.owner, row.expires_at = owner, expiry
            row.payload = payload or {}
            return True

    def release_runner(self, user_id, owner):
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyRunnerLease, user_id)
            if row is not None and row.owner == owner:
                db.delete(row)

    def runner_status(self, user_id, now=None):
        with self.sessions() as db:
            row = db.get(NiftyRunnerLease, user_id)
            if row is None:
                return {"operational": False, "reason": "RUNNER_NOT_ATTACHED"}
            return {
                **row.payload,
                "operational": datetime.fromisoformat(_instant(row.expires_at))
                > (now or datetime.now(UTC)),
                "expires_at": _instant(row.expires_at),
            }

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

    def record_event(self, user_id, kind, payload, now):
        with self.sessions.begin() as db:
            db.add(NiftyEvent(user_id=user_id, kind=kind, payload=payload, created_at=now))

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
            self._lock(db, user_id)
            row = db.get(NiftyAccount, user_id)
            if row is None:
                capital = Decimal(str(db.get(NiftyState, user_id).configuration["virtual_capital"]))
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
                db.get(NiftyState, user_id).daily_locked = 0
            return self._account_dict(row)

    def mark_reconciled(self, user_id, now=None):
        self.account(user_id, now)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyAccount, user_id)
            row.reconciled = 1
            row.updated_at = now or datetime.now(UTC)

    def reconciliation_issues(self, user_id):
        """Check durable fill/position/cash invariants without inventing repairs.

        Historical quantities are aggregated in SQL; startup does not load an
        unbounded order/trade history into the long-lived application worker.
        """
        from sqlalchemy import and_, func, or_

        from services.nifty_algo.models import Instrument

        with self.sessions.begin() as db:
            self._lock(db, user_id)
            account = db.get(NiftyAccount, user_id)
            positions = list(
                db.scalars(select(NiftyPosition).where(NiftyPosition.user_id == user_id).limit(2))
            )
            position_count = db.scalar(
                select(func.count())
                .select_from(NiftyPosition)
                .where(NiftyPosition.user_id == user_id)
            )
            position_cost = db.scalar(
                select(func.sum(NiftyPosition.entry_price * NiftyPosition.quantity)).where(
                    NiftyPosition.user_id == user_id
                )
            ) or Decimal("0")
            issues = []
            if account is None or any(
                not Decimal(str(value)).is_finite() or value < 0
                for value in (account.equity, account.available)
            ):
                issues.append("ACCOUNT_BALANCE_INVALID")
            elif account.equity != account.available + position_cost:
                issues.append("ACCOUNT_POSITION_BALANCE_MISMATCH")
            if position_count > 1:
                issues.append("POSITION_LIMIT_INCONSISTENT")
            for position in positions:
                entry = db.get(NiftyOrder, (user_id, position.entry_order_id))
                if (
                    position.quantity <= 0
                    or entry is None
                    or entry.status != "FILLED"
                    or entry.side != "BUY"
                    or entry.token != position.token
                    or entry.symbol != position.symbol
                    or entry.price != position.entry_price
                ):
                    issues.append("POSITION_ENTRY_FILL_MISMATCH")
                try:
                    instrument = Instrument.model_validate(position.instrument)
                    if instrument.token != position.token or instrument.kind not in ("CE", "PE"):
                        raise ValueError("Position identity mismatch")
                except ValueError:
                    issues.append("POSITION_IDENTITY_INVALID")
            invalid_exits = db.scalar(
                select(func.count())
                .select_from(NiftyTrade)
                .outerjoin(
                    NiftyOrder,
                    and_(
                        NiftyOrder.user_id == NiftyTrade.user_id,
                        NiftyOrder.order_id == NiftyTrade.exit_order_id,
                    ),
                )
                .where(
                    NiftyTrade.user_id == user_id,
                    or_(
                        NiftyOrder.order_id.is_(None),
                        NiftyOrder.status != "FILLED",
                        NiftyOrder.side != "SELL",
                        NiftyOrder.quantity != NiftyTrade.quantity,
                    ),
                )
            )
            if invalid_exits:
                issues.append("JOURNAL_EXIT_FILL_MISSING")
            closed = (
                select(
                    NiftyTrade.entry_order_id.label("entry_id"),
                    func.sum(NiftyTrade.quantity).label("quantity"),
                )
                .where(NiftyTrade.user_id == user_id)
                .group_by(NiftyTrade.entry_order_id)
                .subquery()
            )
            held = (
                select(
                    NiftyPosition.entry_order_id.label("entry_id"),
                    func.sum(NiftyPosition.quantity).label("quantity"),
                )
                .where(NiftyPosition.user_id == user_id)
                .group_by(NiftyPosition.entry_order_id)
                .subquery()
            )
            mismatched_entries = db.scalar(
                select(func.count())
                .select_from(NiftyOrder)
                .outerjoin(closed, closed.c.entry_id == NiftyOrder.order_id)
                .outerjoin(held, held.c.entry_id == NiftyOrder.order_id)
                .where(
                    NiftyOrder.user_id == user_id,
                    NiftyOrder.side == "BUY",
                    NiftyOrder.status == "FILLED",
                    NiftyOrder.quantity
                    != func.coalesce(closed.c.quantity, 0) + func.coalesce(held.c.quantity, 0),
                )
            )
            if mismatched_entries:
                issues.append("ENTRY_QUANTITY_NOT_RECONCILED")
            pending_buys = db.scalar(
                select(func.count())
                .select_from(NiftyOrder)
                .where(
                    NiftyOrder.user_id == user_id,
                    NiftyOrder.side == "BUY",
                    NiftyOrder.status == "PENDING",
                )
            )
            if pending_buys > 1 or (pending_buys and position_count):
                issues.append("ENTRY_RESERVATION_INCONSISTENT")
            pending_exits = (
                select(
                    NiftyOrder.token.label("token"), func.sum(NiftyOrder.quantity).label("quantity")
                )
                .where(
                    NiftyOrder.user_id == user_id,
                    NiftyOrder.side == "SELL",
                    NiftyOrder.status == "PENDING",
                )
                .group_by(NiftyOrder.token)
                .subquery()
            )
            uncovered_exits = db.scalar(
                select(func.count())
                .select_from(pending_exits)
                .outerjoin(
                    NiftyPosition,
                    and_(
                        NiftyPosition.user_id == user_id,
                        NiftyPosition.token == pending_exits.c.token,
                    ),
                )
                .where(pending_exits.c.quantity > func.coalesce(NiftyPosition.quantity, 0))
            )
            if uncovered_exits:
                issues.append("EXIT_RESERVATION_INCONSISTENT")
            return sorted(set(issues))

    def block_reconciliation(self, user_id, now, reason):
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            db.get(NiftyAccount, user_id).reconciled = 0
            state = db.get(NiftyState, user_id)
            if not state.killed:
                state.state = "PAUSED"
            db.add(
                NiftyEvent(
                    user_id=user_id,
                    kind="reconciliation_blocked",
                    payload={"reason": reason},
                    created_at=now,
                )
            )

    def recover_legacy(self, user_id, now):
        """Cancel pre-v2 buys and protect recorded exposure without inventing confidence.

        Unknown legacy targets stay unavailable. Emergency stops may tighten to
        8%, and entries stay paused until these legacy positions are closed.
        """
        from services.nifty_algo.config import StrategyConfig
        from services.nifty_algo.protection import ceiling_tick

        self.account(user_id, now)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            state = db.get(NiftyState, user_id)
            try:
                config = StrategyConfig.model_validate(state.configuration)
            except ValueError:
                config = StrategyConfig()  # Exit-only emergency profile.
            for order in db.scalars(
                select(NiftyOrder).where(
                    NiftyOrder.user_id == user_id, NiftyOrder.status == "PENDING"
                )
            ):
                if "configuration" not in order.payload:
                    if order.side == "BUY":
                        order.status, order.reason, order.resolved_at = (
                            "CANCELED",
                            "LEGACY_CONFIGURATION",
                            now,
                        )
                    else:
                        order.payload = {
                            **order.payload,
                            "configuration": config.model_dump(mode="json"),
                        }
            for position in db.scalars(
                select(NiftyPosition).where(NiftyPosition.user_id == user_id)
            ):
                if db.get(NiftyProtection, (user_id, position.token)) is not None:
                    continue
                stop = ceiling_tick(
                    position.entry_price * (1 - config.premium_stop),
                    position.instrument["tick_size"],
                )
                # V1 stored a peak but no protective stop or entry configuration.
                # Never restart such a profitable legacy position at a looser
                # initial stop. Preserve its recorded peak as a conservative
                # protective floor and request an observed-depth closure.
                legacy_peak = position.highest if position.highest > position.entry_price else None
                active_stop = (
                    max(stop, ceiling_tick(legacy_peak, position.instrument["tick_size"]))
                    if legacy_peak is not None
                    else stop
                )
                db.add(
                    NiftyProtection(
                        user_id=user_id,
                        token=position.token,
                        payload={
                            "configuration": config.model_dump(mode="json"),
                            "configuration_id": config.version_id,
                            "confidence": None,
                            "target_fraction": None,
                            "target_price": None,
                            "initial_stop": str(stop),
                            "stop_price": str(active_stop),
                            "highest_bid": None,
                            "trailing_active": False,
                            "last_source_time": None,
                            "exit_reason": "LEGACY_PROTECTION_REVIEW"
                            if legacy_peak is not None
                            else None,
                            "legacy_recorded_peak": str(legacy_peak)
                            if legacy_peak is not None
                            else None,
                            "point_unit": "OPTION_PREMIUM",
                            "trailing_distance_points": str(config.trailing_distance_points),
                            "legacy": True,
                            "reason": "ENTRY_CONFIDENCE_NOT_RECORDED",
                        },
                    )
                )
                if not state.killed:
                    state.state = "PAUSED"
                db.add(
                    NiftyEvent(
                        user_id=user_id,
                        kind="legacy_protection",
                        payload={
                            "token": position.token,
                            "reason": "ENTRY_CONFIDENCE_NOT_RECORDED",
                        },
                        created_at=now,
                    )
                )

    def admit_order(self, user_id, order):
        """Persist a pending intent exactly once; a retry reads the original."""
        try:
            with self.sessions.begin() as db:
                from services.nifty_algo.config import StrategyConfig
                from services.nifty_algo.paper_executor import OrderRefused

                self._lock(db, user_id)
                existing = db.scalar(
                    select(NiftyOrder).where(
                        NiftyOrder.user_id == user_id, NiftyOrder.intent_id == order["intent_id"]
                    )
                )
                if existing is not None:
                    return self._order_dict(existing), False
                state = db.get(NiftyState, user_id)
                account = db.get(NiftyAccount, user_id)
                positions = list(
                    db.scalars(select(NiftyPosition).where(NiftyPosition.user_id == user_id))
                )
                pending = list(
                    db.scalars(
                        select(NiftyOrder).where(
                            NiftyOrder.user_id == user_id, NiftyOrder.status == "PENDING"
                        )
                    )
                )
                if order["side"] == "BUY":
                    config = StrategyConfig.model_validate(order["payload"]["configuration"])
                    reasons = []
                    local_day = order["created_at"].astimezone(ZoneInfo("Asia/Kolkata")).date()
                    approved_calendar = db.scalar(
                        select(NiftyCalendarVersion.id).where(
                            NiftyCalendarVersion.user_id == user_id,
                            NiftyCalendarVersion.year == local_day.year,
                            NiftyCalendarVersion.segment == "NFO",
                            NiftyCalendarVersion.status == "APPROVED",
                        )
                    )
                    if approved_calendar is None:
                        reasons.append("CALENDAR_UNAPPROVED")
                    day_start = datetime.combine(
                        local_day, time.min, tzinfo=ZoneInfo("Asia/Kolkata")
                    ).astimezone(UTC)
                    day_end = day_start + timedelta(days=1)
                    daily_orders = db.scalars(
                        select(NiftyOrder).where(
                            NiftyOrder.user_id == user_id,
                            NiftyOrder.side == "BUY",
                            NiftyOrder.created_at >= day_start,
                            NiftyOrder.created_at < day_end,
                        )
                    )
                    if any(row.status in ("PENDING", "FILLED", "PARTIAL") for row in daily_orders):
                        reasons.append("DAILY_ENTRY_USED")
                    owner = order["payload"].get("runner_owner")
                    lease = db.get(NiftyRunnerLease, user_id)
                    if owner and (
                        lease is None
                        or lease.owner != owner
                        or datetime.fromisoformat(_instant(lease.expires_at)) <= order["created_at"]
                    ):
                        reasons.append("RUNNER_LEASE_LOST")
                    if state.state != "RUNNING" or state.killed or state.daily_locked:
                        reasons.append("ENTRIES_DISABLED")
                    if state.configuration_id != config.version_id:
                        reasons.append("CONFIGURATION_CHANGED")
                    if positions or any(row.side == "BUY" for row in pending):
                        reasons.append("POSITION_OR_RESERVATION_LIMIT")
                    if not account.reconciled:
                        reasons.append("RECONCILIATION_REQUIRED")
                    if account.daily_entries >= config.max_daily_entries:
                        reasons.append("DAILY_ENTRY_LIMIT")
                    if account.equity <= account.starting_day_equity * (
                        1 - config.daily_loss_fraction
                    ):
                        reasons.append("DAILY_LOSS_LIMIT")
                    # Pending intent is the durable reservation. One-position policy
                    # excludes distinct admissions under this same transaction lock.
                    if Decimal(order["payload"]["reserved_capital"]) > account.available:
                        reasons.append("INSUFFICIENT_FUNDS")
                    if (
                        Decimal(order["payload"]["reserved_risk"])
                        > config.max_planned_loss
                    ):
                        reasons.append("PLANNED_LOSS_LIMIT")
                    # Phase 3b: loss cooldown and monthly locks, under the same lock.
                    reasons.extend(self._cooldown_reasons(db, user_id, local_day.isoformat()))
                    reasons.extend(
                        self._month_lock_reasons(db, user_id, order["created_at"], config)
                    )
                    if reasons:
                        raise OrderRefused(reasons)
                else:
                    held = next((p for p in positions if p.token == order["token"]), None)
                    reserved = sum(
                        p.quantity
                        for p in pending
                        if p.side == "SELL" and p.token == order["token"]
                    )
                    if held is None or order["quantity"] + reserved > min(
                        held.quantity, self._remaining_quantity(db, user_id, held)
                    ):
                        raise OrderRefused(["EXIT_ALREADY_PENDING_OR_UNCOVERED"])
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
                db.add(
                    NiftyEvent(
                        user_id=user_id,
                        kind="paper_intent_admitted",
                        payload={
                            "order_id": order["order_id"],
                            "intent_id": order["intent_id"],
                            "decision_id": order["payload"].get("decision_id"),
                            "side": order["side"],
                            "token": order["token"],
                            "quantity": order["quantity"],
                            "risk_approval": order["payload"].get("risk_approval"),
                        },
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

    @staticmethod
    def _remaining_quantity(db, user_id, position):
        """Sell coverage comes from confirmed fills, not only a position counter."""
        from sqlalchemy import func, or_

        entry = db.get(NiftyOrder, (user_id, position.entry_order_id))
        if (
            entry is None
            or entry.status != "FILLED"
            or entry.side != "BUY"
            or entry.token != position.token
        ):
            return 0
        legacy_exits = select(NiftyTrade.exit_order_id).where(
            NiftyTrade.user_id == user_id, NiftyTrade.entry_order_id == entry.order_id
        )
        closed = (
            db.scalar(
                select(func.sum(NiftyOrder.quantity)).where(
                    NiftyOrder.user_id == user_id,
                    NiftyOrder.side == "SELL",
                    NiftyOrder.status == "FILLED",
                    or_(
                        NiftyOrder.payload["entry_order_id"].as_string() == entry.order_id,
                        NiftyOrder.order_id.in_(legacy_exits),
                    ),
                )
            )
            or 0
        )
        return max(0, entry.quantity - closed)

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

    def exit_attempt_count(self, user_id, entry_order_id):
        from sqlalchemy import func

        with self.sessions() as db:
            return db.scalar(
                select(func.count())
                .select_from(NiftyOrder)
                .where(
                    NiftyOrder.user_id == user_id,
                    NiftyOrder.side == "SELL",
                    NiftyOrder.payload["entry_order_id"].as_string() == entry_order_id,
                )
            )

    def expire_pending(self, user_id, now):
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            rows = db.scalars(
                select(NiftyOrder).where(
                    NiftyOrder.user_id == user_id,
                    NiftyOrder.status == "PENDING",
                    NiftyOrder.expires_at <= now,
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

    def fill(
        self,
        user_id,
        order_id,
        price,
        fees,
        now,
        *,
        snapshot_id=None,
        displayed_size=None,
        observation=None,
    ):
        """Resolve a pending order and move money atomically.

        Idempotent: an already-resolved order returns its stored row without a
        second debit or position mutation. A BUY with insufficient funds or a
        SELL without a held position resolves REJECTED instead of filling.
        """
        price, fees = Decimal(str(price)), Decimal(str(fees))
        if not price.is_finite() or price <= 0 or not fees.is_finite() or fees < 0:
            raise ValueError("Invalid fill price or costs")
        with self.sessions.begin() as db:
            from services.nifty_algo.config import StrategyConfig
            from services.nifty_algo.protection import initial_protection

            self._lock(db, user_id)
            order = db.get(NiftyOrder, (user_id, order_id))
            if order.status != "PENDING":
                return self._order_dict(order)
            account = db.get(NiftyAccount, user_id)
            quantity = order.quantity
            if (
                order.side == "BUY"
                and now.astimezone(ZoneInfo("Asia/Kolkata")).time().replace(tzinfo=None)
                >= time(14, 45)
            ):
                order.status, order.reason, order.resolved_at = "EXPIRED", "ENTRY_CUTOFF", now
                return self._order_dict(order)
            if now < datetime.fromisoformat(_instant(order.eligible_at)):
                return self._order_dict(order)
            if now >= datetime.fromisoformat(_instant(order.expires_at)):
                order.status, order.reason, order.resolved_at = "EXPIRED", "ORDER_TTL", now
                return self._order_dict(order)
            if snapshot_id is None or displayed_size is None:
                raise ValueError("Observed depth proof required")
            from hashlib import sha256

            from services.nifty_algo.models import Instrument, Quote

            config = StrategyConfig.model_validate(order.payload["configuration"])
            quote = Quote.model_validate(observation)
            instrument = Instrument.model_validate(order.payload["instrument"])
            level, size = (
                (quote.ask, quote.ask_size) if order.side == "BUY" else (quote.bid, quote.bid_size)
            )
            expected = (
                None
                if level is None
                else level
                + instrument.tick_size * config.slippage_ticks * (1 if order.side == "BUY" else -1)
            )
            expected_id = sha256(
                f"{quote.token}:{quote.source_time.isoformat()}:{order.side}".encode()
            ).hexdigest()
            from services.nifty_algo.paper_executor import _charges

            if fees != _charges(order.side, price, quantity, config):
                raise ValueError("Fill costs do not match frozen configuration")
            if (
                quote.token != order.token
                or not quote.source_time <= quote.received_time <= now
                or not 0 <= (now - quote.source_time).total_seconds() <= config.quote_max_age
                or level is None
                or size < quantity
                or displayed_size != size
                or price != expected
                or price % instrument.tick_size
                or snapshot_id != expected_id
            ):
                raise ValueError("Final execution observation failed validation")
            use = db.get(NiftyDepthUse, (user_id, snapshot_id))
            consumed = use.quantity if use else 0
            if quantity + consumed > displayed_size:
                return self._order_dict(order)
            if order.side == "BUY":
                cost = price * quantity + fees
                state = db.get(NiftyState, user_id)
                existing = db.scalar(select(NiftyPosition).where(NiftyPosition.user_id == user_id))
                try:
                    protection = initial_protection(
                        price, instrument.tick_size, config, order.payload["confidence"]
                    )
                    protection["signal_context"] = order.payload.get("signal_context")
                    protection["entry_fees_remaining"] = str(fees)
                except ValueError:
                    order.status, order.reason, order.resolved_at = (
                        "REJECTED",
                        "PROTECTION_TICK_INVALID",
                        now,
                    )
                    return self._order_dict(order)
                from services.nifty_algo.paper_executor import _charges

                stop_exit = (
                    Decimal(protection["initial_stop"])
                    - Decimal(order.payload["instrument"]["tick_size"]) * config.slippage_ticks
                )
                planned = (price - stop_exit) * quantity + fees
                planned += (
                    _charges("SELL", stop_exit, quantity, config) + config.planned_loss_buffer
                )
                if (
                    state.killed
                    or state.daily_locked
                    or state.state != "RUNNING"
                    or state.configuration_id != config.version_id
                ):
                    order.status, order.reason = "CANCELED", "ENTRIES_DISABLED"
                elif entry_locks := (
                    self._cooldown_reasons(
                        db, user_id, now.astimezone(_IST).date().isoformat()
                    )
                    + self._month_lock_reasons(db, user_id, now, config)
                ):
                    order.status, order.reason = "REJECTED", entry_locks[0]
                elif existing is not None:
                    order.status, order.reason = "REJECTED", "POSITION_LIMIT"
                elif (
                    instrument.master_date != now.astimezone(ZoneInfo("Asia/Kolkata")).date()
                    or instrument.expiry < now.astimezone(ZoneInfo("Asia/Kolkata")).date()
                ):
                    order.status, order.reason = "REJECTED", "METADATA_INVALID"
                elif planned > config.max_planned_loss:
                    order.status, order.reason = "REJECTED", "PLANNED_LOSS_LIMIT"
                elif planned > Decimal(order.payload["reserved_risk"]):
                    order.status, order.reason = "REJECTED", "FILL_RISK_BUDGET"
                elif (
                    account.daily_entries >= config.max_daily_entries
                    or account.equity
                    <= account.starting_day_equity * (1 - config.daily_loss_fraction)
                ):
                    order.status, order.reason = "REJECTED", "DAILY_RISK_LIMIT"
                elif cost > account.available or cost > Decimal(order.payload["reserved_capital"]):
                    order.status, order.reason = "REJECTED", "INSUFFICIENT_FUNDS"
                else:
                    account.available -= cost
                    account.equity -= fees
                    if not order.payload.get("daily_entry_counted"):
                        account.daily_entries += 1
                        order.payload = dict(order.payload, daily_entry_counted=True)
                    existing = db.get(NiftyPosition, (user_id, order.token))
                    if existing is None:
                        db.add(
                            NiftyProtection(user_id=user_id, token=order.token, payload=protection)
                        )
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
                    order.status = "FILLED"
            else:
                position = db.get(NiftyPosition, (user_id, order.token))
                if (
                    position is None
                    or min(position.quantity, self._remaining_quantity(db, user_id, position))
                    < quantity
                ):
                    order.status, order.reason = "REJECTED", "UNCOVERED_SELL"
                else:
                    proceeds = price * quantity - fees
                    account.available += proceeds
                    gross = (price - position.entry_price) * quantity
                    entry = db.get(NiftyOrder, (user_id, position.entry_order_id))
                    protection_row = db.get(NiftyProtection, (user_id, order.token))
                    protection_payload = protection_row.payload if protection_row else {}
                    profit_floor = protection_payload.get("profit_floor_stop")
                    floor_net = Decimal(
                        (protection_payload.get("profit_lock_activation") or {}).get(
                            "floor_net",
                            config.profit_lock_floor_net,
                        )
                    )
                    remaining_fees = Decimal(
                        (protection_row.payload if protection_row else {}).get(
                            "entry_fees_remaining",
                            str(
                                (Decimal("0") if entry is None else Decimal(entry.fees))
                                * Decimal(position.quantity)
                                / Decimal(entry.quantity if entry else position.quantity)
                            ),
                        )
                    )
                    entry_fees = (
                        remaining_fees
                        if quantity == position.quantity
                        else (
                            remaining_fees * Decimal(quantity) / Decimal(position.quantity)
                        ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                    )
                    if protection_row is not None:
                        protection_row.payload = {
                            **protection_row.payload,
                            "entry_fees_remaining": str(remaining_fees - entry_fees),
                        }
                    net = gross - fees - entry_fees
                    account.equity += gross - fees
                    account.realized_day += net
                    floor_gap = (
                        protection_payload.get("profit_lock_active", False)
                        and profit_floor is not None
                        and observation is not None
                        and Decimal(str(observation.get("bid", 0))) < Decimal(profit_floor)
                        and net < floor_net
                    )
                    if floor_gap:
                        db.add(
                            NiftyEvent(
                                user_id=user_id,
                                kind="PROFIT_FLOOR_GAP",
                                payload={
                                    "token": order.token,
                                    "order_id": order.order_id,
                                    "floor_stop": str(profit_floor),
                                    "expected_floor_net": str(floor_net),
                                    "realized_net": str(net),
                                    "realized_quantity": quantity,
                                    "realized_price": str(price),
                                },
                                created_at=now,
                            )
                        )
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
                            reason=(
                                "PROFIT_FLOOR_GAP"
                                if floor_gap
                                else order.payload.get("exit_reason", "SIGNAL_EXIT")
                            ),
                            opened_at=position.opened_at,
                            closed_at=now,
                        )
                    )
                    self._record_month_net(
                        db,
                        user_id,
                        now,
                        net,
                        self._limit_config(db.get(NiftyState, user_id), config),
                    )
                    position.quantity -= quantity
                    if position.quantity == 0:
                        # Session finalisation: the single primary entry is now flat.
                        self._schedule_cooldown(db, user_id, position, entry, now)
                        db.delete(position)
                        protection = db.get(NiftyProtection, (user_id, order.token))
                        if protection is not None:
                            # Keep the immutable entry and final protection in the
                            # exit order, which outlives the open position.
                            order.payload = {**order.payload, "protection": protection.payload}
                            db.delete(protection)
                    order.status = "FILLED"
            if order.status == "FILLED":
                order.price, order.fees = price, fees
                order.payload = {**order.payload, "fill_observation": observation}
                if use is None:
                    db.add(
                        NiftyDepthUse(user_id=user_id, snapshot_id=snapshot_id, quantity=quantity)
                    )
                else:
                    use.quantity += quantity
                state = db.get(NiftyState, user_id)
                if account.equity <= account.starting_day_equity * (1 - config.daily_loss_fraction):
                    state.daily_locked = 1
                    if not state.killed:
                        state.state = "PAUSED"
            order.resolved_at = now
            account.updated_at = now
            return self._order_dict(order)

    def positions(self, user_id):
        with self.sessions() as db:
            rows = db.scalars(select(NiftyPosition).where(NiftyPosition.user_id == user_id))
            result = [
                {
                    "symbol": row.symbol,
                    "token": row.token,
                    "instrument": row.instrument,
                    "quantity": row.quantity,
                    "entry_price": str(row.entry_price),
                    "highest": str(row.highest),
                    "opened_at": _instant(row.opened_at),
                    "entry_order_id": row.entry_order_id,
                    "protection": (
                        db.get(NiftyProtection, (user_id, row.token)).payload
                        if db.get(NiftyProtection, (user_id, row.token))
                        else None
                    ),
                }
                for row in rows
            ]
            pending = list(
                db.scalars(
                    select(NiftyOrder).where(
                        NiftyOrder.user_id == user_id,
                        NiftyOrder.side == "SELL",
                        NiftyOrder.status == "PENDING",
                    )
                )
            )
            for row in result:
                protection = row.get("protection") or {}
                row.update(
                    {
                        key: protection.get(key)
                        for key in (
                            "initial_stop",
                            "stop_price",
                            "target_price",
                            "target_fraction",
                            "highest_bid",
                            "trailing_active",
                            "trailing_distance_points",
                            "point_unit",
                            "exit_reason",
                            "configuration_id",
                        )
                    }
                )
                row["confidence_score"] = (protection.get("confidence") or {}).get("score")
                row["exit_state"] = (
                    "EXITING"
                    if any(o.token == row["token"] for o in pending)
                    else "EXIT_REQUIRED"
                    if protection.get("exit_reason")
                    else "OPEN"
                )
            return result

    def mark_highest(self, user_id, token, price):
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyPosition, (user_id, token))
            if row is not None and price > row.highest:
                row.highest = price

    def observe_position(self, user_id, token, quote, now, forced_reason=None):
        """Serialize monotonic protection and reject stale/reordered observations."""
        from services.nifty_algo.config import StrategyConfig
        from services.nifty_algo.paper_executor import _charges
        from services.nifty_algo.protection import observe_bid

        with self.sessions.begin() as db:
            self._lock(db, user_id)
            position = db.get(NiftyPosition, (user_id, token))
            row = db.get(NiftyProtection, (user_id, token))
            if row is None or position is None:
                return None
            config = StrategyConfig.model_validate(row.payload["configuration"])
            previous = row.payload.get("last_source_time")
            valid = (
                quote is not None
                and quote.token == token
                and quote.bid is not None
                and quote.bid_size > 0
                and quote.source_time <= quote.received_time <= now
                and 0 <= (now - quote.source_time).total_seconds() <= config.quote_max_age
                and quote.source_time >= datetime.fromisoformat(_instant(position.opened_at))
                and (previous is None or quote.source_time > datetime.fromisoformat(previous))
            )
            payload = dict(row.payload)
            if valid:
                previous_exit_reason = payload.get("exit_reason")
                previous_stop = Decimal(
                    payload.get("stop_price", payload["initial_stop"])
                )
                quantity = min(position.quantity, self._remaining_quantity(db, user_id, position))
                payload = observe_bid(
                    payload,
                    position.entry_price,
                    quote.bid,
                    position.instrument["tick_size"],
                    config,
                    quantity=quantity if quantity > 0 else None,
                    entry_fees=payload.get("entry_fees_remaining", "0"),
                    charges=_charges,
                    bid_size=quote.bid_size,
                    source_time=quote.source_time,
                )
                payload["last_source_time"] = quote.source_time.isoformat()
                payload["last_bid"] = str(quote.bid)
                payload["last_bid_size"] = quote.bid_size
                if (
                    payload.get("stop_price") is not None
                    and Decimal(payload["stop_price"]) < previous_stop
                ):
                    raise ValueError("Persisted protection stop cannot decrease")
                position.highest = max(position.highest, Decimal(payload["highest_bid"]))
                if previous_exit_reason == "EARLY_PROFIT_BOOKING":
                    if payload.get("exit_reason") is None:
                        payload["exit_reason"] = previous_exit_reason
                    elif forced_reason:
                        payload["exit_reason"] = forced_reason
            if forced_reason and (
                not payload.get("exit_reason")
                or payload.get("exit_reason") == "EARLY_PROFIT_BOOKING"
            ):
                payload["exit_reason"] = forced_reason
            for event in payload.pop("new_events", []):
                kind = event.get("kind")
                transitioned = (
                    kind == "PROFIT_LOCK_ACTIVATED"
                    and not row.payload.get("profit_lock_active", False)
                    and payload.get("profit_lock_active", False)
                ) or (
                    kind == "PROFIT_FLOOR_UNREPRESENTABLE"
                    and row.payload.get("exit_reason") != "PROFIT_FLOOR_UNREPRESENTABLE"
                    and payload.get("exit_reason") == "PROFIT_FLOOR_UNREPRESENTABLE"
                )
                if transitioned:
                    event_payload = {key: value for key, value in event.items() if key != "kind"}
                    db.add(
                        NiftyEvent(
                            user_id=user_id,
                            kind=kind,
                            payload={"token": token, **event_payload},
                            created_at=now,
                        )
                    )
            row.payload = payload
            return payload

    def update_position_snapshot(self, user_id, token, snapshot):
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyProtection, (user_id, token))
            if row is None:
                return False
            previous = row.payload.get("last_snapshot") or {}
            previous_end = previous.get("end")
            current_end = snapshot.get("end")
            if previous_end and current_end:
                if datetime.fromisoformat(current_end) <= datetime.fromisoformat(previous_end):
                    return False
            row.payload = {**row.payload, "last_snapshot": snapshot}
            return True

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
                    "entry_context": (
                        db.get(NiftyOrder, (user_id, row.entry_order_id)).payload
                        if db.get(NiftyOrder, (user_id, row.entry_order_id))
                        else None
                    ),
                    "exit_context": (
                        db.get(NiftyOrder, (user_id, row.exit_order_id)).payload
                        if db.get(NiftyOrder, (user_id, row.exit_order_id))
                        else None
                    ),
                }
                for row in rows
            ]

    def performance(self, user_id):
        from sqlalchemy import case, func

        account = self.account(user_id)
        with self.sessions() as db:
            count, wins, total, best, worst = db.execute(
                select(
                    func.count(NiftyTrade.id),
                    func.sum(case((NiftyTrade.net > 0, 1), else_=0)),
                    func.sum(NiftyTrade.net),
                    func.max(NiftyTrade.net),
                    func.min(NiftyTrade.net),
                ).where(NiftyTrade.user_id == user_id)
            ).one()
        wins = wins or 0
        return {
            "account": account,
            "equity_basis": "BOOK_COST_NOT_MARK_TO_MARKET",
            "trades": count,
            "wins": wins,
            "win_rate": round(wins / count, 4) if count else None,
            "realized_total": str(total or Decimal("0")),
            "realized_day": account["realized_day"],
            "best": str(best) if count else None,
            "worst": str(worst) if count else None,
        }

    # Loss cooldown and monthly limits ------------------------------------
    #
    # Writers (fill, entry_locks, resolve_cooldowns) take the user lock. The
    # reason helpers are read-only so admit_order can evaluate them inside its
    # own locked transaction without persisting anything on a refusal.

    @staticmethod
    def _limit_config(state, fallback):
        from services.nifty_algo.config import StrategyConfig

        try:
            return StrategyConfig.model_validate(state.configuration)
        except (ValueError, AttributeError):
            return fallback

    @staticmethod
    def _trade_month_sum(db, user_id, key):
        from sqlalchemy import func

        start, end = _month_bounds(key)
        total = db.scalar(
            select(func.sum(NiftyTrade.net)).where(
                NiftyTrade.user_id == user_id,
                NiftyTrade.closed_at >= start,
                NiftyTrade.closed_at < end,
            )
        )
        return Decimal(str(total or 0))

    def _create_month(self, db, user_id, key, now):
        # Backfill from the immutable journal so trades closed before this
        # table existed (or before the row was created) still count.
        db.flush()
        row = NiftyMonth(
            user_id=user_id,
            month=key,
            realized_net=self._trade_month_sum(db, user_id, key),
            lock_detail={},
            milestone_report_ids=[],
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def _month_breaches(net, config):
        loss = net < 0 and -net >= config.monthly_loss_limit
        profit = (
            config.monthly_profit_target is not None and net >= config.monthly_profit_target
        )
        return loss, profit

    def _latch_month_locks(self, db, user_id, row, config, now):
        net = Decimal(str(row.realized_net))
        loss, profit = self._month_breaches(net, config)
        detail = dict(row.lock_detail or {})
        latched = []
        if loss and row.loss_locked_at is None:
            row.loss_locked_at = now
            detail["loss"] = {
                "realized_net": str(net),
                "limit": str(config.monthly_loss_limit),
                "at": now.isoformat(),
            }
            latched.append(("MONTHLY_LOSS_LOCKED", detail["loss"]))
        if profit and row.profit_locked_at is None:
            row.profit_locked_at = now
            detail["profit"] = {
                "realized_net": str(net),
                "target": str(config.monthly_profit_target),
                "at": now.isoformat(),
            }
            latched.append(("MONTHLY_PROFIT_LOCKED", detail["profit"]))
        if latched:
            row.lock_detail = detail
            row.updated_at = now
            for kind, payload in latched:
                db.add(
                    NiftyEvent(
                        user_id=user_id,
                        kind=kind,
                        payload={"month": row.month, **payload},
                        created_at=now,
                    )
                )

    def _record_month_net(self, db, user_id, now, net, config):
        key = _month_key(now)
        row = db.get(NiftyMonth, (user_id, key))
        if row is None:
            row = self._create_month(db, user_id, key, now)  # includes this trade
        else:
            row.realized_net = Decimal(str(row.realized_net)) + net
            row.updated_at = now
        self._latch_month_locks(db, user_id, row, config, now)

    def _month_lock_reasons(self, db, user_id, moment, config):
        """Read-only: latched locks plus a live threshold check for this IST month."""
        key = _month_key(moment)
        row = db.get(NiftyMonth, (user_id, key))
        net = (
            Decimal(str(row.realized_net))
            if row is not None
            else self._trade_month_sum(db, user_id, key)
        )
        loss, profit = self._month_breaches(net, config)
        reasons = []
        if loss or (row is not None and row.loss_locked_at is not None):
            reasons.append("MONTHLY_LOSS_LOCK")
        if profit or (row is not None and row.profit_locked_at is not None):
            reasons.append("MONTHLY_PROFIT_LOCK")
        return reasons

    @staticmethod
    def _cooldown_reasons(db, user_id, day):
        """Read-only: ``day`` (IST ISO date) falls inside a scheduled cooldown."""
        from sqlalchemy import or_

        rows = db.scalars(
            select(NiftyCooldown).where(
                NiftyCooldown.user_id == user_id,
                NiftyCooldown.loss_session < day,
                or_(
                    NiftyCooldown.cooldown_session.is_(None),
                    NiftyCooldown.cooldown_session >= day,
                ),
            )
        )
        reasons = [
            "COOLDOWN_UNRESOLVED" if row.cooldown_session is None else "COOLDOWN_ACTIVE"
            for row in rows
        ]
        return list(dict.fromkeys(reasons))

    def _schedule_cooldown(self, db, user_id, position, entry, now):
        from sqlalchemy import func

        db.flush()
        total = db.scalar(
            select(func.sum(NiftyTrade.net)).where(
                NiftyTrade.user_id == user_id,
                NiftyTrade.entry_order_id == position.entry_order_id,
            )
        )
        total = Decimal(str(total or 0))
        if total >= 0:
            return
        opened = entry.created_at if entry is not None else position.opened_at
        loss_session = datetime.fromisoformat(_instant(opened)).astimezone(_IST).date()
        if db.get(NiftyCooldown, (user_id, loss_session.isoformat())) is not None:
            return
        event = NiftyEvent(
            user_id=user_id,
            kind="SESSION_LOSS_COOLDOWN",
            payload={
                "loss_session": loss_session.isoformat(),
                "entry_order_id": position.entry_order_id,
                "realized_net": str(total),
            },
            created_at=now,
        )
        db.add(event)
        db.flush()
        db.add(
            NiftyCooldown(
                user_id=user_id,
                loss_session=loss_session.isoformat(),
                cooldown_session=None,  # Resolved outside the lock via the calendar.
                loss_event_id=event.id,
                entry_order_id=position.entry_order_id,
                realized_net=total,
                created_at=now,
                updated_at=now,
            )
        )

    def resolve_cooldowns(self, user_id, now, *, recompute=False):
        """Assign cooldown sessions from the approved calendar.

        Calendar lookups run outside the user lock. An unresolvable session
        stays NULL, which admission treats as blocking. ``recompute`` also
        revisits current and future sessions after a calendar revision; a
        recomputed date never moves before today (fail closed).
        """
        from datetime import date

        from sqlalchemy import or_

        from services.nifty_algo.calendar import next_eligible_session

        today = now.astimezone(_IST).date()
        with self.sessions() as db:
            query = select(NiftyCooldown).where(NiftyCooldown.user_id == user_id)
            if recompute:
                query = query.where(
                    or_(
                        NiftyCooldown.cooldown_session.is_(None),
                        NiftyCooldown.cooldown_session >= today.isoformat(),
                    )
                )
            else:
                query = query.where(NiftyCooldown.cooldown_session.is_(None))
            pending = [(row.loss_session, row.cooldown_session) for row in db.scalars(query)]
        if not pending:
            return []
        resolved = {}
        for loss_session, current in pending:
            try:
                value = next_eligible_session(
                    user_id, date.fromisoformat(loss_session), store=self
                )
                if current is not None and value < today:
                    value = next_eligible_session(
                        user_id, today - timedelta(days=1), store=self
                    )
                resolved[loss_session] = (current, value.isoformat())
            except ValueError:
                resolved[loss_session] = (current, None)
        changes = []
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            for loss_session, (current, value) in resolved.items():
                row = db.get(NiftyCooldown, (user_id, loss_session))
                # Skip rows changed by a concurrent writer since the lookup.
                if row is None or row.cooldown_session != current or value == current:
                    continue
                row.cooldown_session = value
                row.updated_at = now
                change = {
                    "loss_session": loss_session,
                    "previous": current,
                    "cooldown_session": value,
                    "loss_event_id": row.loss_event_id,
                }
                db.add(
                    NiftyEvent(
                        user_id=user_id,
                        kind="COOLDOWN_SCHEDULED" if current is None else "COOLDOWN_RECOMPUTED",
                        payload=change,
                        created_at=now,
                    )
                )
                changes.append(change)
        return changes

    def entry_locks(self, user_id, now, config):
        """Latch monthly locks and return cooldown/monthly entry refusals."""
        self.ensure_user(user_id)
        day = now.astimezone(_IST).date().isoformat()
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            key = _month_key(now)
            row = db.get(NiftyMonth, (user_id, key)) or self._create_month(
                db, user_id, key, now
            )
            self._latch_month_locks(db, user_id, row, config, now)
            return self._cooldown_reasons(db, user_id, day) + self._month_lock_reasons(
                db, user_id, now, config
            )

    def risk_locks(self, user_id, now=None):
        """Read-only status of the cooldown and the current IST month."""
        from services.nifty_algo.config import StrategyConfig

        now = now or datetime.now(UTC)
        state = self.read(user_id)
        try:
            config = StrategyConfig.model_validate(state["configuration"])
        except ValueError:
            config = StrategyConfig()
        day = now.astimezone(_IST).date().isoformat()
        key = _month_key(now)
        with self.sessions() as db:
            cooldown_reasons = self._cooldown_reasons(db, user_id, day)
            latest = db.scalar(
                select(NiftyCooldown)
                .where(NiftyCooldown.user_id == user_id)
                .order_by(NiftyCooldown.loss_session.desc())
                .limit(1)
            )
            month = db.get(NiftyMonth, (user_id, key))
            net = (
                Decimal(str(month.realized_net))
                if month is not None
                else self._trade_month_sum(db, user_id, key)
            )
            month_reasons = self._month_lock_reasons(db, user_id, now, config)
            return {
                "session": day,
                "reasons": cooldown_reasons + month_reasons,
                "cooldown": {
                    "active": bool(cooldown_reasons),
                    "loss_session": latest.loss_session if latest else None,
                    "cooldown_session": latest.cooldown_session if latest else None,
                },
                "month": {
                    "month": key,
                    "realized_net": str(net),
                    "loss_limit": str(config.monthly_loss_limit),
                    "profit_target": (
                        None
                        if config.monthly_profit_target is None
                        else str(config.monthly_profit_target)
                    ),
                    "loss_locked_at": (
                        _instant(month.loss_locked_at)
                        if month is not None and month.loss_locked_at
                        else None
                    ),
                    "profit_locked_at": (
                        _instant(month.profit_locked_at)
                        if month is not None and month.profit_locked_at
                        else None
                    ),
                },
            }
