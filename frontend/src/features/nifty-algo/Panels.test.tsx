import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Workspace from './Workspace'

const api = vi.hoisted(() => ({
  read: vi.fn(),
  approve: vi.fn(),
  reject: vi.fn(),
  upload: vi.fn(),
  mode: vi.fn(),
  patch: vi.fn(),
  resend: vi.fn(),
}))
vi.mock('./api', () => ({
  createRecording: vi.fn(),
  sealRecording: vi.fn(),
  acknowledgeSafetyIncident: vi.fn(),
  resolveSafetyIncident: vi.fn(),
  updateCalendarEntries: api.patch,
  niftyKeys: { all: ['nifty-algo'] },
  readNifty: api.read,
  controlNifty: vi.fn(),
  saveConfiguration: vi.fn(),
  assessNativeHistory: vi.fn(),
  preparePaperMonitor: vi.fn(),
  uploadCalendar: api.upload,
  approveCalendar: api.approve,
  rejectCalendar: api.reject,
  requestMode: api.mode,
  resendReport: api.resend,
  reportPdfUrl: (id: number) => `/api/nifty-algo/reports/${id}/pdf`,
  MAX_CALENDAR_BYTES: 2 * 1024 * 1024,
}))
vi.mock('@/components/socket/SocketProvider', () => ({
  useSocketContext: () => ({ socket: null }),
}))

const SECRET = 'SECRET-TOKEN-SHOULD-NEVER-RENDER'

const risk = {
  mode: 'PAPER_ONLY',
  killed: false,
  daily_locked: false,
  account_reconciled: true,
  entry_locks: {
    session: '2026-03-10',
    reasons: ['COOLDOWN_ACTIVE', 'MONTHLY_LOSS_LOCK'],
    cooldown: { active: true, loss_session: '2026-03-09', cooldown_session: '2026-03-10' },
    month: {
      month: '2026-03',
      realized_net: '-2150.00',
      loss_limit: '2000',
      profit_target: null,
      loss_locked_at: '2026-03-09T10:00:00+00:00',
      profit_locked_at: null,
    },
  },
  calendar: { year: 2026, status: 'CALENDAR_UNAPPROVED', approved_version_id: null },
  trading_mode: { mode: 'PAPER', revision: 1, live_available: false, live_readiness: [] },
}

const draft = {
  id: 7,
  year: 2026,
  segment: 'NFO',
  source_filename: 'nse-fo-holidays-2026.pdf',
  status: 'DRAFT',
  entries: [
    {
      date: '2026-01-26',
      weekday: 'Monday',
      name: 'Republic Day',
      ambiguous: false,
      issue: null,
      raw: '26-Jan-2026 Monday Republic Day',
    },
  ],
  issues: [],
  created_at: '2026-01-02T09:00:00+00:00',
  approved_at: null,
  approved_by: null,
  supersedes_id: null,
  preview_diff: { legacy_only: [], calendar_only: [] },
}

const mode = {
  mode: 'PAPER',
  revision: 3,
  history: [],
  updated_at: '2026-03-10T03:00:00+00:00',
  live_available: false,
  adapter: 'LIVE_ADAPTER_STUB',
  readiness: ['AUTH_EXPIRED', 'BROKER_UNREACHABLE', 'LIVE_NOT_READY', 'ACK_REQUIRED'],
  exposure: { positions: 0, pending_orders: 0 },
  broker: {
    available: true,
    code: null,
    broker: 'zerodha',
    broker_name: 'Zerodha',
    auth_token_present: true,
    feed_token_present: false,
    revoked: false,
    session_current: false,
    api_key_configured: true,
    api_secret_configured: true,
    key_source: 'saved',
    openalgo_api_key_configured: true,
    // A field outside the masked contract must never be rendered.
    auth: SECRET,
  },
}

