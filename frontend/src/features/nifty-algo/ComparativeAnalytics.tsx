import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { niftyKeys, readComparativePdf, readNifty } from './api'
import { Facts } from './parts'

interface Metrics {
  trades: number
  total_gross: string
  costs: string
  total_net: string
  maximum_drawdown: string
}
interface Comparison {
  paper: {
    metrics: Metrics
    quality: { suggestions: { code: string; evidence_count: number; message: string }[] }
  }
  independent_shadow: { metrics: Metrics | null; unavailable_outcomes: number }
  mirrors: { total: number; additive: false; items: { id: number; net: string | null }[] }
  replay_comparisons: { experiment_id: string; result: unknown }[]
}

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  try {
    link.href = url
    link.download = name
    document.body.append(link)
    link.click()
  } finally {
    link.remove()
    URL.revokeObjectURL(url)
  }
}

export function ComparativeAnalytics({ start, end }: { start: string; end: string }) {
  const [side, setSide] = useState('')
  const [reason, setReason] = useState('')
  const params = new URLSearchParams({
    ...(start ? { start } : {}),
    ...(end ? { end } : {}),
    ...(side ? { side } : {}),
    ...(reason ? { reason } : {}),
  }).toString()
  const query = useQuery({
    queryKey: [...niftyKeys.all, 'analytics-comparison', params],
    queryFn: () => readNifty<Comparison>(`analytics/comparison?${params}`),
    retry: false,
  })
  const data = query.isError ? undefined : query.data
  const pdf = useMutation({
    mutationFn: async () =>
      download(await readComparativePdf(params), 'nifty-comparative-analytics.pdf'),
    retry: false,
  })
  return (
    <section aria-label="Comparative strategy analytics">
      <h3>Independent mode comparison</h3>
      <p>
        PAPER is authoritative realized accounting. Shadow is hypothetical. Mirrors and research are
        non-additive. Missing quote quality remains unavailable; sampled extrema are not continuous
        extremes.
      </p>
      <label htmlFor="comparison-side">Option type</label>
      <select id="comparison-side" value={side} onChange={(e) => setSide(e.target.value)}>
        <option value="">All option types</option>
        <option>CE</option>
        <option>PE</option>
      </select>
      <label htmlFor="comparison-reason">Exit reason filter</label>
      <Input
        id="comparison-reason"
        value={reason}
        maxLength={64}
        onChange={(e) => setReason(e.target.value)}
      />
      {query.isPending && <output>Loading independent mode evidence...</output>}
      {query.isError && (
        <p role="alert">
          Comparison unavailable. Stored evidence or selected filters failed validation.
        </p>
      )}
      {data?.paper?.metrics && (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table aria-label="PAPER and Shadow results">
              <thead>
                <tr>
                  <th>Mode</th>
                  <th>Trades</th>
                  <th>Gross</th>
                  <th>Costs</th>
                  <th>Net (Rs)</th>
                  <th>Drawdown</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { name: 'PAPER', metrics: data.paper.metrics },
                  {
                    name: 'Independent hypothetical Shadow',
                    metrics: data.independent_shadow.metrics,
                  },
                ].map(({ name, metrics: m }) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>{m?.trades ?? 'Unavailable'}</td>
                    <td>{m?.total_gross ?? 'Unavailable'}</td>
                    <td>{m?.costs ?? 'Unavailable'}</td>
                    <td>{m?.total_net ?? 'Unavailable'}</td>
                    <td>{m?.maximum_drawdown ?? 'Unavailable'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Facts
            rows={[
              ['Mirrors (never added to PAPER)', data.mirrors.total],
              ['Unavailable hypothetical outcomes', data.independent_shadow.unavailable_outcomes],
              ['Live', 'Unavailable: execution disabled'],
            ]}
          />
          <details>
            <summary>Non-additive mirror detail</summary>
            {data.mirrors.items.map((r) => (
              <p key={r.id}>
                Mirror #{r.id}: {r.net ?? 'Unavailable'}; non-additive
              </p>
            ))}
          </details>
          <details>
            <summary>Entry, exit and protection quality</summary>
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
              {JSON.stringify(data.paper.quality, null, 2)}
            </pre>
          </details>
          <h4>Evidence-based research suggestions</h4>
          {!data.paper.quality.suggestions.length && <p>No supported suggestion in this sample.</p>}
          {data.paper.quality.suggestions.map((s) => (
            <p key={s.code}>
              {s.code}: {s.message} Evidence: {s.evidence_count}. Explicit approval required for any
              settings change.
            </p>
          ))}
          <h4>Validated replay comparisons within this period</h4>
          {!data.replay_comparisons.length && (
            <p>No saved execution comparisons match the complete selected period.</p>
          )}
          {data.replay_comparisons.map((r) => (
            <details key={r.experiment_id}>
              <summary>{r.experiment_id}: research only</summary>
              <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                {JSON.stringify(r.result, null, 2)}
              </pre>
            </details>
          ))}
          <Button
            variant="outline"
            disabled={pdf.isPending || query.isFetching}
            onClick={() => pdf.mutate()}
          >
            Download comparative PDF
          </Button>
          <Button
            variant="outline"
            disabled={query.isFetching}
            onClick={() =>
              download(
                new Blob([JSON.stringify(data)], { type: 'application/json' }),
                'nifty-comparative-analytics.json'
              )
            }
          >
            Download comparative JSON
          </Button>
          {pdf.isError && (
            <p role="alert">Comparative PDF unavailable. Reload evidence before retrying.</p>
          )}
        </>
      )}
    </section>
  )
}
