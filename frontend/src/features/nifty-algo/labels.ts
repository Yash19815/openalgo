/** Human labels for backend refusal, readiness and status codes. The raw code stays visible. */
const LABELS: Record<string, string> = {
  // Entry locks (Phase 3b)
  COOLDOWN_ACTIVE: 'Loss cooldown active for this session',
  COOLDOWN_UNRESOLVED: 'Loss cooldown date not yet resolved',
  MONTHLY_LOSS_LOCK: 'Monthly loss limit reached',
  MONTHLY_PROFIT_LOCK: 'Monthly profit target reached',
  CALENDAR_UNAPPROVED: 'No approved NFO calendar for this year',
  DAILY_ENTRY_USED: 'Session entry allowance already used',
  SPOT_REFERENCE_UNAVAILABLE:
    'Fresh NIFTY spot is unavailable. Check the market feed before the next assessment.',
  DATA_PIPELINE_UNAVAILABLE:
    'Market data is unavailable. Check your broker connection and market feed, then wait for the next assessment.',
  RUNNER_RESTORE_FAILED:
    'Position monitoring could not restart. Check the server logs and restore monitoring before starting entries.',
  // Live readiness (Phase 5)
  BROKER_STATUS_UNAVAILABLE: 'Broker status could not be read',
  API_MISSING: 'Broker or OpenAlgo API key missing',
  AUTH_EXPIRED: 'Broker session expired or not current',
  BROKER_UNREACHABLE: 'Broker reachability unverified',
  LIVE_NOT_READY: 'Live execution not available in this release',
  MARKET_DATA_UNVERIFIED: 'Live market data unverified',
  PROTECTIVE_ORDERS_UNVERIFIED: 'Protective broker orders unverified',
  FILL_RECONCILIATION_UNVERIFIED: 'Broker fill reconciliation unverified',
  STATIC_IP_UNVERIFIED: 'Static IP registration unverified',
  OPEN_EXPOSURE: 'Open positions or pending orders exist',
  ACK_REQUIRED: 'Explicit acknowledgement required',
  // Calendar validation (Phase 3a)
  DATE_FORMAT_UNCLEAR: 'Date format is ambiguous',
  DATE_INVALID: 'Date could not be read',
  DATE_OUTSIDE_CIRCULAR_YEAR: 'Date outside the circular year',
  WEEKDAY_MISMATCH: 'Stated weekday does not match the date',
  WEEKEND_HOLIDAY: 'Holiday falls on a weekend',
  DUPLICATE_DATE: 'Date listed more than once',
  MULTIPLE_YEARS: 'Document mentions more than one year',
  SEGMENT_UNCONFIRMED: 'F&O segment not confirmed in document',
  YEAR_UNCONFIRMED: 'Calendar year not confirmed',
  SCANNED_OR_UNREADABLE: 'Document has no readable text',
  // Research outcomes (Phase 4)
  THRESHOLD_FAVORABLE: 'Favorable threshold reached',
  THRESHOLD_ADVERSE: 'Adverse threshold reached',
  WINDOW_45M: '45-minute window ended',
  SESSION_CUTOFF: 'Session cutoff reached',
  // Zero-trade report reasons (Phase 6)
  NO_ASSESSMENT_RECORDED: 'No signal assessment was recorded',
  NO_ELIGIBLE_SIGNAL: 'No eligible signal in the session',
  ENTRY_NOT_FILLED: 'Entry order expired or was not filled',
  NO_ENTRY_ATTEMPTED: 'No entry was attempted',
  KILL_SWITCH: 'Kill switch activated',
}

export function codeLabel(code: string): string {
  return LABELS[code] ?? code.replaceAll('_', ' ').toLowerCase()
}
