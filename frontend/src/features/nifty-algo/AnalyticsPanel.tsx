import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { niftyKeys, readAnalyticsPdf, readNifty } from './api'
import { ComparativeAnalytics } from './ComparativeAnalytics'
import { Facts, Panel, text } from './parts'
import { RealizedCurve } from './RealizedCurve'

interface AnalyticsSnapshot {
  opening_realized_equity: string
  period: { start: string; end: string }
  metrics: {
    trades: number
    fills: number
    wins: number
    losses: number
    breakeven: number
    total_gross: string
    best: string | null
    worst: string | null
    total_net: string
    costs: string
    win_rate: number | null
    maximum_drawdown: string
    average_realized_r: string | null
    profit_factor: number | null
    average_duration_seconds: number | null
    risk_coverage: { available: number; total: number }
    equity_curve: { timestamp: string; equity: string }[]
    drawdown_curve: { timestamp: string; drawdown: string }[]
    groups: { daily: Record<string, { trades: number; net: string }> }
  }
  details: {
    total: number
    items: {
      id: number
      symbol: string
      quantity: number
      opened_at: string
      closed_at: string
      entry_price: string
      exit_price: string
      fees: string
      net: string
      reason: string
    }[]
  }
}

function TradeEvidence({ tradeId, onClose }: { tradeId: number; onClose: () => void }) {
  const query = useQuery({
    queryKey: [...niftyKeys.all, 'trade-detail', tradeId],
    queryFn: () => readNifty<Record<string, unknown>>(`analytics/trades/${tradeId}`),
    retry: false,
  })
  return (
    <section aria-label={`Trade ${tradeId} evidence`}>
      <h3>Trade {tradeId}: authoritative PAPER fill evidence</h3>
      <Button variant="outline" onClick={onClose}>
        Close trade evidence
      </Button>
      {query.isPending ? (
        <output>Loading trade evidence...</output>
      ) : query.isError ? (
        <p role="alert">Trade evidence unavailable or failed reconciliation.</p>
      ) : (
        <>
          <p className="nifty-muted">
            Excursions use sampled executable bids. Missing observations are unavailable. Later
            movement does not prove an exit was wrong.
          </p>
          {Object.entries(query.data ?? {}).map(([name, value]) => (
            <details key={name}>
              <summary>{name.replaceAll('_', ' ')}</summary>
              <pre
                style={{
                  maxWidth: '100%',
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  overflowWrap: 'anywhere',
                }}
              >
                {JSON.stringify(value, null, 2)}
              </pre>
            </details>
          ))}
        </>
      )}
    </section>
  )
}

