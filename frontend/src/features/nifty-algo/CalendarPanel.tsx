import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarX2, Pencil, Plus, Trash2, Upload } from 'lucide-react'
import { type ChangeEvent, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  approveCalendar,
  type CalendarEntry,
  type CalendarEntryEdit,
  type CalendarVersion,
  MAX_CALENDAR_BYTES,
  niftyKeys,
  readNifty,
  rejectCalendar,
  updateCalendarEntries,
  uploadCalendar,
} from './api'
import { describeError } from './errors'
import { Code, CodeList, Panel, text } from './parts'
import { useRiskOverview } from './RiskLocksPanel'

const calendarKey = [...niftyKeys.all, 'calendar/versions'] as const

/** Prominent block banner when the backend reports no approved calendar for this year. */
export function CalendarBanner() {
  const risk = useRiskOverview()
  const calendar = risk.data?.calendar
  if (calendar?.status !== 'CALENDAR_UNAPPROVED') return null
  return (
    <div className="nifty-banner" role="alert">
      <CalendarX2 size={18} aria-hidden />
      <div>
        <strong>Trading blocked: no approved calendar</strong>
        <p>
          New entries are refused until an NSE F&amp;O holiday calendar for {calendar.year} is
          uploaded and approved. <Code code="CALENDAR_UNAPPROVED" />
        </p>
      </div>
    </div>
  )
}

/** Mirrors the backend approval rule: NFO segment and no ambiguous entry. */
export function approvalBlocks(version: CalendarVersion): string[] {
  const blocks: string[] = []
  if (version.status !== 'DRAFT') blocks.push(`Version is ${version.status}, not a draft.`)
  if (version.segment !== 'NFO') blocks.push(`Segment ${version.segment} is not confirmed as NFO.`)
  const ambiguous = version.entries.filter((entry) => entry.ambiguous).length
  if (ambiguous) blocks.push(`${ambiguous} ambiguous entr${ambiguous === 1 ? 'y' : 'ies'}.`)
  if (!version.entries.length) blocks.push('No holiday entries were parsed.')
  return blocks
}

function statusVariant(status: CalendarVersion['status']) {
  if (status === 'APPROVED') return 'default' as const
  if (status === 'REJECTED') return 'destructive' as const
  return 'secondary' as const
}

interface EditRow {
  key: number
  date: string
  name: string
  weekday: string | null
  raw: string
  originalDate: string | null
  flagged: boolean
  issue: string | null
  confirmed: boolean
  isNew: boolean
}

function toRows(entries: CalendarEntry[]): EditRow[] {
  return entries.map((entry, index) => ({
    key: index,
    date: entry.date ?? '',
    name: entry.name,
    weekday: entry.weekday,
    raw: entry.raw,
    originalDate: entry.date,
    flagged: entry.ambiguous,
    issue: entry.issue,
    confirmed: false,
    isNew: false,
  }))
}

/** The operator has looked at this row's date: typed it, changed it, or confirmed it. */
function reviewed(row: EditRow) {
  return row.isNew || row.confirmed || row.date !== (row.originalDate ?? '')
}

/**
 * The backend recomputes `ambiguous` from the date, weekday, year and duplicates.
 * A reviewed row sends weekday null so the backend derives it from the date; an
 * untouched row keeps the document's stated weekday so a mismatch stays visible.
 */
function entriesPayload(rows: EditRow[]): CalendarEntryEdit[] {
  return rows.map((row) => ({
    date: row.date || null,
    weekday: reviewed(row) ? null : row.weekday,
    name: row.name.trim(),
    raw: row.raw,
  }))
}

