import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { createRecording, niftyKeys, type RecordingList, readNifty, sealRecording } from './api'
import { describeError } from './errors'
import { Facts, Panel } from './parts'

const recordingKey = [...niftyKeys.all, 'research/recordings']

export function RecordingsPanel() {
  const client = useQueryClient()
  const introduction = useRef<HTMLParagraphElement>(null)
  const reviewControl = useRef<HTMLButtonElement>(null)
  const [duration, setDuration] = useState(60)
  const [maximum, setMaximum] = useState(500)
  const [native, setNative] = useState(false)
  const [consent, setConsent] = useState(false)
  const [confirmation, setConfirmation] = useState<{ id: string; expected_count: number } | null>(
    null
  )
  const query = useQuery({
    queryKey: recordingKey,
    queryFn: () => readNifty<RecordingList>('research/recordings'),
    refetchInterval: 15_000,
  })
  const refresh = () => client.invalidateQueries({ queryKey: recordingKey })
  const creation = useMutation({
    mutationFn: createRecording,
    retry: false,
    onSuccess: () => setConsent(false),
    onSettled: refresh,
  })
  const sealing = useMutation({
    mutationFn: sealRecording,
    retry: false,
    onSuccess: () => setConfirmation(null),
    onSettled: refresh,
  })
  const busy = creation.isPending || sealing.isPending
  const valid =
    Number.isInteger(duration) &&
    duration >= 1 &&
    duration <= 1440 &&
    Number.isInteger(maximum) &&
    maximum >= 1 &&
    maximum <= 10000
  const items = Array.isArray(query.data?.items) ? query.data.items : null
  const selected = items?.find((item) => item.id === confirmation?.id)
  const changed =
    !selected || selected.status !== 'RECORDING' || selected.count !== confirmation?.expected_count
  const unavailable = query.isError || !items
  return (
    <Panel title="Research recordings">
      <p ref={introduction} tabIndex={-1} className="nifty-muted">
        Quote evidence only. Recordings never authorize execution or change the paper strategy.
        Creating a recording does not start a runner, connect a feed, or subscribe to instruments.
      </p>
      <form
        className="nifty-form"
        aria-label="New research recording"
        aria-busy={creation.isPending}
        onSubmit={(event) => {
          event.preventDefault()
          if (busy || creation.isError || unavailable || !valid || !consent) return
          creation.mutate({
            duration_minutes: duration,
            max_observations: maximum,
            native_capture: native,
          })
        }}
      >
        <label htmlFor="nifty-recording-duration">Duration (minutes, 1-1440)</label>
        <Input
          id="nifty-recording-duration"
          type="number"
          min={1}
          max={1440}
          step={1}
          required
          value={Number.isNaN(duration) ? '' : duration}
          disabled={busy}
          onChange={(event) => setDuration(event.target.valueAsNumber)}
        />
        <label htmlFor="nifty-recording-maximum">Observation limit (1-10000)</label>
        <Input
          id="nifty-recording-maximum"
          type="number"
          min={1}
          max={10000}
          step={1}
          required
          value={Number.isNaN(maximum) ? '' : maximum}
          disabled={busy}
          onChange={(event) => setMaximum(event.target.valueAsNumber)}
        />
        <label className="nifty-mode-row">
          <input
            type="checkbox"
            checked={native}
            disabled={busy}
            aria-describedby="nifty-capture-help"
            onChange={(event) => setNative(event.target.checked)}
          />
          Request native cache capture
        </label>
        <p id="nifty-capture-help" className="nifty-muted">
          Opt-in only. Requires an already attached, verified native feed and current runner
          ownership. Missing or rejected samples leave gaps; no connection is created here.
        </p>
        <label className="nifty-mode-row">
          <input
            type="checkbox"
            checked={consent}
            disabled={busy}
            required
            onChange={(event) => setConsent(event.target.checked)}
          />
          I confirm this recording is research-only.
        </label>
        <Button
          type="submit"
          disabled={busy || creation.isError || unavailable || !consent || !valid}
        >
          Create research recording
        </Button>
      </form>
      {creation.isPending && (
        <output>Creating recording. Controls are temporarily disabled.</output>
      )}
      {creation.isSuccess && (
        <output>Research recording created. Execution remains disabled.</output>
      )}
      {creation.error && (
        <p role="alert">
          {describeError(creation.error).message}. The result may be unknown. Refresh recordings
          before trying again; creation is not retried automatically.
        </p>
      )}
      <Button
        variant="outline"
        disabled={busy || query.isFetching}
        onClick={async () => {
          const result = await query.refetch()
          if (!result.isError) creation.reset()
        }}
      >
        Refresh recordings
      </Button>
      {query.isPending ? (
        <output>Loading research recordings...</output>
      ) : unavailable ? (
        <p role="alert">Recordings unavailable. Refresh before taking action.</p>
      ) : (
        <>
          <p className="nifty-muted">
            {query.data?.capture_status === 'NATIVE_CAPTURE_REQUESTED'
              ? 'Native capture requested for at least one recording.'
              : 'No native capture requested in this list.'}{' '}
            Request presence is not feed health or complete coverage.
          </p>
          {!items.length && <p className="nifty-empty">No research recordings.</p>}
          <ul aria-label="Research recordings" className="nifty-codes">
            {items.map((item) => (
              <li key={item.id}>
                <h3 className="nifty-subhead break-all">{item.id}</h3>
                <Facts
                  rows={[
                    ['Storage status', item.status],
                    ['Saved observations', `${item.count} / ${item.max_observations}`],
                    [
                      'Capture window',
                      item.status === 'SEALED'
                        ? 'Sealed; no further capture'
                        : item.count >= item.max_observations
                          ? 'Observation limit reached'
                          : Date.parse(item.ends_at) <= Date.now()
                            ? 'Window ended'
                            : 'Open window; samples not guaranteed',
                    ],
                    ['Window starts (UTC)', item.starts_at],
                    ['Window ends (UTC)', item.ends_at],
                    ['Last saved availability (UTC)', item.last_available_at ?? 'No samples saved'],
                    [
                      'Native scope',
                      item.capture
                        ? item.capture.scope
                          ? `${item.capture.scope.instruments.length} frozen instruments`
                          : 'Requested; scope not frozen'
                        : 'Not requested',
                    ],
                    [
                      'Scope SHA-256',
                      <code className="break-all" key="scope">
                        {item.capture?.scope_sha256 ?? 'Unavailable'}
                      </code>,
                    ],
                    [
                      'Content SHA-256',
                      <code className="break-all" key="content">
                        {item.content_sha256}
                      </code>,
                    ],
                  ]}
                />
                <p className="nifty-muted">
                  Research only. Provenance is not authenticated. Quote evidence does not prove
                  tradable coverage or achievable fills.
                </p>
                {item.status === 'RECORDING' && (
                  <Button
                    variant="outline"
                    aria-label={`Review seal for recording ${item.id}`}
                    disabled={busy || query.isFetching}
                    onClick={(event) => {
                      reviewControl.current = event.currentTarget
                      sealing.reset()
                      setConfirmation({ id: item.id, expected_count: item.count })
                    }}
                  >
                    Review seal
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      <Dialog
        open={confirmation !== null}
        onOpenChange={(open) => {
          if (!open && !sealing.isPending) setConfirmation(null)
        }}
      >
        <DialogContent
          showCloseButton={!sealing.isPending}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            const target =
              !sealing.isSuccess && reviewControl.current?.isConnected
                ? reviewControl.current
                : introduction.current
            target?.focus()
          }}
        >
          <DialogHeader>
            <DialogTitle>Seal research recording?</DialogTitle>
            <DialogDescription className="break-all">
              Recording {confirmation?.id}, reviewed count {confirmation?.expected_count}. Sealing
              permanently stops additions. It does not validate evidence or enable execution.
            </DialogDescription>
          </DialogHeader>
          {changed && <p role="alert">Recording changed. Close and review the latest count.</p>}
          {sealing.error && (
            <p role="alert">
              {describeError(sealing.error).message}. Close, refresh recordings, and review again.
              This request is not retried automatically.
            </p>
          )}
          {sealing.isPending && <output>Sealing recording. Please wait for the result.</output>}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={sealing.isPending}
              onClick={() => setConfirmation(null)}
            >
              Cancel
            </Button>
            <Button
              disabled={busy || unavailable || query.isFetching || changed || sealing.isError}
              onClick={() => {
                if (confirmation && !changed) sealing.mutate(confirmation)
              }}
            >
              Confirm seal only
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Panel>
  )
}
