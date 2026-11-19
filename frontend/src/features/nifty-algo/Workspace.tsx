import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  BarChart3,
  BookOpen,
  CandlestickChart,
  FlaskConical,
  LayoutDashboard,
  Play,
  Settings2,
  ShieldCheck,
  Square,
  Zap,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useSocketContext } from '@/components/socket/SocketProvider'
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
  assessNativeHistory,
  controlNifty,
  niftyKeys,
  readNifty,
  saveConfiguration,
  type ConfigurationResponse,
  type DataRecord,
  type NiftyStatus,
} from './api'
import './workspace.css'

const pages = [
  ['overview', 'Dashboard', LayoutDashboard],
  ['signals', 'Signal Monitor', Activity],
  ['terminal', 'Paper Trading', Play],
  ['positions', 'Positions & Orders', BookOpen],
  ['performance', 'Performance', BarChart3],
  ['configuration', 'Strategy Settings', Settings2],
  ['risk', 'Risk Management', ShieldCheck],
  ['connections', 'Connections & Setup', Zap],
] as const

function valueText(value: unknown): string {
  if (value === null || value === undefined) return 'Unavailable'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="nifty-panel">
      <h2>{title}</h2>
      {children}
    </section>
  )
}

function Fields({ data }: { data: DataRecord | undefined }) {
  if (!data || Object.keys(data).length === 0)
    return <p className="nifty-empty">No observations available.</p>
  return (
    <dl className="nifty-fields">
      {Object.entries(data).map(([key, value]) => (
        <div key={key}>
          <dt>{key.replaceAll('_', ' ')}</dt>
          <dd>{valueText(value)}</dd>
        </div>
      ))}
    </dl>
  )
}