export function AnalyticsPanel() {
  const [selectedTrade, setSelectedTrade] = useState<number | null>(null)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [period, setPeriod] = useState({ start: '', end: '' })
  const [offset, setOffset] = useState(0)
  const params = new URLSearchParams({ limit: '25', offset: String(offset) })
  if (period.start) params.set('start', period.start)
  if (period.end) params.set('end', period.end)
  const resource = `analytics?${params}`
  const query = useQuery({
    queryKey: [...niftyKeys.all, resource],
    queryFn: () => readNifty<AnalyticsSnapshot>(resource),
    retry: false,
  })
  const data = query.isError ? undefined : query.data
  const metrics = data?.metrics
  const pdf = useMutation({
    mutationFn: async () => {
      if (!data) return
      const istDate = (stamp: string) =>
        new Intl.DateTimeFormat('en-CA', {
          timeZone: 'Asia/Kolkata',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
        }).format(new Date(stamp))
      const exportParams = new URLSearchParams({
        limit: '25',
        offset: String(offset),
        start: istDate(data.period.start),
        end: istDate(data.period.end),
      })
      const blob = await readAnalyticsPdf(exportParams.toString())
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      try {
        link.href = url
        link.download = 'nifty-paper-analytics.pdf'
        document.body.append(link)
        link.click()
      } finally {
        link.remove()
        URL.revokeObjectURL(url)
      }
    },
  })
  return (
    <Panel title="Realized paper analytics">
      <ComparativeAnalytics start={period.start} end={period.end} />
      {selectedTrade !== null && (
        <TradeEvidence tradeId={selectedTrade} onClose={() => setSelectedTrade(null)} />
      )}
      <p className="nifty-muted">
        Full-period metrics use persisted paper fills, not the journal page. Equity is seed plus
        realized net, not mark-to-market. Marked unrealized P&amp;L and observed-equity drawdown are
        unavailable without a persisted mark series. Partial exits share one trade; each exit
        remains a separate fill. Amounts are in Rs.
      </p>
      <form
        className="nifty-form"
        onSubmit={(event) => {
          event.preventDefault()
          setOffset(0)
          setPeriod({ start, end })
        }}
      >
        <label htmlFor="nifty-analytics-start">Start (IST)</label>
        <Input
          id="nifty-analytics-start"
          type="date"
          required
          value={start}
          onChange={(event) => setStart(event.target.value)}
        />
        <label htmlFor="nifty-analytics-end">End (IST, exclusive)</label>
        <Input
          id="nifty-analytics-end"
          type="date"
          required
          value={end}
          onChange={(event) => setEnd(event.target.value)}
        />
        <Button type="submit" disabled={query.isFetching}>
          Apply period
        </Button>
      </form>
      {query.isError && (
        <p role="alert">
          Analytics unavailable. Check the period and paper fill evidence.
          <Button variant="outline" disabled={query.isFetching} onClick={() => query.refetch()}>
            Retry analytics
          </Button>
        </p>
      )}
      {query.isPending && <output>Loading analytics...</output>}
      {data && metrics && (
        <>
          <p className="nifty-muted">
            Period: {data.period.start} to {data.period.end} (exclusive). Planned risk available for{' '}
            {metrics.risk_coverage.available} of {metrics.risk_coverage.total} trades.
          </p>
          <Facts
            rows={[
              ['Trades with exits in period', metrics.trades],
              ['Realized fills', metrics.fills],
              [
                'Winning / losing / breakeven trades',
                `${metrics.wins} / ${metrics.losses} / ${metrics.breakeven}`,
              ],
              ['Gross P&L', metrics.total_gross],
              ['Realized net', metrics.total_net],
              ['Best trade in period', text(metrics.best)],
              ['Worst trade in period', text(metrics.worst)],
              ['Costs', metrics.costs],
              [
                'Win rate',
                metrics.win_rate === null
                  ? 'Unavailable'
                  : `${(metrics.win_rate * 100).toFixed(1)}%`,
              ],
              ['Realized maximum drawdown', metrics.maximum_drawdown],
              ['Average realized R', text(metrics.average_realized_r)],
              ['Profit factor', text(metrics.profit_factor)],
              ['Average duration (seconds)', text(metrics.average_duration_seconds)],
              ['Opening realized equity', data.opening_realized_equity],
            ]}
          />
          <Button
            variant="outline"
            disabled={pdf.isPending || query.isFetching}
            onClick={() => pdf.mutate()}
          >
            {pdf.isPending ? 'Generating PDF...' : 'Download analytics PDF'}
          </Button>
          {pdf.isError && (
            <p role="alert">PDF export failed. Retry or check the selected period.</p>
          )}
          {pdf.isSuccess && <output>Analytics PDF download requested.</output>}
          <p className="nifty-muted">
            PDF export reads fresh ledger evidence. New fills can change totals since this view
            loaded.
          </p>
          <div className="nifty-grid">
            <RealizedCurve
              title="Realized equity"
              opening={data.opening_realized_equity}
              start={data.period.start}
              points={metrics.equity_curve.map((point) => ({
                timestamp: point.timestamp,
                value: point.equity,
              }))}
            />
            <RealizedCurve
              title="Realized drawdown"
              opening="0"
              start={data.period.start}
              points={metrics.drawdown_curve.map((point) => ({
                timestamp: point.timestamp,
                value: point.drawdown,
              }))}
            />
          </div>
          <div className="nifty-table-scroll">
            <table>
              <caption>Daily realized results (IST)</caption>
              <thead>
                <tr>
                  <th scope="col">Session</th>
                  <th scope="col">Trades with exits</th>
                  <th scope="col">Net (Rs)</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(metrics.groups.daily)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([day, row]) => (
                    <tr key={day}>
                      <th scope="row">{day}</th>
                      <td>{row.trades}</td>
                      <td>{row.net}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
            {!Object.keys(metrics.groups.daily).length && (
              <p className="nifty-empty">No realized sessions in this period.</p>
            )}
          </div>
          <h3>Realized fill details</h3>
          {data.details.items.length ? (
            <div className="nifty-table-scroll">
              <table>
                <caption>Closed fills; {data.details.total} in the selected period</caption>
                <thead>
                  <tr>
                    {[
                      'Contract',
                      'Quantity',
                      'Opened (UTC)',
                      'Closed (UTC)',
                      'Entry',
                      'Exit',
                      'Fees',
                      'Net',
                      'Reason',
                      'Evidence',
                    ].map((heading) => (
                      <th key={heading} scope="col">
                        {heading}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.details.items.map((row) => (
                    <tr key={row.id}>
                      <td>{row.symbol}</td>
                      <td>{row.quantity}</td>
                      <td>{row.opened_at}</td>
                      <td>{row.closed_at}</td>
                      <td>{row.entry_price}</td>
                      <td>{row.exit_price}</td>
                      <td>{row.fees}</td>
                      <td>{row.net}</td>
                      <td>{row.reason}</td>
                      <td>
                        <Button variant="outline" onClick={() => setSelectedTrade(row.id)}>
                          Inspect trade {row.id}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="nifty-empty">No realized fills on this page.</p>
          )}
          <div className="nifty-actions">
            <Button
              variant="outline"
              disabled={offset === 0 || query.isFetching}
              onClick={() => setOffset(Math.max(0, offset - 25))}
            >
              Previous fills
            </Button>
            <Button
              variant="outline"
              disabled={offset + 25 >= data.details.total || query.isFetching}
              onClick={() => setOffset(offset + 25)}
            >
              Next fills
            </Button>
          </div>
        </>
      )}
    </Panel>
  )
}
