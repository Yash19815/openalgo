import { useMutation, useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { niftyKeys, queueExecutionResearch, readNifty } from './api'

interface ExecutionResult {
  status: string
  sha256: string | null
  result: {
    variants?: {
      name: string
      configuration_id: string
      profit_lock: boolean
      splits: {
        kind: string
        status: string
        missing: string[]
        rejections: { at: string; code: string }[]
        performance: { total_net: string; maximum_drawdown: string; trades: number } | null
      }[]
    }[]
    status?: string
    assumptions?: string[]
  } | null
}

export function ExecutionComparison({ id }: { id: string }) {
  const query = useQuery({
    queryKey: [...niftyKeys.all, 'execution', id],
    queryFn: () => readNifty<ExecutionResult | null>(`research/experiments/${id}/execution`),
    retry: false,
    refetchInterval: 5000,
  })
  const run = useMutation({
    mutationFn: () => queueExecutionResearch(id),
    retry: false,
    onSuccess: () => query.refetch(),
  })
  const data = query.isError ? undefined : query.data
  return (
    <section aria-label="Execution research comparison">
      <h3>Baseline / current / experimental</h3>
      <p>
        Research only. A excludes the additional profit lock; B retains approved protection; C uses
        the immutable experimental definition. All consume identical evidence. Each split starts
        with Rs 20,000. No active settings change.
      </p>
      <Button
        variant="outline"
        disabled={query.isFetching || run.isPending || run.isError || query.isError || !!data}
        onClick={() => run.mutate()}
      >
        Queue validated A/B/C replay
      </Button>
      <Button
        variant="outline"
        disabled={query.isFetching || run.isPending}
        onClick={async () => {
          const fresh = await query.refetch()
          if (!fresh.isError) run.reset()
        }}
      >
        Refresh execution result
      </Button>
      {run.isError && (
        <p role="alert">Request outcome unknown. Refresh saved research before trying again.</p>
      )}
      {query.isError && (
        <p role="alert">Execution research unavailable or failed integrity verification.</p>
      )}
      {data && (
        <p>
          Research job: {data.status}.{' '}
          {data.status !== 'COMPLETE' && 'A separate research worker must be running.'}
        </p>
      )}
      {data?.sha256 && (
        <p style={{ overflowWrap: 'anywhere' }}>Immutable execution hash: {data.sha256}</p>
      )}
      {data?.result?.status && <p>{data.result.status}. Financial performance unavailable.</p>}
      {data?.result?.variants && (
        <div style={{ overflowX: 'auto' }}>
          <table aria-label="A/B/C execution results">
            <thead>
              <tr>
                <th>Variant</th>
                <th>Configuration</th>
                <th>Split</th>
                <th>Status</th>
                <th>Net (Rs)</th>
                <th>Drawdown (Rs)</th>
                <th>Trades</th>
              </tr>
            </thead>
            <tbody>
              {data.result.variants.flatMap((v) =>
                v.splits.map((s) => (
                  <tr key={`${v.name}-${s.kind}`}>
                    <td>{v.name}</td>
                    <td style={{ maxWidth: '12rem', overflowWrap: 'anywhere' }}>
                      {v.configuration_id}
                    </td>
                    <td>{s.kind}</td>
                    <td>
                      {s.status}
                      {s.missing.length > 0 && <p>{s.missing.join(', ')}</p>}
                      <details>
                        <summary>Rejection evidence</summary>
                        {s.rejections.map((r, i) => (
                          <p key={`${r.at}-${r.code}-${i}`}>
                            {r.at}: {r.code}
                          </p>
                        ))}
                      </details>
                    </td>
                    <td>{s.performance?.total_net ?? 'Unavailable'}</td>
                    <td>{s.performance?.maximum_drawdown ?? 'Unavailable'}</td>
                    <td>{s.performance?.trades ?? 'Unavailable'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
      {data?.result?.assumptions?.map((a) => (
        <p key={a}>{a}</p>
      ))}
    </section>
  )
}
