import { useQuery } from '@tanstack/react-query'
import { Badge } from '@/components/ui/badge'
import { niftyKeys, type Opportunity, readNifty, type ShadowStatus } from './api'
import { Code, Facts, Panel, text } from './parts'

function kindLabel(kind: string) {
  if (kind === 'MIRROR') return 'Mirror of primary entry'
  if (kind === 'INDEPENDENT') return 'Independent shadow'
  return kind
}

function NonAdditive() {
  return (
    <Badge variant="outline" className="nifty-nonadditive">
      non-additive
    </Badge>
  )
}

export function ShadowPanel() {
  const query = useQuery({
    queryKey: [...niftyKeys.all, 'shadow'],
    queryFn: () => readNifty<ShadowStatus>('shadow'),
    refetchInterval: 15_000,
  })
  const data = query.data
  const active = data?.active ?? null
  const closed = (data?.positions ?? []).filter((row) => !row.active).slice(0, 10)
  return (
    <Panel title="Hypothetical shadow positions">
      <p className="nifty-muted">
        Shadows are hypothetical and never place orders. Mirror P&amp;L duplicates the primary paper
        trade and is never added to totals.
      </p>
      {query.isPending ? (
        <output>Loading shadow state…</output>
      ) : query.error ? (
        <p role="alert">{query.error.message}</p>
      ) : !data ? (
        <p className="nifty-empty">Shadow state unavailable.</p>
      ) : (
        <>
          <h3 className="nifty-subhead">Active shadow</h3>
          {active ? (
            <Facts
              rows={[
                [
                  'Type',
                  <>
                    {kindLabel(active.kind)} {active.kind === 'MIRROR' && <NonAdditive />}
                  </>,
                ],
                ['Contract', `${active.symbol} x ${active.quantity}`],
                ['Entry price', text(active.entry_price)],
                ['Stop price', text(active.protection?.stop_price)],
                ['Target price', text(active.protection?.target_price)],
                [
                  'Current hypothetical P&L (Rs, est. net)',
                  text(active.protection?.estimated_net, 'Awaiting first bid'),
                ],
                ['Profit lock', active.protection?.profit_lock_active ? 'Active' : 'Inactive'],
                ['Opened', text(active.opened_at)],
              ]}
            />
          ) : (
            <p className="nifty-empty">No active shadow.</p>
          )}
          <h3 className="nifty-subhead">Hypothetical ledger</h3>
          <Facts
            rows={[
              ['Basis', text(data.ledger.basis)],
              ['Capital (Rs)', text(data.ledger.capital)],
              ['Independent realized net (Rs)', text(data.ledger.realized_net)],
              ['Hypothetical equity (Rs)', text(data.ledger.equity)],
              [
                'Mirror P&L (Rs)',
                <>
                  {text(data.ledger.mirror_realized_net)} <NonAdditive />
                </>,
              ],
            ]}
          />
          <h3 className="nifty-subhead">Recent closed shadows</h3>
          {closed.length ? (
            <div className="nifty-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Contract</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>Net (Rs)</th>
                    <th>Exit reason</th>
                    <th>Status</th>
                    <th>Closed</th>
                  </tr>
                </thead>
                <tbody>
                  {closed.map((row) => (
                    <tr key={row.id}>
                      <td>
                        {kindLabel(row.kind)}{' '}
                        {!row.additive && row.kind === 'MIRROR' && <NonAdditive />}
                      </td>
                      <td>
                        {row.symbol} x {row.quantity}
                      </td>
                      <td>{text(row.entry_price)}</td>
                      <td>{text(row.exit_price)}</td>
                      <td>{text(row.net)}</td>
                      <td>{text(row.exit_reason, '')}</td>
                      <td>{row.status}</td>
                      <td>{text(row.closed_at, '')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="nifty-empty">No closed shadows yet.</p>
          )}
        </>
      )}
    </Panel>
  )
}

export function OpportunitiesPanel() {
  const query = useQuery({
    queryKey: [...niftyKeys.all, 'research/opportunities'],
    queryFn: () => readNifty<Opportunity[]>('research/opportunities'),
    refetchInterval: 30_000,
  })
  const rows = Array.isArray(query.data) ? query.data.slice(0, 20) : []
  return (
    <Panel title="Research opportunities">
      <p className="nifty-muted">
        Research-only observations of qualifying signals. They carry no order authority.
      </p>
      {query.isPending ? (
        <output>Loading research opportunities…</output>
      ) : query.error ? (
        <p role="alert">{query.error.message}</p>
      ) : !rows.length ? (
        <p className="nifty-empty">No research opportunities recorded.</p>
      ) : (
        <div className="nifty-table-scroll">
          <table>
            <thead>
              <tr>
                <th>Candle end</th>
                <th>Side</th>
                <th>Reference</th>
                <th>Max favorable</th>
                <th>Max adverse</th>
                <th>Status</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.opportunity_id}>
                  <td>{row.candle_end}</td>
                  <td>{row.direction}</td>
                  <td>{text(row.reference_price)}</td>
                  <td>{text(row.max_favorable)}</td>
                  <td>{text(row.max_adverse)}</td>
                  <td>{row.status}</td>
                  <td>{row.outcome ? <Code code={row.outcome} /> : 'Observing'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}
