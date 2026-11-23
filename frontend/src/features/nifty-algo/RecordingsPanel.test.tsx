import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import type { RecordingList, ResearchRecording } from './api'
import { RecordingsPanel } from './RecordingsPanel'

const api = vi.hoisted(() => ({ read: vi.fn(), create: vi.fn(), seal: vi.fn() }))
vi.mock('./api', () => ({
  niftyKeys: { all: ['nifty-algo'] },
  readNifty: api.read,
  createRecording: api.create,
  sealRecording: api.seal,
}))

const recording: ResearchRecording = {
  id: 'research-only-1',
  mode: 'RESEARCH',
  schema_version: 1,
  status: 'RECORDING',
  starts_at: '2099-01-01T04:00:00+00:00',
  ends_at: '2099-01-01T05:00:00+00:00',
  last_available_at: null,
  count: 0,
  size_bytes: 0,
  max_observations: 500,
  configuration_id: 'frozen-server-configuration',
  content_sha256: '1'.repeat(64),
  sealed_at: null,
  execution_eligible: false,
  limitations: ['QUOTE_EVIDENCE_ONLY', 'PROVENANCE_NOT_AUTHENTICATED'],
  capture: { scope: null, scope_sha256: null },
}

function list(items: ResearchRecording[] = [recording]): RecordingList {
  return { items, capture_status: 'NATIVE_CAPTURE_REQUESTED' }
}

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: 3 } },
  })
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <RecordingsPanel />
      </QueryClientProvider>
    ),
  }
}

beforeEach(() => {
  vi.resetAllMocks()
  api.read.mockResolvedValue(list())
  api.create.mockResolvedValue(recording)
  api.seal.mockResolvedValue({ ...recording, status: 'SEALED' })
})

it('reports opt-in without claiming a connected feed, quote coverage or execution authority', async () => {
  renderPanel()
  await screen.findByText(recording.id)
  expect(screen.getByText('Requested; scope not frozen')).toBeInTheDocument()
  expect(screen.getByText('No samples saved')).toBeInTheDocument()
  expect(screen.getByText(/Request presence is not feed health/)).toBeInTheDocument()
  expect(screen.getByText(/Provenance is not authenticated/)).toBeInTheDocument()
  expect(api.create).not.toHaveBeenCalled()
  expect(api.seal).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: /connect|start|trade|order|live/i })).toBeNull()
})

it('requires research consent and defaults native capture to false', async () => {
  renderPanel()
  await screen.findByText(recording.id)
  const create = screen.getByRole('button', { name: 'Create research recording' })
  expect(create).toBeDisabled()
  expect(screen.getByRole('checkbox', { name: 'Request native cache capture' })).not.toBeChecked()
  fireEvent.click(screen.getByRole('checkbox', { name: /I confirm/ }))
  fireEvent.click(create)
  await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1))
  expect(api.create.mock.calls[0][0]).toEqual({
    duration_minutes: 60,
    max_observations: 500,
    native_capture: false,
  })
  await screen.findByText(/Research recording created/)
  expect(screen.getByRole('checkbox', { name: /I confirm/ })).not.toBeChecked()
  expect(api.seal).not.toHaveBeenCalled()
})

it('enforces integer bounds and sends an explicit native opt-in without caller evidence', async () => {
  renderPanel()
  await screen.findByText(recording.id)
  const duration = screen.getByLabelText('Duration (minutes, 1-1440)')
  const maximum = screen.getByLabelText('Observation limit (1-10000)')
  const create = screen.getByRole('button', { name: 'Create research recording' })
  fireEvent.click(screen.getByRole('checkbox', { name: /I confirm/ }))
  for (const value of ['', '0', '1441', '1.5']) {
    fireEvent.change(duration, { target: { value } })
    expect(create).toBeDisabled()
  }
  fireEvent.change(duration, { target: { value: '1440' } })
  fireEvent.change(maximum, { target: { value: '10001' } })
  expect(create).toBeDisabled()
  fireEvent.change(maximum, { target: { value: '10000' } })
  fireEvent.click(screen.getByRole('checkbox', { name: 'Request native cache capture' }))
  fireEvent.click(create)
  await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1))
  expect(api.create.mock.calls[0][0]).toEqual({
    duration_minutes: 1440,
    max_observations: 10000,
    native_capture: true,
  })
})

