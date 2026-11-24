import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AnalyticsPanel } from './AnalyticsPanel'

const api = vi.hoisted(() => ({ read: vi.fn(), pdf: vi.fn() }))
vi.mock('./api', () => ({
  niftyKeys: { all: ['nifty-algo'] },
  readNifty: api.read,
  readAnalyticsPdf: api.pdf,
}))

// The comparison view has its own tests and its own error state; isolating it keeps
// this file's single-alert assertions about the primary PAPER evidence meaningful.
vi.mock('./ComparativeAnalytics', () => ({ ComparativeAnalytics: () => null }))

const evidence = {
  mode: 'PAPER',
  opening_realized_equity: '20000',
  period: { start: '2026-11-18T18:30:00+00:00', end: '2026-11-19T18:30:00+00:00' },
  metrics: {
    trades: 205,
    fills: 205,
    wins: 123,
    losses: 80,
    breakeven: 2,
    total_gross: '1555.50',
    best: '100',
    worst: '-150',
    total_net: '1234.50',
    costs: '321.00',
    win_rate: 0.6,
    maximum_drawdown: '150.00',
    observed_maximum_drawdown: null,
    average_realized_r: null,
    average_duration_seconds: 120,
    profit_factor: 2,
    risk_coverage: { available: 0, total: 205 },
    equity_curve: [
      { timestamp: '2026-11-19T05:01:00+00:00', equity: '20100' },
      { timestamp: '2026-11-19T05:02:00+00:00', equity: '19950' },
      { timestamp: '2026-11-19T05:03:00+00:00', equity: '21234.50' },
    ],
    drawdown_curve: [
      { timestamp: '2026-11-19T05:01:00+00:00', drawdown: '0' },
      { timestamp: '2026-11-19T05:02:00+00:00', drawdown: '150' },
      { timestamp: '2026-11-19T05:03:00+00:00', drawdown: '0' },
    ],
    groups: { daily: { '2026-11-19': { trades: 205, net: '1234.50' } } },
  },
  details: {
    total: 205,
    limit: 25,
    offset: 0,
    items: [
      {
        id: 1,
        symbol: 'NIFTY_TEST_CE',
        quantity: 25,
        opened_at: '2026-11-19T05:00:00+00:00',
        closed_at: '2026-11-19T05:02:00+00:00',
        entry_price: '165',
        exit_price: '166',
        fees: '1',
        net: '24',
        reason: 'TARGET_HIT',
      },
    ],
  },
}

function mount() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <AnalyticsPanel />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.read.mockResolvedValue(evidence)
})

afterEach(() => {
  vi.restoreAllMocks()
})

