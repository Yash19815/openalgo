import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MailWarning } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  type NiftyReport,
  niftyKeys,
  type ReportList,
  readNifty,
  reportPdfUrl,
  resendReport,
} from './api'
import { describeError, type NiftyApiError } from './errors'
import { Code, Panel, text } from './parts'

const reportsKey = [...niftyKeys.all, 'reports'] as const

const KIND_LABELS: Record<string, string> = {
  DAILY: 'Daily',
  MILESTONE: 'Milestone',
  MONTH_END: 'Month-end',
}

/** FAILED and SKIPPED_NO_SMTP can be queued again; the server re-checks with compare-and-set. */
function resendable(row: NiftyReport) {
  return (
    row.generation_status === 'GENERATED' &&
    (row.delivery_status === 'FAILED' || row.delivery_status === 'SKIPPED_NO_SMTP')
  )
}

function kindLabel(row: NiftyReport) {
  const label = KIND_LABELS[row.kind] ?? row.kind
  return row.variant === 'ZERO_TRADE' ? `${label} (zero-trade)` : label
}

export function ReportsPanel() {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: reportsKey,
    queryFn: () => readNifty<ReportList>('reports'),
    refetchInterval: 30_000,
  })
  const [failure, setFailure] = useState<NiftyApiError | null>(null)
  const [notice, setNotice] = useState('')
  const resend = useMutation({
    mutationFn: resendReport,
    onMutate: () => {
      setFailure(null)
      setNotice('')
    },
    onSuccess: (row) => {
      setNotice(`Report ${row.period_key} queued for delivery.`)
      queryClient.invalidateQueries({ queryKey: reportsKey })
    },
    onError: (error) => {
      setFailure(describeError(error))
      queryClient.invalidateQueries({ queryKey: reportsKey })
    },
  })
  const data = query.data
  const rows = Array.isArray(data?.reports) ? data.reports : []
  return (
    <Panel title="Reports">
      <p className="nifty-muted">
        Daily, milestone and month-end PDF reports of the paper system. Mirror P&amp;L in reports is
        non-additive. Reports never place orders.
      </p>
      {data?.smtp_configured === false && (
        <div className="nifty-banner nifty-banner-info">
          <MailWarning size={16} aria-hidden />
          <p>
            SMTP is not configured, so email delivery is skipped (SKIPPED_NO_SMTP). Reports are
            still generated and can be downloaded here. Configure SMTP in{' '}
            <Link to="/profile">account settings</Link>, then resend.
          </p>
        </div>
      )}
      {query.isPending ? (
        <output>Loading reports…</output>
      ) : query.error ? (
        <p role="alert">{query.error.message}</p>
      ) : !rows.length ? (
        <p className="nifty-empty">No reports generated yet.</p>
      ) : (
        <div className="nifty-table-scroll">
          <table aria-label="Generated reports">
            <thead>
              <tr>
                <th>Kind</th>
                <th>Period</th>
                <th>Generation</th>
                <th>Delivery</th>
                <th>Attempts</th>
                <th>Next attempt / sent</th>
                <th>Notes</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{kindLabel(row)}</td>
                  <td>{row.period_key}</td>
                  <td>
                    {row.generation_status}
                    {row.generation_error_type ? ` (${row.generation_error_type})` : ''}
                  </td>
                  <td>
                    <Badge
                      variant={
                        row.delivery_status === 'SENT'
                          ? 'secondary'
                          : row.delivery_status === 'FAILED'
                            ? 'destructive'
                            : 'outline'
                      }
                    >
                      {row.delivery_status}
                    </Badge>
                    {row.last_error_type ? ` ${row.last_error_type}` : ''}
                  </td>
                  <td>
                    {row.attempts} / {data?.max_attempts ?? '—'}
                  </td>
                  <td>{text(row.sent_at ?? row.next_attempt_at, '')}</td>
                  <td>
                    {(row.summary?.zero_trade_reasons ?? []).map((code) => (
                      <Code key={code} code={code} />
                    ))}
                  </td>
                  <td>
                    <div className="nifty-controls">
                      {row.generation_status === 'GENERATED' && row.filename && (
                        <a href={reportPdfUrl(row.id)} download={row.filename}>
                          Download {row.filename}
                        </a>
                      )}
                      {resendable(row) && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={resend.isPending}
                          onClick={() => resend.mutate(row.id)}
                        >
                          Resend {row.period_key}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {failure && (
        <p role="alert" className="nifty-refusal">
          Resend refused: {failure.message}
          {failure.code ? ` (${failure.code})` : ''}
        </p>
      )}
      {notice && <output>{notice}</output>}
    </Panel>
  )
}
