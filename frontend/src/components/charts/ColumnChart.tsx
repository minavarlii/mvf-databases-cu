import { useId } from 'react'
import { barUp, niceTicks, useWidth } from './scale'

export interface Column {
  label: string
  value: number
  valueLabel: string
  tooltip: string
  marker?: number | null
  muted?: boolean
}

interface Props {
  title: string
  description: string
  columns: Column[]
  yMax: number
  yTicks?: number[]
  formatTick: (v: number) => string
  yLabel: string
  xLabel: string
}

const HEIGHT = 250
const TOP = 34
const BOTTOM = 46

export function ColumnChart({ title, description, columns, yMax, yTicks, formatTick, yLabel, xLabel }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const id = useId()
  const ticks = yTicks ?? niceTicks(yMax)
  const top = Math.max(yMax, ticks[ticks.length - 1])
  const left = 42
  const right = 8
  const plotW = Math.max(0, width - left - right)
  const baseline = HEIGHT - BOTTOM
  const y = (v: number) => baseline - (v / top) * (baseline - TOP)
  const band = plotW / columns.length
  const barW = Math.min(44, band * 0.62)

  return (
    <div className="chart" ref={ref}>
      {width > 0 && (
        <svg width={width} height={HEIGHT} role="img" aria-labelledby={`${id}-t ${id}-d`}>
          <title id={`${id}-t`}>{title}</title>
          <desc id={`${id}-d`}>{description}</desc>

          <text className="chart-axis-title" x={0} y={12}>
            {yLabel}
          </text>
          {ticks.map((t) => (
            <g key={t}>
              <line className={t === 0 ? 'chart-baseline' : 'chart-grid'} x1={left} x2={width - right} y1={y(t)} y2={y(t)} />
              <text className="chart-tick" x={left - 8} y={y(t)} dy="0.32em" textAnchor="end">
                {formatTick(t)}
              </text>
            </g>
          ))}

          {columns.map((c, i) => {
            const cx = left + band * i + band / 2
            const x = cx - barW / 2
            const barTop = y(c.value)
            const markerY = c.marker == null ? null : y(c.marker)
            const labelY = Math.min(barTop, markerY ?? barTop) - 8
            return (
              <g key={c.label}>
                <title>{c.tooltip}</title>
                <rect className="chart-hit" x={left + band * i} y={TOP} width={band} height={baseline - TOP} />
                {c.value > 0 && (
                  <path className={c.muted ? 'chart-bar is-muted' : 'chart-bar'} d={barUp(x, barTop, barW, baseline)} />
                )}
                {markerY !== null && (
                  <>
                    <line className="chart-marker-ring" x1={x - 5} x2={x + barW + 5} y1={markerY} y2={markerY} />
                    <line className="chart-marker" x1={x - 5} x2={x + barW + 5} y1={markerY} y2={markerY} />
                  </>
                )}
                <text className="chart-value" x={cx} y={labelY} textAnchor="middle">
                  {c.valueLabel}
                </text>
                <text className="chart-tick" x={cx} y={baseline + 17} textAnchor="middle">
                  {c.label}
                </text>
              </g>
            )
          })}

          <text className="chart-axis-title" x={left + plotW / 2} y={HEIGHT - 4} textAnchor="middle">
            {xLabel}
          </text>
        </svg>
      )}
    </div>
  )
}
