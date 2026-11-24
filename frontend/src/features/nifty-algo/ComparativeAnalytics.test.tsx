import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ComparativeAnalytics } from './ComparativeAnalytics'

const api = vi.hoisted(() => ({ read: vi.fn(), pdf: vi.fn() }))
vi.mock('./api', () => ({
  niftyKeys: { all: ['nifty-algo'] },
  readNifty: api.read,
  readComparativePdf: api.pdf,
}))

const metrics = (net: string) => ({
  trades: 1,
  total_gross: '100',
  costs: '20',
  total_net: net,
  maximum_drawdown: '5',
})
const comparison = {
  paper: { metrics: metrics('80'), quality: { suggestions: [] } },
  independent_shadow: { metrics: null, unavailable_outcomes: 3 },
  mirrors: { total: 1, additive: false, items: [{ id: 7, net: '-999' }] },
  replay_comparisons: [],
}

function mount() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ComparativeAnalytics start="2026-11-19" end="2026-11-20" />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.read.mockResolvedValue(comparison)
})

it('shows unavailable Shadow results instead of zeros and keeps mirrors non-additive', async () => {
  mount()
  const table = await screen.findByRole('table', { name: 'PAPER and Shadow results' })
  expect(within(table).getAllByText('80').length).toBeGreaterThan(0)
  const shadow = within(table).getByText('Independent hypothetical Shadow').closest('tr')
  expect(shadow).not.toBeNull()
  expect(within(shadow as HTMLElement).getAllByText('Unavailable')).toHaveLength(5)
  expect(screen.getByText('Mirror #7: -999; non-additive')).toBeInTheDocument()
  expect(screen.getByText(/never added to PAPER/i)).toBeInTheDocument()
  expect(screen.getByText('No supported suggestion in this sample.')).toBeInTheDocument()
})

it('sends the period and validated filters only through the query string', async () => {
  mount()
  await screen.findByRole('table', { name: 'PAPER and Shadow results' })
  expect(api.read).toHaveBeenCalledWith('analytics/comparison?start=2026-11-19&end=2026-11-20')
  fireEvent.change(screen.getByLabelText('Option type'), { target: { value: 'PE' } })
  await waitFor(() =>
    expect(api.read).toHaveBeenCalledWith(
      'analytics/comparison?start=2026-11-19&end=2026-11-20&side=PE'
    )
  )
})

it('shows a trader-readable error and no figures when evidence fails validation', async () => {
  api.read.mockRejectedValue(new Error('HTTP 400'))
  mount()
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('Comparison unavailable')
  expect(alert).not.toHaveTextContent('400')
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
})

it('states research suggestions need explicit approval and never apply themselves', async () => {
  api.read.mockResolvedValue({
    ...comparison,
    paper: {
      metrics: metrics('80'),
      quality: {
        suggestions: [{ code: 'WIDE_ENTRY_SPREAD', evidence_count: 4, message: 'Spread.' }],
      },
    },
  })
  mount()
  expect(
    await screen.findByText(/Explicit approval required for any settings change/)
  ).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /apply/i })).not.toBeInTheDocument()
})
