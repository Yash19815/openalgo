import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { DiscordPanel } from './DiscordPanel'

const api = vi.hoisted(() => ({ read: vi.fn(), save: vi.fn(), action: vi.fn() }))
vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  readNifty: api.read,
  saveDiscordSettings: api.save,
  discordSetupAction: api.action,
}))

const channels = [
  'critical-alerts',
  'system-warnings',
  'bot-status',
  'live-trades',
  'paper-trades',
  'shadow-trades',
  'risk-management',
  'daily-summary',
  'monthly-summary',
  'research-insights',
]
const center = () => ({
  settings: {
    revision: 3,
    token_configured: true,
    verified: true,
    verification: { errors: [] },
    updated_at: '2026-11-23T04:00:00Z',
    rate_limit_until: null,
    configuration: {
      enabled: true,
      application_id: '100000000000000001',
      guild_id: '100000000000000002',
      public_key: 'a'.repeat(64),
      channels: Object.fromEntries(
        channels.map((name, index) => [name, String(200000000000000000n + BigInt(index))])
      ),
      authorized_users: ['100000000000000003'],
      authorized_roles: [],
      critical_role: null,
      preferences: {},
      reminder_interval_seconds: 900,
    },
  },
  health: { counts: { PENDING: 2 }, attempts: [] },
  incidents: [{ id: 1, severity: 'CRITICAL', status: 'OPEN', mode: 'PAPER', code: 'STALE_DATA' }],
  deliveries: [],
})
function view() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: 3 } } })
      }
    >
      <DiscordPanel />
    </QueryClientProvider>
  )
}
beforeEach(() => {
  vi.resetAllMocks()
  api.read.mockResolvedValue(center())
  api.save.mockResolvedValue({ status: 'success' })
  api.action.mockResolvedValue({ status: 'success' })
})

it('shows server-side credential status, unresolved incidents and all channel ID controls', async () => {
  view()
  expect(await screen.findByText('Configured server-side')).toBeInTheDocument()
  expect(screen.getByText('#1 PAPER: STALE_DATA / OPEN')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Edit Discord settings' }))
  for (const name of channels)
    expect(screen.getByLabelText(`${name} channel ID`)).toBeInTheDocument()
  expect(screen.getByLabelText(/Bot token/)).toHaveValue('')
  expect(screen.queryByLabelText('CRITICAL notifications')).not.toBeInTheDocument()
})

it('clears replacement credentials immediately and saves the reviewed revision', async () => {
  view()
  fireEvent.click(await screen.findByRole('button', { name: 'Edit Discord settings' }))
  fireEvent.change(screen.getByLabelText(/Bot token/), { target: { value: 'test-only-rotation' } })
  fireEvent.submit(
    screen.getByRole('button', { name: 'Save Discord settings' }).closest('form') as HTMLFormElement
  )
  await waitFor(() =>
    expect(api.save).toHaveBeenCalledWith(3, center().settings.configuration, 'test-only-rotation')
  )
  await waitFor(() => expect(screen.queryByLabelText(/Bot token/)).not.toBeInTheDocument())
})

it('never retries uncertain writes and requires successful manual refresh', async () => {
  api.save.mockRejectedValue(new Error('503'))
  view()
  fireEvent.click(await screen.findByRole('button', { name: 'Edit Discord settings' }))
  fireEvent.submit(
    screen.getByRole('button', { name: 'Save Discord settings' }).closest('form') as HTMLFormElement
  )
  expect(await screen.findByRole('alert')).toHaveTextContent('No automatic retry')
  expect(api.save).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button', { name: 'Queue test message' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh Discord status' }))
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Queue test message' })).toBeEnabled()
  )
})

it('unavailable settings block setup actions without invented readiness', async () => {
  api.read.mockRejectedValue(new Error('503'))
  view()
  expect(await screen.findByRole('alert')).toHaveTextContent('configuration unavailable')
  expect(screen.queryByRole('button', { name: 'Queue test message' })).not.toBeInTheDocument()
})

it('queues test intent once without claiming verified delivery', async () => {
  view()
  fireEvent.click(await screen.findByRole('button', { name: 'Queue test message' }))
  await waitFor(() => expect(api.action).toHaveBeenCalledWith('test', 3))
  expect(await screen.findByText(/Inspect refreshed status and delivery queue/)).toBeInTheDocument()
})