it('shows full-period totals separately from fill pagination and unavailable marks', async () => {
  mount()
  expect((await screen.findAllByText('1234.50')).length).toBeGreaterThan(0)
  expect(screen.getByText('NIFTY_TEST_CE')).toBeInTheDocument()
  expect(screen.getByText(/not mark-to-market/i, { selector: 'p' })).toBeInTheDocument()
  expect(screen.getByText(/planned risk available for 0 of 205/i)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Next fills' }))
  await waitFor(() => expect(api.read).toHaveBeenCalledWith('analytics?limit=25&offset=25'))
})

it('shows fill-timed curves and daily groups independently of the detail page', async () => {
  mount()
  await screen.findByText('NIFTY_TEST_CE')
  expect(screen.getByRole('img', { name: 'Realized equity chart' })).toBeInTheDocument()
  expect(screen.getByRole('img', { name: 'Realized drawdown chart' })).toBeInTheDocument()
  const daily = screen.getByRole('table', { name: 'Daily realized results (IST)' })
  expect(within(daily).getByText('2026-11-19')).toBeInTheDocument()
  expect(within(daily).getByText('1234.50')).toBeInTheDocument()
  expect(screen.getByText('1555.50')).toBeInTheDocument()
})

it('exports the applied period and surfaces PDF failures without hiding metrics', async () => {
  let fail: (reason: Error) => void = () => {}
  api.pdf.mockImplementation(
    () =>
      new Promise((_, reject) => {
        fail = reject
      })
  )
  mount()
  await screen.findByText('NIFTY_TEST_CE')
  fireEvent.click(screen.getByRole('button', { name: 'Download analytics PDF' }))
  await waitFor(() =>
    expect(api.pdf).toHaveBeenCalledWith('limit=25&offset=0&start=2026-11-19&end=2026-11-20')
  )
  expect(screen.getByRole('button', { name: 'Generating PDF...' })).toBeDisabled()
  fail(new Error('Export refused'))
  expect(await screen.findByRole('alert')).toHaveTextContent('PDF export failed')
  expect(screen.getByText('NIFTY_TEST_CE')).toBeInTheDocument()
})

it('applies an explicit half-open IST period and resets fill pagination', async () => {
  mount()
  await screen.findByText('NIFTY_TEST_CE')
  fireEvent.click(screen.getByRole('button', { name: 'Next fills' }))
  await waitFor(() => expect(api.read).toHaveBeenCalledWith('analytics?limit=25&offset=25'))
  fireEvent.change(screen.getByLabelText('Start (IST)'), { target: { value: '2026-11-01' } })
  fireEvent.change(screen.getByLabelText('End (IST, exclusive)'), {
    target: { value: '2026-12-01' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Apply period' }))
  await waitFor(() =>
    expect(api.read).toHaveBeenCalledWith(
      'analytics?limit=25&offset=0&start=2026-11-01&end=2026-12-01'
    )
  )
})

it.each([
  false,
  true,
])('releases PDF download resources when browser download fails: %s', async (fails) => {
  const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
  api.pdf.mockResolvedValue(blob)
  const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:nifty-export')
  const release = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {
    if (fails) throw new Error('Browser download unavailable')
  })
  mount()
  await screen.findByText('NIFTY_TEST_CE')
  // Draft dates must not change the period represented by the current evidence.
  fireEvent.change(screen.getByLabelText('Start (IST)'), { target: { value: '2026-01-01' } })
  fireEvent.click(screen.getByRole('button', { name: 'Download analytics PDF' }))
  await waitFor(() => expect(release).toHaveBeenCalledWith('blob:nifty-export'))
  expect(create).toHaveBeenCalledWith(blob)
  expect(click).toHaveBeenCalledOnce()
  expect(document.querySelector('a[download]')).toBeNull()
  expect(api.pdf).toHaveBeenCalledWith('limit=25&offset=0&start=2026-11-19&end=2026-11-20')
  if (fails) expect(await screen.findByRole('alert')).toHaveTextContent('PDF export failed')
  else expect(await screen.findByText('Analytics PDF download requested.')).toBeInTheDocument()
})

it('shows empty curves, daily groups and fills without inventing observations', async () => {
  api.read.mockResolvedValue({
    ...evidence,
    metrics: {
      ...evidence.metrics,
      trades: 0,
      fills: 0,
      equity_curve: [],
      drawdown_curve: [],
      groups: { daily: {} },
    },
    details: { ...evidence.details, total: 0, items: [] },
  })
  mount()
  expect(await screen.findByText('No realized sessions in this period.')).toBeInTheDocument()
  expect(screen.getByText('No fills for realized equity.')).toBeInTheDocument()
  expect(screen.getByText('No fills for realized drawdown.')).toBeInTheDocument()
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Next fills' })).toBeDisabled()
})

it('does not turn evidence errors into zero-valued performance', async () => {
  api.read.mockRejectedValue(new Error('Unavailable'))
  mount()
  expect(await screen.findByRole('alert')).toHaveTextContent('Analytics unavailable')
  expect(screen.queryByText('1234.50')).not.toBeInTheDocument()
})
