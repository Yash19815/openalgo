import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ResearchOperations } from './ResearchOperations'

const api = vi.hoisted(() => ({ read: vi.fn(), retention: vi.fn(), define: vi.fn() }))
vi.mock('./api', () => ({
  niftyKeys: { all: ['nifty-algo'] },
  readNifty: api.read,
  recordingRetention: api.retention,
  defineExecutionComparison: api.define,
}))

const recording = {
  id: 'rec-1',
  count: 10,
  status: 'SEALED',
  content_sha256: 'hash-1',
  configuration: { adx_min: 20 },
}

function mount() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ResearchOperations />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.read.mockImplementation(async (path: string) =>
    path.endsWith('/archives') ? { items: [{ id: 'old-1' }] } : { items: [recording] }
  )
})

it('archives and restores only through explicit named actions', async () => {
  api.retention.mockResolvedValue({})
  mount()
  fireEvent.click(await screen.findByRole('button', { name: 'Archive sealed recording rec-1' }))
  await waitFor(() => expect(api.retention).toHaveBeenCalledWith('rec-1', 'archive'))
  fireEvent.click(await screen.findByRole('button', { name: 'Restore recording old-1' }))
  await waitFor(() => expect(api.retention).toHaveBeenCalledWith('old-1', 'restore'))
  expect(screen.getByRole('link', { name: 'Download verified archive old-1' })).toHaveAttribute(
    'href',
    '/api/nifty-algo/research/recordings/old-1/archive'
  )
})

it('blocks retention actions when the catalogue cannot be read', async () => {
  api.read.mockRejectedValue(new Error('down'))
  mount()
  expect(await screen.findByRole('alert')).toHaveTextContent('Recording catalogue unavailable')
  expect(screen.queryByRole('button', { name: /Archive sealed recording/ })).not.toBeInTheDocument()
})

it('requires approval and valid chronological splits before defining a comparison', async () => {
  api.define.mockResolvedValue({})
  mount()
  fireEvent.click(await screen.findByLabelText(/Recording rec-1/))
  const define = screen.getByRole('button', { name: 'Define pinned comparison' })
  expect(define).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Training end (UTC)'), {
    target: { value: '2026-11-10T00:00' },
  })
  fireEvent.change(screen.getByLabelText('Validation end (UTC)'), {
    target: { value: '2026-11-05T00:00' },
  })
  fireEvent.click(screen.getByLabelText(/I approve this research definition only/))
  expect(define).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Validation end (UTC)'), {
    target: { value: '2026-11-15T00:00' },
  })
  expect(define).toBeEnabled()
  fireEvent.click(define)
  await waitFor(() =>
    expect(api.define).toHaveBeenCalledWith(
      expect.objectContaining({
        sources: [{ id: 'rec-1', count: 10, content_sha256: 'hash-1' }],
        train_end: '2026-11-10T00:00Z',
      })
    )
  )
})

it('refuses submission for overrides that are not a JSON object', async () => {
  mount()
  fireEvent.click(await screen.findByLabelText(/Recording rec-1/))
  fireEvent.change(screen.getByLabelText('Training end (UTC)'), {
    target: { value: '2026-11-10T00:00' },
  })
  fireEvent.change(screen.getByLabelText('Validation end (UTC)'), {
    target: { value: '2026-11-15T00:00' },
  })
  fireEvent.change(screen.getByLabelText(/Experimental research overrides/), {
    target: { value: '[1]' },
  })
  fireEvent.click(screen.getByLabelText(/I approve this research definition only/))
  expect(screen.getByRole('button', { name: 'Define pinned comparison' })).toBeDisabled()
})
