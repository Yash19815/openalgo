import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { type ExperimentSummary, inspectExperiment, niftyKeys, readNifty } from './api'
import { ExecutionComparison } from './ExecutionComparison'
import { Panel } from './parts'
import { ResearchOperations } from './ResearchOperations'

interface Inspection {
  sha256: string
  result: {
    fidelity: string
    samples: number
    split_counts: Record<string, number>
    full_execution_refused: string[]
    variants: { name: string; status: string }[]
  }
}
interface ReplayPage {
  execution_eligible: false
  next_after: number
  items: {
    sequence: number
    available_at: string
    source_time: string
    kind?: 'QUOTE' | 'FRAME' | 'LEDGER'
    payload: { token: string; bid: string | null; ask: string | null }
  }[]
}

export function ReplayPanel() {
  const [id, setId] = useState('')
  const [clock, setClock] = useState('')
  const [request, setRequest] = useState<{ id: string; clock: string; after: number } | null>(null)
  const experiments = useQuery({
    queryKey: [...niftyKeys.all, 'research/experiments'],
    queryFn: () => readNifty<{ items: ExperimentSummary[] }>('research/experiments'),
    retry: false,
  })
  const inspection = useQuery({
    queryKey: [...niftyKeys.all, 'inspection', id],
    queryFn: () => readNifty<Inspection | null>(`research/experiments/${id}/inspection`),
    enabled: !!id,
    retry: false,
  })
  const create = useMutation({
    mutationFn: () => inspectExperiment(id),
    retry: false,
    onSuccess: () => inspection.refetch(),
  })
  const page = useQuery({
    queryKey: [...niftyKeys.all, 'replay', request],
    enabled: request !== null,
    queryFn: () =>
      readNifty<ReplayPage>(
        `research/experiments/${request?.id}/replay?${new URLSearchParams({ as_of: `${request?.clock}Z`, after: String(request?.after ?? 0) })}`
      ),
    retry: false,
  })
  const validClock = clock !== '' && Number.isFinite(Date.parse(`${clock}Z`))
  const current =
    request?.id === id && request?.clock === clock && !page.isError ? page.data : undefined
  const bundle = experiments.data?.items.find((item) => item.id === id)?.execution_bundle === true
  return (
    <Panel title="Historical Replay Lab">
      <ResearchOperations />
      <p className="nifty-muted">
        RESEARCH only. Replays sealed evidence by receipt availability. Financial results require
        validated futures, PCR, spot, candidate metadata and executable depth. Missing evidence
        stays unavailable.
      </p>
      <label htmlFor="nifty-replay-experiment">Experiment</label>
      <select
        id="nifty-replay-experiment"
        value={id}
        disabled={experiments.isError || experiments.isPending}
        onChange={(event) => {
          setId(event.target.value)
          setRequest(null)
          create.reset()
        }}
      >
        <option value="">Select an immutable experiment</option>
        {!experiments.isError &&
          experiments.data?.items?.map((item) => (
            <option key={item.id} value={item.id}>
              {item.id}
            </option>
          ))}
      </select>
      {experiments.isError && (
        <p role="alert">Experiment list unavailable. Reload the workspace before continuing.</p>
      )}
      {experiments.isPending && <output>Loading experiments...</output>}
      {id && (
        <>
          <ExecutionComparison key={id} id={id} />
          {bundle ? (
            <p>
              Multi-session bundle: use the isolated comparison worker above. Inspect individual
              recordings for raw evidence.
            </p>
          ) : (
            <>
              <Button
                variant="outline"
                disabled={create.isPending || create.isError || experiments.isError}
                onClick={() => create.mutate()}
              >
                Inspect and save dataset coverage
              </Button>
              {create.isError && (
                <p role="alert">
                  Inspection outcome unavailable. Inspect saved results before retrying.
                </p>
              )}
              {inspection.isError && (
                <p role="alert">Saved research result unavailable or failed verification.</p>
              )}
              {!inspection.isError && inspection.data && (
                <>
                  <p>
                    {inspection.data.result.fidelity}: {inspection.data.result.samples} quote
                    samples
                  </p>
                  <p>
                    Immutable result hash:{' '}
                    <code style={{ overflowWrap: 'anywhere' }}>{inspection.data.sha256}</code>
                  </p>
                  <ul>
                    {Object.entries(inspection.data.result.split_counts).map(([split, count]) => (
                      <li key={split}>
                        {split}: {count} samples
                      </li>
                    ))}
                  </ul>
                  <p>
                    Full execution refused:{' '}
                    {inspection.data.result.full_execution_refused.join(', ')}
                  </p>
                  <ul>
                    {inspection.data.result.variants.map((variant) => (
                      <li key={variant.name}>
                        {variant.name}: {variant.status}; no performance calculated
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <label htmlFor="nifty-replay-clock">Replay clock (UTC)</label>
              <Input
                id="nifty-replay-clock"
                type="datetime-local"
                value={clock}
                onChange={(event) => {
                  setClock(event.target.value)
                  setRequest(null)
                }}
              />
              <Button
                variant="outline"
                disabled={!validClock || page.isFetching || experiments.isError}
                onClick={() => setRequest({ id, clock, after: 0 })}
              >
                Start evidence replay
              </Button>
              {page.isFetching && <output>Verifying and reading recorded evidence...</output>}
              {page.isError && (
                <p role="alert">Replay unavailable. Clock or stored evidence failed validation.</p>
              )}
              {current && (
                <>
                  <p>
                    Quote evidence only. No orders, fills, realized returns or active settings
                    changes.
                  </p>
                  <ul>
                    {current.items.map((item) => (
                      <li key={item.sequence}>
                        #{item.sequence}{' '}
                        {item.kind && item.kind !== 'QUOTE' ? (
                          `${item.kind} observation`
                        ) : (
                          <>
                            {item.payload.token}: bid {item.payload.bid ?? 'Unavailable'} / ask{' '}
                            {item.payload.ask ?? 'Unavailable'}
                            {`; source ${item.source_time}; available ${item.available_at}`}
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                  {!current.items.length && <p>No further evidence available at this clock.</p>}
                  <Button
                    variant="outline"
                    disabled={!current.items.length || page.isFetching}
                    onClick={() => setRequest({ id, clock, after: current.next_after })}
                  >
                    Step next evidence page
                  </Button>
                </>
              )}
            </>
          )}
        </>
      )}
    </Panel>
  )
}
