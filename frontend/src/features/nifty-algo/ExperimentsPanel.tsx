import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  defineExperiment,
  type ExperimentDefinition,
  type ExperimentRequest,
  type ExperimentSummary,
  niftyKeys,
  type RecordingList,
  type ResearchRecording,
  readNifty,
} from './api'
import { Facts, Panel } from './parts'

const recordingKey = [...niftyKeys.all, 'research/recordings']
const experimentKey = [...niftyKeys.all, 'research/experiments']

export function ExperimentsPanel() {
  const client = useQueryClient()
  const [source, setSource] = useState<ResearchRecording | null>(null)
  const [train, setTrain] = useState('')
  const [validation, setValidation] = useState('')
  const [adx, setAdx] = useState('')
  const [atr, setAtr] = useState('')
  const [factor, setFactor] = useState('')
  const [consent, setConsent] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)
  const sources = useQuery({
    queryKey: recordingKey,
    queryFn: () => readNifty<RecordingList>('research/recordings'),
    refetchInterval: 15_000,
    retry: false,
  })
  const listing = useQuery({
    queryKey: experimentKey,
    queryFn: () => readNifty<{ items: ExperimentSummary[] }>('research/experiments'),
    refetchInterval: 15_000,
    retry: false,
  })
  const detailPath = `research/experiments/${encodeURIComponent(detailId ?? '')}`
  const detail = useQuery({
    queryKey: [...niftyKeys.all, detailPath],
    queryFn: () => readNifty<ExperimentDefinition>(detailPath),
    enabled: detailId !== null,
    retry: false,
  })
  const creation = useMutation({
    mutationFn: defineExperiment,
    retry: false,
    onSuccess: async (result) => {
      setConsent(false)
      setDetailId(result.id)
      await client.invalidateQueries({ queryKey: experimentKey })
    },
  })
  const recordings =
    !sources.isError && Array.isArray(sources.data?.items) ? sources.data.items : null
  const experiments =
    !listing.isError && Array.isArray(listing.data?.items) ? listing.data.items : null
  const choices = recordings?.filter((item) => item.status === 'SEALED' && item.count > 0) ?? []
  const current = choices.find((item) => item.id === source?.id)
  const changed =
    source !== null &&
    (!current ||
      current.count !== source.count ||
      current.content_sha256 !== source.content_sha256 ||
      current.starts_at !== source.starts_at ||
      current.ends_at !== source.ends_at ||
      current.sealed_at !== source.sealed_at ||
      current.configuration_id !== source.configuration_id)
  const trainTime = Date.parse(`${train}Z`)
  const validationTime = Date.parse(`${validation}Z`)
  const end = Math.min(Date.parse(source?.ends_at ?? ''), Date.parse(source?.sealed_at ?? ''))
  const splitsValid =
    !!source &&
    Date.parse(source.starts_at) < trainTime &&
    trainTime < validationTime &&
    validationTime < end
  const settingsValid =
    (factor === '' ||
      (Number.isFinite(Number(factor)) && Number(factor) > 0 && Number(factor) <= 10)) &&
    (adx === '' || (Number.isFinite(Number(adx)) && Number(adx) >= 0 && Number(adx) <= 100)) &&
    (atr === '' || (Number.isInteger(Number(atr)) && Number(atr) >= 2 && Number(atr) <= 100))
  const refreshing =
    sources.isFetching || listing.isFetching || (detailId !== null && detail.isFetching)
  const busy = creation.isPending
  const canDefine =
    !!source &&
    !!recordings &&
    !!experiments &&
    experiments.length < 50 &&
    !changed &&
    splitsValid &&
    settingsValid &&
    consent &&
    !busy &&
    !creation.isError
  const inspected = !detail.isError && detail.data?.id === detailId ? detail.data : null

  async function refresh() {
    const results = await Promise.all([
      sources.refetch(),
      listing.refetch(),
      ...(detailId ? [detail.refetch()] : []),
    ])
    if (results.every((result) => !result.isError)) creation.reset()
  }

  return (
    <Panel title="Experiment definitions">
      <p className="nifty-muted">
        Freeze a sealed recording and research settings without changing active strategy settings.
        No replay runs or performance results are available. Quote evidence does not authenticate
        provenance or support options execution simulation.
      </p>
      <form
        className="nifty-form"
        aria-label="New experiment definition"
        aria-busy={busy}
        onSubmit={(event) => {
          event.preventDefault()
          if (!canDefine || !source) return
          const configuration_overrides: ExperimentRequest['configuration_overrides'] = {}
          if (adx !== '') configuration_overrides.adx_min = Number(adx)
          if (atr !== '') configuration_overrides.atr_period = Number(atr)
          if (factor !== '') configuration_overrides.atr_multiplier = Number(factor)
          creation.mutate({
            recording_id: source.id,
            expected_count: source.count,
            expected_sha256: source.content_sha256,
            train_end: new Date(trainTime).toISOString(),
            validation_end: new Date(validationTime).toISOString(),
            configuration_overrides,
          })
        }}
      >
        <label htmlFor="nifty-experiment-source">Sealed recording</label>
        <select
          id="nifty-experiment-source"
          className="nifty-select w-full min-w-0"
          value={source?.id ?? ''}
          required
          disabled={busy || !recordings}
          onChange={(event) => {
            setSource(choices.find((item) => item.id === event.target.value) ?? null)
            setConsent(false)
          }}
        >
          <option value="">Choose sealed evidence</option>
          {choices.map((item) => (
            <option key={item.id} value={item.id}>
              {item.id} ({item.count} observations)
            </option>
          ))}
        </select>
        <p id="nifty-experiment-splits" className="nifty-muted">
          Enter UTC times. Train starts at the recording start. Validation starts at train end. Test
          starts at validation end and ends at the earlier of seal time or recording end. Each
          interval includes its start and excludes its end. Coverage is not guaranteed.
        </p>
        <label htmlFor="nifty-experiment-train">Train ends (UTC)</label>
        <Input
          id="nifty-experiment-train"
          type="datetime-local"
          step={1}
          required
          aria-describedby="nifty-experiment-splits"
          aria-invalid={train !== '' && validation !== '' && !splitsValid}
          value={train}
          disabled={busy}
          onChange={(event) => setTrain(event.target.value)}
        />
        <label htmlFor="nifty-experiment-validation">Validation ends (UTC)</label>
        <Input
          id="nifty-experiment-validation"
          type="datetime-local"
          step={1}
          required
          aria-describedby="nifty-experiment-splits"
          aria-invalid={train !== '' && validation !== '' && !splitsValid}
          value={validation}
          disabled={busy}
          onChange={(event) => setValidation(event.target.value)}
        />
        <p id="nifty-experiment-settings" className="nifty-muted">
          Optional overrides affect this definition only. Blank fields and all other settings use
          the recording's frozen configuration, not current active settings.
        </p>
        <label htmlFor="nifty-experiment-adx">Research ADX minimum (optional)</label>
        <Input
          id="nifty-experiment-adx"
          type="number"
          min={0}
          max={100}
          step="any"
          aria-describedby="nifty-experiment-settings"
          aria-invalid={!settingsValid}
          value={adx}
          disabled={busy}
          onChange={(event) => setAdx(event.target.value)}
        />
        <label htmlFor="nifty-experiment-atr">Research ATR period (optional)</label>
        <Input
          id="nifty-experiment-atr"
          type="number"
          min={2}
          max={100}
          step={1}
          aria-describedby="nifty-experiment-settings"
          aria-invalid={!settingsValid}
          value={atr}
          disabled={busy}
          onChange={(event) => setAtr(event.target.value)}
        />
        <label htmlFor="nifty-experiment-factor">Research SuperTrend factor (optional)</label>
        <Input
          id="nifty-experiment-factor"
          type="number"
          min={0}
          max={10}
          step="any"
          aria-describedby="nifty-experiment-settings"
          aria-invalid={!settingsValid}
          value={factor}
          disabled={busy}
          onChange={(event) => setFactor(event.target.value)}
        />
        <label className="nifty-mode-row">
          <input
            type="checkbox"
            checked={consent}
            disabled={busy}
            onChange={(event) => setConsent(event.target.checked)}
          />
          I understand this saves an immutable definition only, not a backtest or trading action.
        </label>
        <p id="nifty-experiment-readiness" className="nifty-muted">
          Choose sealed evidence, set ordered times within its window and confirm to save.
          Definitions cannot be edited. Limit: 50 per owner.
        </p>
        <Button type="submit" disabled={!canDefine} aria-describedby="nifty-experiment-readiness">
          {busy ? 'Saving definition...' : 'Define experiment'}
        </Button>
      </form>
      {source && (
        <Facts
          rows={[
            ['Reviewed observation count', source.count],
            ['Recording starts (UTC)', source.starts_at],
            ['Test ends (UTC)', Number.isFinite(end) ? new Date(end).toISOString() : 'Unavailable'],
            [
              'Reviewed evidence SHA-256',
              <code key="source-hash" className="break-all">
                {source.content_sha256}
              </code>,
            ],
          ]}
        />
      )}
      {changed && (
        <p role="alert">Selected recording changed. Choose evidence again before saving.</p>
      )}
      {creation.isSuccess && (
        <output>Experiment definition saved. No active settings changed.</output>
      )}
      {creation.isError && (
        <p role="alert">
          Definition not confirmed; it may already be saved. Refresh and inspect saved definitions
          before trying again. Check sealed evidence, ordered times and research settings.
        </p>
      )}
      <Button type="button" variant="outline" disabled={busy || refreshing} onClick={refresh}>
        Refresh experiments
      </Button>
      {sources.isPending ? (
        <output>Loading sealed recordings...</output>
      ) : !recordings ? (
        <p role="alert">Recordings unavailable. Refresh before defining an experiment.</p>
      ) : !choices.length ? (
        <p>No sealed recordings with saved observations.</p>
      ) : null}
      {listing.isPending ? (
        <output>Loading experiment definitions...</output>
      ) : !experiments ? (
        <p role="alert">Experiment list unavailable. Refresh before defining an experiment.</p>
      ) : (
        <>
          {!experiments.length && <p className="nifty-empty">No experiment definitions saved.</p>}
          {experiments.length >= 50 && <output>Experiment definition limit reached.</output>}
          <ul aria-label="Saved experiment definitions" className="nifty-codes">
            {experiments.map((item) => (
              <li key={item.id}>
                <h3 className="nifty-subhead break-all">{item.id}</h3>
                <p>Defined only, not run. Saved {item.created_at}.</p>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  aria-label={`Inspect experiment ${item.id}`}
                  onClick={() => setDetailId(item.id)}
                >
                  Inspect definition
                </Button>
              </li>
            ))}
          </ul>
        </>
      )}
      {detailId &&
        (detail.isPending ? (
          <output>Loading saved definition...</output>
        ) : !inspected ? (
          <p role="alert">
            Saved definition unavailable or failed verification. Refresh before reviewing it.
          </p>
        ) : (
          <div>
            <h3 className="nifty-subhead">Saved experiment details</h3>
            <Facts
              rows={[
                ['Experiment', inspected.id],
                ['Status', 'Defined only; not run'],
                ['Execution eligible', 'No'],
                [
                  'Snapshot SHA-256',
                  <code key="snapshot-hash" className="break-all">
                    {inspected.sha256}
                  </code>,
                ],
              ]}
            />
            <p className="nifty-muted">No performance calculated. No active settings changed.</p>
            <details>
              <summary>Frozen research snapshot</summary>
              <pre className="whitespace-pre-wrap break-all text-xs">
                {JSON.stringify(inspected.snapshot, null, 2)}
              </pre>
            </details>
          </div>
        ))}
    </Panel>
  )
}
