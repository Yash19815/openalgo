import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ReplayPanel } from './ReplayPanel'

const api = vi.hoisted(() => ({ read: vi.fn(), inspect: vi.fn() }))
vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  readNifty: api.read,
  inspectExperiment: api.inspect,
}))
const id = 'a'.repeat(32)
function view() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: 3 } } })
      }
    >
      <ReplayPanel />
    </QueryClientProvider>
  )
}
beforeEach(() => {
  vi.resetAllMocks()
  api.read.mockImplementation(async (resource: string) =>
    resource === 'research/experiments'
      ? { items: [{ id }] }
      : resource.endsWith('/inspection')
        ? null
        : { execution_eligible: false, next_after: 0, items: [] }
  )
  api.inspect.mockResolvedValue({})
})

it('requires explicit source and UTC clock, then sends only causal playback controls', async () => {
  view()
  await screen.findByRole('option', { name: id })
  fireEvent.change(screen.getByLabelText('Experiment'), { target: { value: id } })
  expect(screen.getByRole('button', { name: 'Start evidence replay' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Replay clock (UTC)'), {
    target: { value: '2026-11-23T04:10' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Start evidence replay' }))
  await waitFor(() =>
    expect(api.read).toHaveBeenCalledWith(
      `research/experiments/${id}/replay?as_of=2026-11-23T04%3A10Z&after=0`
    )
  )
  expect(
    await screen.findByText('No further evidence available at this clock.')
  ).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Step next evidence page' })).toBeDisabled()
})

it('inspection failure does not retry or show fabricated returns', async () => {
  api.inspect.mockRejectedValue(new Error('503'))
  view()
  await screen.findByRole('option', { name: id })
  fireEvent.change(screen.getByLabelText('Experiment'), { target: { value: id } })
  fireEvent.click(screen.getByRole('button', { name: 'Inspect and save dataset coverage' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Inspection outcome unavailable')
  expect(api.inspect).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button', { name: 'Inspect and save dataset coverage' })).toBeDisabled()
  expect(screen.queryByText('Profit:')).not.toBeInTheDocument()
})