it('does not retry ambiguous creation even when application mutation retries are enabled', async () => {
  api.create.mockRejectedValue(new Error('Connection lost'))
  renderPanel()
  await screen.findByText(recording.id)
  fireEvent.click(screen.getByRole('checkbox', { name: /I confirm/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Create research recording' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(/result may be unknown/)
  expect(api.create).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button', { name: 'Create research recording' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh recordings' }))
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Create research recording' })).toBeEnabled()
  )
  expect(api.create).toHaveBeenCalledTimes(1)
})

it('requires seal review and confirms exactly the reviewed observation count', async () => {
  renderPanel()
  const review = await screen.findByRole('button', { name: /Review seal for recording/ })
  review.focus()
  fireEvent.click(review)
  const dialog = screen.getByRole('dialog')
  expect(dialog).toHaveTextContent('reviewed count 0')
  expect(api.seal).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  await waitFor(() => expect(review).toHaveFocus())
  fireEvent.click(review)
  fireEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: 'Confirm seal only' })
  )
  await waitFor(() => expect(api.seal).toHaveBeenCalledTimes(1))
  expect(api.seal.mock.calls[0][0]).toEqual({ id: recording.id, expected_count: 0 })
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
})

it('never substitutes a new count when background capture changes the reviewed recording', async () => {
  const { client } = renderPanel()
  fireEvent.click(await screen.findByRole('button', { name: /Review seal for recording/ }))
  await act(async () => {
    client.setQueryData(['nifty-algo', 'research/recordings'], list([{ ...recording, count: 2 }]))
  })
  const dialog = screen.getByRole('dialog')
  expect(dialog).toHaveTextContent('reviewed count 0')
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('Recording changed')
  expect(within(dialog).getByRole('button', { name: 'Confirm seal only' })).toBeDisabled()
  expect(api.seal).not.toHaveBeenCalled()
})

it('shows stale seal conflicts and requires another review rather than retrying', async () => {
  api.seal.mockRejectedValue({
    response: { status: 409, data: { message: 'Recording changed during capture' } },
  })
  renderPanel()
  fireEvent.click(await screen.findByRole('button', { name: /Review seal for recording/ }))
  const dialog = screen.getByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm seal only' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent(
    /Recording changed during capture/
  )
  expect(api.seal).toHaveBeenCalledTimes(1)
  expect(within(dialog).getByRole('button', { name: 'Confirm seal only' })).toBeDisabled()
})

it('disables controls for failed reads and does not retain stale seal authority', async () => {
  const { client } = renderPanel()
  await screen.findByText(recording.id)
  api.read.mockRejectedValue(new Error('Read unavailable'))
  await act(async () => {
    await client.invalidateQueries({ queryKey: ['nifty-algo', 'research/recordings'] })
  })
  expect(await screen.findByRole('alert')).toHaveTextContent('Recordings unavailable')
  expect(screen.queryByRole('button', { name: /Review seal for recording/ })).toBeNull()
  expect(screen.getByRole('button', { name: 'Create research recording' })).toBeDisabled()
})

it('shows sealed, full and expired windows without inventing a capture health state', async () => {
  api.read.mockResolvedValue(
    list([
      { ...recording, id: 'sealed', status: 'SEALED' },
      { ...recording, id: 'full', count: 500 },
      { ...recording, id: 'expired', ends_at: '2000-01-01T05:00:00+00:00', capture: null },
    ])
  )
  renderPanel()
  await screen.findByText('sealed')
  expect(screen.getByText('Sealed; no further capture')).toBeInTheDocument()
  expect(screen.getByText('Observation limit reached')).toBeInTheDocument()
  expect(screen.getByText('Window ended')).toBeInTheDocument()
  expect(screen.getByText('Not requested')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Review seal for recording sealed' })).toBeNull()
})
