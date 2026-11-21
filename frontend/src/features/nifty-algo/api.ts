import { webClient } from '@/api/client'

export type RecordValue =
  | string
  | number
  | boolean
  | null
  | RecordValue[]
  | { [key: string]: RecordValue }
export type DataRecord = { [key: string]: RecordValue }
export interface NiftyStatus {
  mode: 'PAPER_ONLY'
  state: string
  revision: number
  ready: boolean
  readiness: (string | { code: string; ready: boolean; detail?: string })[]
  [key: string]: unknown
}

export const niftyKeys = { all: ['nifty-algo'] as const }
const base = '/api/nifty-algo'

export async function readNifty<T>(resource: string): Promise<T> {
  const response = await webClient.get<{ status: string; data: T }>(`${base}/${resource}`)
  return response.data.data
}

export interface ConfigurationResponse {
  configuration: DataRecord
  revision: number
  configuration_id: string
}

export async function controlNifty({
  action,
  revision,
}: {
  action: 'start' | 'pause' | 'stop' | 'kill-switch'
  revision: number
}) {
  const response = await webClient.post(`${base}/strategy/${action}`, { revision })
  return response.data
}

export async function saveConfiguration(configuration: ConfigurationResponse) {
  const response = await webClient.put(`${base}/configuration`, {
    configuration: configuration.configuration,
    revision: configuration.revision,
  })
  return response.data
}

export async function assessNativeHistory() {
  const response = await webClient.post(`${base}/assessment`, {})
  return response.data
}

export async function preparePaperMonitor() {
  const response = await webClient.post(`${base}/runner`, {})
  return response.data
}

// Risk, entry locks and calendar status (GET /risk) -------------------------

export interface EntryLocks {
  session: string
  reasons: string[]
  cooldown: {
    active: boolean
    loss_session: string | null
    cooldown_session: string | null
  }
  month: {
    month: string
    realized_net: string
    loss_limit: string
    profit_target: string | null
    loss_locked_at: string | null
    profit_locked_at: string | null
  }
}

export interface RiskOverview {
  mode: 'PAPER_ONLY'
  killed: boolean
  daily_locked: boolean
  account_reconciled: boolean
  entry_locks: EntryLocks
  calendar?: {
    year: number
    status: 'APPROVED' | 'CALENDAR_UNAPPROVED'
    approved_version_id: number | null
  }
  trading_mode: {
    mode: TradingModeName
    revision: number
    live_available: boolean
    live_readiness: string[]
  }
  [key: string]: unknown
}

// Calendar (Phase 3a) --------------------------------------------------------

/** Mirrors MAX_CALENDAR_BYTES in services/nifty_algo/calendar_import.py. */
export const MAX_CALENDAR_BYTES = 2 * 1024 * 1024

export interface CalendarEntry {
  date: string | null
  weekday: string | null
  name: string
  ambiguous: boolean
  issue: string | null
  raw: string
}

export interface CalendarVersion {
  id: number
  year: number
  segment: string
  source_filename: string
  status: 'DRAFT' | 'APPROVED' | 'REJECTED' | 'SUPERSEDED'
  entries: CalendarEntry[]
  issues: string[]
  created_at: string
  approved_at: string | null
  approved_by: string | null
  supersedes_id: number | null
  preview_diff?: { legacy_only: string[]; calendar_only: string[] }
}

export async function uploadCalendar({ file, year }: { file: File; year?: number }) {
  const form = new FormData()
  form.append('file', file)
  if (year) form.append('year', String(year))
  const response = await webClient.post<{ status: string; data: CalendarVersion }>(
    `${base}/calendar/upload`,
    form
  )
  return response.data.data
}

export async function approveCalendar(version: Pick<CalendarVersion, 'id' | 'year' | 'segment'>) {
  const response = await webClient.post<{ status: string; data: CalendarVersion }>(
    `${base}/calendar/versions/${version.id}/approve`,
    { confirmed_year: version.year, confirmed_segment: version.segment }
  )
  return response.data.data
}

/**
 * Fields the backend reads from each draft entry. It recomputes `ambiguous` and
 * `issue` itself, so those are never sent. A non-null `weekday` that disagrees
 * with `date` is reported as WEEKDAY_MISMATCH; null lets the backend derive it.
 */
