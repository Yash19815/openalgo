import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import type { ExperimentDefinition, RecordingList, ResearchRecording } from './api'
import { ExperimentsPanel } from './ExperimentsPanel'

const api = vi.hoisted(() => ({ read: vi.fn(), define: vi.fn() }))
vi.mock('./api', () => ({
  niftyKeys: { all: ['nifty-algo'] },
  readNifty: api.read,
  defineExperiment: api.define,
}))

const source: ResearchRecording = {
  id: 'a'.repeat(32),
  mode: 'RESEARCH',
  schema_version: 1,
  status: 'SEALED',
  starts_at: '2026-01-01T04:00:00+00:00',
  ends_at: '2026-01-01T05:00:00+00:00',
  sealed_at: '2026-01-01T04:30:00+00:00',
  last_available_at: '2026-01-01T04:29:00+00:00',
  count: 17,
  size_bytes: 2048,
  max_observations: 500,
  configuration_id: 'frozen-configuration',
  content_sha256: 'b'.repeat(64),
  execution_eligible: false,
  limitations: ['QUOTE_EVIDENCE_ONLY'],
  capture: null,
}
const definition: ExperimentDefinition = {
  id: 'c'.repeat(32),
  sha256: 'd'.repeat(64),
  created_at: '2026-01-02T04:00:00+00:00',
  status: 'DEFINED',
  mode: 'RESEARCH',
  execution_eligible: false,
  performance: null,
  limitations: ['DEFINITION_ONLY', 'QUOTE_EVIDENCE_ONLY'],
  snapshot: {
    configuration: { adx_min: 30, atr_period: 20 },
    dataset: { id: source.id, count: source.count, content_sha256: source.content_sha256 },
    splits: [],
  },
}

function recordings(items = [source]): RecordingList {
  return { items, capture_status: 'NOT_CONNECTED' }
}

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: 3 } },
  })
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <ExperimentsPanel />
      </QueryClientProvider>
    ),
  }
}

function chooseSource() {
  fireEvent.change(screen.getByLabelText('Sealed recording'), { target: { value: source.id } })
}

function fillForm() {
  chooseSource()
  fireEvent.change(screen.getByLabelText('Train ends (UTC)'), {
    target: { value: '2026-01-01T04:10:00' },
  })
  fireEvent.change(screen.getByLabelText('Validation ends (UTC)'), {
    target: { value: '2026-01-01T04:20:00' },
  })
  fireEvent.click(screen.getByRole('checkbox', { name: /I understand/ }))
}

beforeEach(() => {
  vi.resetAllMocks()
  api.read.mockImplementation(async (resource: string) => {
    if (resource === 'research/recordings') return recordings()
    if (resource === 'research/experiments') return { items: [] }
    return definition
  })
  api.define.mockResolvedValue(definition)
})

it('shows definition-only limitations and requires reviewed evidence, splits and consent', async () => {
  renderPanel()
  await screen.findByRole('option', { name: new RegExp(source.id) })
  expect(screen.getByRole('button', { name: 'Define experiment' })).toBeDisabled()
  expect(screen.getByText(/No replay runs or performance results/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /run|start|trade|live|promote/i })).toBeNull()
  expect(api.define).not.toHaveBeenCalled()
})

