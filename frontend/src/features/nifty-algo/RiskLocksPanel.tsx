import { useQuery } from '@tanstack/react-query'
import { niftyKeys, type RiskOverview, readNifty } from './api'
import { CodeList, Facts, Flag, Panel, text } from './parts'

export function useRiskOverview() {
  return useQuery({
    queryKey: [...niftyKeys.all, 'risk'],
    queryFn: () => readNifty<RiskOverview>('risk'),
    refetchInterval: 30_000,
  })
}

function lockState(at: string | null | undefined) {
  return at ? `Locked since ${at}` : 'Not locked'
}

export function RiskLocksPanel() {
  const query = useRiskOverview()
  const locks = query.data?.entry_locks
  const reasons = locks?.reasons ?? []
  const unresolved = reasons.includes('COOLDOWN_UNRESOLVED')
  return (
    <Panel title="Entry locks">
      {query.isPending ? (
        <output>Loading entry locks…</output>
      ) : query.error ? (
        <p role="alert">{query.error.message}</p>
      ) : !locks ? (
        <p className="nifty-empty">Entry lock state unavailable.</p>
      ) : (
        <>
          <div className="nifty-flags">
            <Flag label="Cooldown active" value={locks.cooldown.active} />
            <Flag label="Cooldown unresolved" value={unresolved} />
            <Flag label="Monthly loss lock" value={Boolean(locks.month.loss_locked_at)} />
            <Flag label="Monthly profit lock" value={Boolean(locks.month.profit_locked_at)} />
            <Flag label="Account reconciled" value={Boolean(query.data?.account_reconciled)} />
          </div>
          <Facts
            rows={[
              ['Session (IST)', text(locks.session)],
              ['Last loss session', text(locks.cooldown.loss_session, 'None')],
              [
                'Cooldown session',
                text(
                  locks.cooldown.cooldown_session,
                  locks.cooldown.loss_session ? 'Not yet resolved' : 'None'
                ),
              ],
              ['Month', text(locks.month.month)],
              ['Monthly realized net (Rs)', text(locks.month.realized_net)],
              ['Monthly loss limit (Rs)', text(locks.month.loss_limit)],
              ['Monthly profit target (Rs)', text(locks.month.profit_target, 'Not set')],
              ['Monthly loss lock', lockState(locks.month.loss_locked_at)],
              ['Monthly profit lock', lockState(locks.month.profit_locked_at)],
            ]}
          />
          <h3 className="nifty-subhead">Current entry refusals</h3>
          <CodeList
            codes={reasons}
            label="Entry refusal codes"
            empty="No cooldown or monthly lock refuses new entries."
          />
          <p className="nifty-muted">
            Locks refuse new entries only. Protective exits continue. Monthly locks latch until the
            next IST month.
          </p>
        </>
      )}
    </Panel>
  )
}
