import { useId } from 'react'
import { barRight, formatMs, niceTicks, useWidth } from './scale'

interface LatencyRow {
  label: string
  p50: number
  p95: number
  note?: string
}

interface Props {
  title: string
  description: string
  rows: LatencyRow[]
  max?: number
  xLabel: string
}

const ROW = 64
const ROW_NARROW = 78
const TOP = 6
const BOTTOM = 44
const BAR = 14

export function LatencyChart({ title, description, rows, max, xLabel }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const id = useId()
  const ticks = niceTicks(max ?? Math.max(...rows.map((r) => r.p95)))
  const top = ticks[ticks.length - 1]
  const narrow = width < 480
  const left = narrow ? 104 : 160
  const rowH = narrow ? ROW_NARROW : ROW
  const right = 14
  const plotW = Math.max(0, width - left - right)
  const x = (v: number) => left + (v / top) * plotW
  const height = TOP + rows.length * rowH + BOTTOM
  const axisY = TOP + rows.length * rowH

  return (
    <div className="chart" ref={ref}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-labelledby={`${id}-t ${id}-d`}>
          <title id={`${id}-t`}>{title}</title>
          <desc id={`${id}-d`}>{description}</desc>

          {ticks.map((t) => (
            <g key={t}>
              <line className={t === 0 ? 'chart-baseline' : 'chart-grid'} x1={x(t)} x2={x(t)} y1={TOP} y2={axisY} />
              <text className="chart-tick" x={x(t)} y={axisY + 16} textAnchor="middle">
                {String(t)}
              </text>
            </g>
          ))}

          {rows.map((r, i) => {
            const rowY = TOP + i * rowH
            const cy = rowY + rowH / 2 - 4
            const len = Math.max(2, x(r.p50) - left)
            const p95x = Math.max(left + len, x(r.p95))
            return (
              <g key={r.label}>
                <title>{`${r.label}: median ${formatMs(r.p50)} ms, p95 ${formatMs(r.p95)} ms`}</title>
                <rect className="chart-hit" x={0} y={rowY} width={width} height={rowH} />
                <text className="chart-row-label" x={0} y={rowY + 20}>
                  {r.label}
                </text>
                {narrow ? (
                  <>
                    <text className="chart-row-values" x={0} y={rowY + 37}>{`p50 ${formatMs(r.p50)} ms`}</text>
                    <text className="chart-row-values" x={0} y={rowY + 52}>{`p95 ${formatMs(r.p95)} ms`}</text>
                  </>
                ) : (
                  <text className="chart-row-values" x={0} y={rowY + 37}>
                    {`p50 ${formatMs(r.p50)} · p95 ${formatMs(r.p95)} ms`}
                  </text>
                )}
                {r.note && (
                  <text className="chart-row-note" x={0} y={rowY + (narrow ? 67 : 53)}>
                    {r.note}
                  </text>
                )}
                <path className="chart-bar" d={barRight(left, cy - BAR / 2, len, BAR)} />
                {p95x > left + len + 1 && <line className="chart-whisker" x1={left + len} x2={p95x} y1={cy} y2={cy} />}
                <line className="chart-whisker" x1={p95x} x2={p95x} y1={cy - 6} y2={cy + 6} />
              </g>
            )
          })}

          <text className="chart-axis-title" x={left + plotW / 2} y={height - 4} textAnchor="middle">
            {xLabel}
          </text>
        </svg>
      )}
    </div>
  )
}
