"""Notification operations on NiftyStore's existing transactions and outbox.

No transport is called while a database connection or owner lock is held.
New tables are additive; old notification claims retain their conservative
uncertain-outcome behavior.
"""

from datetime import UTC, timedelta

from sqlalchemy import and_, func, or_, select

from services.nifty_algo.discord_bot import (
    DiscordSettings,
    event_projection,
    private_response,
    snowflake,
)


class NotificationStore:
    def project_shadow_notifications(self, user_id, now):
        from database.nifty_algo_db import (
            NiftyDiscordSettings,
            NiftyNotificationDelivery,
            NiftyShadowEvent,
            NiftyShadowNotificationCursor,
        )

        now = self._notification_time(now)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            config = db.get(NiftyDiscordSettings, user_id)
            if config is None or not config.configuration.get("enabled"):
                return 0
            cursor = db.get(NiftyShadowNotificationCursor, user_id)
            if cursor is not None and now < self._notification_time(
                cursor.next_at.replace(tzinfo=UTC)
            ):
                return 0
            backlog = db.scalar(
                select(func.count())
                .select_from(NiftyNotificationDelivery)
                .where(
                    NiftyNotificationDelivery.user_id == user_id,
                    NiftyNotificationDelivery.status.in_(("PENDING", "RETRY", "DISPATCHING")),
                )
            )
            if backlog >= 5000:
                return 0
            events = db.scalars(
                select(NiftyShadowEvent)
                .where(
                    NiftyShadowEvent.user_id == user_id,
                    NiftyShadowEvent.id > (cursor.event_id if cursor else 0),
                )
                .order_by(NiftyShadowEvent.id)
                .limit(50)
            ).all()
            if not events:
                return 0
            if cursor is None:
                cursor = NiftyShadowNotificationCursor(user_id=user_id, event_id=0, next_at=now)
                db.add(cursor)
            cursor.event_id, cursor.next_at = events[-1].id, now + timedelta(seconds=60)
            if config.configuration.get("preferences", {}).get("TRADE", True):
                envelope = {
                    "schema_version": 1,
                    "event_id": -events[-1].id,
                    "kind": "shadow_digest",
                    "severity": "TRADE",
                    "mode": "SHADOW",
                    "occurred_at": now.isoformat(),
                    "events": len(events),
                    "mirror_events_non_additive": sum("MIRROR" in e.kind for e in events),
                    "activity": [{"shadow_id": e.shadow_id, "kind": e.kind} for e in events[:10]],
                    "omitted_details": max(0, len(events) - 10),
                }
                db.add(
                    NiftyNotificationDelivery(
                        user_id=user_id,
                        event_id=-events[-1].id,
                        destination="shadow-trades",
                        envelope=envelope,
                        status="PENDING",
                        attempts=0,
                        next_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
                return 1
            return 0

    def discord_status_snapshot(self, user_id, now):
        from database.nifty_algo_db import NiftyMonth, NiftyState, _month_key

        with self.sessions() as db:
            state = db.get(NiftyState, user_id)
            month = db.get(NiftyMonth, (user_id, _month_key(now)))
            return {
                "state": state.state if state is not None else "UNAVAILABLE",
                "month": {
                    "realized_net": str(month.realized_net) if month else "0",
                    "loss_locked": month is not None and month.loss_locked_at is not None,
                    "profit_locked": month is not None and month.profit_locked_at is not None,
                    "profit_target": (state.configuration or {}).get("monthly_profit_target")
                    if state
                    else None,
                },
            }

    def discord_configuration(self, user_id, *, secrets=False):
        from database.nifty_algo_db import NiftyDiscordSettings, _instant

        with self.sessions() as db:
            row = db.get(NiftyDiscordSettings, user_id)
            if row is None:
                return None
            settings = DiscordSettings.model_validate(row.configuration)
            result = {
                "revision": row.revision,
                "configuration": settings.model_dump(mode="json"),
                "token_configured": bool(row.token_encrypted),
                "verified": row.verified_revision == row.revision
                and bool((row.verification or {}).get("ready")),
                "verification": row.verification,
                "updated_at": _instant(row.updated_at),
                "rate_limit_until": _instant(row.rate_limit_until)
                if row.rate_limit_until
                else None,
            }
            if secrets:
                from database.auth_db import decrypt_token

                result["token"] = decrypt_token(row.token_encrypted)
            return result

    def save_discord_configuration(self, user_id, revision, configuration, token, now):
        from database.auth_db import encrypt_token
        from database.nifty_algo_db import (
            NiftyDiscordSettings,
            NiftyEvent,
            NiftyState,
            StateConflict,
        )

        settings = DiscordSettings.model_validate(configuration)
        if type(revision) is not int or revision < 0:
            raise ValueError("Invalid configuration revision")
        if token is not None and (
            not isinstance(token, str)
            or not 10 <= len(token) <= 256
            or any(c.isspace() for c in token)
        ):
            raise ValueError("Invalid token")
        now = self._notification_time(now)
        encrypted = encrypt_token(token) if token is not None else None
        # Existing NIFTY ownership must exist; configuration cannot create an account.
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            if db.get(NiftyState, user_id) is None:
                raise ValueError("Existing NIFTY owner required")
            row = db.get(NiftyDiscordSettings, user_id)
            if (row.revision if row else 0) != revision:
                raise StateConflict("Discord settings changed. Reload before saving.")
            if row is None:
                if encrypted is None:
                    raise ValueError("Token required for initial setup")
                row = NiftyDiscordSettings(user_id=user_id, revision=0, token_encrypted=encrypted)
                db.add(row)
            row.configuration = settings.model_dump(mode="json")
            row.application_id = settings.application_id
            row.revision += 1
            row.verified_revision, row.verification = None, None
            if encrypted is not None:
                row.token_encrypted = encrypted
            row.updated_at = now
            db.add(
                NiftyEvent(
                    user_id=user_id,
                    kind="discord_settings_changed",
                    payload={"revision": row.revision, "token_rotated": encrypted is not None},
                    created_at=now,
                )
            )
        return self.discord_configuration(user_id)

    def discord_owner(self, application_id):
        from database.nifty_algo_db import NiftyDiscordSettings

        if not snowflake(application_id):
            return None
        with self.sessions() as db:
            return db.scalar(
                select(NiftyDiscordSettings.user_id).where(
                    NiftyDiscordSettings.application_id == application_id
                )
            )

    def verify_discord_configuration(self, user_id, revision, result, now):
        from database.nifty_algo_db import NiftyDiscordSettings, StateConflict

        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyDiscordSettings, user_id)
            if row is None or row.revision != revision:
                raise StateConflict("Discord configuration changed during verification")
            row.verification = {
                "ready": result["ready"] is True,
                "errors": result["errors"][:11],
                "bot_id": result.get("bot_id"),
                "verified_at": self._notification_time(now).isoformat(),
            }
            row.verified_revision = revision
        return self.discord_configuration(user_id)

    def project_discord_notifications(self, user_id, now):
        from database.nifty_algo_db import (
            NiftyDiscordSettings,
            NiftyEvent,
            NiftyNotificationCursor,
            NiftyNotificationDelivery,
            NiftySafetyIncident,
        )

        now = self._notification_time(now)
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyDiscordSettings, user_id)
            if row is None:
                return 0
            settings = DiscordSettings.model_validate(row.configuration)
            # Critical incident creation is unconditional. Delivery opt-in is distinct.
            if not settings.enabled:
                return 0
            backlog = db.scalar(
                select(func.count())
                .select_from(NiftyNotificationDelivery)
                .where(
                    NiftyNotificationDelivery.user_id == user_id,
                    NiftyNotificationDelivery.status.in_(("PENDING", "RETRY", "DISPATCHING")),
                )
            )
            if backlog >= 5000:
                return 0  # Keep cursor in place; never discard critical or unsent records.
            cursor = db.get(NiftyNotificationCursor, user_id)
            if cursor is None:
                cursor = NiftyNotificationCursor(user_id=user_id, event_id=0)
                db.add(cursor)
            events = db.scalars(
                select(NiftyEvent)
                .where(NiftyEvent.user_id == user_id, NiftyEvent.id > cursor.event_id)
                .order_by(NiftyEvent.id)
                .limit(min(50, 5000 - backlog))
            ).all()
            count = 0
            for event in events:
                incident = (
                    db.get(NiftySafetyIncident, event.payload.get("id"))
                    if event.kind.startswith("safety_")
                    and isinstance(event.payload, dict)
                    and type(event.payload.get("id")) is int
                    else None
                )
                projected = event_projection(event, incident)
                if projected is not None:
                    destination, envelope = projected
                    if envelope["severity"] == "CRITICAL" or settings.preferences.get(
                        envelope["severity"], True
                    ):
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

    def schedule_incident_reminders(self, user_id, now):
        from database.nifty_algo_db import (
            NiftyDiscordSettings,
            NiftyEvent,
            NiftyIncidentReminder,
            NiftyNotificationDelivery,
            NiftySafetyIncident,
            _instant,
        )

        now = self._notification_time(now)
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
            if backlog >= 5000:
                return 0
            incidents = db.scalars(
                select(NiftySafetyIncident)
                .outerjoin(
                    NiftyIncidentReminder,
                    and_(
                        NiftyIncidentReminder.user_id == NiftySafetyIncident.user_id,
                        NiftyIncidentReminder.incident_id == NiftySafetyIncident.id,
                    ),
                )
                .where(
                    NiftySafetyIncident.user_id == user_id,
                    NiftySafetyIncident.severity == "CRITICAL",
                    NiftySafetyIncident.status.in_(("OPEN", "ACKNOWLEDGED")),
                    or_(
                        NiftyIncidentReminder.incident_id.is_(None),
                        NiftyIncidentReminder.next_at <= now,
                    ),
                )
                .order_by(NiftySafetyIncident.id)
                .limit(min(100, 5000 - backlog))
            ).all()
            count = 0
            for incident in incidents:
                reminder = db.get(NiftyIncidentReminder, (user_id, incident.id))
                if reminder is None:
                    reminder = NiftyIncidentReminder(
                        user_id=user_id,
                        incident_id=incident.id,
                        stage=0,
                        next_at=incident.created_at + timedelta(seconds=120),
                    )
                    db.add(reminder)
                if now < reminder.next_at.replace(tzinfo=UTC):
                    continue
                event = NiftyEvent(
                    user_id=user_id,
                    kind="incident_reminder",
                    created_at=now,
                    payload={
                        "id": incident.id,
                        "stage": reminder.stage,
                        "acknowledged": incident.status == "ACKNOWLEDGED",
                    },
                )
                db.add(event)
                db.flush()
                envelope = {
                    "schema_version": 1,
                    "event_id": event.id,
                    "kind": "incident_reminder",
                    "mode": incident.mode,
                    "severity": "CRITICAL",
                    "incident_id": incident.id,
                    "code": incident.code,
                    "status": incident.status,
                    "occurred_at": _instant(now),
                }
                db.add(
                    NiftyNotificationDelivery(
                        user_id=user_id,
                        event_id=event.id,
                        destination="critical-alerts",
                        envelope=envelope,
                        status="PENDING",
                        attempts=0,
                        next_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
                # Acknowledgement changes the visible status, never claims safety or resolution.
                offsets = (300, 900)
                reminder.stage += 1
                reminder.next_at = (
                    incident.created_at + timedelta(seconds=offsets[reminder.stage - 1])
                    if reminder.stage <= 2
                    else now + timedelta(seconds=config.configuration["reminder_interval_seconds"])
                )
                if reminder.next_at.replace(tzinfo=UTC) <= now:
                    reminder.next_at = now + timedelta(
                        seconds=config.configuration["reminder_interval_seconds"]
                    )
                count += 1
            return count

    def notification_result(self, user_id, claim, result, now):
        """Persist sanitized attempt evidence, global cooldown and outcome atomically."""
        from database.nifty_algo_db import (
            NiftyDiscordSettings,
            NiftyNotificationAttempt,
            NiftyNotificationDelivery,
            _instant,
        )

        now = self._notification_time(now)
        safe = {
            key: result[key]
            for key in ("outcome", "code", "message_id", "retry_after")
            if key in result
        }
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            row = db.get(NiftyNotificationDelivery, claim["id"])
            if (
                row is None
                or row.user_id != user_id
                or row.status != "DISPATCHING"
                or row.claim_token != claim["claim_token"]
            ):
                return False
            outcome = safe["outcome"]
            if now >= row.claimed_until.replace(tzinfo=UTC):
                outcome = "AMBIGUOUS"
            if outcome not in ("DELIVERED", "RETRY", "DEAD", "AMBIGUOUS"):
                raise ValueError("Invalid transport outcome")
            safe["outcome"] = outcome
            row.status = "DEAD" if outcome == "RETRY" and row.attempts >= 5 else outcome
            row.updated_at = now
            delay = min(86400, max(1, int(result.get("retry_after", min(3600, 2**row.attempts)))))
            if row.status == "RETRY":
                row.next_at = now + timedelta(seconds=delay)
                config = db.get(NiftyDiscordSettings, user_id)
                if config is not None:
                    config.rate_limit_until = row.next_at
            db.add(
                NiftyNotificationAttempt(
                    user_id=user_id,
                    delivery_id=row.id,
                    attempt=row.attempts,
                    result=safe,
                    created_at=now,
                )
            )
            if row.status in ("DEAD", "AMBIGUOUS", "RETRY"):
                self._notification_fallback(db, row, now)
            return True

    def notification_health(self, user_id):
        from database.nifty_algo_db import (
            NiftyNotificationAttempt,
            NiftyNotificationDelivery,
            _instant,
        )

        with self.sessions() as db:
            counts = dict(
                db.execute(
                    select(NiftyNotificationDelivery.status, func.count())
                    .where(NiftyNotificationDelivery.user_id == user_id)
                    .group_by(NiftyNotificationDelivery.status)
                ).all()
            )
            attempts = db.scalars(
                select(NiftyNotificationAttempt)
                .where(NiftyNotificationAttempt.user_id == user_id)
                .order_by(NiftyNotificationAttempt.id.desc())
                .limit(50)
            ).all()
            return {
                "counts": counts,
                "attempts": [
                    {
                        "delivery_id": row.delivery_id,
                        "attempt": row.attempt,
                        "result": row.result,
                        "at": _instant(row.created_at),
                    }
                    for row in attempts
                ],
                "acceptance_is_acknowledgement": False,
            }

    def discord_acknowledge(self, user_id, incident_id, actor, interaction_id, now, *, roles=()):
        from database.nifty_algo_db import (
            NiftyDiscordInteraction,
            NiftyDiscordSettings,
            NiftyEvent,
            NiftySafetyIncident,
        )

        if not snowflake(actor) or not snowflake(interaction_id):
            raise ValueError("Invalid Discord identity")
        with self.sessions.begin() as db:
            self._lock(db, user_id)
            configuration = db.get(NiftyDiscordSettings, user_id)
            if configuration is None or not configuration.configuration.get("enabled"):
                return private_response("Not authorized.")
            settings = DiscordSettings.model_validate(configuration.configuration)
            if actor not in settings.authorized_users and not set(roles) & set(
                settings.authorized_roles
            ):
                return private_response("Not authorized.")
            existing = db.get(NiftyDiscordInteraction, (user_id, interaction_id))
            if existing is not None:
                return existing.response
            row = db.get(NiftySafetyIncident, incident_id)
            if row is None or row.user_id != user_id:
                return private_response("Incident not found.")
            if row.status == "OPEN":
                row.status = "ACKNOWLEDGED"
                row.revision += 1
                row.acknowledged_at, row.acknowledged_by = now, "discord:" + actor
                db.add(
                    NiftyEvent(
                        user_id=user_id,
                        kind="safety_acknowledged",
                        payload={
                            "id": row.id,
                            "revision": row.revision,
                            "actor": "discord:" + actor,
                            "status": row.status,
                            "interaction_id": interaction_id,
                        },
                        created_at=now,
                    )
                )
            response = private_response(
                f"Incident {row.id}: {row.status}. Acknowledgement does not resolve or resume trading."
            )
            db.add(
                NiftyDiscordInteraction(
                    user_id=user_id,
                    interaction_id=interaction_id,
                    response=response,
                    created_at=now,
                )
            )
            return response
