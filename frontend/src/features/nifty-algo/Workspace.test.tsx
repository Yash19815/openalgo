import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Workspace from './Workspace'

const api = vi.hoisted(() => ({ read: vi.fn(), control: vi.fn(), assess: vi.fn() }))
const socketContext = vi.hoisted(() => ({ read: vi.fn() }))
vi.mock('./api', () => ({
  niftyKeys: { all: ['nifty-algo'] },
  readNifty: api.read,
  controlNifty: api.control,
  saveConfiguration: vi.fn(),
  assessNativeHistory: api.assess,
  preparePaperMonitor: vi.fn(),
}))
vi.mock('@/components/socket/SocketProvider', () => ({
  useSocketContext: socketContext.read,
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
    socketContext.read.mockReturnValue({ socket: null })
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
    expect(screen.getByRole('button', { name: 'Start / resume paper strategy' })).toBeDisabled()
  })

  it('requires confirmation before submitting the persistent kill action', async () => {
    renderPage()
    await screen.findAllByText('PAUSED')
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

  it('renders indicator strength contributions from backend observations', async () => {
    api.read.mockImplementation(async (resource: string) =>
      resource === 'indicators'
        ? {
            indicator_states: {
              macd: {
                value: { histogram: 1.2 },
                timestamp: 'offline-fixture',
                valid: true,
                gate: 'PASS',
                direction: 1,
                reason: null,
              },
            },
            confidence: {
              score: 60,
              target_fraction: '0.13',
              method: 'five-indicator-v1',
              contributions: {
                macd: {
                  normalized: 0.5,
                  weight: 0.2,
                  points: 10,
                  explanation: 'Offline test contribution',
                },
              },
            },
          }
        : resource === 'status'
          ? { mode: 'PAPER_ONLY', state: 'PAUSED', revision: 1, ready: false, readiness: [] }
          : []
    )
    renderPage('signals')
    expect(await screen.findByText('Offline test contribution')).toBeInTheDocument()
    expect(screen.getByText('0.13')).toBeInTheDocument()
    expect(screen.getByText(/not a calibrated win probability/)).toBeInTheDocument()
  })

  it('allows Start only when backend readiness is true', async () => {
    api.read.mockImplementation(async (resource: string) =>
      resource === 'status'
        ? { mode: 'PAPER_ONLY', state: 'PAUSED', revision: 2, ready: true, readiness: [] }
        : []
    )
    renderPage()
    const start = await screen.findByRole('button', { name: 'Start / resume paper strategy' })
    await waitFor(() => expect(start).toBeEnabled())
    fireEvent.click(start)
    await waitFor(() =>
      expect(api.control).toHaveBeenCalledWith({ action: 'start', revision: 2 }, expect.anything())
    )
  })

  it('joins the authenticated update room and cleans up reconnect listeners', () => {
    const socket = { emit: vi.fn(), on: vi.fn(), off: vi.fn() }
    socketContext.read.mockReturnValue({ socket })
    const page = renderPage()
    expect(socket.emit).toHaveBeenCalledWith('nifty_algo_subscribe')
    const reconnect = socket.on.mock.calls.find(([event]) => event === 'connect')?.[1]
    expect(reconnect).toBeTypeOf('function')
    reconnect()
    expect(
      socket.emit.mock.calls.filter(([event]) => event === 'nifty_algo_subscribe')
    ).toHaveLength(2)
    page.unmount()
    expect(socket.emit).toHaveBeenCalledWith('nifty_algo_unsubscribe')
    expect(socket.off).toHaveBeenCalledWith('connect', reconnect)
  })
})