const shadow = {
  mode: 'HYPOTHETICAL',
  active: {
    id: 2,
    kind: 'MIRROR',
    status: 'OPEN',
    active: true,
    additive: false,
    symbol: 'NIFTY10MAR2622500CE',
    quantity: 75,
    entry_price: '101.5',
    exit_price: null,
    net: null,
    exit_reason: null,
    valuation: null,
    session: '2026-03-10',
    opened_at: '2026-03-10T05:00:00+00:00',
    closed_at: null,
    protection: { stop_price: '93.4', target_price: '114.2', estimated_net: '212.35' },
  },
  positions: [
    {
      id: 1,
      kind: 'INDEPENDENT',
      status: 'CLOSED',
      active: false,
      additive: true,
      symbol: 'NIFTY10MAR2622450PE',
      quantity: 75,
      entry_price: '88',
      exit_price: '95',
      net: '410.20',
      exit_reason: 'TARGET',
      valuation: 'BID',
      session: '2026-03-09',
      opened_at: '2026-03-09T05:00:00+00:00',
      closed_at: '2026-03-09T05:30:00+00:00',
      protection: null,
    },
  ],
  events: [],
  ledger: {
    capital: '20000',
    realized_net: '410.20',
    equity: '20410.20',
    mirror_realized_net: '-120.00',
    mirror_additive: false,
    basis: 'HYPOTHETICAL_INDEPENDENT_SHADOWS_ONLY',
  },
}

const opportunities = [
  {
    opportunity_id: 'abc',
    candle_end: '2026-03-10T05:00:00+00:00',
    direction: 'CE',
    status: 'CLOSED',
    outcome: 'THRESHOLD_FAVORABLE',
    reference_price: '22510',
    max_favorable: '31',
    max_adverse: '4',
    deadline: '2026-03-10T05:45:00+00:00',
    closed_at: '2026-03-10T05:25:00+00:00',
  },
]

const reportRow = {
  id: 11,
  kind: 'DAILY',
  variant: 'STANDARD',
  period_key: '2026-03-09',
  filename: '2026-03-09.pdf',
  sha256: 'a'.repeat(64),
  size_bytes: 2048,
  generation_status: 'GENERATED',
  generation_error_type: null,
  delivery_status: 'SENT',
  attempts: 1,
  next_attempt_at: null,
  last_error_type: null,
  summary: { trades: 1 },
  generated_at: '2026-03-09T10:10:00+00:00',
  sent_at: '2026-03-09T10:11:00+00:00',
  created_at: '2026-03-09T10:10:00+00:00',
}

const reports = {
  smtp_configured: true,
  max_attempts: 5,
  reports: [
    {
      ...reportRow,
      id: 12,
      variant: 'ZERO_TRADE',
      period_key: '2026-03-10',
      filename: '2026-03-10.pdf',
      delivery_status: 'FAILED',
      attempts: 5,
      last_error_type: 'SMTPAuthenticationError',
      sent_at: null,
      summary: { trades: 0, zero_trade_reasons: ['COOLDOWN_ACTIVE', 'NO_ELIGIBLE_SIGNAL'] },
      // A field outside the masked contract must never be rendered.
      path: SECRET,
    },
    reportRow,
    {
      ...reportRow,
      id: 13,
      kind: 'MILESTONE',
      period_key: '2026-03-LOSS_LOCK',
      filename: null,
      generation_status: 'PENDING',
      delivery_status: 'PENDING',
      attempts: 0,
      sent_at: null,
    },
  ],
}

function respond(overrides: Record<string, unknown> = {}) {
  const fixtures: Record<string, unknown> = {
    status: { mode: 'PAPER_ONLY', state: 'PAUSED', revision: 1, ready: false, readiness: [] },
    risk,
    'calendar/versions': [draft],
    mode,
    shadow,
    'research/opportunities': opportunities,
    reports,
    configuration: {
      revision: 4,
      configuration_id: 'cfg',
      configuration: {
        selection: 'ATM',
        monthly_loss_limit: '2000',
        monthly_profit_target: null,
        max_lots: 3,
      },
    },
    ...overrides,
  }
  api.read.mockImplementation(async (resource: string) => fixtures[resource] ?? {})
}

