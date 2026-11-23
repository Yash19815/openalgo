# Discord Notification and Monitoring Center

This is a dedicated bot using Discord API v10 and signed HTTP interactions,
not per-channel webhooks. It uses the existing HTTPX client, cryptography,
NIFTY outbox and SMTP integration. No new package or Discord environment
variable is required. Credentials use the existing auth Fernet encryption.

## Setup

1. Create an application and bot in the Discord Developer Portal. Retain its
   application ID, public Ed25519 key and bot token server-side.
2. Invite the bot to a private server with `bot` and `applications.commands`
   scopes. Grant View Channel, Send Messages, Embed Links and Attach Files in
   each destination. No privileged gateway intent or trading permission is used.
3. Create ten private destinations: `critical-alerts`, `system-warnings`,
   `bot-status`, `live-trades`, `paper-trades`, `shadow-trades`, `risk-management`,
   `daily-summary`, `monthly-summary`, `research-insights`.
4. In NIFTY Connections & Setup, open Discord Notification Center. Enter IDs,
   not channel names; configure all ten mappings, authorized user/role IDs and
   optional critical-alert role. Make that role mentionable in the critical
   destination. Arbitrary users, roles, everyone and here are not allowed mentions.
5. Save settings, then verify bot membership and effective channel permissions.
   Renames do not affect ID routing. Invalid destinations produce explicit errors.
6. Configure the application's HTTPS interactions URL as
   `/api/nifty-algo/discord/interactions/APPLICATION_ID` on your OpenAlgo origin.
   Only this route is CSRF exempt; every request, including PING, needs a valid
   Ed25519 signature over the timestamp and exact body. Keep server time synced.
7. Register read-only commands from the authenticated dashboard. Discord server
   integration permissions must also allow the intended users/roles to invoke
   commands; server-side OpenAlgo authorization is still required.
8. Start a separate supervised dispatcher under the same protected deployment
   environment: `uv run --no-sync python -m services.nifty_algo.notification_worker --user YOUR_USERNAME`.
   `--once` runs one bounded cycle. Do not run the bot in a protection job.
9. Queue a dashboard test message. Inspect durable attempt status; enqueue
   acceptance alone is not delivery. Test critical Discord failure and Gmail
   fallback in a controlled environment before operational acceptance.

The worker reads the existing DATABASE_URL and auth-encryption environment.
Preserve API_KEY_PEPPER and FERNET_SALT with backups. Rotation uses a replacement
token submitted through the authenticated application. Tokens never return to
the browser, events, reports or provider-error payloads. Every settings change
invalidates prior verification and requires a new permission check.

## Commands and authorization

`/status`, `/position`, `/today`, `/month`, `/health`, `/report daily`,
`/report monthly` and `/ack incident-id` form the entire allowlist. Guild,
application, channel and authorized user or role are checked server-side.
Financial replies are ephemeral. Read-only commands issue SELECTs only. `/ack`
is idempotent by interaction identity and changes only incident acknowledgement.
It cannot resolve, trade, resume, switch mode, change settings or modify stops.
Report commands identify the latest archived report; PDF downloads remain in
the authenticated application. Report notifications can attach an owned,
hash-verified PDF up to the worker's 8 MiB bound.

## Delivery and escalation

Committed safety/fill/risk/report/shadow events project into the existing durable
outbox. Only allowlisted fields are projected. Critical incident creation and
scheduled reminders mention only the configured critical role. Acknowledgements
and resolutions do not create additional role pings.

Shadow events keep a separate durable checkpoint and produce a bounded
60-second digest. Mirror activity is explicitly non-additive. The projector
does not change primary event counts, positions or P&L.

Unresolved incidents produce reminders at 2, 5 and 15 minutes, then the configured
bounded interval. Acknowledged incidents remain visibly unresolved and retain
safety escalation. Reminder identity is durable across restarts. Backlog
backpressure pauses projection/reminders without discarding source events.

An attempt is claimed before transport and recorded independently of provider
acceptance. HTTP 429 schedules a durable cooldown. Definite 4xx refusals become
dead letters; lost replies and 5xx become AMBIGUOUS, not assumed rejection.
Unknown sends are not blindly replayed. Reminders can still send new incident
updates. Critical failure also queues an independent Gmail fallback. SMTP and
Discord results never imply human acknowledgement or position recovery.

Existing Gmail PDF generation, archive, delivery claims and resend behavior are
preserved. The new worker releases scoped settings/user sessions before SMTP
and bounds network calls. HTTP clients are shared rather than created per send.

## Known acceptance gaps

No external message or real Discord/Gmail integration test has been performed.
The HTTP command response deadline needs production latency evidence. Digesting
routine trailing/research events, provider-bucket-specific proactive rate
limits, persistent worker heartbeat, operator dead-letter replay and full
report-command attachments remain unfinished. This is not a claim of full
Discord or Live production readiness.

Protocol references: [Discord interactions](https://docs.discord.com/developers/interactions/receiving-and-responding),
[message API](https://docs.discord.com/developers/resources/message),
[rate limits](https://docs.discord.com/developers/topics/rate-limits).
