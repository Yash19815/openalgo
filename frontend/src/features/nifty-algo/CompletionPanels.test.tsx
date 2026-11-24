import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ComparativeAnalytics } from './ComparativeAnalytics'
import { ExecutionComparison } from './ExecutionComparison'
import { ResearchOperations } from './ResearchOperations'

const api = vi.hoisted(() => ({
  read: vi.fn(),
  queue: vi.fn(),
  define: vi.fn(),
  retention: vi.fn(),
}))
vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  readNifty: api.read,
  queueExecutionResearch: api.queue,
  defineExecutionComparison: api.define,
  recordingRetention: api.retention,
}))

function view(child: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: 3 },
          },
        })
      }
    >
      {child}
    </QueryClientProvider>
  )
}
beforeEach(() => vi.resetAllMocks())

it('shows unavailable performance and exact coverage failures without zero returns', async () => {
  api.read.mockResolvedValue({
    status: 'COMPLETE',
    sha256: 'verified-hash',
    result: {
      variants: [
        {
          name: 'B_CURRENT',
          configuration_id: 'fixed-config',
          profit_lock: true,
          splits: [
            {
              kind: 'TRAIN',
              status: 'REFUSED_MISSING_EVIDENCE',
              missing: ['HISTORICAL_PCR_MISSING'],
              rejections: [],
              performance: null,
            },
          ],
        },
      ],
    },
  })
  view(<ExecutionComparison id="owned-experiment" />)
  const table = await screen.findByRole('table', { name: 'A/B/C execution results' })
  expect(within(table).getAllByText('Unavailable')).toHaveLength(3)
  expect(within(table).getByText('HISTORICAL_PCR_MISSING')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Queue validated A/B/C replay' })).toBeDisabled()
})

it('does not retry an uncertain replay queue write', async () => {
  api.read.mockResolvedValue(null)
  api.queue.mockRejectedValue(new Error('response lost'))
  view(<ExecutionComparison id="owned-experiment" />)
  const queue = screen.getByRole('button', { name: 'Queue validated A/B/C replay' })
  await waitFor(() => expect(queue).toBeEnabled())
  fireEvent.click(queue)
  expect(await screen.findByRole('alert')).toHaveTextContent('Request outcome unknown')
  expect(api.queue).toHaveBeenCalledTimes(1)
  expect(queue).toBeDisabled()
})

const metrics = {
  trades: 1,
  total_gross: '450',
  costs: '50',
  total_net: '400',
  maximum_drawdown: '0',
}
const comparison = () => ({
  paper: { metrics, quality: { suggestions: [] } },
  independent_shadow: { metrics: null, unavailable_outcomes: 2 },
  mirrors: { total: 1, additive: false, items: [{ id: 7, net: '400' }] },
  replay_comparisons: [],
})

it('separates authoritative PAPER, unavailable Shadow and non-additive mirrors', async () => {
  api.read.mockResolvedValue(comparison())
  view(<ComparativeAnalytics start="2026-11-19" end="2026-11-20" />)
  const table = await screen.findByRole('table', { name: 'PAPER and Shadow results' })
  expect(within(table).getAllByText('Unavailable')).toHaveLength(5)
  expect(screen.getByText('Mirror #7: 400; non-additive')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Option type'), { target: { value: 'PE' } })
  await waitFor(() =>
    expect(api.read).toHaveBeenLastCalledWith(
      'analytics/comparison?start=2026-11-19&end=2026-11-20&side=PE'
    )
  )
})

it('hides financial results and exports when comparative evidence fails', async () => {
  api.read.mockRejectedValue(new Error('integrity failed'))
  view(<ComparativeAnalytics start="" end="" />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Comparison unavailable')
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  expect(
    screen.queryByRole('button', { name: 'Download comparative JSON' })
  ).not.toBeInTheDocument()
})

const recording = {
  id: 'recording-one',
  status: 'SEALED',
  count: 4,
  content_sha256: 'source-hash',
  configuration: { adx_min: 25 },
}
function catalogue() {
  api.read.mockImplementation(async (path: string) => ({
    items: path.endsWith('/archives') ? [] : [recording],
  }))
}

it('requires explicit research approval and pins source identities for the definition', async () => {
  catalogue()
  api.define.mockResolvedValue({ id: 'new-definition' })
  view(<ResearchOperations />)
  const choice = await screen.findByLabelText('Recording recording-one: 4 observations')
  fireEvent.click(choice)
  fireEvent.change(screen.getByLabelText('Training end (UTC)'), {
    target: { value: '2026-11-20T00:00' },
  })
  fireEvent.change(screen.getByLabelText('Validation end (UTC)'), {
    target: { value: '2026-11-21T00:00' },
  })
  const define = screen.getByRole('button', { name: 'Define pinned comparison' })
  expect(define).toBeDisabled()
  fireEvent.click(
    screen.getByLabelText(
      'I approve this research definition only; active trading settings remain unchanged.'
    )
  )
  expect(define).toBeEnabled()
  fireEvent.click(define)
  await waitFor(() =>
    expect(api.define).toHaveBeenCalledWith({
      sources: [{ id: recording.id, count: 4, content_sha256: 'source-hash' }],
      configuration: { adx_min: 25 },
      train_end: '2026-11-20T00:00Z',
      validation_end: '2026-11-21T00:00Z',
    })
  )
})

it('holds archive retries after an unknown outcome and failed catalogue refresh', async () => {
  catalogue()
  api.retention.mockRejectedValue(new Error('response lost'))
  view(<ResearchOperations />)
  const archive = await screen.findByRole('button', {
    name: 'Archive sealed recording recording-one',
  })
  fireEvent.click(archive)
  expect(await screen.findByRole('alert')).toHaveTextContent('Retention outcome unavailable')
  expect(api.retention).toHaveBeenCalledTimes(1)
  expect(archive).toBeDisabled()
  api.read.mockRejectedValue(new Error('catalogue unavailable'))
  fireEvent.click(screen.getByRole('button', { name: 'Refresh research catalogues' }))
  expect(
    await screen.findByText('Recording catalogue unavailable. Retention actions are blocked.')
  ).toBeInTheDocument()
  expect(api.retention).toHaveBeenCalledTimes(1)
})
