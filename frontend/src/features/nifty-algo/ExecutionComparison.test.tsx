import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ExecutionComparison } from './ExecutionComparison'

const api = vi.hoisted(() => ({ read: vi.fn(), queue: vi.fn() }))
vi.mock('./api', () => ({
  niftyKeys: { all: ['nifty-algo'] },
  readNifty: api.read,
  queueExecutionResearch: api.queue,
}))

function mount() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ExecutionComparison id="exp-1" />
    </QueryClientProvider>
  )
}

const split = (status: string, performance: unknown, missing: string[] = []) => ({
  kind: 'TEST',
  status,
  missing,
  rejections: [{ at: '2026-11-19T05:00:00+00:00', code: 'MONTHLY_LOSS_LOCK' }],
  performance,
})

beforeEach(() => {
  vi.clearAllMocks()
  api.read.mockResolvedValue(null)
})

it('queues the replay once and never offers to change active settings', async () => {
  api.queue.mockResolvedValue({ status: 'QUEUED' })
  mount()
  const queue = await screen.findByRole('button', { name: 'Queue validated A/B/C replay' })
  await waitFor(() => expect(queue).toBeEnabled())
  fireEvent.click(queue)
  await waitFor(() => expect(api.queue).toHaveBeenCalledWith('exp-1'))
  expect(screen.getByText(/No active settings change/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /apply|activate/i })).not.toBeInTheDocument()
})

it('shows unavailable, never zero, for a split withheld by the evidence gate', async () => {
  api.read.mockResolvedValue({
    status: 'COMPLETE',
    sha256: 'abc123',
    result: {
      variants: [
        {
          name: 'A',
          configuration_id: 'cfg-a',
          profit_lock: false,
          splits: [split('INSUFFICIENT_EVIDENCE', null, ['PROTECTION_INTERVAL_UNOBSERVED'])],
        },
        {
          name: 'B',
          configuration_id: 'cfg-b',
          profit_lock: true,
          splits: [split('COMPLETE', { total_net: '80', maximum_drawdown: '5', trades: 1 })],
        },
      ],
      assumptions: ['Fills use recorded displayed depth only.'],
    },
  })
  mount()
  const table = await screen.findByRole('table', { name: 'A/B/C execution results' })
  const rows = within(table).getAllByRole('row')
  expect(within(rows[1]).getAllByText('Unavailable')).toHaveLength(3)
  expect(within(rows[1]).getByText('PROTECTION_INTERVAL_UNOBSERVED')).toBeInTheDocument()
  expect(within(rows[2]).getByText('80')).toBeInTheDocument()
  expect(screen.getByText('Immutable execution hash: abc123')).toBeInTheDocument()
  expect(screen.getByText('Fills use recorded displayed depth only.')).toBeInTheDocument()
})

it('does not retry a queue request whose outcome is unknown', async () => {
  api.queue.mockRejectedValue(new Error('network'))
  mount()
  const queue = await screen.findByRole('button', { name: 'Queue validated A/B/C replay' })
  await waitFor(() => expect(queue).toBeEnabled())
  fireEvent.click(queue)
  expect(await screen.findByRole('alert')).toHaveTextContent('Request outcome unknown')
  expect(api.queue).toHaveBeenCalledTimes(1)
  expect(queue).toBeDisabled()
})
