import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  BarChart3,
  BookOpen,
  CalendarDays,
  CandlestickChart,
  FileText,
  FlaskConical,
  LayoutDashboard,
  Play,
  Settings2,
  ShieldCheck,
  Square,
  Telescope,
  Zap,
} from 'lucide-react'
import { lazy, Suspense, useEffect, useState } from 'react'
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
import { AnalyticsPanel } from './AnalyticsPanel'
import {
  assessNativeHistory,
  type ConfigurationResponse,
  controlNifty,
  type DataRecord,
  type NiftyStatus,
  niftyKeys,
  preparePaperMonitor,
  readNifty,
  saveConfiguration,
} from './api'
import { CalendarBanner, CalendarPanel } from './CalendarPanel'
import { KeySettings } from './KeySettings'
import { Panel } from './parts'
import { ReportsPanel } from './ReportsPanel'
import { RiskLocksPanel } from './RiskLocksPanel'
import { SafetyCenterPanel } from './SafetyCenterPanel'
import { SelectorPanel } from './SelectorPanel'
import { OpportunitiesPanel, ShadowPanel } from './ShadowResearchPanel'
import { TradingModePanel } from './TradingModePanel'
import './workspace.css'

const RecordingsPanel = lazy(() =>
  import('./RecordingsPanel').then((module) => ({ default: module.RecordingsPanel }))
)
const ExperimentsPanel = lazy(() =>
  import('./ExperimentsPanel').then((module) => ({ default: module.ExperimentsPanel }))
)
const DiscordPanel = lazy(() =>
  import('./DiscordPanel').then((module) => ({ default: module.DiscordPanel }))
)
const ReplayPanel = lazy(() =>
  import('./ReplayPanel').then((module) => ({ default: module.ReplayPanel }))
)

const pages = [
  ['overview', 'Dashboard', LayoutDashboard],
  ['signals', 'Signal Monitor', Activity],
  ['terminal', 'Paper Trading', Play],
  ['positions', 'Positions & Orders', BookOpen],
  ['performance', 'Performance', BarChart3],
  ['research', 'Shadow & Research', Telescope],
  ['reports', 'Reports', FileText],
  ['configuration', 'Strategy Settings', Settings2],
  ['risk', 'Risk Management', ShieldCheck],
  ['calendar', 'Session Calendar', CalendarDays],
  ['connections', 'Connections & Setup', Zap],
] as const

