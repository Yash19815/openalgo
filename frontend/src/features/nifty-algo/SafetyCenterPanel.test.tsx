import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { SafetyCenterPanel } from './SafetyCenterPanel'

const api = vi.hoisted(() => ({ read: vi.fn(), acknowledge: vi.fn(), resolve: vi.fn() }))
vi.mock('./api', () => ({
  niftyKeys: { all: ['nifty-algo'] },
  readNifty: api.read,
  acknowledgeSafetyIncident: api.acknowledge,
  resolveSafetyIncident: api.resolve,
}))

const incident = {
  id: 7,
  mode: 'PAPER',
  code: 'STALE_DATA',
  severity: 'CRITICAL',
  status: 'OPEN',
  revision: 3,
  created_at: '2026-11-22T05:00:00+00:00',
  acknowledged_at: null,
  acknowledged_by: null,
}
const status = {
  entry_blocked: true,
  reasons: ['SAFETY_INTERLOCK'],
  recovery_available: false,
  incidents: [incident],
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SafetyCenterPanel />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  api.read.mockResolvedValue(status)
})

it('keeps the durable hold visible after acknowledgement and never offers resume', async () => {
  api.acknowledge.mockImplementation(async () => {
    api.read.mockResolvedValue({
      ...status,
      incidents: [{ ...incident, status: 'ACKNOWLEDGED', revision: 4 }],
    })
  })
  renderPanel()
  fireEvent.click(await screen.findByRole('button', { name: 'Acknowledge incident 7' }))
  await waitFor(() => expect(api.acknowledge.mock.calls[0]?.[0]).toEqual({ id: 7, revision: 3 }))
  expect(await screen.findByText('ACKNOWLEDGED')).toBeInTheDocument()
  expect(screen.getByText('New entries blocked')).toBeInTheDocument()
  expect(screen.getByText(/Acknowledgement does not resolve/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /resume|resolve|live/i })).not.toBeInTheDocument()
})

it('refreshes stale revisions without treating a conflict as success', async () => {
  api.acknowledge.mockRejectedValue(new Error('Incident changed. Reload before acknowledging.'))
  renderPanel()
  fireEvent.click(await screen.findByRole('button', { name: 'Acknowledge incident 7' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(/Incident changed/)
  await waitFor(() => expect(api.read.mock.calls.length).toBeGreaterThan(1))
  expect(screen.getByText('New entries blocked')).toBeInTheDocument()
})

it('shows failed safety observations instead of claiming entries are safe', async () => {
  api.read.mockRejectedValue(new Error('Safety observations unavailable'))
  renderPanel()
  expect(await screen.findByRole('alert')).toHaveTextContent('Safety observations unavailable')
  expect(screen.queryByText('No incident entry hold')).not.toBeInTheDocument()
})

it('explains why acknowledgement is disabled while saving', async () => {
  let finish: (() => void) | undefined
  api.acknowledge.mockReturnValueOnce(
    new Promise<void>((resolve) => {
      finish = resolve
    })
  )
  renderPanel()
  const button = await screen.findByRole('button', { name: 'Acknowledge incident 7' })
  fireEvent.click(button)
  try {
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Saving acknowledgement. Incident controls are temporarily disabled.'
    )
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(api.acknowledge).toHaveBeenCalledTimes(1)
  } finally {
    finish?.()
  }
})

it('requires confirmation and both revisions to resolve without resuming', async () => {
  api.read.mockResolvedValue({
    ...status,
    recovery_available: true,
    state_revision: 12,
    incidents: [{ ...incident, status: 'ACKNOWLEDGED', revision: 4 }],
  })
  api.resolve.mockImplementation(async () => {
    api.read.mockResolvedValue({
      ...status,
      recovery_available: true,
      state_revision: 13,
      entry_blocked: false,
      incidents: [{ ...incident, status: 'RESOLVED', revision: 5 }],
    })
  })
  renderPanel()
  fireEvent.click(await screen.findByRole('button', { name: 'Review resolution for incident 7' }))
  expect(api.resolve).not.toHaveBeenCalled()
  expect(await screen.findByRole('dialog')).toHaveTextContent('Trading stays paused')
  fireEvent.click(screen.getByRole('button', { name: 'Confirm resolution only' }))
  await waitFor(() =>
    expect(api.resolve.mock.calls[0]?.[0]).toEqual({ id: 7, revision: 4, state_revision: 12 })
  )
  expect(await screen.findByText('RESOLVED')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /resume|start trading/i })).not.toBeInTheDocument()
})

it('never offers recovery for Live or unknown safety conditions', async () => {
  api.read.mockResolvedValue({
    ...status,
    recovery_available: true,
    state_revision: 12,
    incidents: [
      { ...incident, status: 'ACKNOWLEDGED', mode: 'LIVE' },
      { ...incident, id: 8, status: 'ACKNOWLEDGED', code: 'BROKER_AMBIGUITY' },
    ],
  })
  renderPanel()
  expect(await screen.findByText('Incident 8: BROKER_AMBIGUITY')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /resolution|resolve/i })).not.toBeInTheDocument()
})

it('returns keyboard focus to the review control when resolution is cancelled', async () => {
  api.read.mockResolvedValue({
    ...status,
    recovery_available: true,
    state_revision: 12,
    incidents: [{ ...incident, status: 'ACKNOWLEDGED', revision: 4 }],
  })
  renderPanel()
  const review = await screen.findByRole('button', { name: 'Review resolution for incident 7' })
  review.focus()
  fireEvent.click(review)
  fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
  await waitFor(() => expect(review).toHaveFocus())
  expect(api.resolve).not.toHaveBeenCalled()
})

it('announces one resolution failure and keeps the confirmation open without resuming', async () => {
  api.read.mockResolvedValue({
    ...status,
    recovery_available: true,
    state_revision: 12,
    incidents: [{ ...incident, status: 'ACKNOWLEDGED', revision: 4 }],
  })
  api.resolve.mockRejectedValue(new Error('Incident changed. Reload before resolving.'))
  renderPanel()
  fireEvent.click(await screen.findByRole('button', { name: 'Review resolution for incident 7' }))
  fireEvent.click(screen.getByRole('button', { name: 'Confirm resolution only' }))
  await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(1))
  expect(screen.getByRole('dialog')).toHaveTextContent('Incident changed.')
  expect(screen.queryByRole('button', { name: /resume|start trading/i })).not.toBeInTheDocument()
})
