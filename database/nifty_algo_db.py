"""Additive feature state in OpenAlgo's configured database.

Sessions are short lived. Revisions use compare-and-set updates so a delayed
browser save cannot overwrite another control or configuration change. The
paper ledger keeps funds, order intents, positions and closed trades inside
this feature only; it never shares the shared Sandbox balance.
"""

from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256 as sha256_bytes
from json import dumps
from pathlib import Path
from re import fullmatch
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    and_,
    func,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, aliased, sessionmaker

from database.nifty_notifications import NotificationStore
from database.nifty_research_analytics import ResearchAnalyticsStore
from services.nifty_algo import analytics
from services.nifty_algo.config import StrategyConfig
from services.nifty_algo.ledger_analytics import AnalyticsDataError, fill_facts
from services.nifty_algo.research import experiment_snapshot, recording_cursor


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


class NiftySafetyIncident(Base):
    """Entry interlocks are separate from, and cannot disable, held protection."""

    __tablename__ = "nifty_algo_safety_incident"
    __table_args__ = (
        UniqueConstraint("user_id", "incident_key"),
        Index("ix_nifty_safety_open", "user_id", "mode", "severity", "status"),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), nullable=False)
    incident_key = Column(String(128), nullable=False)
    mode = Column(String(12), nullable=False)
    code = Column(String(64), nullable=False)
    severity = Column(String(12), nullable=False)
    status = Column(String(20), nullable=False, default="OPEN")
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False)
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledged_by = Column(String(255))


class NiftyNotificationCursor(Base):
    __tablename__ = "nifty_algo_notification_cursor"
    user_id = Column(String(255), primary_key=True)
    event_id = Column(Integer, nullable=False, default=0)


class NiftyShadowNotificationCursor(Base):
    __tablename__ = "nifty_algo_shadow_notification_cursor"
    user_id = Column(String(255), primary_key=True)
    event_id = Column(Integer, nullable=False)
    next_at = Column(DateTime(timezone=True), nullable=False)


class NiftyNotificationDelivery(Base):
    __tablename__ = "nifty_algo_notification_delivery"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", "destination"),
        Index("ix_nifty_notification_due", "user_id", "status", "next_at"),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), nullable=False)
    event_id = Column(Integer, nullable=False)
    destination = Column(String(24), nullable=False)
    envelope = Column(JSON, nullable=False)
    status = Column(String(16), nullable=False, default="PENDING")
    attempts = Column(Integer, nullable=False, default=0)
    next_at = Column(DateTime(timezone=True), nullable=False)
    claim_token = Column(String(32))
    claimed_until = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class NiftyDiscordSettings(Base):
    __tablename__ = "nifty_algo_discord_settings"
    user_id = Column(String(255), primary_key=True)
    application_id = Column(String(20), nullable=False, unique=True)
    revision = Column(Integer, nullable=False)
    configuration = Column(JSON, nullable=False)
    token_encrypted = Column(String(1024), nullable=False)
    verified_revision = Column(Integer)
    verification = Column(JSON)
    rate_limit_until = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), nullable=False)


