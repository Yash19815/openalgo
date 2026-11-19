import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Workspace from './Workspace'

const api = vi.hoisted(() => ({ read: vi.fn(), control: vi.fn(), assess: vi.fn() }))
vi.mock('./api', () => ({
  niftyKeys: { all: ['nifty-algo'] },
  readNifty: api.read,
  controlNifty: api.control,
  saveConfiguration: vi.fn(),
  assessNativeHistory: api.assess,
}))
vi.mock('@/components/socket/SocketProvider', () => ({
  useSocketContext: () => ({ socket: null }),
}))

function renderPage(view = 'overview') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/nifty-algo?view=${view}`]}>
        <Workspace />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('NIFTY workspace', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    api.read.mockImplementation(async (resource: string) =>
      resource === 'status'
        ? { mode: 'PAPER_ONLY', state: 'PAUSED', revision: 1, readiness: ['Data unavailable'] }
        : resource === 'signals'
          ? []
          : {}
    )
    api.control.mockResolvedValue({ status: 'success' })
  })

  it('shows backend paper state and unavailable observations without sample prices', async () => {
    renderPage()
    expect(await screen.findAllByText('PAUSED')).toHaveLength(2)
    expect(screen.getByText('PAPER_ONLY')).toBeInTheDocument()
    expect(screen.getAllByText('No observations available.').length).toBeGreaterThan(0)
    expect(screen.queryByText('26,250')).not.toBeInTheDocument()
  })

  it('requires confirmation before submitting the persistent kill action', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Kill switch', exact: true }))
    expect(api.control).not.toHaveBeenCalled()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Activate kill switch', exact: true })
    )
    await waitFor(() =>
      expect(api.control).toHaveBeenCalledWith(
        { action: 'kill-switch', revision: 1 },
        expect.anything()
      )
    )
  })

  it('surfaces failed data requests', async () => {
    api.read.mockRejectedValue(new Error('Feed unavailable'))
    renderPage('signals')
    expect((await screen.findAllByRole('alert')).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Feed unavailable/).length).toBeGreaterThan(0)
  })

  it('requests historical assessment only after an explicit click', async () => {
    api.assess.mockResolvedValue({ status: 'success' })
    renderPage('signals')
    expect(api.assess).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Assess native history' }))
    await screen.findByText('Assessment recorded.')
    expect(api.assess).toHaveBeenCalledTimes(1)
  })
})
