"""Bounded outbox dispatcher, run as a separate process from trading protection.

No scheduler job, thread pool or bot gateway shares protection capacity.
Tests inject both providers; this module never sends at import time.
"""

from datetime import UTC, datetime

from .discord_bot import DiscordREST, DiscordSettings, message_payload


class NotificationWorker:
    def __init__(self, store, user_id, *, transport=None, email=None, clock=None):
        self.store, self.user_id = store, user_id
        self.transport, self.email = transport, email
        self.clock = clock or (lambda: datetime.now(UTC))

    def tick(self):
        now = self.clock()
        configuration = self.store.discord_configuration(self.user_id, secrets=True)
        if configuration is None:
            return {"status": "NOT_CONFIGURED"}
        settings = DiscordSettings.model_validate(configuration["configuration"])
        self.store.project_discord_notifications(self.user_id, now)
        self.store.project_shadow_notifications(self.user_id, now)
        self.store.schedule_incident_reminders(self.user_id, now)
        discord_ready = settings.enabled and configuration["verified"]
        claim = self.store.claim_notification(self.user_id, now=now, email_only=not discord_ready)
        if claim is None:
            return {"status": "IDLE" if discord_ready else "CONFIGURATION_NOT_VERIFIED"}
        if claim["destination"] == "email_fallback":
            result = self.email(claim) if self.email else self._email(claim)
        else:
            transport = self.transport or DiscordREST(configuration["token"])
            channel = settings.channels.get(claim["destination"])
            payload = message_payload(claim["envelope"], settings, claim["id"])
            if claim["envelope"].get("kind") == "report_generated":
                try:
                    attachment = self._attachment(claim["envelope"].get("report_id"))
                    result = transport.send(channel, payload, attachment=attachment)
                except (OSError, ValueError, LookupError):
                    result = {"outcome": "DEAD", "code": "REPORT_ATTACHMENT_UNVERIFIED"}
            else:
                result = transport.send(channel, payload)
        self.store.notification_result(self.user_id, claim, result, self.clock())
        return {"status": result["outcome"], "delivery_id": claim["id"]}

    def _attachment(self, report_id):
        from hashlib import sha256

        from .reports import resolve_report_path

        row = self.store.report(self.user_id, report_id)
        if row is None or row["generation_status"] != "GENERATED" or not row["path"]:
            raise LookupError("Report unavailable")
        path = resolve_report_path(self.store.report_dir, row["path"])
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Report exceeds attachment bound")
        with path.open("rb") as stream:
            data = stream.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024 or sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("Report verification failed")
        return (row["filename"], data, "application/pdf")

    def _email(self, claim):
        from utils.db_sessions import session_cleanup

        from .reports import _default_recipient, _default_send, _default_smtp_settings, smtp_ready

        try:
            with session_cleanup():
                settings = _default_smtp_settings()
                recipient = _default_recipient(self.user_id)
            if not smtp_ready(settings) or not recipient:
                return {"outcome": "RETRY", "code": "SMTP_NOT_CONFIGURED", "retry_after": 60}
            envelope = claim["envelope"]
            sent = _default_send(
                recipient,
                "NIFTY critical safety incident",
                "\n".join(f"{key}: {value}" for key, value in envelope.items()),
                smtp_settings=settings,
                timeout=5,
                redact=True,
            )
            return {
                "outcome": "DELIVERED" if sent else "AMBIGUOUS",
                "code": "SMTP_ACCEPTED" if sent else "SMTP_UNKNOWN",
            }
        except Exception:
            return {"outcome": "AMBIGUOUS", "code": "SMTP_UNKNOWN"}


def main():
    import argparse
    import os
    import time

    from dotenv import load_dotenv

    from database.engine_factory import create_db_engine
    from database.nifty_algo_db import NiftyStore

    parser = argparse.ArgumentParser(
        description="Separate NIFTY notification dispatcher; never places orders"
    )
    parser.add_argument("--user", required=True, help="Existing OpenAlgo username")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    load_dotenv()
    engine = create_db_engine(os.environ["DATABASE_URL"])
    store = NiftyStore(engine)
    store.initialize()
    worker = NotificationWorker(store, args.user)
    try:
        while True:
            try:
                worker.tick()
            except Exception:
                # Provider errors cannot print credentials or untrusted response bodies.
                print("NIFTY notification cycle failed; durable records retained", flush=True)
            if args.once:
                break
            time.sleep(1)
    finally:
        from utils.httpx_client import cleanup_httpx_client

        cleanup_httpx_client()
        engine.dispose()


if __name__ == "__main__":
    main()