class NiftyNotificationAttempt(Base):
    __tablename__ = "nifty_algo_notification_attempt"
    __table_args__ = (UniqueConstraint("delivery_id", "attempt"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    delivery_id = Column(Integer, nullable=False)
    attempt = Column(Integer, nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class NiftyNotificationWorker(Base):
    __tablename__ = "nifty_algo_notification_worker"
    user_id = Column(String(255), primary_key=True)
    owner = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    heartbeat_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class NiftyDiscordBucket(Base):
    __tablename__ = "nifty_algo_discord_bucket"
    user_id = Column(String(255), primary_key=True)
    destination = Column(String(32), primary_key=True)
    bucket = Column(String(128), nullable=False)
    blocked_until = Column(DateTime(timezone=True), nullable=False)


class NiftyNotificationDigest(Base):
    __tablename__ = "nifty_algo_notification_digest"
    user_id = Column(String(255), primary_key=True)
    kind = Column(String(16), primary_key=True)
    cursor = Column(Integer, nullable=False)
    next_at = Column(DateTime(timezone=True), nullable=False)


class NiftyResearchNotificationSeen(Base):
    __tablename__ = "nifty_algo_research_notification_seen"
    user_id = Column(String(255), primary_key=True)
    opportunity_id = Column(String(64), primary_key=True)


class NiftyDiscordReportRequest(Base):
    __tablename__ = "nifty_algo_discord_report_request"
    user_id = Column(String(255), primary_key=True)
    interaction_id = Column(String(20), primary_key=True)
    application_id = Column(String(20), nullable=False)
    token_encrypted = Column(String(2048))
    payload = Column(JSON, nullable=False)
    status = Column(String(16), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    claim_token = Column(String(32))
    claimed_until = Column(DateTime(timezone=True))
    next_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    result = Column(JSON)


class NiftyIncidentReminder(Base):
    __tablename__ = "nifty_algo_incident_reminder"
    user_id = Column(String(255), primary_key=True)
    incident_id = Column(Integer, primary_key=True)
    stage = Column(Integer, nullable=False)
    next_at = Column(DateTime(timezone=True), nullable=False)


class NiftyDiscordInteraction(Base):
    __tablename__ = "nifty_algo_discord_interaction"
    user_id = Column(String(255), primary_key=True)
    interaction_id = Column(String(20), primary_key=True)
    response = Column(JSON, nullable=False)
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


class NiftyShadowPosition(Base):
    """Hypothetical position with its own ledger; never an order or primary exposure.

    ``active_slot`` is 1 while active and NULL once ended. NULLs never collide,
    so the unique constraint admits at most one active row per user, mirrors
    included. ``shadow_key`` makes each signal or primary entry open once.
    """

    __tablename__ = "nifty_algo_shadow_position"
    __table_args__ = (
        UniqueConstraint("user_id", "shadow_key"),
        UniqueConstraint("user_id", "active_slot"),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    shadow_key = Column(String(160), nullable=False)
    kind = Column(String(12), nullable=False)
    status = Column(String(32), nullable=False)
    active_slot = Column(Integer)
    additive = Column(Integer, nullable=False)
    decision_id = Column(String(64))
    primary_entry_order_id = Column(String(64))
    token = Column(String(32), nullable=False)
    symbol = Column(String(64), nullable=False)
    instrument = Column(JSON, nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Numeric(18, 4), nullable=False)
    entry_fees = Column(Numeric(18, 4), nullable=False)
    protection = Column(JSON, nullable=False)
    exit_price = Column(Numeric(18, 4))
    exit_fees = Column(Numeric(18, 4))
    gross = Column(Numeric(18, 4))
    net = Column(Numeric(18, 4))
    exit_reason = Column(String(64))
    valuation = Column(String(20))
    session = Column(String(10), nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=False)
    closed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), nullable=False)


class NiftyShadowEvent(Base):
    __tablename__ = "nifty_algo_shadow_event"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    shadow_id = Column(Integer, nullable=False)
    kind = Column(String(40), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class NiftyOpportunity(Base):
    """Research-only signal observation keyed by candle end, side and configuration."""

    __tablename__ = "nifty_algo_opportunity"
    user_id = Column(String(255), primary_key=True)
    opportunity_id = Column(String(64), primary_key=True)
    candle_end = Column(DateTime(timezone=True), nullable=False)
    direction = Column(String(2), nullable=False)
    configuration_id = Column(String(64), nullable=False)
    decision_id = Column(String(64))
    status = Column(String(16), nullable=False)
    outcome = Column(String(32))
    deadline = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    closed_at = Column(DateTime(timezone=True))


class NiftyMode(Base):
    """Per-user trading mode. PAPER by default; Live cannot activate in this release.

    ``revision`` is the compare-and-set token for mode requests. ``history``
    keeps the most recent changes; the full trail is in ``nifty_algo_event``.
    """

    __tablename__ = "nifty_algo_mode"
    user_id = Column(String(255), primary_key=True)
    mode = Column(String(8), nullable=False, default="PAPER")
    revision = Column(Integer, nullable=False, default=1)
    history = Column(JSON, nullable=False, default=list)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class NiftyResearchRecording(Base):
    """Bounded research evidence; never an account, order or active configuration."""

    __tablename__ = "nifty_algo_research_recording"
    user_id = Column(String(255), primary_key=True)
    id = Column(String(32), primary_key=True)
    status = Column(String(16), nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    last_available_at = Column(DateTime(timezone=True))
    count = Column(Integer, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    max_observations = Column(Integer, nullable=False)
    configuration_id = Column(String(64), nullable=False)
    configuration = Column(JSON, nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    sealed_at = Column(DateTime(timezone=True))


class NiftyResearchCapture(Base):
    """Explicit native opt-in and immutable scope; never adopts existing recordings."""

    __tablename__ = "nifty_algo_research_capture"
    user_id = Column(String(255), primary_key=True)
    recording_id = Column(String(32), primary_key=True)
    payload = Column(JSON)
    sha256 = Column(String(64))


class NiftyResearchObservation(Base):
    __tablename__ = "nifty_algo_research_observation"
    __table_args__ = (UniqueConstraint("user_id", "recording_id", "sha256"),)
    user_id = Column(String(255), primary_key=True)
    recording_id = Column(String(32), primary_key=True)
    sequence = Column(Integer, primary_key=True)
    sha256 = Column(String(64), nullable=False)
    available_at = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSON, nullable=False)


class NiftyResearchSample(Base):
    """Sample identities exclude poll availability; one row per accepted observation."""

    __tablename__ = "nifty_algo_research_sample"
    user_id = Column(String(255), primary_key=True)
    recording_id = Column(String(32), primary_key=True)
    sha256 = Column(String(64), primary_key=True)


class NiftyResearchExperiment(Base):
    """Write-once research definition; no primary account or execution state."""

    __tablename__ = "nifty_algo_research_experiment"
    user_id = Column(String(255), primary_key=True)
    id = Column(String(32), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    snapshot = Column(JSON, nullable=False)
    sha256 = Column(String(64), nullable=False)


class NiftyExitStudy(Base):
    __tablename__ = "nifty_algo_exit_study"
    user_id = Column(String(255), primary_key=True)
    trade_id = Column(Integer, primary_key=True)
    payload = Column(JSON, nullable=False)


class NiftyResearchResult(Base):
    __tablename__ = "nifty_algo_research_result"
    user_id = Column(String(255), primary_key=True)
    experiment_id = Column(String(32), primary_key=True)
    payload = Column(JSON, nullable=False)
    sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class NiftyExecutionResearch(Base):
    """Pure research job; no permission to mutate accounts or trading settings."""

    __tablename__ = "nifty_algo_execution_research"
    user_id = Column(String(255), primary_key=True)
    experiment_id = Column(String(32), primary_key=True)
    status = Column(String(16), nullable=False)
    claim_token = Column(String(32))
    claimed_until = Column(DateTime(timezone=True))
    payload = Column(JSON)
    sha256 = Column(String(64))
    updated_at = Column(DateTime(timezone=True), nullable=False)


class NiftyRecordingArchive(Base):
    __tablename__ = "nifty_algo_recording_archive"
    user_id = Column(String(255), primary_key=True)
    recording_id = Column(String(32), primary_key=True)
    sha256 = Column(String(64), nullable=False)
    path = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class NiftyReport(Base):
    """One PDF report per (user, kind, period). Generation and delivery are tracked
    separately; ``claim_token`` with ``claimed_until`` is the compare-and-set claim
    that makes a send happen once. ``path`` is relative to the reports root.
    """

    __tablename__ = "nifty_algo_report"
    __table_args__ = (UniqueConstraint("user_id", "kind", "period_key"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(String(255), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    variant = Column(String(16), nullable=False, default="STANDARD")
    period_key = Column(String(32), nullable=False)
    path = Column(String(255))
    sha256 = Column(String(64))
    size_bytes = Column(Integer)
    generation_status = Column(String(12), nullable=False, default="PENDING")
    generation_attempts = Column(Integer, nullable=False, default=0)
    generation_error_type = Column(String(64))
    delivery_status = Column(String(16), nullable=False, default="PENDING")
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True))
    last_error_type = Column(String(64))
    claim_token = Column(String(32))
    claimed_until = Column(DateTime(timezone=True))
    summary = Column(JSON, nullable=False, default=dict)
    generated_at = Column(DateTime(timezone=True))
    sent_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class NiftyReportScan(Base):
    """Durable position of bounded report-period discovery per user.

    The cursor is an IST ISO date (next unexamined session); it does not
    imply PDF generation or delivery succeeded. Those are separate rows.
    """

    __tablename__ = "nifty_algo_report_scan"
    user_id = Column(String(255), primary_key=True)
    next_day = Column(String(10), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class NiftyReportScanBlock(Base):
    """An unresolved IST session; scanned days must never disappear silently."""

    __tablename__ = "nifty_algo_report_scan_block"
    user_id = Column(String(255), primary_key=True)
    day = Column(String(10), primary_key=True)
    reason = Column(String(40), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    last_checked_at = Column(DateTime(timezone=True), nullable=False)


MODE_HISTORY_LIMIT = 50


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


class NiftyStore(NotificationStore, ResearchAnalyticsStore):
    def __init__(self, engine, calendar_blob_dir=None, report_dir=None):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False)
        self.calendar_blob_dir = Path(calendar_blob_dir or "db/nifty_calendar")
        self.report_dir = Path(report_dir or "db/nifty_reports")

    def initialize(self):
        Base.metadata.create_all(self.engine)

    @staticmethod
    def _calendar_dict(row):
        if row is None:
            return None
        return {
            "id": row.id,
            "user_id": row.user_id,
            "year": row.year,
            "segment": row.segment,
            "source_filename": row.source_filename,
            "sha256": row.sha256,
            "uploader": row.uploader,
            "status": row.status,
            "entries": row.entries,
            "issues": row.issues,
            "audit": row.audit,
            "created_at": _instant(row.created_at),
            "approved_at": _instant(row.approved_at) if row.approved_at else None,
            "approved_by": row.approved_by,
            "supersedes_id": row.supersedes_id,
        }

    def create_calendar_draft(
        self,
        user_id,
        *,
        year,
        segment,
        source_filename,
        sha256,
        uploader,
        entries,
        issues,
        data,
        extension,
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
        audit = [
            {
                "at": now.isoformat(),
                "actor": uploader,
                "action": "DRAFT_CREATED",
                "detail": {"sha256": sha256},
            }
        ]
        try:
            with self.sessions.begin() as db:
                self._lock(db, user_id)
                row = NiftyCalendarVersion(
                    user_id=user_id,
                    year=int(year),
                    segment=segment,
                    source_filename=Path(source_filename).name[:255],
                    sha256=sha256,
                    uploader=uploader,
                    status="DRAFT",
                    entries=entries,
                    issues=list(issues),
                    audit=audit,
                    created_at=now,
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
            row = db.scalar(
                select(NiftyCalendarVersion).where(
                    NiftyCalendarVersion.user_id == user_id,
                    NiftyCalendarVersion.id == int(version_id),
                )
            )
            return self._calendar_dict(row)

    def approved_calendar_version(self, user_id, year):
        self.ensure_user(user_id)
        with self.sessions() as db:
            row = db.scalar(
                select(NiftyCalendarVersion).where(
                    NiftyCalendarVersion.user_id == user_id,
                    NiftyCalendarVersion.year == int(year),
                    NiftyCalendarVersion.segment == "NFO",
                    NiftyCalendarVersion.status == "APPROVED",
                )
            )
            return self._calendar_dict(row)

    def update_draft_entries(self, user_id, version_id, entries, actor):
        from services.nifty_algo.calendar_import import recompute_entries

        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.scalar(
                select(NiftyCalendarVersion).where(
                    NiftyCalendarVersion.user_id == user_id,
                    NiftyCalendarVersion.id == int(version_id),
                )
            )
            if row is None or row.status != "DRAFT":
                raise ValueError("Calendar version is not an editable draft")
            normalized, issues = recompute_entries(entries, row.year)
            row.entries = normalized
            row.issues = list(issues)
            row.audit = [
                *row.audit,
                {
                    "at": datetime.now(UTC).isoformat(),
                    "actor": actor,
                    "action": "DRAFT_ENTRIES_UPDATED",
                    "detail": {"count": len(normalized)},
                },
            ]
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
        # A revised calendar can affect historical report eligibility as well.
        self.rewind_report_scan_cursor(user_id, result["year"])
        # A revised calendar recomputes current and future cooldown sessions.
        self.resolve_cooldowns(user_id, now or datetime.now(UTC), recompute=True)
        return result

    def _approve_calendar(self, user_id, version_id, *, confirmed_year, confirmed_segment, actor):
        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.scalar(
                select(NiftyCalendarVersion).where(
                    NiftyCalendarVersion.user_id == user_id,
                    NiftyCalendarVersion.id == int(version_id),
                )
            )
            if row is None or row.status != "DRAFT":
                raise ValueError("Calendar version is not an approvable draft")
            if int(confirmed_year) != row.year or confirmed_segment != row.segment:
                raise ValueError("Calendar year and segment confirmation must match")
            if row.segment != "NFO" or any(item.get("ambiguous") for item in row.entries):
                raise ValueError("Calendar has an unconfirmed segment or ambiguous entries")
            # An empty/unparsed calendar would treat every ordinary weekday as tradable.
            if not row.entries or not all(
                isinstance(item, dict) and item.get("date") for item in row.entries
            ):
                raise ValueError("Calendar must contain reviewed dated NFO holidays")
            prior = db.scalar(
                select(NiftyCalendarVersion).where(
                    NiftyCalendarVersion.user_id == user_id,
                    NiftyCalendarVersion.year == row.year,
                    NiftyCalendarVersion.status == "APPROVED",
                )
            )
            now = datetime.now(UTC)
            if prior:
                prior.status = "SUPERSEDED"
                row.supersedes_id = prior.id
                prior.audit = [
                    *prior.audit,
                    {
                        "at": now.isoformat(),
                        "actor": actor,
                        "action": "SUPERSEDED",
                        "detail": {"by_version": row.id},
                    },
                ]
            row.status = "APPROVED"
            row.approved_at = now
            row.approved_by = actor
            row.audit = [
                *row.audit,
                {
                    "at": now.isoformat(),
                    "actor": actor,
                    "action": "APPROVED",
                    "detail": {"year": row.year, "segment": row.segment},
                },
            ]
            result = self._calendar_dict(row)
        return result

    def reject_calendar(self, user_id, version_id, actor, detail=None):
        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.scalar(
                select(NiftyCalendarVersion).where(
                    NiftyCalendarVersion.user_id == user_id,
                    NiftyCalendarVersion.id == int(version_id),
                )
            )
            if row is None or row.status != "DRAFT":
                raise ValueError("Calendar version is not a rejectable draft")
            row.status = "REJECTED"
            row.audit = [
                *row.audit,
                {
                    "at": datetime.now(UTC).isoformat(),
                    "actor": actor,
                    "action": "REJECTED",
                    "detail": detail or {},
                },
            ]
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
                if db.get(NiftyMode, user_id) is None:
                    db.add(
                        NiftyMode(
                            user_id=user_id, mode="PAPER", revision=1, history=[], updated_at=now
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
                if self._safety_reasons(db, user_id):
                    raise StateConflict("Safety interlock requires operator recovery.")
                lease = db.get(NiftyRunnerLease, user_id)
                account = db.get(NiftyAccount, user_id)
                if (
                    row.killed
                    or row.daily_locked
                    or lease is None
                    or account is None
                    or not account.reconciled
                    or datetime.fromisoformat(_instant(lease.expires_at)) <= now
                    or self._fresh_runner_assessment(lease, row.configuration_id, now) is None
                    or self.reconciliation_issues(user_id, _session=db)
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
            now = now or datetime.now(UTC)
            state = db.get(NiftyState, user_id)
            ready = (
                state is not None
                and self._fresh_runner_assessment(row, state.configuration_id, now) is not None
            )
            return {
                **row.payload,
                "entries_ready": ready,
                "reason": "READINESS_EVIDENCE_STALE"
                if row.payload.get("entries_ready") and not ready
                else row.payload.get("reason"),
                "operational": datetime.fromisoformat(_instant(row.expires_at)) > now,
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

    def events(self, user_id, *, kind=None, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Event limit must be an integer from 1 to 100")
        statement = select(NiftyEvent).where(NiftyEvent.user_id == user_id)
        if kind is not None:
            statement = statement.where(NiftyEvent.kind == kind)
        with self.sessions() as db:
            rows = db.scalars(statement.order_by(NiftyEvent.id.desc()).limit(limit))
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

    # Safety Center --------------------------------------------------------

    @staticmethod
    def _safety_reasons(db, user_id):
        mode = db.get(NiftyMode, user_id)
        primary_mode = mode.mode if mode is not None else "PAPER"
        blocked = db.scalar(
            select(NiftySafetyIncident.id)
            .where(
                NiftySafetyIncident.user_id == user_id,
                NiftySafetyIncident.mode == primary_mode,
                NiftySafetyIncident.severity == "CRITICAL",
                NiftySafetyIncident.status.in_(("OPEN", "ACKNOWLEDGED")),
            )
            .limit(1)
        )
        return ["SAFETY_INTERLOCK"] if blocked is not None else []

    @staticmethod
    def _incident_dict(row):
        return {
            "id": row.id,
            "incident_key": row.incident_key,
            "mode": row.mode,
            "code": row.code,
            "severity": row.severity,
            "status": row.status,
            "revision": row.revision,
            "created_at": _instant(row.created_at),
            "acknowledged_at": _instant(row.acknowledged_at) if row.acknowledged_at else None,
            "acknowledged_by": row.acknowledged_by,
        }

    @staticmethod
    def _fresh_runner_assessment(lease, configuration_id, now):
        """A heartbeat renews ownership, not the age of its readiness evidence."""
        if (
            lease is None
            or not isinstance(lease.payload, dict)
            or lease.payload.get("entries_ready") is not True
            or lease.payload.get("configuration_id") != configuration_id
        ):
            return None
        try:
            assessed = datetime.fromisoformat(lease.payload["assessed_at"])
            if (
                assessed.utcoffset() is not None
                and 0 <= (now - assessed).total_seconds() <= 30
                and datetime.fromisoformat(_instant(lease.expires_at)) > now
            ):
                return assessed
        except (KeyError, TypeError, ValueError):
            pass
        return None

    def safety_status(self, user_id):
        """Read-only, bounded incident page; the gate considers all open incidents."""
        with self.sessions() as db:
            reasons = self._safety_reasons(db, user_id)
            rows = list(
                db.scalars(
                    select(NiftySafetyIncident)
                    .where(NiftySafetyIncident.user_id == user_id)
                    .order_by(NiftySafetyIncident.id.desc())
                    .limit(100)
                )
            )
            resolved_ids = [row.id for row in rows if row.status == "RESOLVED"]
            resolutions = {}
            if resolved_ids:
                # The committed resolution event is the existing audit authority.
                events = db.scalars(
                    select(NiftyEvent)
                    .where(
                        NiftyEvent.user_id == user_id,
                        NiftyEvent.kind == "safety_resolved",
                        NiftyEvent.payload["id"].as_integer().in_(resolved_ids),
                    )
                    .order_by(NiftyEvent.id.desc())
                    .limit(100)
                )
                for event in events:
                    resolutions.setdefault(event.payload["id"], event.payload)
            incidents = []
            for row in rows:
                incident = self._incident_dict(row)
                resolution = resolutions.get(row.id)
                if resolution and resolution.get("revision") == row.revision:
                    for field in ("resolved_by", "resolved_at", "evidence"):
                        incident[field] = resolution.get(field)
                incidents.append(incident)
            return {
                "entry_blocked": bool(reasons),
                "reasons": reasons,
                "incidents": incidents,
                "recovery_available": True,
                "state_revision": (
                    state.revision if (state := db.get(NiftyState, user_id)) else None
                ),
            }

    def raise_safety_incident(self, user_id, incident_key, *, mode, code, severity, now):
        """Persist a retry-safe incident and pause primary critical entries atomically."""
        if (
            mode not in ("PAPER", "LIVE", "SHADOW", "RESEARCH")
            or severity not in ("WARNING", "CRITICAL")
            or not isinstance(incident_key, str)
            or not fullmatch(r"[A-Za-z0-9_.:-]{1,128}", incident_key)
            or not isinstance(code, str)
            or not fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code)
            or not isinstance(now, datetime)
            or now.utcoffset() is None
        ):
            raise ValueError("Invalid safety incident")
        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            existing = db.scalar(
                select(NiftySafetyIncident).where(
                    NiftySafetyIncident.user_id == user_id,
                    NiftySafetyIncident.incident_key == incident_key,
                )
            )
            if existing is not None:
                if (existing.mode, existing.code, existing.severity) != (mode, code, severity):
                    raise ValueError("Incident identity cannot change")
                return self._incident_dict(existing)
            row = NiftySafetyIncident(
                user_id=user_id,
                incident_key=incident_key,
                mode=mode,
                code=code,
                severity=severity,
                status="OPEN",
                revision=1,
                created_at=now,
            )
            db.add(row)
            db.flush()
            if self._safety_reasons(db, user_id):
                state = db.get(NiftyState, user_id)
                # Existing PAUSED survives rollback to code without incident tables.
                state.state = "KILLED" if state.killed else "PAUSED"
                state.revision += 1
                state.updated_at = now
            db.add(
                NiftyEvent(
                    user_id=user_id,
                    kind="safety_incident",
                    payload=self._incident_dict(row),
                    created_at=now,
                )
            )
            return self._incident_dict(row)

    def acknowledge_safety_incident(self, user_id, incident_id, revision, *, actor, now):
        """Acknowledgement is audited; it never resolves or resumes an entry gate."""
        if (
            actor != user_id
            or type(incident_id) is not int
            or incident_id < 1
            or type(revision) is not int
            or revision < 1
            or not isinstance(now, datetime)
            or now.utcoffset() is None
        ):
            raise ValueError("Invalid incident acknowledgement")
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.scalar(
                select(NiftySafetyIncident).where(
                    NiftySafetyIncident.user_id == user_id,
                    NiftySafetyIncident.id == incident_id,
                )
            )
            if row is None:
                raise LookupError("Incident not found")
            if row.revision != revision or row.status != "OPEN":
                raise StateConflict("Incident changed. Reload before acknowledging.")
            row.status = "ACKNOWLEDGED"
            row.revision += 1
            row.acknowledged_at = now
            row.acknowledged_by = actor
            db.add(
                NiftyEvent(
                    user_id=user_id,
                    kind="safety_acknowledged",
                    payload=self._incident_dict(row),
                    created_at=now,
                )
            )
            return self._incident_dict(row)

    def resolve_safety_incident(
        self, user_id, incident_id, revision, state_revision, *, actor, now
    ):
        """Resolve verified paper conditions, never kill flags or trading state."""
        if (
            actor != user_id
            or any(
                type(value) is not int or value < 1
                for value in (incident_id, revision, state_revision)
            )
            or not isinstance(now, datetime)
            or now.utcoffset() is None
        ):
            raise ValueError("Invalid incident resolution")
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.scalar(
                select(NiftySafetyIncident).where(
                    NiftySafetyIncident.user_id == user_id,
                    NiftySafetyIncident.id == incident_id,
                )
            )
            if row is None:
                raise LookupError("Incident not found")
            state = db.get(NiftyState, user_id)
            mode = db.get(NiftyMode, user_id)
            account = db.get(NiftyAccount, user_id)
            lease = db.get(NiftyRunnerLease, user_id)
            if (
                row.status != "ACKNOWLEDGED"
                or row.revision != revision
                or state.revision != state_revision
                or row.mode != "PAPER"
                or (mode is not None and mode.mode != "PAPER")
                or row.code
                not in ("STALE_DATA", "MARKET_DATA_DISCONNECTED", "RECONCILIATION_BLOCKED")
                or state.state != "PAUSED"
                or state.killed
                or state.daily_locked
                or account is None
                or not account.reconciled
            ):
                raise StateConflict("Incident recovery prerequisites changed.")
            assessed = self._fresh_runner_assessment(lease, state.configuration_id, now)
            if (
                assessed is None
                or assessed < datetime.fromisoformat(_instant(row.created_at))
                or self.reconciliation_issues(user_id, _session=db)
            ):
                raise StateConflict("Fresh runner and paper reconciliation evidence required.")
            pending = db.scalar(
                select(NiftyOrder.order_id)
                .where(
                    NiftyOrder.user_id == user_id,
                    NiftyOrder.side == "BUY",
                    NiftyOrder.status == "PENDING",
                )
                .limit(1)
            )
            positions = db.scalars(
                select(NiftyPosition).where(NiftyPosition.user_id == user_id).limit(2)
            )
            if pending is not None or any(
                not p.protection or p.protection.get("legacy") for p in positions
            ):
                raise StateConflict("Pending entries or unverified protection require review.")
            row.status = "RESOLVED"
            row.revision += 1
            state.revision += 1
            state.updated_at = now
            result = {
                **self._incident_dict(row),
                "resolved_by": actor,
                "resolved_at": now.isoformat(),
                "evidence": {
                    "scope": "ISOLATED_PAPER_LEDGER",
                    "checked_at": now.isoformat(),
                    "assessed_at": assessed.isoformat(),
                    "configuration_id": state.configuration_id,
                    "runner_owner": lease.owner,
                },
            }
            db.add(
                NiftyEvent(
                    user_id=user_id,
                    kind="safety_resolved",
                    payload=result,
                    created_at=now,
                )
            )
            return result

    # Notification outbox ---------------------------------------------------

    @staticmethod
    def _notification_time(now):
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError("Timezone-aware notification time required")
        return now.astimezone(UTC)

    @staticmethod
    def _notification_dict(row):
        return {
            "id": row.id,
            "event_id": row.event_id,
            "destination": row.destination,
            "envelope": row.envelope,
            "status": row.status,
            "attempts": row.attempts,
            "next_at": _instant(row.next_at),
            "created_at": _instant(row.created_at),
            "updated_at": _instant(row.updated_at),
        }

    def notifications(self, user_id):
        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyNotificationDelivery)
                .where(NiftyNotificationDelivery.user_id == user_id)
                .order_by(NiftyNotificationDelivery.id.desc())
                .limit(100)
            )
            return [self._notification_dict(row) for row in rows]

    def project_notifications(self, user_id, destinations, *, now):
        """Project at most 100 committed events; never copy arbitrary event payloads."""
        routes = {
            "safety",
            "system",
            "execution",
            "trades",
            "signals",
            "risk",
            "daily",
            "weekly",
            "monthly",
            "research",
        }
        if (
            not isinstance(destinations, list)
            or not 1 <= len(destinations) <= 10
            or any(not isinstance(item, str) or item not in routes for item in destinations)
            or len(set(destinations)) != len(destinations)
        ):
            raise ValueError("One to ten distinct logical notification routes required")
        now = self._notification_time(now)
        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            cursor = db.get(NiftyNotificationCursor, user_id)
            if cursor is None:
                cursor = NiftyNotificationCursor(user_id=user_id, event_id=0)
                db.add(cursor)
            events = db.scalars(
                select(NiftyEvent)
                .where(NiftyEvent.user_id == user_id, NiftyEvent.id > cursor.event_id)
                .order_by(NiftyEvent.id)
                .limit(100)
            ).all()
            count = 0
            for event in events:
                if event.kind in ("safety_incident", "safety_acknowledged"):
                    payload = event.payload
                    incident_id = payload.get("id") if isinstance(payload, dict) else None
                    incident = (
                        db.get(NiftySafetyIncident, incident_id)
                        if type(incident_id) is int
                        else None
                    )
                    if incident is None or incident.user_id != user_id:
                        raise ValueError("Notification incident identity is invalid")
                    # The incident supplies bounded codes; audit revision remains point-in-time.
                    revision = payload.get("revision")
                    if type(revision) is not int or not 1 <= revision <= incident.revision:
                        raise ValueError("Notification event revision is invalid")
                    envelope = {
                        "schema_version": 1,
                        "event_id": event.id,
                        "kind": event.kind,
                        "occurred_at": _instant(event.created_at),
                        "mode": incident.mode,
                        "code": incident.code,
                        "severity": incident.severity,
                        "incident_id": incident.id,
                        "revision": revision,
                    }
                    for destination in destinations:
                        db.add(
                            NiftyNotificationDelivery(
                                user_id=user_id,
                                event_id=event.id,
                                destination=destination,
                                envelope=envelope,
                                status="PENDING",
                                attempts=0,
                                next_at=now,
                                created_at=now,
                                updated_at=now,
                            )
                        )
                        count += 1
                cursor.event_id = event.id
            return count

    @staticmethod
    def _notification_fallback(db, row, now):
        if row.destination == "email_fallback" or row.envelope["severity"] != "CRITICAL":
            return
        existing = db.scalar(
            select(NiftyNotificationDelivery.id).where(
                NiftyNotificationDelivery.user_id == row.user_id,
                NiftyNotificationDelivery.event_id == row.event_id,
                NiftyNotificationDelivery.destination == "email_fallback",
            )
        )
        if existing is None:
            db.add(
                NiftyNotificationDelivery(
                    user_id=row.user_id,
                    event_id=row.event_id,
                    destination="email_fallback",
                    envelope=row.envelope,
                    status="PENDING",
                    attempts=0,
                    next_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.flush()

    def claim_notification(self, user_id, *, now, email_only=False):
        """Fence a single transport attempt. Expired dispatches cannot be replayed."""
        from sqlalchemy import case

        now = self._notification_time(now)
        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            expired = db.scalars(
                select(NiftyNotificationDelivery)
                .where(
                    NiftyNotificationDelivery.user_id == user_id,
                    NiftyNotificationDelivery.status == "DISPATCHING",
                    NiftyNotificationDelivery.claimed_until <= now,
                )
                .order_by(NiftyNotificationDelivery.id)
                .limit(100)
            ).all()
            for row in expired:
                row.status, row.updated_at = "AMBIGUOUS", now
                self._notification_fallback(db, row, now)
            db.flush()
            settings = db.get(NiftyDiscordSettings, user_id)
            rate_limited = bool(
                settings is not None
                and settings.rate_limit_until is not None
                and datetime.fromisoformat(_instant(settings.rate_limit_until)) > now
            )
            row = db.scalar(
                select(NiftyNotificationDelivery)
                .where(
                    NiftyNotificationDelivery.user_id == user_id,
                    NiftyNotificationDelivery.status.in_(("PENDING", "RETRY")),
                    NiftyNotificationDelivery.next_at <= now,
                    ~NiftyNotificationDelivery.destination.in_(
                        select(NiftyDiscordBucket.destination).where(
                            NiftyDiscordBucket.user_id == user_id,
                            NiftyDiscordBucket.blocked_until > now,
                        )
                    ),
                    NiftyNotificationDelivery.destination == "email_fallback"
                    if rate_limited or email_only
                    else True,
                )
                .order_by(
                    case(
                        (
                            NiftyNotificationDelivery.envelope["severity"].as_string()
                            == "CRITICAL",
                            0,
                        ),
                        else_=1,
                    ),
                    NiftyNotificationDelivery.id,
                )
                .limit(1)
            )
            if row is None:
                return None
            row.status = "DISPATCHING"
            row.attempts += 1
            row.claim_token = uuid4().hex
            row.claimed_until = now + timedelta(seconds=60)
            row.updated_at = now
            db.flush()
            return {**self._notification_dict(row), "claim_token": row.claim_token}

    def finish_notification(
        self, user_id, delivery_id, claim_token, outcome, *, now, retry_after=30
    ):
        """Only RETRY means a confirmed non-acceptance, never a network timeout."""
        now = self._notification_time(now)
        if (
            type(delivery_id) is not int
            or delivery_id < 1
            or not isinstance(claim_token, str)
            or not 1 <= len(claim_token) <= 32
            or outcome not in ("DELIVERED", "RETRY", "AMBIGUOUS", "DEAD")
            or type(retry_after) is not int
            or not 1 <= retry_after <= 86400
        ):
            raise ValueError("Invalid notification result")
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyNotificationDelivery, delivery_id)
            if row is None or row.user_id != user_id:
                raise LookupError("Notification not found")
            if row.status == "AMBIGUOUS":
                return False
            if row.status != "DISPATCHING" or row.claim_token != claim_token:
                raise ValueError("Notification claim is not current")
            if datetime.fromisoformat(_instant(row.claimed_until)) <= now:
                outcome = "AMBIGUOUS"
            row.status = "DEAD" if outcome == "RETRY" and row.attempts >= 5 else outcome
            row.updated_at = now
            if row.status == "RETRY":
                row.next_at = now + timedelta(seconds=retry_after)
            if row.status in ("DEAD", "AMBIGUOUS"):
                self._notification_fallback(db, row, now)
            return outcome != "AMBIGUOUS"

    # Trading mode ----------------------------------------------------------

    @staticmethod
    def _mode_dict(row):
        return {
            "mode": row.mode,
            "revision": row.revision,
            "history": list(row.history or []),
            "updated_at": _instant(row.updated_at),
        }

    @staticmethod
    def _mode_reasons(db, user_id):
        """A missing row is PAPER. Any other mode has no executor in this release."""
        row = db.get(NiftyMode, user_id)
        return [] if row is None or row.mode == "PAPER" else ["LIVE_NOT_READY"]

    @staticmethod
    def _exposure(db, user_id, now):
        """Open primary exposure: held positions and live pending intents. Shadows excluded."""
        from sqlalchemy import func

        positions = db.scalar(
            select(func.count()).select_from(NiftyPosition).where(NiftyPosition.user_id == user_id)
        )
        pending = db.scalar(
            select(func.count())
            .select_from(NiftyOrder)
            .where(
                NiftyOrder.user_id == user_id,
                NiftyOrder.status == "PENDING",
                NiftyOrder.expires_at > now,
            )
        )
        return {"positions": int(positions or 0), "pending_orders": int(pending or 0)}

    def open_exposure(self, user_id, now=None):
        with self.sessions() as db:
            return self._exposure(db, user_id, now or datetime.now(UTC))

    def trading_mode(self, user_id):
        """The user's mode row, created as PAPER for users that predate it."""
        self.ensure_user(user_id)
        with self.sessions() as db:
            row = db.get(NiftyMode, user_id)
            if row is not None:
                return self._mode_dict(row)
        try:
            with self.sessions.begin() as db:
                row = NiftyMode(
                    user_id=user_id,
                    mode="PAPER",
                    revision=1,
                    history=[],
                    updated_at=datetime.now(UTC),
                )
                db.add(row)
                db.flush()
                result = self._mode_dict(row)
        except IntegrityError:
            with self.sessions() as db:
                return self._mode_dict(db.get(NiftyMode, user_id))
        return result

    def change_mode(self, user_id, revision, requested, *, actor, evaluate, snapshot, now=None):
        """Compare-and-set mode change, decided once under the user lock.

        ``evaluate(exposure, current_mode)`` is a pure callable returning refusal
        codes. Live is refused here whatever it returns: no live executor exists.
        Returns ``(mode, codes, changed)``; a refusal is audited and changes nothing.
        """
        if requested not in ("PAPER", "LIVE"):
            raise ValueError("Unsupported trading mode")
        self.trading_mode(user_id)
        now = now or datetime.now(UTC)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyMode, user_id)
            if row.revision != revision:
                raise StateConflict("Trading mode changed. Reload before switching.")
            exposure = self._exposure(db, user_id, now)
            codes = list(dict.fromkeys(evaluate(exposure, row.mode)))
            if requested == "LIVE" and "LIVE_NOT_READY" not in codes:
                codes.append("LIVE_NOT_READY")
            previous = row.mode
            audit = {
                "previous": previous,
                "requested": requested,
                "actor": actor,
                "at": now.isoformat(),
                "revision": revision,
                "exposure": exposure,
                "readiness": snapshot,
            }
            if codes:
                db.add(
                    NiftyEvent(
                        user_id=user_id,
                        kind="mode_change_refused",
                        payload={**audit, "codes": codes},
                        created_at=now,
                    )
                )
                return self._mode_dict(row), codes, False
            if requested == previous:
                return self._mode_dict(row), [], False
            entry = {
                "at": now.isoformat(),
                "actor": actor,
                "previous": previous,
                "new": requested,
                "revision": revision + 1,
            }
            changed = db.execute(
                update(NiftyMode)
                .where(NiftyMode.user_id == user_id, NiftyMode.revision == revision)
                .values(
                    mode=requested,
                    revision=revision + 1,
                    history=[*(row.history or []), entry][-MODE_HISTORY_LIMIT:],
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                raise StateConflict("Trading mode changed. Reload before switching.")
            db.add(
                NiftyEvent(
                    user_id=user_id,
                    kind="mode_changed",
                    payload={**audit, "new": requested, "revision": revision + 1},
                    created_at=now,
                )
            )
        return self.trading_mode(user_id), [], True

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

    def reconciliation_issues(self, user_id, *, _session=None):
        """Check durable fill/position/cash invariants without inventing repairs.

        Historical quantities are aggregated in SQL; startup does not load an
        unbounded order/trade history into the long-lived application worker.
        """
        from sqlalchemy import and_, func, or_

        from services.nifty_algo.models import Instrument

        with self.sessions.begin() if _session is None else nullcontext(_session) as db:
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

    def admit_order(self, user_id, order, *, validate_entry=None):
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
                    # Paper entries only; a non-PAPER mode has no executor here.
                    reasons = self._mode_reasons(db, user_id) + self._safety_reasons(db, user_id)
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
                    if Decimal(order["payload"]["reserved_risk"]) > config.max_planned_loss:
                        reasons.append("PLANNED_LOSS_LIMIT")
                    # Phase 3b: loss cooldown and monthly locks, under the same lock.
                    reasons.extend(self._cooldown_reasons(db, user_id, local_day.isoformat()))
                    reasons.extend(
                        self._month_lock_reasons(db, user_id, order["created_at"], config)
                    )
                    if reasons:
                        raise OrderRefused(reasons)
                    if validate_entry is not None:
                        validate_entry()
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
        spot=None,
        atm_strike=None,
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
            if order.side == "BUY" and now.astimezone(ZoneInfo("Asia/Kolkata")).time().replace(
                tzinfo=None
            ) >= time(14, 45):
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
            if (
                instrument.token != order.token
                or instrument.symbol != order.symbol
                or instrument.exchange != "NFO"
                or instrument.kind not in ("CE", "PE")
            ):
                raise ValueError("Final execution instrument failed validation")
            if order.side == "BUY":
                try:
                    spot = Decimal(str(spot))
                except (TypeError, ValueError, ArithmeticError):
                    raise ValueError("Current spot required for entry fill") from None
                if not spot.is_finite() or spot <= 0:
                    raise ValueError("Current spot required for entry fill")
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
                from services.nifty_algo.contract_resolver import moneyness
                from services.nifty_algo.paper_executor import _charges

                stop_exit = (
                    Decimal(protection["initial_stop"])
                    - Decimal(order.payload["instrument"]["tick_size"]) * config.slippage_ticks
                )
                planned = (price - stop_exit) * quantity + fees
                planned += (
                    _charges("SELL", stop_exit, quantity, config) + config.planned_loss_buffer
                )
                target = Decimal(protection["target_price"])
                reward = (
                    (target - price) * quantity - fees - _charges("SELL", target, quantity, config)
                )
                if (
                    state.killed
                    or state.daily_locked
                    or state.state != "RUNNING"
                    or state.configuration_id != config.version_id
                ):
                    order.status, order.reason = "CANCELED", "ENTRIES_DISABLED"
                elif mode_reasons := self._mode_reasons(db, user_id):
                    order.status, order.reason = "REJECTED", mode_reasons[0]
                elif safety_reasons := self._safety_reasons(db, user_id):
                    order.status, order.reason = "REJECTED", safety_reasons[0]
                elif entry_locks := (
                    self._cooldown_reasons(db, user_id, now.astimezone(_IST).date().isoformat())
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
                elif stop_exit <= 0:
                    order.status, order.reason = "REJECTED", "STOP_PRICE_INVALID"
                elif (
                    spot is not None
                    # Selection-time ATM evidence must not override current spot.
                    # ``atm_strike`` is the caller's listed ATM for this same spot,
                    # recomputed from today's master; without it the strict
                    # spot-only rule applies.
                    and moneyness(instrument, spot, atm_strike) == "OTM"
                ):
                    order.status, order.reason = "REJECTED", "OTM_PROHIBITED"
                elif (
                    quote.bid is None
                    or quote.bid <= 0
                    or quote.bid >= quote.ask
                    or quote.bid_size < quantity
                    or (quote.ask - quote.bid) / quote.ask * 10000 > config.max_spread_bps
                    or quote.volume is None
                    or quote.volume < config.min_volume
                ):
                    order.status, order.reason = "REJECTED", "LIQUIDITY_LOST"
                elif planned > config.max_planned_loss:
                    order.status, order.reason = "REJECTED", "PLANNED_LOSS_LIMIT"
                elif planned > Decimal(order.payload["reserved_risk"]):
                    order.status, order.reason = "REJECTED", "FILL_RISK_BUDGET"
                elif reward < config.min_projected_net_reward:
                    order.status, order.reason = "REJECTED", "NET_REWARD_BELOW_MINIMUM"
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
                db.add(
                    NiftyEvent(
                        user_id=user_id,
                        kind="paper_fill_verified",
                        created_at=now,
                        payload={
                            "order_id": order.order_id,
                            "side": order.side,
                            "quantity": quantity,
                            "price": str(price),
                            "fees": str(fees),
                        },
                    )
                )
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
            valid = self._observable(quote, token, now, config, position.opened_at, previous)
            payload = dict(row.payload)
            if valid:
                previous_exit_reason = payload.get("exit_reason")
                previous_stop = Decimal(payload.get("stop_price", payload["initial_stop"]))
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
            events = payload.pop("new_events", [])
            for kind, event_payload in self._protection_transitions(row.payload, payload, events):
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

    @staticmethod
    def _observable(quote, token, now, config, opened_at, previous):
        """A fresh, ordered, executable bid observed after the position opened."""
        return (
            quote is not None
            and quote.token == token
            and quote.bid is not None
            and quote.bid_size > 0
            and quote.source_time <= quote.received_time <= now
            and 0 <= (now - quote.source_time).total_seconds() <= config.quote_max_age
            and quote.source_time >= datetime.fromisoformat(_instant(opened_at))
            and (previous is None or quote.source_time > datetime.fromisoformat(previous))
        )

    @staticmethod
    def _protection_transitions(before, after, events):
        """Protection events persisted once, on the observation that changes state."""
        if (
            after.get("trailing_stop") is not None
            and Decimal(after["stop_price"]) > Decimal(before["stop_price"])
            and (
                before.get("trailing_stop") is None
                or Decimal(after["trailing_stop"]) > Decimal(before["trailing_stop"])
            )
        ):
            yield (
                "trailing_stop_updated",
                {
                    "stop_before": before["stop_price"],
                    "stop_price": after["stop_price"],
                    "source_time": after.get("last_source_time"),
                },
            )
        for event in events:
            kind = event.get("kind")
            transitioned = (
                kind == "PROFIT_LOCK_ACTIVATED"
                and not before.get("profit_lock_active", False)
                and after.get("profit_lock_active", False)
            ) or (
                kind == "PROFIT_FLOOR_UNREPRESENTABLE"
                and before.get("exit_reason") != "PROFIT_FLOOR_UNREPRESENTABLE"
                and after.get("exit_reason") == "PROFIT_FLOOR_UNREPRESENTABLE"
            )
            if transitioned:
                yield kind, {key: value for key, value in event.items() if key != "kind"}

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

    def analytics_snapshot(self, user_id, start, end, *, limit=50, offset=0):
        """Bounded, read-only realized analytics; detail paging never changes totals."""
        if (
            not isinstance(start, datetime)
            or not isinstance(end, datetime)
            or start.utcoffset() is None
            or end.utcoffset() is None
            or not timedelta(0) < end - start <= timedelta(days=366)
            or type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or not 0 <= offset <= 5000
        ):
            raise ValueError("Invalid analytics period or pagination")
        start, end = start.astimezone(UTC), end.astimezone(UTC)
        entry, exit_order = aliased(NiftyOrder), aliased(NiftyOrder)
        with self.sessions() as db:
            # Owner-locked fill writers append immutable trades in commit order.
            # Fence later fills without taking a write lock or rolling the account day.
            watermark = (
                db.scalar(select(func.max(NiftyTrade.id)).where(NiftyTrade.user_id == user_id)) or 0
            )
            owner_rows = (NiftyTrade.user_id == user_id, NiftyTrade.id <= watermark)
            prior_net = db.scalar(
                select(func.sum(NiftyTrade.net)).where(*owner_rows, NiftyTrade.closed_at < start)
            ) or Decimal(0)
            rows = db.execute(
                select(NiftyTrade, entry, exit_order)
                .outerjoin(
                    entry,
                    and_(
                        entry.user_id == NiftyTrade.user_id,
                        entry.order_id == NiftyTrade.entry_order_id,
                    ),
                )
                .outerjoin(
                    exit_order,
                    and_(
                        exit_order.user_id == NiftyTrade.user_id,
                        exit_order.order_id == NiftyTrade.exit_order_id,
                    ),
                )
                .where(*owner_rows, NiftyTrade.closed_at >= start, NiftyTrade.closed_at < end)
                .order_by(NiftyTrade.closed_at, NiftyTrade.id)
                .limit(5001)
            ).all()
            if len(rows) > 5000:
                raise AnalyticsDataError("Analytics period exceeds 5000 fills; narrow the period")
            journal, details, entry_totals = [], [], {}
            for trade, entry_fill, exit_fill in rows:
                normalized, detail = fill_facts(trade, entry_fill, exit_fill)
                quantity, fees = entry_totals.get(entry_fill.order_id, (0, Decimal(0)))
                quantity += trade.quantity
                fees += trade.fees - exit_fill.fees
                if quantity > entry_fill.quantity or fees > entry_fill.fees:
                    raise AnalyticsDataError("Partial exits exceed persisted entry fill evidence")
                entry_totals[entry_fill.order_id] = quantity, fees
                journal.append(normalized)
                details.append(detail)
        opening = StrategyConfig().virtual_capital + prior_net
        try:
            metrics = analytics.performance(journal, opening)
        except (ValueError, TypeError, KeyError, ArithmeticError):
            raise AnalyticsDataError("Persisted paper fill evidence is inconsistent") from None
        return {
            "schema_version": 1,
            "mode": "PAPER",
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "timezone": "Asia/Kolkata",
            },
            "watermark": watermark,
            "opening_realized_equity": str(opening),
            "equity_basis": "SEED_PLUS_REALIZED_NET_NOT_MARK_TO_MARKET",
            "trade_scope": "ENTRIES_WITH_REALIZED_EXITS_IN_PERIOD",
            "marked_unrealized": {"value": None, "reason": "NO_PERSISTED_MARK_SERIES"},
            "metrics": metrics,
            "details": {
                "total": len(details),
                "limit": limit,
                "offset": offset,
                "items": list(reversed(details))[offset : offset + limit],
            },
        }

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
        profit = config.monthly_profit_target is not None and net >= config.monthly_profit_target
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
                value = next_eligible_session(user_id, date.fromisoformat(loss_session), store=self)
                if current is not None and value < today:
                    value = next_eligible_session(user_id, today - timedelta(days=1), store=self)
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
            row = db.get(NiftyMonth, (user_id, key)) or self._create_month(db, user_id, key, now)
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

    def cooldown_reasons(self, user_id, now):
        """Read-only cooldown refusals for ``now``'s IST session."""
        with self.sessions() as db:
            return self._cooldown_reasons(db, user_id, now.astimezone(_IST).date().isoformat())

    # Hypothetical shadow positions ---------------------------------------
    #
    # Shadows keep their own ledger in nifty_algo_shadow_position. They read
    # primary exposure and cooldowns but never write the primary account,
    # order, position, trade, month or cooldown tables.

    @staticmethod
    def _shadow_dict(row):
        if row is None:
            return None

        def amount(value):
            return None if value is None else str(value)

        return {
            "id": row.id,
            "shadow_key": row.shadow_key,
            "kind": row.kind,
            "status": row.status,
            "active": row.active_slot is not None,
            "additive": bool(row.additive),
            "decision_id": row.decision_id,
            "primary_entry_order_id": row.primary_entry_order_id,
            "token": row.token,
            "symbol": row.symbol,
            "instrument": row.instrument,
            "quantity": row.quantity,
            "entry_price": str(row.entry_price),
            "entry_fees": str(row.entry_fees),
            "protection": row.protection,
            "exit_price": amount(row.exit_price),
            "exit_fees": amount(row.exit_fees),
            "gross": amount(row.gross),
            "net": amount(row.net),
            "exit_reason": row.exit_reason,
            "valuation": row.valuation,
            "session": row.session,
            "opened_at": _instant(row.opened_at),
            "closed_at": None if row.closed_at is None else _instant(row.closed_at),
            "updated_at": _instant(row.updated_at),
        }

    @staticmethod
    def _active_shadow(db, user_id):
        return db.scalar(
            select(NiftyShadowPosition).where(
                NiftyShadowPosition.user_id == user_id,
                NiftyShadowPosition.active_slot == 1,
            )
        )

    @staticmethod
    def _shadow_event(db, user_id, shadow_id, kind, payload, now):
        db.add(
            NiftyShadowEvent(
                user_id=user_id, shadow_id=shadow_id, kind=kind, payload=payload, created_at=now
            )
        )

    def _shadow_by_key(self, user_id, key):
        with self.sessions() as db:
            return self._shadow_dict(
                db.scalar(
                    select(NiftyShadowPosition).where(
                        NiftyShadowPosition.user_id == user_id,
                        NiftyShadowPosition.shadow_key == key,
                    )
                )
            )

    def active_shadow(self, user_id):
        with self.sessions() as db:
            return self._shadow_dict(self._active_shadow(db, user_id))

    def open_shadow(self, user_id, shadow, config):
        """Open one independent hypothetical position under the user lock.

        Returns ``(row, reasons)``. A repeated signal returns its original row.
        """
        now = shadow["opened_at"]
        local = now.astimezone(_IST)
        key = "independent:" + shadow["decision_id"]
        try:
            with self.sessions.begin() as db:
                self._lock(db, user_id)
                existing = db.scalar(
                    select(NiftyShadowPosition).where(
                        NiftyShadowPosition.user_id == user_id,
                        NiftyShadowPosition.shadow_key == key,
                    )
                )
                if existing is not None:
                    return self._shadow_dict(existing), []
                reasons = []
                if self._active_shadow(db, user_id) is not None:
                    reasons.append("SHADOW_ACTIVE")
                if (
                    db.scalar(
                        select(NiftyPosition.token).where(NiftyPosition.user_id == user_id).limit(1)
                    )
                    is not None
                ):
                    reasons.append("PRIMARY_ACTIVE")
                if (
                    db.scalar(
                        select(NiftyOrder.order_id)
                        .where(
                            NiftyOrder.user_id == user_id,
                            NiftyOrder.side == "BUY",
                            NiftyOrder.status == "PENDING",
                        )
                        .limit(1)
                    )
                    is not None
                ):
                    reasons.append("PRIMARY_PENDING")
                if not (
                    config.shadow_entry_after
                    <= local.time().replace(tzinfo=None)
                    < config.entry_before
                ):
                    reasons.append("SHADOW_ENTRY_WINDOW")
                reasons.extend(self._cooldown_reasons(db, user_id, local.date().isoformat()))
                if reasons:
                    return None, reasons
                row = NiftyShadowPosition(
                    user_id=user_id,
                    shadow_key=key,
                    kind="INDEPENDENT",
                    status="ACTIVE",
                    active_slot=1,
                    additive=1,
                    decision_id=shadow["decision_id"],
                    token=shadow["token"],
                    symbol=shadow["symbol"],
                    instrument=shadow["instrument"],
                    quantity=shadow["quantity"],
                    entry_price=Decimal(str(shadow["entry_price"])),
                    entry_fees=Decimal(str(shadow["entry_fees"])),
                    protection=shadow["protection"],
                    session=local.date().isoformat(),
                    opened_at=now,
                    updated_at=now,
                )
                db.add(row)
                db.flush()
                self._shadow_event(
                    db,
                    user_id,
                    row.id,
                    "SHADOW_OPENED",
                    {
                        "decision_id": row.decision_id,
                        "token": row.token,
                        "quantity": row.quantity,
                        "entry_price": str(row.entry_price),
                    },
                    now,
                )
                result = self._shadow_dict(row)
        except IntegrityError:
            existing = self._shadow_by_key(user_id, key)
            if existing is not None:
                return existing, []
            return None, ["SHADOW_ACTIVE"]
        return result, []

    def _close_shadow(self, db, row, bid, now, reason, valuation, config, status="CLOSED"):
        """End a hypothetical position at the modeled exit of ``bid``."""
        from services.nifty_algo.paper_executor import _charges
        from services.nifty_algo.protection import modeled_exit_net

        tick = Decimal(str(row.instrument["tick_size"]))
        entry_fees = Decimal(str(row.protection.get("entry_fees_remaining", row.entry_fees)))
        exit_fill = None if bid is None else Decimal(str(bid)) - tick * config.slippage_ticks
        if exit_fill is not None and exit_fill > 0:
            row.exit_price = exit_fill
            row.exit_fees = _charges("SELL", exit_fill, row.quantity, config)
            row.gross = (exit_fill - row.entry_price) * row.quantity
            row.net = modeled_exit_net(
                row.entry_price, row.quantity, bid, entry_fees, tick, config, _charges
            )
            row.valuation = valuation
        else:
            row.valuation = "UNAVAILABLE"
        row.status, row.active_slot, row.exit_reason = status, None, reason
        row.closed_at = row.updated_at = now
        self._shadow_event(
            db,
            row.user_id,
            row.id,
            "SHADOW_PREEMPTED" if status == "PREEMPTED_BY_ACTUAL_MIRROR" else "SHADOW_CLOSED",
            {
                "reason": reason,
                "valuation": row.valuation,
                "net": None if row.net is None else str(row.net),
                "primary_entry_order_id": row.primary_entry_order_id,
            },
            now,
        )

    def observe_shadow(
        self, user_id, shadow_id, quote, now, forced_reason=None, *, market_closed=False
    ):
        """Hypothetical exits through the primary protection evaluator.

        A latched exit closes on a fillable bid. After the session closes
        without one, the shadow ends at its last observed bid.
        """
        from services.nifty_algo.config import StrategyConfig
        from services.nifty_algo.paper_executor import _charges
        from services.nifty_algo.protection import observe_bid

        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyShadowPosition, shadow_id)
            if row is None or row.user_id != user_id:
                return None
            if row.active_slot is None or row.kind != "INDEPENDENT":
                return self._shadow_dict(row)
            config = StrategyConfig.model_validate(row.protection["configuration"])
            tick = Decimal(str(row.instrument["tick_size"]))
            previous = row.protection.get("last_source_time")
            valid = self._observable(quote, row.token, now, config, row.opened_at, previous)
            payload = dict(row.protection)
            if valid:
                previous_stop = Decimal(payload.get("stop_price", payload["initial_stop"]))
                payload = observe_bid(
                    payload,
                    row.entry_price,
                    quote.bid,
                    tick,
                    config,
                    quantity=row.quantity,
                    entry_fees=payload.get("entry_fees_remaining", "0"),
                    charges=_charges,
                    bid_size=quote.bid_size,
                    source_time=quote.source_time,
                )
                payload["last_source_time"] = quote.source_time.isoformat()
                payload["last_bid"] = str(quote.bid)
                payload["last_bid_size"] = quote.bid_size
                if Decimal(payload["stop_price"]) < previous_stop:
                    raise ValueError("Shadow protection stop cannot decrease")
            if forced_reason and not payload.get("exit_reason"):
                payload["exit_reason"] = forced_reason
            events = payload.pop("new_events", [])
            for kind, event_payload in self._protection_transitions(
                row.protection, payload, events
            ):
                self._shadow_event(
                    db, user_id, row.id, kind, {"token": row.token, **event_payload}, now
                )
            row.protection = payload
            row.updated_at = now
            reason = payload.get("exit_reason")
            if reason:
                if (
                    valid
                    and quote.bid_size >= row.quantity
                    and quote.bid - tick * config.slippage_ticks > 0
                ):
                    self._close_shadow(db, row, quote.bid, now, reason, "DEPTH_MODEL", config)
                elif market_closed:
                    self._close_shadow(
                        db, row, payload.get("last_bid"), now, reason, "LAST_BID", config
                    )
            return self._shadow_dict(row)

    def sync_shadow_mirrors(self, user_id, now):
        """Follow the authoritative primary position.

        A primary fill ends an active independent shadow as
        ``PREEMPTED_BY_ACTUAL_MIRROR`` and opens a non-additive mirror linked
        by the primary entry order id. The mirror closes from the primary
        trade journal once the primary is flat.
        """
        from services.nifty_algo.config import StrategyConfig

        with self.sessions() as db:
            held = db.scalar(
                select(NiftyPosition.entry_order_id)
                .where(NiftyPosition.user_id == user_id)
                .limit(1)
            )
            active = self._active_shadow(db, user_id)
            wanted = None if held is None else "mirror:" + held
            if wanted is None and (active is None or active.kind != "MIRROR"):
                return None
            if active is not None and active.shadow_key == wanted:
                return None
            if (
                active is None
                and db.scalar(
                    select(NiftyShadowPosition.id).where(
                        NiftyShadowPosition.user_id == user_id,
                        NiftyShadowPosition.shadow_key == wanted,
                    )
                )
                is not None
            ):
                return None
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            position = db.scalar(
                select(NiftyPosition).where(NiftyPosition.user_id == user_id).limit(1)
            )
            active = self._active_shadow(db, user_id)
            if (
                active is not None
                and active.kind == "MIRROR"
                and (position is None or active.primary_entry_order_id != position.entry_order_id)
            ):
                self._close_mirror(db, active, now)
                active = None
            if position is None:
                return None
            key = "mirror:" + position.entry_order_id
            if active is not None and active.shadow_key == key:
                return self._shadow_dict(active)
            if (
                db.scalar(
                    select(NiftyShadowPosition.id).where(
                        NiftyShadowPosition.user_id == user_id,
                        NiftyShadowPosition.shadow_key == key,
                    )
                )
                is not None
            ):
                return None
            if active is not None:
                active.primary_entry_order_id = position.entry_order_id
                self._close_shadow(
                    db,
                    active,
                    active.protection.get("last_bid"),
                    now,
                    "PREEMPTED_BY_ACTUAL_MIRROR",
                    "LAST_BID",
                    StrategyConfig.model_validate(active.protection["configuration"]),
                    status="PREEMPTED_BY_ACTUAL_MIRROR",
                )
                db.flush()  # Release the active slot before the mirror claims it.
            entry = db.get(NiftyOrder, (user_id, position.entry_order_id))
            protection = db.get(NiftyProtection, (user_id, position.token))
            opened = datetime.fromisoformat(_instant(position.opened_at))
            mirror = NiftyShadowPosition(
                user_id=user_id,
                shadow_key=key,
                kind="MIRROR",
                status="ACTIVE",
                active_slot=1,
                additive=0,
                decision_id=(entry.payload.get("decision_id") if entry is not None else None),
                primary_entry_order_id=position.entry_order_id,
                token=position.token,
                symbol=position.symbol,
                instrument=position.instrument,
                quantity=entry.quantity if entry is not None else position.quantity,
                entry_price=position.entry_price,
                entry_fees=(
                    Decimal(str(entry.fees))
                    if entry is not None and entry.fees is not None
                    else Decimal("0")
                ),
                protection=dict(protection.payload) if protection is not None else {},
                session=opened.astimezone(_IST).date().isoformat(),
                opened_at=opened,
                updated_at=now,
            )
            db.add(mirror)
            db.flush()
            self._shadow_event(
                db,
                user_id,
                mirror.id,
                "SHADOW_MIRROR_OPENED",
                {
                    "primary_entry_order_id": position.entry_order_id,
                    "preempted_shadow_id": None if active is None else active.id,
                    "additive": False,
                },
                now,
            )
            return self._shadow_dict(mirror)

    def _close_mirror(self, db, mirror, now):
        trades = list(
            db.scalars(
                select(NiftyTrade)
                .where(
                    NiftyTrade.user_id == mirror.user_id,
                    NiftyTrade.entry_order_id == mirror.primary_entry_order_id,
                )
                .order_by(NiftyTrade.closed_at, NiftyTrade.id)
            )
        )
        if trades:
            last = trades[-1]
            fees = sum((Decimal(str(trade.fees)) for trade in trades), Decimal("0"))
            mirror.gross = sum((Decimal(str(trade.gross)) for trade in trades), Decimal("0"))
            mirror.net = sum((Decimal(str(trade.net)) for trade in trades), Decimal("0"))
            mirror.exit_fees = fees - Decimal(str(mirror.entry_fees))
            mirror.exit_price = last.exit_price
            mirror.exit_reason = last.reason
            mirror.valuation = "PRIMARY_JOURNAL"
            mirror.closed_at = last.closed_at
            exit_order = db.get(NiftyOrder, (mirror.user_id, last.exit_order_id))
            if exit_order is not None and exit_order.payload.get("protection"):
                mirror.protection = exit_order.payload["protection"]
        else:
            mirror.exit_reason = "PRIMARY_CLOSED"
            mirror.valuation = "UNAVAILABLE"
            mirror.closed_at = now
        mirror.status, mirror.active_slot, mirror.updated_at = "CLOSED", None, now
        self._shadow_event(
            db,
            mirror.user_id,
            mirror.id,
            "SHADOW_MIRROR_CLOSED",
            {
                "primary_entry_order_id": mirror.primary_entry_order_id,
                "net": None if mirror.net is None else str(mirror.net),
                "additive": False,
            },
            now,
        )

    def shadow_ledger(self, user_id):
        """Hypothetical ledger: only independent (additive) shadow P&L compounds."""
        from sqlalchemy import func

        state = self.read(user_id)
        capital = Decimal(str(state["configuration"].get("virtual_capital", "20000")))
        with self.sessions() as db:
            totals = dict(
                db.execute(
                    select(NiftyShadowPosition.additive, func.sum(NiftyShadowPosition.net))
                    .where(
                        NiftyShadowPosition.user_id == user_id,
                        NiftyShadowPosition.net.is_not(None),
                    )
                    .group_by(NiftyShadowPosition.additive)
                ).all()
            )
        realized = Decimal(str(totals.get(1) or 0))
        return {
            "capital": str(capital),
            "realized_net": str(realized),
            "equity": str(capital + realized),
            "mirror_realized_net": str(Decimal(str(totals.get(0) or 0))),
            "mirror_additive": False,
            "basis": "HYPOTHETICAL_INDEPENDENT_SHADOWS_ONLY",
        }

    def shadow_status(self, user_id, limit=50):
        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyShadowPosition)
                .where(NiftyShadowPosition.user_id == user_id)
                .order_by(NiftyShadowPosition.id.desc())
                .limit(limit)
            )
            positions = [self._shadow_dict(row) for row in rows]
            events = [
                {
                    "id": row.id,
                    "shadow_id": row.shadow_id,
                    "kind": row.kind,
                    "payload": row.payload,
                    "created_at": _instant(row.created_at),
                }
                for row in db.scalars(
                    select(NiftyShadowEvent)
                    .where(NiftyShadowEvent.user_id == user_id)
                    .order_by(NiftyShadowEvent.id.desc())
                    .limit(limit)
                )
            ]
        return {
            "mode": "HYPOTHETICAL",
            "active": next((row for row in positions if row["active"]), None),
            "positions": positions,
            "events": events,
            "ledger": self.shadow_ledger(user_id),
        }

    # Research observations -------------------------------------------------

    @staticmethod
    def _recording_dict(row, capture=None):
        if row is None:
            return None
        return {
            "id": row.id,
            "mode": "RESEARCH",
            "schema_version": 1,
            "status": "SEALED" if row.status == "ARCHIVED" else row.status,
            "starts_at": _instant(row.starts_at),
            "ends_at": _instant(row.ends_at),
            "last_available_at": _instant(row.last_available_at) if row.last_available_at else None,
            "count": row.count,
            "size_bytes": row.size_bytes,
            "max_observations": row.max_observations,
            "configuration_id": row.configuration_id,
            "configuration": row.configuration,
            "content_sha256": row.content_sha256,
            "sealed_at": _instant(row.sealed_at) if row.sealed_at else None,
            "execution_eligible": False,
            "limitations": ["QUOTE_EVIDENCE_ONLY", "PROVENANCE_NOT_AUTHENTICATED"],
            "capture": (
                {"scope": capture.payload, "scope_sha256": capture.sha256}
                if capture is not None
                else None
            ),
        }

    def recordings(self, user_id):
        """Read the owner's bounded manifests without creating trading state."""
        with self.sessions() as db:
            rows = db.execute(
                select(NiftyResearchRecording, NiftyResearchCapture)
                .outerjoin(
                    NiftyResearchCapture,
                    and_(
                        NiftyResearchCapture.user_id == NiftyResearchRecording.user_id,
                        NiftyResearchCapture.recording_id == NiftyResearchRecording.id,
                    ),
                )
                .where(
                    NiftyResearchRecording.user_id == user_id,
                    NiftyResearchRecording.status != "ARCHIVED",
                )
                .order_by(NiftyResearchRecording.starts_at.desc(), NiftyResearchRecording.id)
                .limit(20)
            ).all()
            return [self._recording_dict(row, capture) for row, capture in rows]

    def create_recording(
        self, user_id, starts_at, ends_at, now, *, max_observations=10000, native_capture=False
    ):
        """Create explicit research storage with a fixed window and configuration."""
        if (
            any(
                not isinstance(at, datetime) or at.tzinfo is None
                for at in (starts_at, ends_at, now)
            )
            or not starts_at <= now < ends_at
            or ends_at - starts_at > timedelta(days=1)
            or type(max_observations) is not int
            or not 1 <= max_observations <= 10000
            or type(native_capture) is not bool
        ):
            raise ValueError("Invalid recording window or observation limit")
        starts_at, ends_at = starts_at.astimezone(UTC), ends_at.astimezone(UTC)
        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            total = db.scalar(
                select(func.count())
                .select_from(NiftyResearchRecording)
                .where(
                    NiftyResearchRecording.user_id == user_id,
                    NiftyResearchRecording.status != "ARCHIVED",
                )
            )
            if total >= 20:
                raise ValueError("Recording quota reached; evidence is not automatically deleted")
            catalogue = db.scalar(
                select(func.count())
                .select_from(NiftyResearchRecording)
                .where(NiftyResearchRecording.user_id == user_id)
            )
            if catalogue >= 1000:
                raise ValueError(
                    "Archive catalogue quota reached; preserve and review existing evidence"
                )
            state = db.get(NiftyState, user_id)
            configuration = StrategyConfig.model_validate(state.configuration).model_dump(
                mode="json"
            )
            context = {
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
                "configuration": configuration,
                "schema_version": 1,
            }
            if native_capture:
                context["capture"] = "NATIVE_FEED"
            row = NiftyResearchRecording(
                user_id=user_id,
                id=uuid4().hex,
                status="RECORDING",
                starts_at=starts_at,
                ends_at=ends_at,
                count=0,
                size_bytes=0,
                max_observations=max_observations,
                configuration=configuration,
                configuration_id=state.configuration_id,
                content_sha256=sha256_bytes(
                    dumps(context, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            )
            db.add(row)
            capture = None
            if native_capture:
                capture = NiftyResearchCapture(user_id=user_id, recording_id=row.id)
                db.add(capture)
            result = self._recording_dict(row, capture)
        return result

    @staticmethod
    def _recording_runner(db, user_id, owner, now):
        lease = db.get(NiftyRunnerLease, user_id)
        if (
            not isinstance(owner, str)
            or not owner
            or lease is None
            or lease.owner != owner
            or datetime.fromisoformat(_instant(lease.expires_at)) <= now
        ):
            raise StateConflict("Research capture runner no longer owns the lease")

    def freeze_recording_scope(
        self, user_id, recording_id, now, *, instruments, broker, runner_owner
    ):
        """Bind a native opt-in recording to server-derived metadata before evidence."""
        from services.nifty_algo.research import recording_scope

        scope = recording_scope(instruments, broker, now)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            self._recording_runner(db, user_id, runner_owner, now)
            row = db.get(NiftyResearchRecording, (user_id, recording_id))
            capture = db.get(NiftyResearchCapture, (user_id, recording_id))
            if row is None:
                raise ValueError("Recording not found")
            if (
                capture is None
                or row.status != "RECORDING"
                or not datetime.fromisoformat(_instant(row.starts_at))
                <= now
                < datetime.fromisoformat(_instant(row.ends_at))
            ):
                raise StateConflict("Recording is not available for native capture")
            if capture.payload is not None:
                if (
                    capture.payload["broker"] != scope["broker"]
                    or capture.payload["instruments"] != scope["instruments"]
                ):
                    raise StateConflict("Native recording scope is immutable")
                return self._recording_dict(row, capture)
            if row.count:
                raise StateConflict("Native scope must precede observations")
            capture.payload = scope
            capture.sha256 = sha256_bytes(
                dumps(scope, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            row.content_sha256 = sha256_bytes(
                (row.content_sha256 + capture.sha256).encode("ascii")
            ).hexdigest()
            return self._recording_dict(row, capture)

    def append_recording(
        self,
        user_id,
        recording_id,
        observations,
        now,
        *,
        expected_count,
        deduplicate_samples=False,
        runner_owner=None,
    ):
        """Append atomically in availability order, fenced by the durable row count."""
        from services.nifty_algo.research import recording_batch

        batch = recording_batch(observations, now)
        if type(expected_count) is not int or expected_count < 0:
            raise ValueError("Invalid recording cursor")
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            if runner_owner is not None:
                self._recording_runner(db, user_id, runner_owner, now)
            row = db.get(NiftyResearchRecording, (user_id, recording_id))
            if row is None:
                raise ValueError("Recording not found")
            if row.status != "RECORDING" or row.count != expected_count:
                raise StateConflict("Recording is sealed or the append cursor changed")
            capture = db.get(NiftyResearchCapture, (user_id, recording_id))
            if capture is not None:
                if runner_owner is None or capture.payload is None:
                    raise StateConflict("Native recording requires a frozen scope and runner")
                tokens = {item["token"] for item in capture.payload["instruments"]}
                frozen_at = datetime.fromisoformat(capture.payload["frozen_at"])
                if any(
                    item["source"] != "NATIVE_FEED"
                    or (
                        item["kind"] in ("QUOTE", "LEDGER")
                        and item["payload"]["token"] not in tokens
                    )
                    or (
                        item["kind"] == "FRAME"
                        and not {i["token"] for i in item["payload"]["instruments"]} <= tokens
                    )
                    or datetime.fromisoformat(item["source_time"]) < frozen_at
                    for item in batch
                ):
                    raise ValueError("Observation is outside frozen native scope")
            if deduplicate_samples:
                identities = [
                    sha256_bytes(
                        dumps(item["payload"], sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest()
                    for item in batch
                ]
                seen = set(
                    db.scalars(
                        select(NiftyResearchSample.sha256).where(
                            NiftyResearchSample.user_id == user_id,
                            NiftyResearchSample.recording_id == recording_id,
                            NiftyResearchSample.sha256.in_(identities),
                        )
                    ).all()
                )
                unseen = []
                for identity, item in zip(identities, batch, strict=True):
                    if identity not in seen:
                        seen.add(identity)
                        unseen.append(item)
                        db.add(
                            NiftyResearchSample(
                                user_id=user_id,
                                recording_id=recording_id,
                                sha256=identity,
                            )
                        )
                batch = unseen
                if not batch:
                    return self._recording_dict(row, capture)
            encoded_size = sum(
                len(dumps(item, sort_keys=True, separators=(",", ":")).encode()) for item in batch
            )
            duplicate = db.scalar(
                select(NiftyResearchObservation.sequence)
                .where(
                    NiftyResearchObservation.user_id == user_id,
                    NiftyResearchObservation.recording_id == recording_id,
                    NiftyResearchObservation.sha256.in_([item["sha256"] for item in batch]),
                )
                .limit(1)
            )
            if duplicate is not None:
                raise ValueError("Duplicate point-in-time quote evidence")
            start = datetime.fromisoformat(_instant(row.starts_at))
            end = datetime.fromisoformat(_instant(row.ends_at))
            previous = (
                datetime.fromisoformat(_instant(row.last_available_at))
                if row.last_available_at
                else start
            )
            if (
                row.count + len(batch) > row.max_observations
                or row.size_bytes + encoded_size > 16777216
                or datetime.fromisoformat(batch[0]["available_at"]) < previous
                or any(
                    not start
                    <= datetime.fromisoformat(item["source_time"])
                    <= datetime.fromisoformat(item["available_at"])
                    <= end
                    for item in batch
                )
            ):
                raise ValueError("Recording bounds or chronology violated")
            digest = row.content_sha256
            for sequence, item in enumerate(batch, start=row.count + 1):
                db.add(
                    NiftyResearchObservation(
                        user_id=user_id,
                        recording_id=recording_id,
                        sequence=sequence,
                        sha256=item["sha256"],
                        available_at=datetime.fromisoformat(item["available_at"]),
                        payload=item,
                    )
                )
                digest = sha256_bytes((digest + item["sha256"]).encode("ascii")).hexdigest()
            row.count = expected_count + len(batch)
            row.size_bytes += encoded_size
            row.last_available_at = datetime.fromisoformat(batch[-1]["available_at"])
            row.content_sha256 = digest
            result = self._recording_dict(row, capture)
        return result

    def seal_recording(self, user_id, recording_id, now, *, expected_count):
        """Freeze evidence; sealing never claims completeness or execution readiness."""
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or type(expected_count) is not int
            or expected_count < 0
        ):
            raise ValueError("Invalid seal time or recording cursor")
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyResearchRecording, (user_id, recording_id))
            if row is None:
                raise ValueError("Recording not found")
            if row.count != expected_count:
                raise StateConflict("Recording cursor changed")
            if now < datetime.fromisoformat(_instant(row.last_available_at or row.starts_at)):
                raise ValueError("Seal time predates evidence")
            if row.status == "RECORDING":
                row.status, row.sealed_at = "SEALED", now.astimezone(UTC)
            result = self._recording_dict(
                row, db.get(NiftyResearchCapture, (user_id, recording_id))
            )
        return result

    def recording_page(self, user_id, recording_id, *, after=0, limit=100, as_of=None):
        """Bounded owner-scoped evidence page; an as-of cursor never reveals future arrivals."""
        if (
            type(after) is not int
            or not 0 <= after <= 10000
            or type(limit) is not int
            or not 1 <= limit <= 100
            or (as_of is not None and (not isinstance(as_of, datetime) or as_of.tzinfo is None))
        ):
            raise ValueError("Invalid recording page")
        if as_of is not None:
            try:
                as_of = as_of.astimezone(UTC)
            except (OverflowError, ValueError):
                raise ValueError("Invalid recording page") from None
        archive = self.load_archived_recording(user_id, recording_id)
        if archive is not None:
            rows = [
                r
                for r in archive["items"]
                if r["sequence"] > after
                and (as_of is None or datetime.fromisoformat(r["available_at"]) <= as_of)
            ][:limit]
            return {
                "manifest": archive["manifest"],
                "items": rows,
                "next_after": rows[-1]["sequence"] if rows else after,
            }
        with self.sessions() as db:
            row = db.get(NiftyResearchRecording, (user_id, recording_id))
            if row is None:
                return None
            query = select(NiftyResearchObservation).where(
                NiftyResearchObservation.user_id == user_id,
                NiftyResearchObservation.recording_id == recording_id,
                NiftyResearchObservation.sequence > after,
                NiftyResearchObservation.sequence <= row.count,
            )
            if as_of is not None:
                query = query.where(NiftyResearchObservation.available_at <= as_of)
            items = db.scalars(query.order_by(NiftyResearchObservation.sequence).limit(limit)).all()
            return {
                "manifest": self._recording_dict(
                    row, db.get(NiftyResearchCapture, (user_id, recording_id))
                ),
                "items": [{"sequence": item.sequence, **item.payload} for item in items],
                "next_after": items[-1].sequence if items else after,
            }

    @staticmethod
    def _experiment_dict(row):
        if row is None:
            return None
        encoded = dumps(row.snapshot, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) > 1048576 or sha256_bytes(encoded).hexdigest() != row.sha256:
            raise ValueError("Experiment snapshot integrity failed")
        return {
            "id": row.id,
            "mode": "RESEARCH",
            "status": "DEFINED",
            "created_at": _instant(row.created_at),
            "snapshot": deepcopy(row.snapshot),
            "sha256": row.sha256,
            "execution_eligible": False,
            "performance": None,
            "limitations": [
                "DEFINITION_ONLY",
                "EXECUTION_REQUIRES_VALIDATED_EVIDENCE",
                "PROVENANCE_NOT_AUTHENTICATED",
            ]
            if row.snapshot.get("schema_version") == 2
            else [
                "DEFINITION_ONLY",
                "QUOTE_EVIDENCE_ONLY",
                "PROVENANCE_NOT_AUTHENTICATED",
                "OPTION_REPLAY_UNAVAILABLE",
            ],
        }

    def create_experiment(
        self,
        user_id,
        recording_id,
        now,
        *,
        expected_count,
        expected_sha256,
        configuration,
        train_end,
        validation_end,
    ):
        """Validate existing evidence, then persist a bounded immutable definition."""
        manifest = recording_cursor(
            self,
            user_id,
            recording_id,
            expected_count=expected_count,
            expected_sha256=expected_sha256,
        ).manifest
        snapshot = experiment_snapshot(
            manifest,
            configuration,
            train_end=train_end,
            validation_end=validation_end,
            now=now,
        )
        digest = sha256_bytes(
            dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            source = db.get(NiftyResearchRecording, (user_id, recording_id))
            current = self._recording_dict(
                source, db.get(NiftyResearchCapture, (user_id, recording_id))
            )
            if current != manifest:
                raise StateConflict("Recording changed before experiment creation")
            total = db.scalar(
                select(func.count())
                .select_from(NiftyResearchExperiment)
                .where(NiftyResearchExperiment.user_id == user_id)
            )
            if total >= 50:
                raise ValueError("Experiment quota reached; definitions are not deleted")
            row = NiftyResearchExperiment(
                user_id=user_id,
                id=uuid4().hex,
                created_at=now.astimezone(UTC),
                snapshot=snapshot,
                sha256=digest,
            )
            db.add(row)
            result = self._experiment_dict(row)
        return result

    def experiment(self, user_id, experiment_id):
        """Read without creating a user, account, runner lease or transaction write."""
        with self.sessions() as db:
            return self._experiment_dict(db.get(NiftyResearchExperiment, (user_id, experiment_id)))

    def experiments(self, user_id):
        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyResearchExperiment)
                .where(NiftyResearchExperiment.user_id == user_id)
                .order_by(NiftyResearchExperiment.created_at.desc(), NiftyResearchExperiment.id)
                .limit(50)
            ).all()
            return [self._experiment_dict(row) for row in rows]

    def experiment_summaries(self, user_id):
        """List bounded identities without loading full dataset/configuration snapshots."""
        with self.sessions() as db:
            rows = db.execute(
                select(
                    NiftyResearchExperiment.id,
                    NiftyResearchExperiment.sha256,
                    NiftyResearchExperiment.created_at,
                    NiftyResearchExperiment.snapshot["schema_version"]
                    .as_integer()
                    .label("schema_version"),
                )
                .where(NiftyResearchExperiment.user_id == user_id)
                .order_by(NiftyResearchExperiment.created_at.desc(), NiftyResearchExperiment.id)
                .limit(50)
            ).all()
            return [
                {
                    "id": row.id,
                    "sha256": row.sha256,
                    "created_at": _instant(row.created_at),
                    "status": "DEFINED",
                    "execution_eligible": False,
                    "execution_bundle": row.schema_version == 2,
                }
                for row in rows
            ]

    @staticmethod
    def _opportunity_columns(row, payload, now):
        row.payload = payload
        row.status = payload["status"]
        row.outcome = payload.get("outcome")
        row.updated_at = now
        row.closed_at = (
            datetime.fromisoformat(payload["closed_at"]) if payload.get("closed_at") else None
        )

    def record_opportunity(self, user_id, opportunity, now):
        """Idempotent: a repeated candle, side and configuration keeps the first row."""
        key = (user_id, opportunity["opportunity_id"])
        try:
            with self.sessions.begin() as db:
                existing = db.get(NiftyOpportunity, key)
                if existing is not None:
                    return dict(existing.payload), False
                row = NiftyOpportunity(
                    user_id=user_id,
                    opportunity_id=opportunity["opportunity_id"],
                    candle_end=datetime.fromisoformat(opportunity["candle_end"]),
                    direction=opportunity["direction"],
                    configuration_id=opportunity["configuration_id"],
                    decision_id=opportunity.get("decision_id"),
                    deadline=datetime.fromisoformat(opportunity["deadline"]),
                    created_at=now,
                )
                self._opportunity_columns(row, opportunity, now)
                db.add(row)
        except IntegrityError:
            with self.sessions() as db:
                existing = db.get(NiftyOpportunity, key)
                if existing is None:
                    raise
                return dict(existing.payload), False
        return opportunity, True

    def observe_opportunities(self, user_id, observation, now):
        """Apply one completed-candle observation, then stop rows past deadline."""
        from services.nifty_algo.research import expire_opportunity, observe_opportunity

        changed = []
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            rows = db.scalars(
                select(NiftyOpportunity).where(
                    NiftyOpportunity.user_id == user_id,
                    NiftyOpportunity.status == "OBSERVING",
                )
            ).all()
            for row in rows:
                payload = dict(row.payload)
                if observation is not None:
                    payload = observe_opportunity(payload, observation)
                payload = expire_opportunity(payload, now)
                if payload != row.payload:
                    self._opportunity_columns(row, payload, now)
                    changed.append(payload)
        return changed

    def expire_opportunities(self, user_id, now):
        from sqlalchemy import func

        with self.sessions() as db:
            due = db.scalar(
                select(func.count())
                .select_from(NiftyOpportunity)
                .where(
                    NiftyOpportunity.user_id == user_id,
                    NiftyOpportunity.status == "OBSERVING",
                    NiftyOpportunity.deadline <= now,
                )
            )
        return self.observe_opportunities(user_id, None, now) if due else []

    def opportunities(self, user_id, limit=100):
        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyOpportunity)
                .where(NiftyOpportunity.user_id == user_id)
                .order_by(NiftyOpportunity.candle_end.desc())
                .limit(limit)
            )
            return [dict(row.payload) for row in rows]

    # Reports ---------------------------------------------------------------
    #
    # Read-only over feature data. One row per (user, kind, period); generation
    # and delivery advance only by compare-and-set updates, so two ticks or a
    # restart can neither generate a second row nor send a report twice.

    @staticmethod
    def _report_dict(row):
        def at(value):
            return None if value is None else _instant(value)

        return {
            "id": row.id,
            "kind": row.kind,
            "variant": row.variant,
            "period_key": row.period_key,
            "path": row.path,
            "filename": Path(row.path).name if row.path else None,
            "sha256": row.sha256,
            "size_bytes": row.size_bytes,
            "generation_status": row.generation_status,
            "generation_attempts": row.generation_attempts,
            "generation_error_type": row.generation_error_type,
            "delivery_status": row.delivery_status,
            "attempts": row.attempts,
            "next_attempt_at": at(row.next_attempt_at),
            "last_error_type": row.last_error_type,
            "claim_token": row.claim_token,
            "claimed_until": at(row.claimed_until),
            "summary": dict(row.summary or {}),
            "generated_at": at(row.generated_at),
            "sent_at": at(row.sent_at),
            "created_at": at(row.created_at),
            "updated_at": at(row.updated_at),
        }

    @staticmethod
    def _report_where(user_id, report_id):
        return (NiftyReport.user_id == user_id, NiftyReport.id == int(report_id))

    def ensure_report(self, user_id, kind, period_key, now):
        """Create the period's row once. Returns ``(row, created)``."""

        def existing(db):
            return db.scalar(
                select(NiftyReport).where(
                    NiftyReport.user_id == user_id,
                    NiftyReport.kind == kind,
                    NiftyReport.period_key == period_key,
                )
            )

        try:
            with self.sessions.begin() as db:
                row = existing(db)
                if row is not None:
                    return self._report_dict(row), False
                row = NiftyReport(
                    user_id=user_id,
                    kind=kind,
                    variant="STANDARD",
                    period_key=period_key,
                    generation_status="PENDING",
                    generation_attempts=0,
                    delivery_status="PENDING",
                    attempts=0,
                    summary={},
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
                db.flush()
                result = self._report_dict(row)
        except IntegrityError:
            with self.sessions() as db:
                row = existing(db)
                if row is None:
                    raise
                return self._report_dict(row), False
        return result, True

    def reports(self, user_id, limit=100, offset=0):
        """Bounded user-owned report history; 1-based display pages via offset."""
        if not isinstance(limit, int) or not 1 <= limit <= 400:
            raise ValueError("Report page size must be 1..400")
        if not isinstance(offset, int) or not 0 <= offset <= 1000000:
            raise ValueError("Report offset must be 0..1000000")
        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyReport)
                .where(NiftyReport.user_id == user_id)
                .order_by(NiftyReport.created_at.desc(), NiftyReport.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return [self._report_dict(row) for row in rows]

    def report(self, user_id, report_id):
        with self.sessions() as db:
            row = db.scalar(select(NiftyReport).where(*self._report_where(user_id, report_id)))
            return None if row is None else self._report_dict(row)

    def reports_needing_generation(self, user_id, max_attempts):
        from sqlalchemy import or_

        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyReport)
                .where(
                    NiftyReport.user_id == user_id,
                    or_(
                        NiftyReport.generation_status == "PENDING",
                        NiftyReport.generation_status == "FAILED",
                    ),
                    NiftyReport.generation_attempts < max_attempts,
                )
                .order_by(NiftyReport.id)
            )
            return [self._report_dict(row) for row in rows]

    def complete_report_generation(
        self, user_id, report_id, *, path, sha256, size_bytes, variant, summary, now
    ):
        with self.sessions.begin() as db:
            changed = db.execute(
                update(NiftyReport)
                .where(
                    *self._report_where(user_id, report_id),
                    NiftyReport.generation_status != "GENERATED",
                )
                .values(
                    generation_status="GENERATED",
                    generation_attempts=NiftyReport.generation_attempts + 1,
                    generation_error_type=None,
                    path=path,
                    sha256=sha256,
                    size_bytes=size_bytes,
                    variant=variant,
                    summary=summary,
                    generated_at=now,
                    updated_at=now,
                )
            )
            if changed.rowcount == 1:
                row = db.scalar(select(NiftyReport).where(*self._report_where(user_id, report_id)))
                db.add(
                    NiftyEvent(
                        user_id=user_id,
                        kind="report_generated",
                        payload={
                            "report_id": row.id,
                            "kind": row.kind,
                            "variant": variant,
                            "period_key": row.period_key,
                            "sha256": sha256,
                        },
                        created_at=now,
                    )
                )
            return changed.rowcount == 1

    def fail_report_generation(self, user_id, report_id, error_type, now):
        with self.sessions.begin() as db:
            db.execute(
                update(NiftyReport)
                .where(
                    *self._report_where(user_id, report_id),
                    NiftyReport.generation_status != "GENERATED",
                )
                .values(
                    generation_status="FAILED",
                    generation_attempts=NiftyReport.generation_attempts + 1,
                    generation_error_type=str(error_type)[:64],
                    updated_at=now,
                )
            )

    def deliverable_reports(self, user_id, now, max_attempts, limit=10):
        from sqlalchemy import or_

        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyReport)
                .where(
                    NiftyReport.user_id == user_id,
                    NiftyReport.generation_status == "GENERATED",
                    NiftyReport.delivery_status == "PENDING",
                    NiftyReport.attempts < max_attempts,
                    NiftyReport.claim_token.is_(None),
                    NiftyReport.claimed_until.is_(None),
                    or_(NiftyReport.next_attempt_at.is_(None), NiftyReport.next_attempt_at <= now),
                )
                .order_by(NiftyReport.id)
                .limit(limit)
            )
            return [self._report_dict(row) for row in rows]

    def claim_report_delivery(self, user_id, report_id, token, now, *, lease_seconds, max_attempts):
        """Compare-and-set claim. Exactly one caller wins; the attempt is counted here."""
        from sqlalchemy import or_

        with self.sessions.begin() as db:
            changed = db.execute(
                update(NiftyReport)
                .where(
                    *self._report_where(user_id, report_id),
                    NiftyReport.generation_status == "GENERATED",
                    NiftyReport.delivery_status == "PENDING",
                    NiftyReport.attempts < max_attempts,
                    NiftyReport.claim_token.is_(None),
                    NiftyReport.claimed_until.is_(None),
                    or_(NiftyReport.next_attempt_at.is_(None), NiftyReport.next_attempt_at <= now),
                )
                .values(
                    claim_token=token,
                    claimed_until=now + timedelta(seconds=lease_seconds),
                    attempts=NiftyReport.attempts + 1,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                return None
            return db.scalar(
                select(NiftyReport.attempts).where(*self._report_where(user_id, report_id))
            )

    def finish_report_delivery(
        self, user_id, report_id, token, now, *, sent, error_type=None, next_attempt_at=None
    ):
        """Settle a claimed attempt: SENT, PENDING again at ``next_attempt_at``, or FAILED."""
        status = "SENT" if sent else ("PENDING" if next_attempt_at is not None else "FAILED")
        with self.sessions.begin() as db:
            changed = db.execute(
                update(NiftyReport)
                .where(
                    *self._report_where(user_id, report_id),
                    NiftyReport.claim_token == token,
                    NiftyReport.delivery_status == "PENDING",
                )
                .values(
                    delivery_status=status,
                    claim_token=None,
                    claimed_until=None,
                    next_attempt_at=None if sent else next_attempt_at,
                    last_error_type=None if sent else str(error_type or "UNKNOWN")[:64],
                    sent_at=now if sent else None,
                    updated_at=now,
                )
            )
            if changed.rowcount == 1:
                row = db.scalar(select(NiftyReport).where(*self._report_where(user_id, report_id)))
                db.add(
                    NiftyEvent(
                        user_id=user_id,
                        kind="report_delivery",
                        payload={
                            "report_id": row.id,
                            "kind": row.kind,
                            "period_key": row.period_key,
                            "status": status,
                            "attempts": row.attempts,
                            "error_type": row.last_error_type,
                        },
                        created_at=now,
                    )
                )
            return changed.rowcount == 1

    def skip_report_delivery(self, user_id, report_id, error_type, now):
        with self.sessions.begin() as db:
            changed = db.execute(
                update(NiftyReport)
                .where(
                    *self._report_where(user_id, report_id),
                    NiftyReport.generation_status == "GENERATED",
                    NiftyReport.delivery_status == "PENDING",
                    NiftyReport.claim_token.is_(None),
                    NiftyReport.claimed_until.is_(None),
                )
                .values(
                    delivery_status="SKIPPED_NO_SMTP",
                    claim_token=None,
                    claimed_until=None,
                    next_attempt_at=None,
                    last_error_type=str(error_type)[:64],
                    updated_at=now,
                )
            )
            if changed.rowcount == 1:
                row = db.scalar(select(NiftyReport).where(*self._report_where(user_id, report_id)))
                db.add(
                    NiftyEvent(
                        user_id=user_id,
                        kind="report_delivery",
                        payload={
                            "report_id": row.id,
                            "kind": row.kind,
                            "period_key": row.period_key,
                            "status": "SKIPPED_NO_SMTP",
                            "attempts": row.attempts,
                            "error_type": row.last_error_type,
                        },
                        created_at=now,
                    )
                )
            return changed.rowcount == 1

    def fail_interrupted_deliveries(self, user_id, now):
        """Hold expired claims: SMTP may have accepted before the process died."""
        with self.sessions.begin() as db:
            rows = db.execute(
                update(NiftyReport)
                .where(
                    NiftyReport.user_id == user_id,
                    NiftyReport.delivery_status == "PENDING",
                    NiftyReport.claimed_until.is_not(None),
                    NiftyReport.claimed_until <= now,
                )
                .values(
                    delivery_status="FAILED",
                    claim_token=None,
                    claimed_until=None,
                    next_attempt_at=None,
                    last_error_type="DELIVERY_OUTCOME_UNKNOWN",
                    updated_at=now,
                )
                .returning(
                    NiftyReport.id,
                    NiftyReport.kind,
                    NiftyReport.period_key,
                    NiftyReport.attempts,
                )
            ).all()
            for row in rows:
                db.add(
                    NiftyEvent(
                        user_id=user_id,
                        kind="report_delivery",
                        payload={
                            "report_id": row.id,
                            "kind": row.kind,
                            "period_key": row.period_key,
                            "status": "FAILED",
                            "attempts": row.attempts,
                            "error_type": "DELIVERY_OUTCOME_UNKNOWN",
                        },
                        created_at=now,
                    )
                )
            return len(rows)

    def resend_report(self, user_id, report_id, now):
        """Reset delivery of a FAILED or SKIPPED_NO_SMTP report. Compare-and-set on status."""
        with self.sessions.begin() as db:
            changed = db.execute(
                update(NiftyReport)
                .where(
                    *self._report_where(user_id, report_id),
                    NiftyReport.generation_status == "GENERATED",
                    NiftyReport.delivery_status.in_(("FAILED", "SKIPPED_NO_SMTP")),
                )
                .values(
                    delivery_status="PENDING",
                    attempts=0,
                    next_attempt_at=None,
                    claim_token=None,
                    claimed_until=None,
                    last_error_type=None,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                return None
            db.add(
                NiftyEvent(
                    user_id=user_id,
                    kind="report_resend_requested",
                    payload={"report_id": int(report_id)},
                    created_at=now,
                )
            )
        return self.report(user_id, report_id)

    def retry_report_generation(self, user_id, report_id, now, *, max_attempts):
        """Manual retry for an exhausted failed PDF generation, never an email.

        Compare-and-set against FAILED plus exhausted counter; only the owned
        row can be reset. Existing SENT/GENERATED reports are never changed.
        """
        if not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError("Valid maximum generation attempts required")
        with self.sessions.begin() as db:
            changed = db.execute(
                update(NiftyReport)
                .where(
                    *self._report_where(user_id, report_id),
                    NiftyReport.generation_status == "FAILED",
                    NiftyReport.generation_attempts >= max_attempts,
                    NiftyReport.delivery_status == "PENDING",
                )
                .values(
                    generation_status="PENDING",
                    generation_attempts=0,
                    generation_error_type=None,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                return None
            db.add(
                NiftyEvent(
                    user_id=user_id,
                    kind="report_generation_retry_requested",
                    payload={"report_id": int(report_id)},
                    created_at=now,
                )
            )
        return self.report(user_id, report_id)

    def record_report_scan_block(self, user_id, day, reason, now):
        """Persist an undecidable date without treating it as a trading day."""
        day = str(day)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            item = db.get(NiftyReportScanBlock, (user_id, day))
            if item is None:
                db.add(
                    NiftyReportScanBlock(
                        user_id=user_id,
                        day=day,
                        reason=str(reason)[:40],
                        created_at=now,
                        last_checked_at=now,
                    )
                )
            else:
                item.reason = str(reason)[:40]
                item.last_checked_at = now

    def report_scan_blocks(self, user_id, limit=6):
        """Oldest-check-first recheck order prevents one bad day starving others."""
        with self.sessions() as db:
            items = db.scalars(
                select(NiftyReportScanBlock)
                .where(NiftyReportScanBlock.user_id == user_id)
                .order_by(NiftyReportScanBlock.last_checked_at, NiftyReportScanBlock.day)
                .limit(limit)
            )
            return [{"day": row.day, "reason": row.reason} for row in items]

    def clear_report_scan_block(self, user_id, day):
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyReportScanBlock, (user_id, str(day)))
            if row is None:
                return False
            db.delete(row)
            return True

    def report_scan_status(self, user_id):
        """Read-only and user-scoped. No history or trading state is exposed."""
        from sqlalchemy import func

        with self.sessions() as db:
            cursor = db.get(NiftyReportScan, user_id)
            count = db.scalar(
                select(func.count())
                .select_from(NiftyReportScanBlock)
                .where(NiftyReportScanBlock.user_id == user_id)
            )
            blocked = db.scalars(
                select(NiftyReportScanBlock)
                .where(NiftyReportScanBlock.user_id == user_id)
                .order_by(NiftyReportScanBlock.day)
                .limit(10)
            )
            return {
                "next_day": cursor.next_day if cursor else None,
                "blocked_count": int(count or 0),
                "blocked_examples": [{"day": x.day, "reason": x.reason} for x in blocked],
            }

    def report_scan_cursor(self, user_id, since):
        """Create/read durable scan cursor using the established per-user lock."""
        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyReportScan, user_id)
            if row is None:
                row = NiftyReportScan(
                    user_id=user_id, next_day=since.isoformat(), updated_at=datetime.now(UTC)
                )
                db.add(row)
                db.flush()
            return row.next_day

    def advance_report_scan_cursor(self, user_id, expected, next_day):
        """Advance only after all due periods in a bounded scan were reserved."""
        if next_day <= expected:
            return False
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyReportScan, user_id)
            if row is None or row.next_day != expected:
                return False
            row.next_day = next_day
            row.updated_at = datetime.now(UTC)
            return True

    def rewind_report_scan_cursor(self, user_id, year):
        """Revisit affected session periods after an approved calendar amendment."""
        candidate = f"{int(year):04d}-01-01"
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyReportScan, user_id)
            if row is not None and row.next_day > candidate:
                row.next_day = candidate
                row.updated_at = datetime.now(UTC)

    def report_months(self, user_id):
        with self.sessions() as db:
            rows = db.scalars(
                select(NiftyMonth).where(NiftyMonth.user_id == user_id).order_by(NiftyMonth.month)
            )
            return [
                {
                    "month": row.month,
                    "realized_net": str(row.realized_net),
                    "loss_locked_at": _instant(row.loss_locked_at) if row.loss_locked_at else None,
                    "profit_locked_at": (
                        _instant(row.profit_locked_at) if row.profit_locked_at else None
                    ),
                    "lock_detail": dict(row.lock_detail or {}),
                    "milestone_report_ids": list(row.milestone_report_ids or []),
                }
                for row in rows
            ]

    def link_milestone_report(self, user_id, month, report_id, now):
        """Record a milestone report id on the month row once (reserved in Phase 3b)."""
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyMonth, (user_id, month))
            if row is None or int(report_id) in (row.milestone_report_ids or []):
                return False
            row.milestone_report_ids = [*(row.milestone_report_ids or []), int(report_id)]
            return True

    def user_since(self, user_id):
        """When the feature first saw this user: the first configuration revision."""
        from sqlalchemy import func

        with self.sessions() as db:
            first = db.scalar(
                select(func.min(NiftyConfiguration.created_at)).where(
                    NiftyConfiguration.user_id == user_id
                )
            )
        return None if first is None else datetime.fromisoformat(_instant(first))

    def report_inputs(self, user_id, start, end):
        """Plain, ordered facts for ``[start, end)``; the report renderer does no I/O."""
        from sqlalchemy import or_

        def amount(value):
            return None if value is None else str(value)

        with self.sessions() as db:
            trades = [
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
                for row in db.scalars(
                    select(NiftyTrade)
                    .where(
                        NiftyTrade.user_id == user_id,
                        NiftyTrade.closed_at >= start,
                        NiftyTrade.closed_at < end,
                    )
                    .order_by(NiftyTrade.closed_at, NiftyTrade.id)
                )
            ]
            buys = [
                {"status": row.status, "filled": row.price is not None, "reason": row.reason}
                for row in db.scalars(
                    select(NiftyOrder)
                    .where(
                        NiftyOrder.user_id == user_id,
                        NiftyOrder.side == "BUY",
                        NiftyOrder.created_at >= start,
                        NiftyOrder.created_at < end,
                    )
                    .order_by(NiftyOrder.created_at, NiftyOrder.order_id)
                )
            ]
            decisions = [
                {
                    "eligible": bool(row.payload.get("eligible")),
                    "side": row.payload.get("side"),
                    "reasons": [str(item) for item in (row.payload.get("reasons") or []) if item],
                }
                for row in db.scalars(
                    select(NiftyDecision)
                    .where(
                        NiftyDecision.user_id == user_id,
                        NiftyDecision.created_at >= start,
                        NiftyDecision.created_at < end,
                    )
                    .order_by(NiftyDecision.created_at, NiftyDecision.decision_id)
                )
            ]
            events = [
                {"kind": row.kind, "payload": dict(row.payload or {})}
                for row in db.scalars(
                    select(NiftyEvent)
                    .where(
                        NiftyEvent.user_id == user_id,
                        NiftyEvent.created_at >= start,
                        NiftyEvent.created_at < end,
                    )
                    .order_by(NiftyEvent.id)
                )
            ]
            shadows = [
                {
                    "kind": row.kind,
                    "status": row.status,
                    "symbol": row.symbol,
                    "quantity": row.quantity,
                    "net": amount(row.net),
                    "additive": bool(row.additive),
                    "exit_reason": row.exit_reason,
                }
                for row in db.scalars(
                    select(NiftyShadowPosition)
                    .where(
                        NiftyShadowPosition.user_id == user_id,
                        NiftyShadowPosition.opened_at >= start,
                        NiftyShadowPosition.opened_at < end,
                    )
                    .order_by(NiftyShadowPosition.opened_at, NiftyShadowPosition.id)
                )
            ]
            opportunities = [
                {"direction": row.direction, "status": row.status, "outcome": row.outcome}
                for row in db.scalars(
                    select(NiftyOpportunity)
                    .where(
                        NiftyOpportunity.user_id == user_id,
                        NiftyOpportunity.candle_end >= start,
                        NiftyOpportunity.candle_end < end,
                    )
                    .order_by(NiftyOpportunity.candle_end, NiftyOpportunity.opportunity_id)
                )
            ]
            first_day = start.astimezone(_IST).date().isoformat()
            last_day = (end - timedelta(microseconds=1)).astimezone(_IST).date().isoformat()
            cooldowns = [
                {
                    "loss_session": row.loss_session,
                    "cooldown_session": row.cooldown_session,
                    "realized_net": str(row.realized_net),
                }
                for row in db.scalars(
                    select(NiftyCooldown)
                    .where(
                        NiftyCooldown.user_id == user_id,
                        or_(
                            (NiftyCooldown.loss_session >= first_day)
                            & (NiftyCooldown.loss_session <= last_day),
                            (NiftyCooldown.cooldown_session >= first_day)
                            & (NiftyCooldown.cooldown_session <= last_day),
                        ),
                    )
                    .order_by(NiftyCooldown.loss_session)
                )
            ]
            cooldown_reasons = (
                self._cooldown_reasons(db, user_id, first_day) if first_day == last_day else []
            )
            month = db.get(NiftyMonth, (user_id, _month_key(start)))
            month_state = None
            if month is not None:
                month_state = {
                    "month": month.month,
                    "realized_net": str(month.realized_net),
                    "loss_locked_at": (
                        _instant(month.loss_locked_at) if month.loss_locked_at else None
                    ),
                    "profit_locked_at": (
                        _instant(month.profit_locked_at) if month.profit_locked_at else None
                    ),
                    "lock_detail": dict(month.lock_detail or {}),
                }
        return {
            "trades": trades,
            "buys": buys,
            "decisions": decisions,
            "events": events,
            "shadows": shadows,
            "opportunities": opportunities,
            "cooldowns": cooldowns,
            "cooldown_reasons": cooldown_reasons,
            "month": month_state,
        }
