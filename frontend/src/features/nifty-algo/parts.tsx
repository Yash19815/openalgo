import { Check, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { codeLabel } from './labels'

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="nifty-panel">
      <h2>{title}</h2>
      {children}
    </section>
  )
}

/** A backend code as a human label, with the raw code kept visible. */
export function Code({ code }: { code: string }) {
  return (
    <span className="nifty-code-item">
      <span>{codeLabel(code)}</span>
      <code>{code}</code>
    </span>
  )
}

export function CodeList({
  codes,
  empty,
  label,
}: {
  codes: string[]
  empty: string
  label: string
}) {
  if (!codes.length) return <p className="nifty-empty">{empty}</p>
  return (
    <ul className="nifty-codes" aria-label={label}>
      {codes.map((code) => (
        <li key={code}>
          <Code code={code} />
        </li>
      ))}
    </ul>
  )
}

/** A presence or state boolean rendered as an icon with readable text. */
export function Flag({ value, label }: { value: boolean; label: string }) {
  return (
    <span className="nifty-flag" data-state={value ? 'yes' : 'no'}>
      {value ? <Check size={14} aria-hidden /> : <X size={14} aria-hidden />}
      <span>
        {label}: {value ? 'Yes' : 'No'}
      </span>
    </span>
  )
}

export function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="nifty-fields">
      {rows.map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function text(value: string | number | null | undefined, fallback = 'Unavailable') {
  return value === null || value === undefined || value === '' ? fallback : String(value)
}