function Records({ data }: { data: unknown }) {
  const rows = Array.isArray(data) ? (data as DataRecord[]) : []
  if (!rows.length) return <p className="nifty-empty">No records available.</p>
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))].filter((key) =>
    rows.some((row) => typeof row[key] !== 'object')
  )
  return (
    <div className="nifty-table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map((key) => (
              <th key={key}>{key.replaceAll('_', ' ')}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={String(row.id ?? row.decision_id ?? row.orderid ?? index)}>
              {columns.map((key) => (
                <td key={key}>{valueText(row[key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Resource({
  name,
  title,
  records = false,
}: {
  name: string
  title: string
  records?: boolean
}) {
  const query = useQuery({
    queryKey: [...niftyKeys.all, name],
    queryFn: () => readNifty<DataRecord>(name),
    refetchInterval: 30_000,
  })
  return (
    <Panel title={title}>
      {query.isPending ? (
        <p role="status">Loading {title.toLowerCase()}…</p>
      ) : query.error ? (
        <p role="alert">{query.error.message}</p>
      ) : records ? (
        <Records data={query.data} />
      ) : (
        <Fields data={query.data} />
      )}
    </Panel>
  )
}

function Configuration() {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: [...niftyKeys.all, 'configuration'],
    queryFn: () => readNifty<ConfigurationResponse>('configuration'),
  })
  const [draft, setDraft] = useState('')
  const [parseError, setParseError] = useState('')
  const save = useMutation({
    mutationFn: saveConfiguration,
    onSuccess: () => {
      setDraft('')
      queryClient.invalidateQueries({ queryKey: niftyKeys.all })
    },
  })
  function submit() {
    try {
      const parsed: unknown = JSON.parse(draft || JSON.stringify(query.data?.configuration))
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed))
        throw new Error('Configuration must be an object.')
      setParseError('')
      if (!query.data) throw new Error('Configuration revision unavailable. Refresh and try again.')
      save.mutate({ ...query.data, configuration: parsed as DataRecord })
    } catch (error) {
      setParseError(error instanceof Error ? error.message : 'Invalid configuration')
    }
  }
  return (
    <Panel title="Strategy configuration">
      {query.isPending ? (
        <p role="status">Loading configuration…</p>
      ) : query.error ? (
        <p role="alert">{query.error.message}</p>
      ) : (
        <>
          <label htmlFor="nifty-config">Versioned research parameters</label>
          <textarea
            id="nifty-config"
            className="nifty-config"
            value={draft || JSON.stringify(query.data?.configuration, null, 2)}
            onChange={(event) => setDraft(event.target.value)}
            spellCheck={false}
          />
          <p className="nifty-muted">
            Saving creates a configuration version and pauses new entries.
          </p>
          <Button disabled={save.isPending} onClick={submit}>
            Save configuration
          </Button>
          {save.isSuccess && <p role="status">Configuration saved.</p>}
        </>
      )}
      {(parseError || save.error) && <p role="alert">{parseError || save.error?.message}</p>}
    </Panel>
  )
}

export default function Workspace() {
  const [search, setSearch] = useSearchParams()
  const page = search.get('view') || 'overview'
  const queryClient = useQueryClient()
  const { socket } = useSocketContext()
  const [confirmKill, setConfirmKill] = useState(false)
  const status = useQuery({
    queryKey: [...niftyKeys.all, 'status'],
    queryFn: () => readNifty<NiftyStatus>('status'),
    refetchInterval: 30_000,
  })
  const action = useMutation({
    mutationFn: controlNifty,
    onSuccess: () => {
      setConfirmKill(false)
      queryClient.invalidateQueries({ queryKey: niftyKeys.all })
    },
  })
  const assessment = useMutation({
    mutationFn: assessNativeHistory,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: niftyKeys.all }),
  })
  useEffect(() => {
    if (!socket) return
    const refresh = () => {
      queryClient.invalidateQueries({ queryKey: niftyKeys.all })
    }
    socket.on('nifty_algo_update', refresh)
    return () => {
      socket.off('nifty_algo_update', refresh)
    }
  }, [socket, queryClient])
  return (
    <div className="nifty-workspace">
      <aside className="nifty-sidebar">
        <div className="nifty-brand">
          <Activity size={23} />
          <span>
            NIFTY<span>ALGO</span>
            <small>PAPER TERMINAL</small>
          </span>
        </div>
        <nav aria-label="NIFTY ALGO workspace">
          {pages.map(([id, label, Icon]) => (
            <button
              type="button"
              aria-current={page === id ? 'page' : undefined}
              key={id}
              onClick={() => setSearch({ view: id })}
            >
              <Icon size={17} />
              {label}
            </button>
          ))}
          <Link to="/trading">
            <CandlestickChart size={17} />
            Native Chart Workspace
          </Link>
          <Link to="/historify">
            <FlaskConical size={17} />
            Historical Research
          </Link>
        </nav>
        <button type="button" className="nifty-kill" onClick={() => setConfirmKill(true)}>
          Kill switch
        </button>
      </aside>
      <div className="nifty-content">
        <header className="nifty-topbar">
          <div>
            <span className="nifty-eyebrow">NFO / NIFTY OPTIONS</span>
            <h1>{pages.find(([id]) => id === page)?.[1] || 'Dashboard'}</h1>
          </div>
          <span className="nifty-paper">
            <FlaskConical size={16} />
            Paper simulation
          </span>
          <span className="nifty-state">{status.data?.state || 'Awaiting status'}</span>
        </header>
        {status.isPending && <p role="status">Loading paper system status…</p>}
        {status.error && <p role="alert">Status unavailable. {status.error.message}</p>}
        {action.error && <p role="alert">{action.error.message}</p>}
        {(page === 'overview' || page === 'terminal') && (
          <div className="nifty-controls">
            <Button
              disabled={action.isPending || !status.data}
              onClick={() => action.mutate({ action: 'start', revision: status.data!.revision })}
            >
              <Play size={14} />
              Start / resume paper strategy
            </Button>
            <Button
              variant="outline"
              disabled={action.isPending || !status.data}
              onClick={() => action.mutate({ action: 'pause', revision: status.data!.revision })}
            >
              Pause entries
            </Button>
            <Button
              variant="outline"
              disabled={action.isPending || !status.data}
              onClick={() => action.mutate({ action: 'stop', revision: status.data!.revision })}
            >
              <Square size={14} />
              Stop strategy
            </Button>
          </div>
        )}
        {page === 'overview' && (
          <>
            <div className="nifty-grid">
              <Resource name="market" title="NIFTY spot & futures" />
              <Resource name="performance" title="Virtual equity & performance" />
              <Panel title="Automation state">
                <strong className="nifty-metric">{status.data?.state || 'Unavailable'}</strong>
                <p className="nifty-muted">
                  {status.data?.mode || 'Awaiting paper guard confirmation'}
                </p>
              </Panel>
            </div>
            <div className="nifty-split">
              <Resource name="indicators" title="Algorithm confluence" />
              <Resource name="risk" title="Risk & safety" />
            </div>
            <Resource name="signals" title="Latest signal decisions" records />
          </>
        )}
        {page === 'signals' && (
          <>
            <div>
              <Button disabled={assessment.isPending} onClick={() => assessment.mutate()}>
                {assessment.isPending ? 'Assessing native history…' : 'Assess native history'}
              </Button>
              <p className="nifty-muted">
                Records an assessment using available native history. This action submits no orders.
              </p>
              {assessment.error && <p role="alert">{assessment.error.message}</p>}
              {assessment.isSuccess && <p role="status">Assessment recorded.</p>}
            </div>
            <Resource name="indicators" title="Five-indicator state" />
            <Resource name="signals" title="Persisted decisions" records />
          </>
        )}
        {(page === 'positions' || page === 'terminal') && (
          <>
            <p className="nifty-muted">
              Pause, stop and kill persist control state. Automation and paper exits remain
              unavailable until execution integration is ready. Existing Sandbox exposure requires
              separate review.
            </p>
            <Resource name="positions" title="Simulated positions" records />
            <Resource name="orders" title="Paper order lifecycle" records />
            <Resource name="trades" title="Trade journal" records />
          </>
        )}
        {page === 'performance' && (
          <>
            <Resource name="performance" title="Paper performance" />
            <Resource name="trades" title="Trade journal" records />
          </>
        )}
        {page === 'configuration' && <Configuration />}
        {page === 'risk' && <Resource name="risk" title="Risk controls & current utilization" />}
        {page === 'connections' && (
          <>
            <Panel title="Startup readiness">
              <ul className="nifty-readiness">
                {status.data?.readiness?.map((item, index) => (
                  <li key={index}>
                    {typeof item === 'string'
                      ? item
                      : `${item.code} — ${item.ready ? 'Ready' : 'Pending'}${item.detail ? ` · ${item.detail}` : ''}`}
                  </li>
                ))}
              </ul>
              {!status.data?.readiness?.length && (
                <p className="nifty-empty">Readiness observations unavailable.</p>
              )}
            </Panel>
            <Panel title="OpenAlgo setup">
              <div className="nifty-links">
                <Link to="/broker">Broker market-data connection</Link>
                <Link to="/master-contract">Instrument master</Link>
                <Link to="/python">Native Python strategies</Link>
                <Link to="/profile">Account preferences</Link>
                <Link to="/alerts">Notifications</Link>
              </div>
            </Panel>
          </>
        )}
      </div>
      <Dialog open={confirmKill} onOpenChange={setConfirmKill}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Activate NIFTY paper kill switch?</DialogTitle>
            <DialogDescription>
              This persists the NIFTY entry lockout. Automated paper exits require the execution
              integration to be ready. Review existing Sandbox positions separately.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmKill(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={action.isPending || !status.data}
              onClick={() =>
                action.mutate({ action: 'kill-switch', revision: status.data!.revision })
              }
            >
              Activate kill switch
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