function valueText(value: unknown): string {
  if (value === null || value === undefined) return 'Unavailable'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
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

function IndicatorObservation({ data }: { data: DataRecord | undefined }) {
  const states = data?.indicator_states
  const confidence = data?.confidence
  if (!states || typeof states !== 'object' || Array.isArray(states)) return <Fields data={data} />
  const rows = Object.entries(states).map(([name, value]) => ({
    indicator: name,
    ...(value && typeof value === 'object' && !Array.isArray(value) ? value : {}),
    value: valueText(
      value && typeof value === 'object' && !Array.isArray(value) ? value.value : null
    ),
  }))
  const strength =
    confidence && typeof confidence === 'object' && !Array.isArray(confidence) ? confidence : null
  const contributions = strength?.contributions
  return (
    <>
      <Records data={rows} />
      {strength && (
        <Fields
          data={{
            strength_score: strength.score,
            target_fraction: strength.target_fraction,
            method: strength.method,
          }}
        />
      )}
      {contributions && typeof contributions === 'object' && !Array.isArray(contributions) && (
        <Records
          data={Object.entries(contributions).map(([name, value]) => ({
            indicator: name,
            ...(value && typeof value === 'object' && !Array.isArray(value) ? value : {}),
          }))}
        />
      )}
      <p className="nifty-muted">
        Research strength is not a calibrated win probability. Targets use option premium.
      </p>
    </>
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
        <output>Loading {title.toLowerCase()}…</output>
      ) : query.error ? (
        <p role="alert">{query.error.message}</p>
      ) : records ? (
        <Records data={query.data} />
      ) : name === 'indicators' ? (
        <IndicatorObservation data={query.data} />
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
  const text = draft || JSON.stringify(query.data?.configuration ?? {}, null, 2)
  let current: DataRecord | null = null
  try {
    const parsed: unknown = JSON.parse(text)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed))
      current = parsed as DataRecord
  } catch {
    current = null
  }
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
        <output>Loading configuration…</output>
      ) : query.error ? (
        <p role="alert">{query.error.message}</p>
      ) : (
        <>
          <KeySettings
            value={current}
            onChange={(next) => setDraft(JSON.stringify(next, null, 2))}
          />
          <label htmlFor="nifty-config">Versioned research parameters</label>
          <textarea
            id="nifty-config"
            className="nifty-config"
            value={text}
            onChange={(event) => setDraft(event.target.value)}
            spellCheck={false}
          />
          <p className="nifty-muted">
            Saving creates a configuration version and pauses new entries.
          </p>
          <Button disabled={save.isPending} onClick={submit}>
            Save configuration
          </Button>
          {save.isSuccess && <output>Configuration saved.</output>}
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
    refetchInterval: 5_000,
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
  const monitor = useMutation({
    mutationFn: preparePaperMonitor,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: niftyKeys.all }),
  })
  useEffect(() => {
    if (!socket) return
    const refresh = () => {
      queryClient.invalidateQueries({ queryKey: niftyKeys.all })
    }
    const subscribe = () => socket.emit('nifty_algo_subscribe')
    subscribe()
    socket.on('connect', subscribe)
    socket.on('nifty_algo_update', refresh)
    return () => {
      socket.emit('nifty_algo_unsubscribe')
      socket.off('connect', subscribe)
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
        {status.isPending && <output>Loading paper system status…</output>}
        {status.error && <p role="alert">Status unavailable. {status.error.message}</p>}
        {action.error && <p role="alert">{action.error.message}</p>}
        {monitor.error && <p role="alert">{monitor.error.message}</p>}
        {page !== 'calendar' && <CalendarBanner />}
        {(page === 'overview' || page === 'terminal') && (
          <div className="nifty-controls">
            <Button variant="outline" disabled={monitor.isPending} onClick={() => monitor.mutate()}>
              Connect paper monitor
            </Button>
            <Button
              disabled={action.isPending || !status.data?.ready}
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
              {assessment.isSuccess && <output>Assessment recorded.</output>}
            </div>
            <Resource name="indicators" title="Five-indicator state" />
            <SelectorPanel />
            <Resource name="signals" title="Persisted decisions" records />
          </>
        )}
        {(page === 'positions' || page === 'terminal') && (
          <>
            <p className="nifty-muted">
              Pause, stop and kill disable new entries. The attached paper monitor keeps managing
              protective exits. Triggers cannot guarantee fill prices. Readiness shows data or
              connection blocks; exposure stays open until a confirmed bid-depth fill.
            </p>
            <Resource name="positions" title="Simulated positions" records />
            <Resource name="orders" title="Paper order lifecycle" records />
            <Resource name="trades" title="Trade journal" records />
          </>
        )}
        {page === 'performance' && <AnalyticsPanel />}
        {page === 'research' && (
          <>
            <Suspense fallback={<output>Loading research recordings...</output>}>
              <RecordingsPanel />
            </Suspense>
            <Suspense fallback={<output>Loading experiment definitions...</output>}>
              <ExperimentsPanel />
            </Suspense>
            <Suspense fallback={<output>Loading replay lab...</output>}>
              <ReplayPanel />
            </Suspense>
            <ShadowPanel />
            <OpportunitiesPanel />
          </>
        )}
        {page === 'reports' && <ReportsPanel />}
        {page === 'configuration' && <Configuration />}
        {page === 'risk' && (
          <>
            <SafetyCenterPanel />
            <RiskLocksPanel />
            <Resource name="risk" title="Risk controls & current utilization" />
          </>
        )}
        {page === 'calendar' && <CalendarPanel />}
        {page === 'connections' && (
          <>
            <Suspense fallback={<output>Loading Discord center...</output>}>
              <DiscordPanel />
            </Suspense>
            <TradingModePanel />
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
              This persists the NIFTY entry lockout. The paper monitor continues protective exits.
              Positions remain open until a simulated sell fill is confirmed.
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
