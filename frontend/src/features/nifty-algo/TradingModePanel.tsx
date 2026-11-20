import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Lock } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { niftyKeys, readNifty, requestMode, type TradingMode } from './api'
import { describeError, type NiftyApiError } from './errors'
import { CodeList, Facts, Flag, Panel, text } from './parts'

const modeKey = [...niftyKeys.all, 'mode'] as const

/** Only these masked fields are rendered; anything else in the payload is ignored. */
function BrokerStatusView({ broker }: { broker: TradingMode['broker'] }) {
  if (!broker.available)
    return (
      <p className="nifty-empty">
        Broker status unavailable{broker.code ? ` (${broker.code})` : ''}.
      </p>
    )
  return (
    <>
      <Facts
        rows={[
          ['Broker', text(broker.broker_name ?? broker.broker, 'Not configured')],
          ['Key source', text(broker.key_source, 'None')],
        ]}
      />
      <div className="nifty-flags">
        <Flag label="Broker auth token present" value={broker.auth_token_present} />
        <Flag label="Feed token present" value={broker.feed_token_present} />
        <Flag label="Session current" value={broker.session_current} />
        <Flag label="Session revoked" value={broker.revoked} />
        <Flag label="Broker API key configured" value={broker.api_key_configured} />
        <Flag label="Broker API secret configured" value={broker.api_secret_configured} />
        <Flag label="OpenAlgo API key configured" value={broker.openalgo_api_key_configured} />
      </div>
    </>
  )
}

export function TradingModePanel() {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: modeKey,
    queryFn: () => readNifty<TradingMode>('mode'),
    refetchInterval: 30_000,
  })
  const [acknowledged, setAcknowledged] = useState(false)
  const [failure, setFailure] = useState<NiftyApiError | null>(null)
  const [notice, setNotice] = useState('')
  const change = useMutation({
    mutationFn: requestMode,
    onMutate: () => {
      setFailure(null)
      setNotice('')
    },
    onSuccess: (data) => {
      setAcknowledged(false)
      setNotice(
        (data as TradingMode & { changed?: boolean }).changed
          ? `Mode is now ${data.mode}.`
          : `Mode unchanged (${data.mode}).`
      )
      queryClient.invalidateQueries({ queryKey: niftyKeys.all })
    },
    onError: (error) => {
      const detail = describeError(error)
      setFailure(detail)
      if (detail.code === 'REVISION_CONFLICT') {
        setAcknowledged(false)
        queryClient.invalidateQueries({ queryKey: modeKey })
      }
    },
  })
  const data = query.data
  return (
    <Panel title="Trading mode">
      {query.isPending ? (
        <output>Loading trading mode…</output>
      ) : query.error ? (
        <p role="alert">{query.error.message}</p>
      ) : !data ? (
        <p className="nifty-empty">Trading mode unavailable.</p>
      ) : (
        <>
          <div className="nifty-mode-row">
            <Badge variant={data.mode === 'PAPER' ? 'secondary' : 'destructive'}>
              Mode: {data.mode}
            </Badge>
            <span className="nifty-muted">Revision {data.revision}</span>
            <span className="nifty-muted">Adapter {data.adapter}</span>
          </div>
          <div className="nifty-banner nifty-banner-info">
            <Lock size={16} aria-hidden />
            <p>
              Live trading is not available in this release. Every Live request is refused and
              entries stay simulated.
            </p>
          </div>
          <h3 className="nifty-subhead">Open primary exposure</h3>
          <Facts
            rows={[
              ['Open positions', String(data.exposure.positions)],
              ['Pending orders', String(data.exposure.pending_orders)],
            ]}
          />
          <h3 className="nifty-subhead">Broker status (masked)</h3>
          <BrokerStatusView broker={data.broker} />
          <h3 className="nifty-subhead">Live readiness</h3>
          <CodeList
            codes={data.readiness}
            label="Live readiness codes"
            empty="No readiness codes reported."
          />
          <div className="nifty-check">
            <Checkbox
              id="nifty-live-ack"
              checked={acknowledged}
              onCheckedChange={(value) => setAcknowledged(value === true)}
            />
            <Label htmlFor="nifty-live-ack">
              I understand Live mode would place real broker orders with real money.
            </Label>
          </div>
          <div className="nifty-controls">
            <Button
              variant="outline"
              disabled={change.isPending || !acknowledged || data.mode === 'LIVE'}
              onClick={() => change.mutate({ mode: 'LIVE', revision: data.revision, acknowledged })}
            >
              Request Live
            </Button>
            {data.mode !== 'PAPER' && (
              <Button
                disabled={change.isPending}
                onClick={() => change.mutate({ mode: 'PAPER', revision: data.revision })}
              >
                Switch to Paper
              </Button>
            )}
          </div>
          {failure && (
            <div role="alert" className="nifty-refusal">
              {failure.code === 'REVISION_CONFLICT' ? (
                <p>
                  The trading mode changed elsewhere. The latest state was reloaded; review it and
                  try again. (REVISION_CONFLICT)
                </p>
              ) : (
                <>
                  <p>
                    {failure.message}
                    {failure.code ? ` (${failure.code})` : ''}
                  </p>
                  {failure.reasons.length > 0 && (
                    <CodeList codes={failure.reasons} label="Refusal reasons" empty="" />
                  )}
                </>
              )}
            </div>
          )}
          {notice && <output>{notice}</output>}
          {data.history.length > 0 && (
            <p className="nifty-muted">
              Last change: {data.history[data.history.length - 1].previous} to{' '}
              {data.history[data.history.length - 1].new} at{' '}
              {data.history[data.history.length - 1].at}
            </p>
          )}
        </>
      )}
    </Panel>
  )
}