function CalendarEntryEditor({
  version,
  onDone,
}: {
  version: CalendarVersion
  onDone: (saved: CalendarVersion | null) => void
}) {
  const queryClient = useQueryClient()
  const [rows, setRows] = useState(() => toRows(version.entries))
  const [nextKey, setNextKey] = useState(version.entries.length)
  const save = useMutation({
    mutationFn: updateCalendarEntries,
    onSuccess: (saved) => {
      queryClient.setQueryData<CalendarVersion[]>(calendarKey, (old) =>
        old?.map((row) => (row.id === saved.id ? saved : row))
      )
      queryClient.invalidateQueries({ queryKey: niftyKeys.all })
      onDone(saved)
    },
  })
  const update = (key: number, change: Partial<EditRow>) =>
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...change } : row)))
  const unreviewed = rows.filter((row) => row.flagged && !reviewed(row)).length
  const failure = save.error ? describeError(save.error) : null
  return (
    <div className="nifty-entry-editor">
      <p className="nifty-muted">
        Correct each flagged row against the NSE circular. Change its date, or tick Date confirmed
        when the date shown is right, or remove the row. The backend re-validates every row on save.
      </p>
      <div className="nifty-table-scroll">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Name</th>
              <th>Flagged issue</th>
              <th>Date confirmed</th>
              <th>Remove</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const label = `row ${index + 1}`
              return (
                <tr key={row.key} data-ambiguous={row.flagged && !reviewed(row)}>
                  <td>
                    <Input
                      type="date"
                      aria-label={`Date for ${label}`}
                      value={row.date}
                      onChange={(event) => update(row.key, { date: event.target.value })}
                    />
                  </td>
                  <td>
                    <Input
                      aria-label={`Name for ${label}`}
                      value={row.name}
                      onChange={(event) => update(row.key, { name: event.target.value })}
                    />
                  </td>
                  <td>
                    {row.issue
                      ? row.issue.split(',').map((code) => <Code key={code} code={code} />)
                      : row.isNew
                        ? 'New row'
                        : 'None'}
                  </td>
                  <td>
                    {row.flagged ? (
                      <Checkbox
                        aria-label={`Date confirmed for ${label}`}
                        checked={row.confirmed}
                        onCheckedChange={(value) => update(row.key, { confirmed: value === true })}
                      />
                    ) : (
                      ''
                    )}
                  </td>
                  <td>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Remove ${label}`}
                      onClick={() =>
                        setRows((current) => current.filter((item) => item.key !== row.key))
                      }
                    >
                      <Trash2 size={14} aria-hidden />
                    </Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {!rows.length && <p className="nifty-empty">No rows. Add the holidays from the circular.</p>}
      {unreviewed > 0 && (
        <p className="nifty-muted">
          {unreviewed} flagged row{unreviewed === 1 ? '' : 's'} still need review before saving.
        </p>
      )}
      <div className="nifty-controls">
        <Button
          variant="outline"
          onClick={() => {
            setRows((current) => [
              ...current,
              {
                key: nextKey,
                date: '',
                name: '',
                weekday: null,
                raw: '',
                originalDate: null,
                flagged: false,
                issue: null,
                confirmed: false,
                isNew: true,
              },
            ])
            setNextKey((key) => key + 1)
          }}
        >
          <Plus size={14} />
          Add row
        </Button>
        <Button
          disabled={save.isPending || unreviewed > 0}
          onClick={() => save.mutate({ id: version.id, entries: entriesPayload(rows) })}
        >
          {save.isPending ? 'Saving…' : 'Save entries'}
        </Button>
        <Button variant="ghost" disabled={save.isPending} onClick={() => onDone(null)}>
          Cancel editing
        </Button>
      </div>
      {failure && (
        <p role="alert">
          Entries not saved: {failure.message}
          {failure.code ? ` (${failure.code})` : ''}
        </p>
      )}
    </div>
  )
}

function VersionDetail({ version }: { version: CalendarVersion }) {
  const queryClient = useQueryClient()
  const [confirmed, setConfirmed] = useState(false)
  const [editing, setEditing] = useState(false)
  const [savedNotice, setSavedNotice] = useState('')
  const refresh = () => queryClient.invalidateQueries({ queryKey: niftyKeys.all })
  const approve = useMutation({ mutationFn: approveCalendar, onSuccess: refresh })
  const reject = useMutation({ mutationFn: rejectCalendar, onSuccess: refresh })
  const blocks = [...approvalBlocks(version), ...(editing ? ['Entry edits are not saved.'] : [])]
  const busy = approve.isPending || reject.isPending
  const failure = approve.error || reject.error
  return (
    <div className="nifty-calendar-detail">
      <h3 className="nifty-subhead">
        Version {version.id}: {version.year} {version.segment}{' '}
        <Badge variant={statusVariant(version.status)}>{version.status}</Badge>
      </h3>
      <p className="nifty-muted">
        Source {version.source_filename} · uploaded {version.created_at}
        {version.approved_at ? ` · approved ${version.approved_at}` : ''}
      </p>
      <h4 className="nifty-subhead">Validation issues</h4>
      <CodeList codes={version.issues} label="Calendar issues" empty="No validation issues." />
      {savedNotice && <output>{savedNotice}</output>}
      <h4 className="nifty-subhead">
        Parsed holidays
        {version.status === 'DRAFT' && !editing && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setSavedNotice('')
              setConfirmed(false)
              setEditing(true)
            }}
          >
            <Pencil size={14} />
            Edit entries
          </Button>
        )}
      </h4>
      {editing && version.status === 'DRAFT' ? (
        <CalendarEntryEditor
          version={version}
          onDone={(saved) => {
            setEditing(false)
            if (saved)
              setSavedNotice(
                saved.issues.length
                  ? `Entries saved. The backend reported ${saved.issues.length} validation issue${saved.issues.length === 1 ? '' : 's'}.`
                  : 'Entries saved. The backend reported no validation issues.'
              )
          }}
        />
      ) : version.entries.length ? (
        <div className="nifty-table-scroll">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Weekday</th>
                <th>Name</th>
                <th>Issue</th>
              </tr>
            </thead>
            <tbody>
              {version.entries.map((entry, index) => (
                <tr key={`${entry.date ?? 'undated'}-${index}`} data-ambiguous={entry.ambiguous}>
                  <td>{text(entry.date, 'Unreadable')}</td>
                  <td>{text(entry.weekday, '')}</td>
                  <td>{entry.name}</td>
                  <td>
                    {entry.issue
                      ? entry.issue.split(',').map((code) => <Code key={code} code={code} />)
                      : 'None'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="nifty-empty">No holiday entries parsed.</p>
      )}
      {version.preview_diff &&
        (version.preview_diff.legacy_only.length > 0 ||
          version.preview_diff.calendar_only.length > 0) && (
          <p className="nifty-muted">
            Differs from the built-in holiday list. Only in built-in list:{' '}
            {version.preview_diff.legacy_only.join(', ') || 'none'}. Only in this calendar:{' '}
            {version.preview_diff.calendar_only.join(', ') || 'none'}.
          </p>
        )}
      {version.status === 'DRAFT' && (
        <>
          {blocks.length > 0 && (
            <div className="nifty-blocked">
              <strong>Approval blocked</strong>
              <ul>
                {blocks.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="nifty-check">
            <Checkbox
              id={`calendar-confirm-${version.id}`}
              checked={confirmed}
              disabled={blocks.length > 0}
              onCheckedChange={(value) => setConfirmed(value === true)}
            />
            <Label htmlFor={`calendar-confirm-${version.id}`}>
              I confirm this is the {version.year} {version.segment} trading holiday calendar.
            </Label>
          </div>
          <div className="nifty-controls">
            <Button
              disabled={busy || blocks.length > 0 || !confirmed}
              onClick={() => approve.mutate(version)}
            >
              Approve calendar
            </Button>
            <Button variant="outline" disabled={busy} onClick={() => reject.mutate(version.id)}>
              Reject calendar
            </Button>
          </div>
        </>
      )}
      {failure && (
        <p role="alert">
          {describeError(failure).message}
          {describeError(failure).code ? ` (${describeError(failure).code})` : ''}
        </p>
      )}
      {approve.isSuccess && <output>Calendar approved.</output>}
      {reject.isSuccess && <output>Calendar rejected.</output>}
    </div>
  )
}

export function CalendarPanel() {
  const queryClient = useQueryClient()
  const versions = useQuery({
    queryKey: calendarKey,
    queryFn: () => readNifty<CalendarVersion[]>('calendar/versions'),
  })
  const [selected, setSelected] = useState<number | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [year, setYear] = useState('')
  const [fileError, setFileError] = useState('')
  const upload = useMutation({
    mutationFn: uploadCalendar,
    onSuccess: (version) => {
      setSelected(version.id)
      setFile(null)
      queryClient.invalidateQueries({ queryKey: niftyKeys.all })
    },
  })
  const rows = Array.isArray(versions.data) ? versions.data : []
  const current =
    rows.find((row) => row.id === selected) ?? rows.find((row) => row.status === 'DRAFT') ?? rows[0]

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] ?? null
    upload.reset()
    if (next && next.size > MAX_CALENDAR_BYTES) {
      setFile(null)
      setFileError('File exceeds the 2 MB limit.')
      return
    }
    setFileError('')
    setFile(next)
  }

  function submit() {
    if (!file) return
    const parsedYear = year ? Number(year) : undefined
    if (parsedYear !== undefined && !(Number.isInteger(parsedYear) && parsedYear >= 2000)) {
      setFileError('Year must be a four-digit year.')
      return
    }
    upload.mutate({ file, year: parsedYear })
  }

  const uploadFailure = upload.error ? describeError(upload.error) : null
  return (
    <>
      <CalendarBanner />
      <Panel title="Upload NSE F&O holiday calendar">
        <div className="nifty-form">
          <Label htmlFor="nifty-calendar-file">Holiday circular (PDF or CSV)</Label>
          <Input
            id="nifty-calendar-file"
            type="file"
            accept=".pdf,.csv,application/pdf,text/csv"
            onChange={choose}
          />
          <p className="nifty-muted">
            Maximum 2 MB. CSV needs date,name columns. Uploads are never auto-approved.
          </p>
          <Label htmlFor="nifty-calendar-year">Calendar year (optional)</Label>
          <Input
            id="nifty-calendar-year"
            inputMode="numeric"
            placeholder="Detected from the document"
            value={year}
            onChange={(event) => setYear(event.target.value.trim())}
          />
          <div>
            <Button disabled={!file || upload.isPending} onClick={submit}>
              <Upload size={14} />
              {upload.isPending ? 'Uploading…' : 'Upload calendar'}
            </Button>
          </div>
        </div>
        {fileError && <p role="alert">{fileError}</p>}
        {uploadFailure && (
          <p role="alert">
            {uploadFailure.message}
            {uploadFailure.code ? ` (${uploadFailure.code})` : ''}
          </p>
        )}
        {upload.isSuccess && <output>Draft created. Review it below before approving.</output>}
      </Panel>
      <Panel title="Calendar versions">
        {versions.isPending ? (
          <output>Loading calendar versions…</output>
        ) : versions.error ? (
          <p role="alert">{versions.error.message}</p>
        ) : !rows.length ? (
          <p className="nifty-empty">No calendar uploaded yet.</p>
        ) : (
          <>
            <div className="nifty-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>Year</th>
                    <th>Segment</th>
                    <th>Status</th>
                    <th>Holidays</th>
                    <th>Issues</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} aria-selected={row.id === current?.id}>
                      <td>
                        <Button size="sm" variant="ghost" onClick={() => setSelected(row.id)}>
                          View {row.id}
                        </Button>
                      </td>
                      <td>{row.year}</td>
                      <td>{row.segment}</td>
                      <td>
                        <Badge variant={statusVariant(row.status)}>{row.status}</Badge>
                      </td>
                      <td>{row.entries.length}</td>
                      <td>{row.issues.length}</td>
                      <td>{row.source_filename}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {current && <VersionDetail key={current.id} version={current} />}
          </>
        )}
      </Panel>
    </>
  )
}
