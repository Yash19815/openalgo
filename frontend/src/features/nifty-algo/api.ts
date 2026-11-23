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

export const discordChannels = [
  'critical-alerts',
  'system-warnings',
  'bot-status',
  'live-trades',
  'paper-trades',
  'shadow-trades',
  'risk-management',
  'daily-summary',
  'monthly-summary',
  'research-insights',
] as const
export interface DiscordConfiguration {
  enabled: boolean
  application_id: string
  guild_id: string
  public_key: string
  channels: Record<string, string>
  authorized_users: string[]
  authorized_roles: string[]
  critical_role: string | null
  preferences: Record<string, boolean>
  reminder_interval_seconds: number
}
export interface DiscordCenter {
  settings: {
    revision: number
    configuration: DiscordConfiguration
    token_configured: boolean
    verified: boolean
    verification: { errors: string[] } | null
    updated_at: string
    rate_limit_until: string | null
  } | null
  health: {
    counts: Record<string, number>
    attempts: {
      delivery_id: number
      attempt: number
      result: { outcome: string; code: string }
      at: string
    }[]
  }
  incidents: SafetyIncident[]
  deliveries: { id: number; destination: string; status: string; attempts: number }[]
}
export async function saveDiscordSettings(
  revision: number,
  configuration: DiscordConfiguration,
  token: string
) {
  const response = await webClient.post(`${base}/discord`, {
    revision,
    configuration,
    ...(token ? { token } : {}),
    confirm: 'SAVE_DISCORD_SETTINGS',
  })
  return response.data
}
export async function discordSetupAction(
  action: 'validate' | 'register-commands' | 'test',
  revision: number
) {
  const confirmation = {
    validate: 'VALIDATE',
    'register-commands': 'REGISTER_READ_ONLY',
    test: 'QUEUE_TEST',
  }
  const response = await webClient.post(`${base}/discord/${action}`, {
    revision,
    confirm: confirmation[action],
  })
  return response.data
}
const base = '/api/nifty-algo'

export async function inspectExperiment(id: string) {
  const response = await webClient.post(
    `${base}/research/experiments/${encodeURIComponent(id)}/inspection`,
    { confirm: 'INSPECT_EVIDENCE_ONLY' }
  )
  return response.data.data
}

export async function readAnalyticsPdf(params: string): Promise<Blob> {
  const response = await webClient.get(`${base}/analytics.pdf?${params}`, { responseType: 'blob' })
  if (response.data.type !== 'application/pdf') throw new Error('PDF export unavailable')
  return response.data
}

export interface SelectorRecord {
  id: number
  created_at: string
  payload: {
    mode: 'PAPER' | 'SHADOW'
    status?: 'RANKED' | 'REJECTED' | 'UNAVAILABLE'
    reasons?: string[]
    policy: string
    configuration_id: string
    decision_id: string
    evaluated_at: string
    spot_reference: string | null
    atm_strike: string | null
    expiry: string | null
    ranked_tokens: string[]
    omitted_candidates: number
    quantity_ranking?: {
      evaluated_at: string
      ranking: {
        token: string
        lots: number
        quantity: number
        capital_required: string
        planned_loss: string
        projected_net_reward: string
        total: string
        scores: Record<string, string>
        coverage: { delta: boolean }
      }[]
      rejections: { token: string | null; lots: number; reason: string }[]
    }
    candidates: {
      instrument: {
        token: string
        symbol: string
        exchange: string
        kind: string
        expiry: string
        strike: string
        lot_size: number
        tick_size: string
      }
      moneyness: string
      rank: number | null
      reasons: string[]
      quote: {
        bid: string | null
        ask: string | null
        bid_size: number
        ask_size: number
        volume: number | null
        source_time: string
        provider: string
      } | null
    }[]
  }
}

export interface SafetyIncident {
  id: number
  mode: 'PAPER' | 'LIVE' | 'SHADOW' | 'RESEARCH'
  code: string
  severity: 'WARNING' | 'CRITICAL'
  status: 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED'
  revision: number
  created_at: string
  acknowledged_at: string | null
  acknowledged_by: string | null
}

export interface SafetyStatus {
  entry_blocked: boolean
  reasons: string[]
  recovery_available: boolean
  state_revision: number | null
  incidents: SafetyIncident[]
}

export async function acknowledgeSafetyIncident({
  id,
  revision,
}: {
  id: number
  revision: number
}) {
  const response = await webClient.post(`${base}/safety/incidents/${id}/acknowledge`, { revision })
  return response.data
}

export async function readNifty<T>(resource: string): Promise<T> {
  const response = await webClient.get<{ status: string; data: T }>(`${base}/${resource}`)
  return response.data.data
}

export interface ResearchRecording {
  id: string
  mode: 'RESEARCH'
  schema_version: number
  status: 'RECORDING' | 'SEALED'
  starts_at: string
  ends_at: string
  last_available_at: string | null
  count: number
  size_bytes: number
  max_observations: number
  configuration_id: string
  content_sha256: string
  sealed_at: string | null
  execution_eligible: false
  limitations: string[]
  capture: {
    scope_sha256: string | null
    scope: {
      broker: string
      frozen_at: string
      instruments: {
        token: string
        symbol: string
        exchange: string
      }[]
    } | null
  } | null
}

export interface RecordingList {
  items: ResearchRecording[]
  capture_status: 'NOT_CONNECTED' | 'NATIVE_CAPTURE_REQUESTED'
}

export interface RecordingRequest {
  duration_minutes: number
  max_observations: number
  native_capture: boolean
}

export interface ExperimentSummary {
  id: string
  sha256: string
  created_at: string
  status: 'DEFINED'
  execution_eligible: false
}

export interface ExperimentDefinition extends ExperimentSummary {
  mode: 'RESEARCH'
  performance: null
  snapshot: DataRecord
  limitations: string[]
}

export interface ExperimentRequest {
  recording_id: string
  expected_count: number
  expected_sha256: string
  train_end: string
  validation_end: string
  configuration_overrides: { adx_min?: number; atr_period?: number }
}

export async function defineExperiment({
  recording_id,
  expected_count,
  expected_sha256,
  train_end,
  validation_end,
  configuration_overrides,
}: ExperimentRequest): Promise<ExperimentDefinition> {
  const response = await webClient.post(`${base}/research/experiments`, {
    recording_id,
    expected_count,
    expected_sha256,
    train_end,
    validation_end,
    configuration_overrides,
    confirm: 'DEFINE_ONLY',
  })
  return response.data.data
}

export async function createRecording({
  duration_minutes,
  max_observations,
  native_capture,
}: RecordingRequest): Promise<ResearchRecording> {
  const response = await webClient.post(`${base}/research/recordings`, {
    duration_minutes,
    max_observations,
    native_capture,
    confirm: 'RESEARCH_ONLY',
  })
  return response.data.data
}

export async function sealRecording({
  id,
  expected_count,
}: {
  id: string
  expected_count: number
}): Promise<ResearchRecording> {
  const response = await webClient.post(
    `${base}/research/recordings/${encodeURIComponent(id)}/seal`,
    { expected_count, confirm: 'SEAL_ONLY' }
  )
  return response.data.data
}

export async function resolveSafetyIncident({
  id,
  revision,
  state_revision,
}: {
  id: number
  revision: number
  state_revision: number
}) {
  const response = await webClient.post(`${base}/safety/incidents/${id}/resolve`, {
    revision,
    state_revision,
    confirm: 'RESOLVE_ONLY',
  })
  return response.data
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