it('creates a count/hash-pinned definition with UTC splits and research-only overrides', async () => {
  renderPanel()
  await screen.findByRole('option', { name: new RegExp(source.id) })
  fillForm()
  fireEvent.change(screen.getByLabelText('Research ADX minimum (optional)'), {
    target: { value: '30' },
  })
  fireEvent.change(screen.getByLabelText('Research ATR period (optional)'), {
    target: { value: '20' },
  })
  fireEvent.change(screen.getByLabelText('Research SuperTrend factor (optional)'), {
    target: { value: '2' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Define experiment' }))
  await waitFor(() => expect(api.define).toHaveBeenCalledTimes(1))
  expect(api.define.mock.calls[0][0]).toEqual({
    recording_id: source.id,
    expected_count: 17,
    expected_sha256: source.content_sha256,
    train_end: '2026-01-01T04:10:00.000Z',
    validation_end: '2026-01-01T04:20:00.000Z',
    configuration_overrides: { adx_min: 30, atr_period: 20, atr_multiplier: 2 },
  })
  await screen.findByText(/Experiment definition saved/)
  expect(screen.getByRole('checkbox', { name: /I understand/ })).not.toBeChecked()
  expect(
    api.read.mock.calls.some(([path]) => path === `research/experiments/${definition.id}`)
  ).toBe(true)
  expect(screen.getAllByText(/No active settings changed/).length).toBeGreaterThan(0)
})

it('rejects empty/equal/out-of-range splits and keeps the test boundary at the seal time', async () => {
  renderPanel()
  await screen.findByRole('option', { name: new RegExp(source.id) })
  fillForm()
  const submit = screen.getByRole('button', { name: 'Define experiment' })
  for (const value of ['2026-01-01T04:10:00', '2026-01-01T04:30:00', '2026-01-01T04:45:00']) {
    fireEvent.change(screen.getByLabelText('Validation ends (UTC)'), { target: { value } })
    expect(submit).toBeDisabled()
  }
  fireEvent.submit(screen.getByRole('form', { name: 'New experiment definition' }))
  expect(api.define).not.toHaveBeenCalled()
})

it('does not offer unsealed or empty sources and never silently selects a recording', async () => {
  api.read.mockImplementation(async (resource: string) =>
    resource === 'research/recordings'
      ? recordings([
          { ...source, status: 'RECORDING' },
          { ...source, id: 'empty', count: 0 },
        ])
      : { items: [] }
  )
  renderPanel()
  await screen.findByText(/No sealed recordings with saved observations/)
  expect(screen.queryByRole('option', { name: new RegExp(source.id) })).toBeNull()
  expect(screen.getByRole('button', { name: 'Define experiment' })).toBeDisabled()
})

it('blocks stale reviewed evidence instead of replacing its count/hash', async () => {
  const { client } = renderPanel()
  await screen.findByRole('option', { name: new RegExp(source.id) })
  fillForm()
  await act(async () => {
    client.setQueryData(
      ['nifty-algo', 'research/recordings'],
      recordings([{ ...source, count: 18, content_sha256: 'e'.repeat(64) }])
    )
  })
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Define experiment' })).toBeDisabled()
  )
  expect(await screen.findByRole('alert')).toHaveTextContent(/Selected recording changed/)
  fireEvent.submit(screen.getByRole('form', { name: 'New experiment definition' }))
  expect(api.define).not.toHaveBeenCalled()
})

it('hides cached source controls when a refresh fails', async () => {
  const { client } = renderPanel()
  await screen.findByRole('option', { name: new RegExp(source.id) })
  fillForm()
  api.read.mockRejectedValue(new Error('Unavailable'))
  await act(async () => {
    await client.invalidateQueries({ queryKey: ['nifty-algo', 'research/recordings'] })
  })
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Define experiment' })).toBeDisabled()
  )
  expect(await screen.findByText(/Recordings unavailable/)).toBeInTheDocument()
})

it('does not retry an uncertain write and requires successful refresh before another attempt', async () => {
  api.define.mockRejectedValue(new Error('Connection lost'))
  renderPanel()
  await screen.findByRole('option', { name: new RegExp(source.id) })
  fillForm()
  fireEvent.click(screen.getByRole('button', { name: 'Define experiment' }))
  await screen.findByRole('alert')
  expect(api.define).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button', { name: 'Define experiment' })).toBeDisabled()
  expect(screen.getByText(/may already be saved/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh experiments' }))
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Define experiment' })).toBeEnabled()
  )
  expect(api.define).toHaveBeenCalledTimes(1)
})

it('loads a persisted definition on request and hides stale detail after verification failure', async () => {
  api.read.mockImplementation(async (resource: string) => {
    if (resource === 'research/recordings') return recordings()
    if (resource === 'research/experiments') return { items: [definition] }
    return definition
  })
  const { client } = renderPanel()
  fireEvent.click(
    await screen.findByRole('button', { name: `Inspect experiment ${definition.id}` })
  )
  await screen.findByText('Saved experiment details')
  expect(screen.getByText(definition.sha256)).toBeInTheDocument()
  api.read.mockImplementation(async (resource: string) => {
    if (resource.includes(`/${definition.id}`))
      throw new Error('Stored experiment failed verification')
    return resource === 'research/recordings' ? recordings() : { items: [definition] }
  })
  await act(async () => {
    await client.invalidateQueries({
      queryKey: ['nifty-algo', `research/experiments/${definition.id}`],
    })
  })
  await waitFor(() => expect(screen.queryByText('Saved experiment details')).toBeNull())
  expect(await screen.findByText(/Saved definition unavailable/)).toBeInTheDocument()
})
