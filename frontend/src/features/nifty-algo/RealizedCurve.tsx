interface CurvePoint {
  timestamp: string
  value: string
}

export function RealizedCurve({
  title,
  opening,
  start,
  points,
}: {
  title: string
  opening: string
  start: string
  points: CurvePoint[]
}) {
  if (!points.length) return <p className="nifty-empty">No fills for {title.toLowerCase()}.</p>
  const series = [{ timestamp: start, value: opening }, ...points]
  const values = series.map((point) => Number(point.value))
  const times = series.map((point) => Date.parse(point.timestamp))
  if (!values.every(Number.isFinite) || !times.every(Number.isFinite)) {
    return <p className="nifty-empty">{title} chart unavailable.</p>
  }
  const low = Math.min(...values)
  const high = Math.max(...values)
  const duration = Math.max(1, times[times.length - 1] - times[0])
  const x = (index: number) => 90 + ((times[index] - times[0]) * 530) / duration
  const y = (value: number) => 175 - ((value - low) * 145) / (high - low || 1)
  const path = values
    .map((value, index) => (index === 0 ? `M${x(index)} ${y(value)}` : `H${x(index)} V${y(value)}`))
    .join(' ')
  return (
    <figure className="min-w-0">
      <figcaption>{title} (Rs)</figcaption>
      <svg role="img" aria-label={`${title} chart`} viewBox="0 0 640 220" className="w-full">
        <title>
          {title}: {points.length} fill observations, from {opening} to{' '}
          {points[points.length - 1].value} Rs
        </title>
        <desc>
          Step curve at persisted exit-fill times, not mark-to-market. Horizontal axis is elapsed
          time in UTC.
        </desc>
        <line x1="90" x2="620" y1="175" y2="175" stroke="currentColor" opacity="0.3" />
        <line x1="90" x2="620" y1="30" y2="30" stroke="currentColor" opacity="0.3" />
        <text x="4" y="35" fill="currentColor" fontSize="12">
          {high.toFixed(2)}
        </text>
        <text x="4" y="180" fill="currentColor" fontSize="12">
          {low.toFixed(2)}
        </text>
        <path d={path} fill="none" stroke="currentColor" strokeWidth="2" />
        <text x="90" y="205" fill="currentColor" fontSize="11">
          {start.slice(0, 19)} UTC
        </text>
        <text x="620" y="220" textAnchor="end" fill="currentColor" fontSize="11">
          {points[points.length - 1].timestamp.slice(0, 19)} UTC
        </text>
      </svg>
      <p className="nifty-muted">
        {points.length} exit-fill observations. Start {opening}; end{' '}
        {points[points.length - 1].value} Rs.
      </p>
    </figure>
  )
}
