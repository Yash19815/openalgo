import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { SelectorPanel } from './SelectorPanel'

const api = vi.hoisted(() => ({ read: vi.fn() }))
vi.mock('./api', () => ({
  niftyKeys: { all: ['nifty-algo'] },
  readNifty: api.read,
}))

const evidence = {
  id: 8,
  created_at: '2026-11-19T05:00:00+00:00',
  payload: {
    mode: 'PAPER',
    policy: 'listed-preference-v1',
    decision_id: 'offline-test',
    configuration_id: 'configuration-test',
    evaluated_at: '2026-11-19T05:00:00+00:00',
    spot_reference: '22000',
    atm_strike: '22000',
    expiry: '2026-11-24',
    ranked_tokens: ['itm'],
    omitted_candidates: 2,
    candidates: [
      {
        instrument: {
          token: 'atm',
          symbol: 'OFFLINE_ATM',
          exchange: 'NFO',
          kind: 'CE',
          expiry: '2026-11-24',
          strike: '22000',
          lot_size: 25,
          tick_size: '0.05',
        },
        moneyness: 'ATM',
        rank: null,
        quote: null,
        reasons: ['QUOTE_UNAVAILABLE'],
      },
      {
        instrument: {
          token: 'itm',
          symbol: 'OFFLINE_ITM',
          exchange: 'NFO',
          kind: 'CE',
          expiry: '2026-11-24',
          strike: '21950',
          lot_size: 25,
          tick_size: '0.05',
        },
        moneyness: 'ITM',
        rank: 1,
        quote: {
          bid: '164',
          ask: '165',
          bid_size: 25,
          ask_size: 25,
          volume: 5000,
          source_time: '2026-11-19T05:00:00+00:00',
          provider: 'OFFLINE_TEST',
        },
        reasons: [],
      },
    ],
  },
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rendered = render(
    <QueryClientProvider client={client}>
      <SelectorPanel />
    </QueryClientProvider>
  )
  return { client, ...rendered }
}

beforeEach(() => {
  vi.resetAllMocks()
  api.read.mockResolvedValue(evidence)
})

it('shows ranked identities and rejection evidence without order controls or invented quotes', async () => {
  renderPanel()
  expect(
    await screen.findByRole('heading', { name: 'Smart contract selector' })
  ).toBeInTheDocument()
  expect(await screen.findByText(/OFFLINE_ATM/)).toBeInTheDocument()
  expect(screen.getByText('QUOTE_UNAVAILABLE')).toBeInTheDocument()
  expect(screen.getByText(/Rank 1/)).toHaveTextContent('OFFLINE_ITM')
  expect(screen.getByText('No quote recorded.')).toBeInTheDocument()
  expect(screen.getByText('OFFLINE_TEST')).toBeInTheDocument()
  expect(screen.getByText(/2 metadata rows omitted/)).toBeInTheDocument()
  expect(screen.getByText(/does not authorize an order/)).toBeInTheDocument()
  expect(
    screen.queryByRole('button', { name: /buy|sell|trade|resume|live/i })
  ).not.toBeInTheDocument()
})

it('shows empty evidence honestly', async () => {
  api.read.mockResolvedValue(null)
  renderPanel()
  expect(await screen.findByText(/No recorded contract assessment/)).toBeInTheDocument()
  expect(screen.queryByText(/Rank 1/)).not.toBeInTheDocument()
})

it('shows durable refusal reasons without inventing spot, expiry or candidate evidence', async () => {
  api.read.mockResolvedValue({
    ...evidence,
    payload: {
      ...evidence.payload,
      status: 'UNAVAILABLE',
      reasons: ['SPOT_REFERENCE_UNAVAILABLE'],
      spot_reference: null,
      atm_strike: null,
      expiry: null,
      candidates: [],
      ranked_tokens: [],
      omitted_candidates: 0,
    },
  })
  renderPanel()
  expect(await screen.findByText('SPOT_REFERENCE_UNAVAILABLE')).toBeInTheDocument()
  expect(
    screen.getByText(
      'Fresh NIFTY spot is unavailable. Check the market feed before the next assessment.'
    )
  ).toBeInTheDocument()
  expect(screen.getAllByText('Unavailable')).toHaveLength(3)
  expect(screen.getByText(/No contract passed selector gates/)).toBeInTheDocument()
  expect(screen.queryByText(/Rank 1/)).not.toBeInTheDocument()
})

it('keeps Paper and Shadow query data separate', async () => {
  api.read.mockImplementation(async (resource: string) =>
    resource.includes('SHADOW') ? null : evidence
  )
  renderPanel()
  await screen.findByText(/OFFLINE_ATM/)
  fireEvent.change(screen.getByLabelText('Selector evidence mode'), { target: { value: 'SHADOW' } })
  expect(await screen.findByText(/No recorded contract assessment/)).toBeInTheDocument()
  expect(screen.queryByText(/OFFLINE_ATM/)).not.toBeInTheDocument()
  expect(api.read).toHaveBeenCalledWith('selector?mode=SHADOW')
})

it('replaces cached evidence with a visible error after a failed refresh', async () => {
  const { client } = renderPanel()
  await screen.findByText(/OFFLINE_ATM/)
  api.read.mockRejectedValue(new Error('Selector unavailable'))
  await client.invalidateQueries({ queryKey: ['nifty-algo'] })
  expect(await screen.findByRole('alert')).toHaveTextContent('Selector unavailable')
  expect(screen.queryByText(/OFFLINE_ATM/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Reload selector evidence' }))
  await waitFor(() => expect(api.read.mock.calls.length).toBeGreaterThan(2))
})

it('shows a pending read without claiming a selection', () => {
  api.read.mockReturnValue(new Promise(() => {}))
  renderPanel()
  expect(screen.getByRole('status')).toHaveTextContent('Loading selector evidence')
  expect(screen.queryByText(/Rank 1/)).not.toBeInTheDocument()
})