export interface CalendarEntryEdit {
  date: string | null
  weekday: string | null
  name: string
  raw: string
}

/** PATCH replaces the whole entry list of a DRAFT version. There is no revision. */
export async function updateCalendarEntries({
  id,
  entries,
}: {
  id: number
  entries: CalendarEntryEdit[]
}) {
  const response = await webClient.patch<{ status: string; data: CalendarVersion }>(
    `${base}/calendar/versions/${id}`,
    { entries }
  )
  return response.data.data
}

export async function rejectCalendar(id: number) {
  const response = await webClient.post<{ status: string; data: CalendarVersion }>(
    `${base}/calendar/versions/${id}/reject`,
    {}
  )
  return response.data.data
}

// Shadow and research (Phase 4, read-only) -----------------------------------

export interface ShadowPosition {
  id: number
  kind: 'INDEPENDENT' | 'MIRROR' | string
  status: string
  active: boolean
  additive: boolean
  symbol: string
  quantity: number
  entry_price: string
  exit_price: string | null
  net: string | null
  exit_reason: string | null
  valuation: string | null
  session: string | null
  opened_at: string
  closed_at: string | null
  protection: {
    stop_price?: string | null
    target_price?: string | null
    estimated_net?: string | null
    profit_lock_active?: boolean
    [key: string]: unknown
  } | null
}

export interface ShadowStatus {
  mode: 'HYPOTHETICAL'
  active: ShadowPosition | null
  positions: ShadowPosition[]
  ledger: {
    capital: string
    realized_net: string
    equity: string
    mirror_realized_net: string
    mirror_additive: false
    basis: string
  }
}

export interface Opportunity {
  opportunity_id: string
  candle_end: string
  direction: 'CE' | 'PE'
  status: 'OBSERVING' | 'CLOSED' | string
  outcome: string | null
  reference_price: string
  max_favorable: string
  max_adverse: string
  deadline: string
  closed_at: string | null
}

// Trading mode (Phase 5) -----------------------------------------------------

export type TradingModeName = 'PAPER' | 'LIVE'

/** Masked broker status: booleans, broker id and key source only. */
export interface BrokerStatus {
  available: boolean
  code: string | null
  broker: string | null
  broker_name: string | null
  auth_token_present: boolean
  feed_token_present: boolean
  revoked: boolean
  session_current: boolean
  api_key_configured: boolean
  api_secret_configured: boolean
  key_source: string | null
  openalgo_api_key_configured: boolean
}

export interface TradingMode {
  mode: TradingModeName
  revision: number
  history: { at: string; actor: string; previous: string; new: string; revision: number }[]
  updated_at: string
  live_available: boolean
  adapter: string
  readiness: string[]
  exposure: { positions: number; pending_orders: number }
  broker: BrokerStatus
}

export async function requestMode(body: {
  mode: TradingModeName
  revision: number
  acknowledged?: boolean
}) {
  const response = await webClient.post<{ status: string; data: TradingMode }>(`${base}/mode`, body)
  return response.data.data
}

// Reports (Phase 6) -----------------------------------------------------------

export type ReportKind = 'DAILY' | 'MILESTONE' | 'MONTH_END'
export type ReportDelivery = 'PENDING' | 'SENT' | 'FAILED' | 'SKIPPED_NO_SMTP'

/** Masked report row: never a server path, only the file name. */
export interface NiftyReport {
  id: number
  kind: ReportKind
  variant: 'STANDARD' | 'ZERO_TRADE' | string
  period_key: string
  filename: string | null
  sha256: string | null
  size_bytes: number | null
  generation_status: 'PENDING' | 'GENERATED' | 'FAILED'
  generation_error_type: string | null
  delivery_status: ReportDelivery
  attempts: number
  next_attempt_at: string | null
  last_error_type: string | null
  summary: { zero_trade_reasons?: string[]; [key: string]: unknown }
  generated_at: string | null
  sent_at: string | null
  created_at: string
}

export interface ReportList {
  reports: NiftyReport[]
  smtp_configured: boolean | null
  max_attempts: number
}

export function reportPdfUrl(id: number) {
  return `${base}/reports/${id}/pdf`
}

export async function resendReport(id: number) {
  const response = await webClient.post<{ status: string; data: NiftyReport }>(
    `${base}/reports/${id}/resend`,
    {}
  )
  return response.data.data
}
