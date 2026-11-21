# NIFTY ALGO setup and operation

Use the existing OpenAlgo installation and `/nifty-algo` route. No second
frontend, database server, broker account or Analyzer setting is needed.

## Paper-mode startup (the only supported mode)

Prerequisites before the first session:

- **Approved NSE calendar.** Upload the year's NSE trading-holiday PDF through
  the workspace calendar panel (`POST /api/nifty-algo/calendar/upload`, then
  review and `.../approve`). Entries refuse `CALENDAR_UNAPPROVED` until a
  version is approved; uploads are never auto-approved.
- **SMTP settings (reports only).** Configure SMTP under OpenAlgo settings
  (`settings_db`) and a user email for daily/milestone/month-end PDF delivery.
  Without it reports still generate and are listed, marked `SKIPPED_NO_SMTP`;
  `POST /api/nifty-algo/reports/<id>/resend` retries after SMTP is fixed.
  `DELIVERY_OUTCOME_UNKNOWN` means an acknowledgement was lost or a delivery
  claim expired after interruption. Automatic retry stops because the message
  may already be in the mailbox. Check the mailbox before requesting a manual
  resend. An SMTP acceptance followed by a failed `QUIT` remains `SENT`.
- **Native scheduler and market data.** The Python strategy host's APScheduler
  must be running (normal app startup) and the native Angel market-data
  connection authenticated with today's full NFO master downloaded.
- **Trading mode.** Default is PAPER. `GET /api/nifty-algo/mode` shows the
  mode, revision and masked Live readiness; LIVE stays `LIVE_NOT_READY` —
  the workspace cannot enable it.

Then:

1. Back up the existing main database through the normal OpenAlgo procedure.
2. Build production assets with the existing `npm run build --prefix frontend` command, then start the existing application with its declared Python/frontend environment.
3. Configure the native Angel market-data connection and download today's full NFO master.
4. Verify the OpenAlgo NFO calendar, source timestamps, genuine futures volume, and complete CE/PE expiry subscriptions.
5. Open the NIFTY workspace and review the migrated v2 configuration. Migration preserves history and pauses entries.
6. Select **Connect paper monitor**. This calls the authenticated, CSRF-protected `POST /api/nifty-algo/runner` endpoint and attaches three named jobs per user on the native scheduler: `:protect` every second, `:entries` every five seconds, `:reports` every minute.
7. Review readiness, five indicator states, PCR scope and rejection reasons. Start remains disabled until the backend's current readiness passes.
8. Start during the allowed session/window (entries 10:30–14:45 IST, flat by 15:10). New entries still require a newly completed qualifying bar and final atomic risk approval — at most one primary BUY and ₹400 planned loss per session.

`POST /api/nifty-algo/strategy/start` checks revision, runner lease, data
readiness, configuration identity, reconciliation and persistent controls.
Pause/Stop/Kill disable entries; the attached protective monitor keeps running.
`POST /api/nifty-algo/positions/<token>/close` requests an owned paper exit;
it never reports a successful closure before a confirmed simulated fill.

The native scheduler must already be initialized. Its normal application
startup restores monitors for existing feature users, including paused or
killed users with exposure. A new process waits for a prior lease to expire,
reconciles durable state, warms indicators, and skips old signals. No generic
Python strategy upload is required. Stopping the whole application suspends
paper protection until recovery; shutdown itself does not flatten exposure.

A full expiry scope may exceed the broker's subscription quota. The runner
reports `FULL_PCR_SCOPE_EXCEEDS_NATIVE_SUBSCRIPTION_QUOTA` rather than treating
a partial window as PCR. Protective contract subscriptions take priority.
Missing OI/volume, unknown master freshness, skewed timestamps, failed
subscription acknowledgments and missing authentication all block entries.

Existing legacy exposure without recorded entry strength retains explicit
unavailable target/confidence fields and receives emergency protection.
Review and close it before resuming entries. Do not invent historical entry
strength or reset peak/stop state by editing current configuration.

Monitor orders, exposure, rejection events and the journal. Pending/expired
exits remain exposure until actual simulated fills occur. Back up the main
feature ledger and configuration history together. Database reads are bounded,
but durable records are retained; archival and retention remain operator work
before prolonged use. See TESTING.md and READINESS_REPORT.md for evidence and
real-market prerequisites. Linux worker rehearsal remains required.

Broker protocol reference: [Angel SmartAPI documentation](https://smartapi.angelone.in/docs/MarketData). The documented 1,000-subscription session quota is a capacity gate, not evidence that this installation has complete-expiry entitlement.

Legacy exposure with a recorded favorable peak retains that level as a conservative protective floor and requests a review exit. Missing entry confidence remains explicitly unavailable. Reconciliation never silently repairs inconsistent balances or invents fills.