function renderPage(view: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/nifty-algo?view=${view}`]}>
        <Workspace />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('NIFTY paper-system panels', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    respond()
  })

  it('renders cooldown and monthly lock state with labelled refusal codes', async () => {
    renderPage('risk')
    const reasons = await screen.findByRole('list', { name: 'Entry refusal codes' })
    expect(within(reasons).getByText('Loss cooldown active for this session')).toBeInTheDocument()
    expect(within(reasons).getByText('COOLDOWN_ACTIVE')).toBeInTheDocument()
    expect(within(reasons).getByText('Monthly loss limit reached')).toBeInTheDocument()
    expect(within(reasons).getByText('MONTHLY_LOSS_LOCK')).toBeInTheDocument()
    expect(screen.getByText('-2150.00')).toBeInTheDocument()
    expect(screen.getByText('Cooldown active: Yes')).toBeInTheDocument()
    expect(screen.getByText('Monthly loss lock: Yes')).toBeInTheDocument()
    expect(screen.getByText('Monthly profit lock: No')).toBeInTheDocument()
    expect(screen.getByText('Locked since 2026-03-09T10:00:00+00:00')).toBeInTheDocument()
  })

  it('shows a trading-blocked banner when no calendar is approved', async () => {
    renderPage('overview')
    expect(await screen.findByText('Trading blocked: no approved calendar')).toBeInTheDocument()
  })

  it('hides the banner once the backend reports an approved calendar', async () => {
    respond({
      risk: { ...risk, calendar: { year: 2026, status: 'APPROVED', approved_version_id: 7 } },
    })
    renderPage('risk')
    await screen.findByRole('list', { name: 'Entry refusal codes' })
    expect(screen.queryByText('Trading blocked: no approved calendar')).not.toBeInTheDocument()
  })

  it('approves a clean draft only after explicit confirmation', async () => {
    api.approve.mockResolvedValue({ ...draft, status: 'APPROVED' })
    renderPage('calendar')
    expect(await screen.findByText('Republic Day')).toBeInTheDocument()
    expect(screen.getByText('Trading blocked: no approved calendar')).toBeInTheDocument()
    const approve = screen.getByRole('button', { name: 'Approve calendar' })
    expect(approve).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox'))
    await waitFor(() => expect(approve).toBeEnabled())
    fireEvent.click(approve)
    await waitFor(() =>
      expect(api.approve).toHaveBeenCalledWith(
        expect.objectContaining({ id: 7, year: 2026, segment: 'NFO' }),
        expect.anything()
      )
    )
    expect(await screen.findByText('Calendar approved.')).toBeInTheDocument()
  })

  it('blocks approval when parsed entries are ambiguous and still allows rejection', async () => {
    api.reject.mockResolvedValue({ ...draft, status: 'REJECTED' })
    respond({
      'calendar/versions': [
        {
          ...draft,
          issues: ['DATE_FORMAT_UNCLEAR'],
          entries: [
            {
              ...draft.entries[0],
              ambiguous: true,
              issue: 'DATE_FORMAT_UNCLEAR',
              date: '2026-02-03',
            },
          ],
        },
      ],
    })
    renderPage('calendar')
    expect(await screen.findByText('Approval blocked')).toBeInTheDocument()
    expect(screen.getByText('1 ambiguous entry.')).toBeInTheDocument()
    expect(screen.getAllByText('Date format is ambiguous').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Approve calendar' })).toBeDisabled()
    expect(screen.getByRole('checkbox')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Reject calendar' }))
    await waitFor(() => expect(api.reject).toHaveBeenCalledWith(7, expect.anything()))
    expect(api.approve).not.toHaveBeenCalled()
  })

  describe('draft entry editing', () => {
    const ambiguousDraft = {
      ...draft,
      issues: ['DATE_FORMAT_UNCLEAR'],
      entries: [
        draft.entries[0],
        {
          date: '2026-03-04',
          weekday: 'Wednesday',
          name: 'Holi',
          ambiguous: true,
          issue: 'DATE_FORMAT_UNCLEAR',
          raw: '04/03/2026 Wednesday Holi',
        },
      ],
    }
    const cleanDraft = {
      ...ambiguousDraft,
      issues: [],
      entries: [
        draft.entries[0],
        {
          date: '2026-03-04',
          weekday: 'Wednesday',
          name: 'Holi',
          ambiguous: false,
          issue: null,
          raw: '04/03/2026 Wednesday Holi',
        },
      ],
    }

    beforeEach(() => respond({ 'calendar/versions': [ambiguousDraft] }))

    async function startEditing() {
      renderPage('calendar')
      fireEvent.click(await screen.findByRole('button', { name: 'Edit entries' }))
      return screen.getByRole('button', { name: 'Save entries' })
    }

    it('saves edited, added and removed rows as the full PATCH entry list', async () => {
      api.patch.mockResolvedValue(cleanDraft)
      const save = await startEditing()
      // A flagged row cannot be saved until its date is reviewed.
      expect(save).toBeDisabled()
      fireEvent.change(screen.getByLabelText('Date for row 2'), {
        target: { value: '2026-03-03' },
      })
      fireEvent.change(screen.getByLabelText('Name for row 2'), {
        target: { value: '  Holi (Dhuleti) ' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Add row' }))
      fireEvent.click(screen.getByRole('button', { name: 'Add row' }))
      fireEvent.change(screen.getByLabelText('Date for row 3'), {
        target: { value: '2026-12-25' },
      })
      fireEvent.change(screen.getByLabelText('Name for row 3'), {
        target: { value: 'Christmas' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Remove row 4' }))
      expect(screen.queryByLabelText('Date for row 4')).not.toBeInTheDocument()
      await waitFor(() => expect(save).toBeEnabled())
      fireEvent.click(save)
      await waitFor(() =>
        expect(api.patch).toHaveBeenCalledWith(
          {
            id: 7,
            entries: [
              {
                date: '2026-01-26',
                weekday: 'Monday',
                name: 'Republic Day',
                raw: '26-Jan-2026 Monday Republic Day',
              },
              {
                date: '2026-03-03',
                weekday: null,
                name: 'Holi (Dhuleti)',
                raw: '04/03/2026 Wednesday Holi',
              },
              { date: '2026-12-25', weekday: null, name: 'Christmas', raw: '' },
            ],
          },
          expect.anything()
        )
      )
    })

    it('shows the server refusal and keeps the edits open', async () => {
      api.patch.mockRejectedValue({
        message: 'Calendar version is not an editable draft',
        response: {
          status: 409,
          data: {
            status: 'error',
            code: 'CALENDAR_UPDATE_REFUSED',
            message: 'Calendar version is not an editable draft',
          },
        },
      })
      const save = await startEditing()
      fireEvent.click(screen.getByRole('checkbox', { name: 'Date confirmed for row 2' }))
      await waitFor(() => expect(save).toBeEnabled())
      fireEvent.click(save)
      expect(
        await screen.findByText(
          'Entries not saved: Calendar version is not an editable draft (CALENDAR_UPDATE_REFUSED)'
        )
      ).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Save entries' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Approve calendar' })).toBeDisabled()
    })

    it('enables Approve only after the backend returns the draft without ambiguity', async () => {
      api.patch.mockImplementation(async () => {
        respond({ 'calendar/versions': [cleanDraft] })
        return cleanDraft
      })
      const save = await startEditing()
      const approve = screen.getByRole('button', { name: 'Approve calendar' })
      expect(approve).toBeDisabled()
      expect(screen.getByText('Entry edits are not saved.')).toBeInTheDocument()
      fireEvent.click(screen.getByRole('checkbox', { name: 'Date confirmed for row 2' }))
      await waitFor(() => expect(save).toBeEnabled())
      fireEvent.click(save)
      await waitFor(() =>
        expect(api.patch).toHaveBeenCalledWith(
          {
            id: 7,
            entries: [
              expect.objectContaining({ date: '2026-01-26', weekday: 'Monday' }),
              {
                date: '2026-03-04',
                weekday: null,
                name: 'Holi',
                raw: '04/03/2026 Wednesday Holi',
              },
            ],
          },
          expect.anything()
        )
      )
      expect(
        await screen.findByText('Entries saved. The backend reported no validation issues.')
      ).toBeInTheDocument()
      expect(screen.getByText('No validation issues.')).toBeInTheDocument()
      expect(screen.queryByText('Approval blocked')).not.toBeInTheDocument()
      const confirm = screen.getByRole('checkbox', {
        name: 'I confirm this is the 2026 NFO trading holiday calendar.',
      })
      await waitFor(() => expect(confirm).toBeEnabled())
      fireEvent.click(confirm)
      await waitFor(() =>
        expect(screen.getByRole('button', { name: 'Approve calendar' })).toBeEnabled()
      )
    })

    it('offers no editing for a non-draft version', async () => {
      respond({ 'calendar/versions': [{ ...cleanDraft, status: 'APPROVED' }] })
      renderPage('calendar')
      expect(await screen.findByText('Republic Day')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Edit entries' })).not.toBeInTheDocument()
    })
  })

  it('refuses oversized calendar files before uploading', async () => {
    renderPage('calendar')
    const input = await screen.findByLabelText('Holiday circular (PDF or CSV)')
    const large = new File(['x'], 'big.pdf', { type: 'application/pdf' })
    Object.defineProperty(large, 'size', { value: 2 * 1024 * 1024 + 1 })
    fireEvent.change(input, { target: { files: [large] } })
    expect(await screen.findByText('File exceeds the 2 MB limit.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload calendar' })).toBeDisabled()
    expect(api.upload).not.toHaveBeenCalled()
  })

  it('shows Live readiness codes and masked broker booleans without secrets', async () => {
    const { container } = renderPage('connections')
    const codes = await screen.findByRole('list', { name: 'Live readiness codes' })
    expect(within(codes).getByText('AUTH_EXPIRED')).toBeInTheDocument()
    expect(within(codes).getByText('Broker session expired or not current')).toBeInTheDocument()
    expect(within(codes).getByText('LIVE_NOT_READY')).toBeInTheDocument()
    expect(screen.getByText('Mode: PAPER')).toBeInTheDocument()
    expect(screen.getByText('Revision 3')).toBeInTheDocument()
    expect(screen.getByText('Broker auth token present: Yes')).toBeInTheDocument()
    expect(screen.getByText('Feed token present: No')).toBeInTheDocument()
    expect(screen.getByText(/Live trading is not available in this release/)).toBeInTheDocument()
    expect(container.textContent).not.toContain(SECRET)
    expect(screen.queryByRole('button', { name: 'Switch to Paper' })).not.toBeInTheDocument()
  })

  it('sends a Live request with acknowledged true only after the box is checked', async () => {
    api.mode.mockRejectedValue({
      message: 'Trading mode change refused.',
      response: {
        status: 409,
        data: {
          code: 'MODE_CHANGE_REFUSED',
          message: 'Trading mode change refused.',
          reasons: ['BROKER_UNREACHABLE', 'LIVE_NOT_READY', 'STATIC_IP_UNVERIFIED'],
        },
      },
    })
    renderPage('connections')
    const request = await screen.findByRole('button', { name: 'Request Live' })
    expect(request).toBeDisabled()
    fireEvent.click(request)
    expect(api.mode).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('checkbox'))
    await waitFor(() => expect(request).toBeEnabled())
    fireEvent.click(request)
    await waitFor(() =>
      expect(api.mode).toHaveBeenCalledWith(
        { mode: 'LIVE', revision: 3, acknowledged: true },
        expect.anything()
      )
    )
    const refusal = await screen.findByRole('list', { name: 'Refusal reasons' })
    expect(within(refusal).getByText('STATIC_IP_UNVERIFIED')).toBeInTheDocument()
    expect(within(refusal).getByText('Static IP registration unverified')).toBeInTheDocument()
    expect(screen.getByText(/MODE_CHANGE_REFUSED/)).toBeInTheDocument()
  })

  it('refetches the mode after a revision conflict', async () => {
    respond({ mode: { ...mode, mode: 'LIVE' } })
    api.mode.mockRejectedValue({
      response: { status: 409, data: { code: 'REVISION_CONFLICT', message: 'stale' } },
    })
    renderPage('connections')
    const toPaper = await screen.findByRole('button', { name: 'Switch to Paper' })
    const before = api.read.mock.calls.filter(([name]) => name === 'mode').length
    fireEvent.click(toPaper)
    await waitFor(() =>
      expect(api.mode).toHaveBeenCalledWith({ mode: 'PAPER', revision: 3 }, expect.anything())
    )
    expect(await screen.findByText(/trading mode changed elsewhere/i)).toBeInTheDocument()
    await waitFor(() =>
      expect(api.read.mock.calls.filter(([name]) => name === 'mode').length).toBeGreaterThan(before)
    )
  })

  it('offers only ATM, ITM and DELTA contract selection', async () => {
    renderPage('configuration')
    const select = await screen.findByLabelText('Contract moneyness')
    const values = within(select)
      .getAllByRole('option')
      .map((option) => (option as HTMLOptionElement).value)
    expect(values).toEqual(['ATM', 'ITM', 'DELTA'])
    expect(values).not.toContain('OTM')
    fireEvent.change(screen.getByLabelText('Monthly profit target (Rs, optional)'), {
      target: { value: '1500' },
    })
    const json = JSON.parse(
      (screen.getByLabelText('Versioned research parameters') as HTMLTextAreaElement).value
    )
    expect(json.monthly_profit_target).toBe('1500')
    fireEvent.change(screen.getByLabelText('Monthly profit target (Rs, optional)'), {
      target: { value: '' },
    })
    const cleared = JSON.parse(
      (screen.getByLabelText('Versioned research parameters') as HTMLTextAreaElement).value
    )
    expect(cleared.monthly_profit_target).toBeNull()
  })

  it('labels mirror P&L non-additive and lists research outcomes', async () => {
    renderPage('research')
    expect(await screen.findByText('Mirror of primary entry')).toBeInTheDocument()
    expect(screen.getByText('212.35')).toBeInTheDocument()
    expect(screen.getByText('93.4')).toBeInTheDocument()
    expect(screen.getByText('-120.00')).toBeInTheDocument()
    expect(screen.getAllByText('non-additive').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('410.20', { selector: 'td' })).toBeInTheDocument()
    expect(await screen.findByText('Favorable threshold reached')).toBeInTheDocument()
    expect(screen.getByText('THRESHOLD_FAVORABLE')).toBeInTheDocument()
  })

  it('lists reports with status, attempts, download links and zero-trade reasons', async () => {
    const { container } = renderPage('reports')
    const table = await screen.findByRole('table', { name: 'Generated reports' })
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(4)
    expect(within(rows[1]).getByText('Daily (zero-trade)')).toBeInTheDocument()
    expect(within(rows[1]).getByText('FAILED')).toBeInTheDocument()
    expect(within(rows[1]).getByText(/SMTPAuthenticationError/)).toBeInTheDocument()
    expect(within(rows[1]).getByText('5 / 5')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Loss cooldown active for this session')).toBeInTheDocument()
    expect(within(rows[1]).getByText('No eligible signal in the session')).toBeInTheDocument()
    const download = within(rows[2]).getByRole('link', { name: 'Download 2026-03-09.pdf' })
    expect(download).toHaveAttribute('href', '/api/nifty-algo/reports/11/pdf')
    expect(within(rows[2]).getByText('SENT')).toBeInTheDocument()
    expect(within(rows[3]).getByText('Milestone')).toBeInTheDocument()
    expect(within(rows[3]).queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^Resend/ })).toHaveLength(1)
    expect(screen.queryByText(/SMTP is not configured/)).not.toBeInTheDocument()
    expect(container.textContent).not.toContain(SECRET)
  })

  it('resends only a failed report and shows a refusal', async () => {
    api.resend.mockRejectedValue({
      response: {
        status: 409,
        data: {
          code: 'RESEND_REFUSED',
          message: 'Only a failed or skipped delivery can be resent.',
        },
      },
    })
    renderPage('reports')
    fireEvent.click(await screen.findByRole('button', { name: 'Resend 2026-03-10' }))
    await waitFor(() => expect(api.resend).toHaveBeenCalledWith(12, expect.anything()))
    expect(
      await screen.findByText(
        'Resend refused: Only a failed or skipped delivery can be resent. (RESEND_REFUSED)'
      )
    ).toBeInTheDocument()
  })

  it('surfaces skipped delivery when SMTP is not configured', async () => {
    api.resend.mockResolvedValue({ ...reportRow, id: 14, delivery_status: 'PENDING' })
    respond({
      reports: {
        smtp_configured: false,
        max_attempts: 5,
        reports: [{ ...reportRow, id: 14, delivery_status: 'SKIPPED_NO_SMTP', attempts: 0 }],
      },
    })
    renderPage('reports')
    expect(await screen.findByText(/SMTP is not configured/)).toBeInTheDocument()
    expect(screen.getByText('SKIPPED_NO_SMTP')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Resend 2026-03-09' }))
    expect(await screen.findByText('Report 2026-03-09 queued for delivery.')).toBeInTheDocument()
  })

  it('shows an empty state before any report exists', async () => {
    respond({ reports: { smtp_configured: true, max_attempts: 5, reports: [] } })
    renderPage('reports')
    expect(await screen.findByText('No reports generated yet.')).toBeInTheDocument()
  })
})
