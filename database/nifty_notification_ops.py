"""Durable monitoring/digests/private report requests, isolated from protection."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import and_, func, or_, select


class NotificationOperations:
    def notification_failures(self, user_id, *, before=None):
        """Seek through all owned held failures without loading the whole outbox."""
        from database.nifty_algo_db import NiftyNotificationAttempt, NiftyNotificationDelivery

        if before is not None and (type(before) is not int or before <= 0):
            raise ValueError("Positive delivery cursor required")
        with self.sessions() as db:
            query = (
                select(NiftyNotificationDelivery, NiftyNotificationAttempt)
                .outerjoin(
                    NiftyNotificationAttempt,
                    and_(
                        NiftyNotificationAttempt.user_id == user_id,
                        NiftyNotificationAttempt.delivery_id == NiftyNotificationDelivery.id,
                        NiftyNotificationAttempt.attempt == NiftyNotificationDelivery.attempts,
                    ),
                )
                .where(
                    NiftyNotificationDelivery.user_id == user_id,
                    NiftyNotificationDelivery.status.in_(("DEAD", "AMBIGUOUS")),
                )
            )
            if before is not None:
                query = query.where(NiftyNotificationDelivery.id < before)
            rows = db.execute(query.order_by(NiftyNotificationDelivery.id.desc()).limit(51)).all()
            return {
                "items": [
                    {
                        **self._notification_dict(row),
                        "last_result": receipt.result if receipt else None,
                    }
                    for row, receipt in rows[:50]
                ],
                "next_before": rows[49][0].id if len(rows) > 50 else None,
            }

    def heartbeat_notification_worker(self, user_id, owner, now, status="RUNNING"):
        from database.nifty_algo_db import NiftyEvent, NiftyNotificationWorker, _instant

        now = self._notification_time(now)
        if status not in ("RUNNING", "IDLE", "BUSY", "ERROR", "STOPPED"):
            raise ValueError("Invalid worker status")
        self.ensure_user(user_id)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyNotificationWorker, user_id)
            if row and row.owner != owner and status == "STOPPED":
                return False
            if row is None:
                row = NiftyNotificationWorker(
                    user_id=user_id, owner=owner, status=status, heartbeat_at=now, expires_at=now
                )
                db.add(row)
            elif (
                datetime.fromisoformat(_instant(row.expires_at)) <= now and row.status != "STOPPED"
            ):
                db.add(
                    NiftyEvent(
                        user_id=user_id,
                        kind="notification_worker_outage",
                        payload={"code": "NOTIFICATION_WORKER_RECOVERED_AFTER_OUTAGE"},
                        created_at=now,
                    )
                )
            row.owner, row.status, row.heartbeat_at = owner, status, now
            row.expires_at = now if status == "STOPPED" else now + timedelta(seconds=30)
            return True

    def notification_worker_health(self, user_id, now):
        with self.sessions() as db:
            return self._notification_worker_health(db, user_id, now)

    @staticmethod
    def _notification_worker_health(db, user_id, now):
        from database.nifty_algo_db import NiftyNotificationWorker, _instant

        row = db.get(NiftyNotificationWorker, user_id)
        if row is None:
            return {"status": "NOT_STARTED", "operational": False, "heartbeat_at": None}
        fresh = datetime.fromisoformat(_instant(row.expires_at)) > now and row.status != "STOPPED"
        return {
            "status": row.status if fresh or row.status == "STOPPED" else "OUTAGE",
            "operational": fresh and row.status in ("RUNNING", "IDLE", "BUSY"),
            "heartbeat_current": fresh,
            "heartbeat_at": _instant(row.heartbeat_at),
            "expires_at": _instant(row.expires_at),
            "trading_safety_authority": False,
        }

    def replay_dead_notification(self, user_id, delivery_id, expected_attempts, now):
        from database.nifty_algo_db import (
            NiftyDiscordSettings,
            NiftyEvent,
            NiftyNotificationAttempt,
            NiftyNotificationDelivery,
            StateConflict,
        )
        from services.nifty_algo.discord_bot import CHANNELS

        if type(delivery_id) is not int or type(expected_attempts) is not int:
            raise ValueError("Integer delivery identity and attempt revision required")
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyNotificationDelivery, delivery_id)
            settings = db.get(NiftyDiscordSettings, user_id)
            receipt = db.scalar(
                select(NiftyNotificationAttempt)
                .where(
                    NiftyNotificationAttempt.user_id == user_id,
                    NiftyNotificationAttempt.delivery_id == delivery_id,
                )
                .order_by(NiftyNotificationAttempt.attempt.desc())
                .limit(1)
            )
            if row is None or row.user_id != user_id:
                raise LookupError("Delivery not found")
            if (
                row.status != "DEAD"
                or row.attempts != expected_attempts
                or row.attempts >= 100
                or row.destination not in CHANNELS
                or receipt is None
                or receipt.attempt != row.attempts
                or receipt.result.get("outcome") not in ("DEAD", "RETRY")
                or settings is None
                or settings.verified_revision != settings.revision
                or not settings.configuration.get("enabled")
                or not (settings.verification or {}).get("ready")
            ):
                raise StateConflict(
                    "Only verified definite failures can be replayed; ambiguous sends remain held"
                )
            row.status, row.next_at, row.updated_at = "PENDING", now, now
            row.claim_token, row.claimed_until = None, None
            db.add(
                NiftyEvent(
                    user_id=user_id,
                    kind="notification_replay_requested",
                    payload={"delivery_id": delivery_id, "previous_attempts": row.attempts},
                    created_at=now,
                )
            )
            return {"status": "PENDING", "id": row.id, "attempts": row.attempts}

    def project_routine_digests(self, user_id, now):
        from database.nifty_algo_db import (
            NiftyDiscordSettings,
            NiftyEvent,
            NiftyNotificationDelivery,
            NiftyNotificationDigest,
            NiftyOpportunity,
            NiftyResearchNotificationSeen,
        )

        with self.sessions.begin() as db:
            self._lock(db, user_id)
            config = db.get(NiftyDiscordSettings, user_id)
            if config is None or not config.configuration.get("enabled"):
                return 0
            backlog = db.scalar(
                select(func.count())
                .select_from(NiftyNotificationDelivery)
                .where(
                    NiftyNotificationDelivery.user_id == user_id,
                    NiftyNotificationDelivery.status.in_(("PENDING", "RETRY", "DISPATCHING")),
                )
            )
            if backlog >= 4998:
                return 0
            count = 0
            for kind, destination, severity in (
                ("TRAIL", "risk-management", "RISK"),
                ("RESEARCH", "research-insights", "RESEARCH"),
            ):
                cursor = db.get(NiftyNotificationDigest, (user_id, kind))
                if cursor and cursor.next_at.replace(tzinfo=UTC) > now:
                    continue
                if cursor is None:
                    cursor = NiftyNotificationDigest(
                        user_id=user_id, kind=kind, cursor=0, next_at=now
                    )
                    db.add(cursor)
                if kind == "TRAIL":
                    rows = list(
                        db.scalars(
                            select(NiftyEvent)
                            .where(
                                NiftyEvent.user_id == user_id,
                                NiftyEvent.id > cursor.cursor,
                                NiftyEvent.kind.in_(
                                    ("trailing_stop_updated", "TRAILING_STOP_UPDATED")
                                ),
                                ~select(NiftyNotificationDelivery.id)
                                .where(
                                    NiftyNotificationDelivery.user_id == user_id,
                                    NiftyNotificationDelivery.event_id == NiftyEvent.id,
                                    NiftyNotificationDelivery.destination == destination,
                                )
                                .exists(),
                            )
                            .order_by(NiftyEvent.id)
                            .limit(50)
                        )
                    )
                    details = [
                        {"token": r.payload.get("token"), "stop_price": r.payload.get("stop_price")}
                        for r in rows[-10:]
                    ]
                    if not rows:
                        continue
                    cursor.cursor = rows[-1].id
                    event_id = rows[-1].id
                else:
                    rows = list(
                        db.scalars(
                            select(NiftyOpportunity)
                            .outerjoin(
                                NiftyResearchNotificationSeen,
                                and_(
                                    NiftyResearchNotificationSeen.user_id == user_id,
                                    NiftyResearchNotificationSeen.opportunity_id
                                    == NiftyOpportunity.opportunity_id,
                                ),
                            )
                            .where(
                                NiftyOpportunity.user_id == user_id,
                                NiftyOpportunity.status == "CLOSED",
                                NiftyResearchNotificationSeen.opportunity_id.is_(None),
                            )
                            .order_by(NiftyOpportunity.closed_at, NiftyOpportunity.opportunity_id)
                            .limit(50)
                        )
                    )
                    if not rows:
                        continue
                    details = [
                        {
                            "opportunity_id": r.opportunity_id,
                            "outcome": r.outcome,
                            "basis": "UNDERLYING_ATR_STUDY_NOT_OPTIONS_PNL",
                        }
                        for r in rows[:10]
                    ]
                    for row in rows:
                        db.add(
                            NiftyResearchNotificationSeen(
                                user_id=user_id, opportunity_id=row.opportunity_id
                            )
                        )
                    cursor.cursor += 1
                    event_id = -cursor.cursor
                cursor.next_at = now + timedelta(seconds=60)
                if not config.configuration.get("preferences", {}).get(severity, True):
                    continue
                db.add(
                    NiftyNotificationDelivery(
                        user_id=user_id,
                        event_id=event_id,
                        destination=destination,
                        envelope={
                            "schema_version": 1,
                            "mode": "PAPER" if kind == "TRAIL" else "RESEARCH",
                            "severity": severity,
                            "kind": kind.lower() + "_digest",
                            "occurred_at": now.isoformat(),
                            "events": len(rows),
                            "details": details,
                            "additive_to_paper": False,
                        },
                        status="PENDING",
                        attempts=0,
                        next_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
                count += 1
            return count

    def defer_discord_report(self, user_id, settings, interaction, period, now):
        from database.auth_db import encrypt_token
        from database.nifty_algo_db import NiftyDiscordReportRequest, NiftyReport
        from services.nifty_algo.discord_bot import (
            private_response,
            snowflake,
            valid_interaction_token,
        )

        token = interaction.get("token")
        if not snowflake(interaction.get("id")) or not valid_interaction_token(token):
            return private_response(
                "Private report continuation is unavailable. Use authenticated OpenAlgo Reports."
            )
        limit = interaction.get("attachment_size_limit", 0)
        if type(limit) is not int or not 0 <= limit <= 100 * 1024 * 1024:
            return private_response(
                "Invalid attachment allowance. Use authenticated OpenAlgo Reports."
            )
        try:
            permission = int(interaction.get("app_permissions", "0"))
        except (ValueError, TypeError):
            permission = 0
        limit = min(limit, 8 * 1024 * 1024) if permission & (1 << 15) else 0
        with self.sessions.begin() as db:
            if db.bind.dialect.name == "sqlite":
                db.connection().exec_driver_sql("PRAGMA busy_timeout=500")
            elif db.bind.dialect.name == "postgresql":
                db.connection().exec_driver_sql("SET LOCAL lock_timeout = '500ms'")
            self._lock(db, user_id)
            existing = db.get(NiftyDiscordReportRequest, (user_id, interaction["id"]))
            if existing is not None:
                return {"type": 5, "data": {"flags": 64}}
            count = db.scalar(
                select(func.count())
                .select_from(NiftyDiscordReportRequest)
                .where(NiftyDiscordReportRequest.user_id == user_id)
            )
            if count >= 5000:
                return private_response(
                    "Private report audit quota reached. Use authenticated OpenAlgo Reports."
                )
            report_id = db.scalar(
                select(NiftyReport.id)
                .where(
                    NiftyReport.user_id == user_id,
                    NiftyReport.kind == ("DAILY" if period == "daily" else "MONTH_END"),
                    NiftyReport.generation_status == "GENERATED",
                    NiftyReport.generated_at <= now,
                )
                .order_by(NiftyReport.period_key.desc(), NiftyReport.id.desc())
                .limit(1)
            )
            db.add(
                NiftyDiscordReportRequest(
                    user_id=user_id,
                    interaction_id=interaction["id"],
                    application_id=settings.application_id,
                    token_encrypted=encrypt_token(token),
                    payload={
                        "report_id": report_id,
                        "limit": limit,
                        "actor": interaction["member"]["user"]["id"],
                        "roles": sorted(
                            set(interaction["member"].get("roles", []))
                            & set(settings.authorized_roles)
                        ),
                        "guild_id": interaction["guild_id"],
                        "channel_id": interaction["channel_id"],
                    },
                    status="PENDING",
                    attempts=0,
                    next_at=now,
                    expires_at=now + timedelta(minutes=14),
                )
            )
        return {"type": 5, "data": {"flags": 64}}

    def claim_discord_report(self, user_id, now):
        from database.auth_db import decrypt_token
        from database.nifty_algo_db import NiftyDiscordReportRequest

        with self.sessions.begin() as db:
            self._lock(db, user_id)
            rows = list(
                db.scalars(
                    select(NiftyDiscordReportRequest)
                    .where(
                        NiftyDiscordReportRequest.user_id == user_id,
                        NiftyDiscordReportRequest.status.in_(("PENDING", "DISPATCHING")),
                    )
                    .order_by(NiftyDiscordReportRequest.interaction_id)
                    .limit(100)
                )
            )
            for row in rows:
                if row.expires_at.replace(tzinfo=UTC) <= now:
                    row.status, row.token_encrypted = "EXPIRED", None
                    continue
                if row.status == "DISPATCHING":
                    if row.claimed_until.replace(tzinfo=UTC) <= now:
                        row.status, row.token_encrypted = "AMBIGUOUS", None
                    continue
                if row.next_at.replace(tzinfo=UTC) > now:
                    continue
                row.status, row.claim_token = "DISPATCHING", uuid4().hex
                row.claimed_until = now + timedelta(seconds=30)
                row.attempts += 1
                return {
                    "id": row.interaction_id,
                    "application_id": row.application_id,
                    "token": decrypt_token(row.token_encrypted),
                    "payload": dict(row.payload),
                    "claim_token": row.claim_token,
                }
        return None

    def finish_discord_report(self, user_id, claim, result, now):
        from database.nifty_algo_db import NiftyDiscordReportRequest

        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyDiscordReportRequest, (user_id, claim["id"]))
            if (
                row is None
                or row.claim_token != claim["claim_token"]
                or row.status != "DISPATCHING"
            ):
                return False
            outcome = result["outcome"]
            if row.claimed_until.replace(tzinfo=UTC) <= now:
                outcome = "AMBIGUOUS"
            if outcome not in ("DELIVERED", "RETRY", "DEAD", "AMBIGUOUS"):
                raise ValueError("Invalid private report outcome")
            if outcome == "RETRY" and row.attempts < 5:
                row.status, row.next_at = (
                    "PENDING",
                    now + timedelta(seconds=min(86400, max(1, int(result.get("retry_after", 30))))),
                )
            else:
                row.status, row.token_encrypted = ("DEAD" if outcome == "RETRY" else outcome), None
            row.result = {"outcome": outcome, "code": result.get("code", "UNKNOWN")}
            return True
