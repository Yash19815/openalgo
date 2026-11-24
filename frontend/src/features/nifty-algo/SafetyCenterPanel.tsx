import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  acknowledgeSafetyIncident,
  niftyKeys,
  readNifty,
  resolveSafetyIncident,
  type SafetyStatus,
} from './api'
import { describeError } from './errors'
import { CodeList, Panel } from './parts'

export function SafetyCenterPanel() {
  const client = useQueryClient()
  const reviewControl = useRef<HTMLButtonElement | null>(null)
  const introduction = useRef<HTMLParagraphElement | null>(null)
  const [confirmation, setConfirmation] = useState<{
    id: number
    revision: number
    state_revision: number
  } | null>(null)
  const query = useQuery({
    queryKey: [...niftyKeys.all, 'safety'],
    queryFn: () => readNifty<SafetyStatus>('safety'),
    refetchInterval: 15_000,
  })
  const acknowledge = useMutation({
    mutationFn: acknowledgeSafetyIncident,
    onSettled: () => client.invalidateQueries({ queryKey: niftyKeys.all }),
  })
  const resolution = useMutation({
    mutationFn: resolveSafetyIncident,
    onSuccess: () => setConfirmation(null),
    onSettled: () => client.invalidateQueries({ queryKey: niftyKeys.all }),
  })
  const busy = acknowledge.isPending || resolution.isPending
  return (
    <Panel title="Execution Safety Center">
      <p ref={introduction} tabIndex={-1} className="nifty-muted">
        Acknowledgement does not resolve an incident or resume trading. Protective exits remain
        active. Live execution stays blocked.
      </p>
      {query.isPending ? (
        <output>Loading safety observations...</output>
      ) : query.error ? (
        <p role="alert">{describeError(query.error).message}</p>
      ) : !query.data || !Array.isArray(query.data.incidents) ? (
        <p role="alert">Safety observations unavailable. Reload before taking action.</p>
      ) : (
        <>
          <Badge variant={query.data.entry_blocked ? 'destructive' : 'secondary'}>
            {query.data.entry_blocked ? 'New entries blocked' : 'No incident entry hold'}
          </Badge>
          <p className="nifty-muted">
            Other entry gates still apply. Resolution rechecks fresh runner evidence and the
            isolated paper ledger. Trading stays paused until a separate Start action.
          </p>
          <CodeList
            codes={query.data.reasons}
            label="Safety hold reasons"
            empty="No incident hold reported."
          />
          {acknowledge.isPending && (
            <output>Saving acknowledgement. Incident controls are temporarily disabled.</output>
          )}
          {acknowledge.error && <p role="alert">{describeError(acknowledge.error).message}</p>}
          {resolution.isPending && (
            <output>Verifying paper recovery. Incident controls are disabled.</output>
          )}
          {resolution.error && !confirmation && (
            <p role="alert">{describeError(resolution.error).message}</p>
          )}
          {query.data.incidents.length === 0 ? (
            <p className="nifty-empty">No recorded safety incidents.</p>
          ) : (
            <ul aria-label="Safety incidents" className="nifty-codes">
              {query.data.incidents.map((incident) => (
                <li key={incident.id}>
                  <h3 className="nifty-subhead">
                    Incident {incident.id}: {incident.code}
                  </h3>
                  <p>
                    {incident.mode} / {incident.severity} / <strong>{incident.status}</strong>
                  </p>
                  <p className="nifty-muted">
                    Revision {incident.revision}. Raised{' '}
                    <time dateTime={incident.created_at}>{incident.created_at}</time>
                  </p>
                  {incident.status === 'OPEN' && (
                    <Button
                      variant="outline"
                      aria-label={`Acknowledge incident ${incident.id}`}
                      disabled={busy || query.isFetching}
                      onClick={() =>
                        acknowledge.mutate({ id: incident.id, revision: incident.revision })
                      }
                    >
                      Acknowledge
                    </Button>
                  )}
                  {incident.status === 'ACKNOWLEDGED' &&
                    incident.mode === 'PAPER' &&
                    ['STALE_DATA', 'MARKET_DATA_DISCONNECTED', 'RECONCILIATION_BLOCKED'].includes(
                      incident.code
                    ) &&
                    query.data.recovery_available &&
                    typeof query.data.state_revision === 'number' && (
                      <Button
                        variant="outline"
                        aria-label={`Review resolution for incident ${incident.id}`}
                        disabled={busy || query.isFetching}
                        onClick={(event) => {
                          reviewControl.current = event.currentTarget
                          resolution.reset()
                          setConfirmation({
                            id: incident.id,
                            revision: incident.revision,
                            state_revision: query.data.state_revision as number,
                          })
                        }}
                      >
                        Review resolution
                      </Button>
                    )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <Dialog
        open={confirmation !== null}
        onOpenChange={(open) => {
          if (!open && !resolution.isPending) setConfirmation(null)
        }}
      >
        <DialogContent
          showCloseButton={!resolution.isPending}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            const target =
              !resolution.isSuccess && reviewControl.current?.isConnected
                ? reviewControl.current
                : introduction.current
            target?.focus()
          }}
        >
          <DialogHeader>
            <DialogTitle>Resolve paper incident {confirmation?.id}?</DialogTitle>
            <DialogDescription>
              Trading stays paused. The server rechecks runner freshness, paper reconciliation,
              protection and both revisions. Kill switches and other incident holds remain
              unchanged. This does not verify Live broker capabilities.
            </DialogDescription>
          </DialogHeader>
          {resolution.error && <p role="alert">{describeError(resolution.error).message}</p>}
          {resolution.isPending && <output>Verifying recovery. Trading stays paused.</output>}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={resolution.isPending}
              onClick={() => setConfirmation(null)}
            >
              Cancel
            </Button>
            <Button
              disabled={busy || query.isFetching || !!query.error || !confirmation}
              onClick={() => {
                if (confirmation) resolution.mutate(confirmation)
              }}
            >
              Confirm resolution only
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Panel>
  )
}
