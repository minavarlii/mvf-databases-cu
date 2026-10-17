import { useId } from 'react'
import type { ReactNode } from 'react'

export interface LegendItem {
  kind: 'bar' | 'muted' | 'marker' | 'whisker'
  label: string
}

interface Props {
  title: string
  icon: ReactNode
  tone: string
  legend?: LegendItem[]
  caption?: ReactNode
  source?: string | null
  table?: { head: string[]; rows: (string | number)[][] }
  children: ReactNode
}

export function ChartCard({ title, icon, tone, legend, caption, source, table, children }: Props) {
  const id = useId()
  return (
    <section className="card eval-card" aria-labelledby={id}>
      <div className="eval-card-head">
        <h3 id={id} className="section-title">
          <span className={`icon-dot ${tone}`}>{icon}</span>
          {title}
        </h3>
        {legend && legend.length > 0 && (
          <ul className="chart-legend" aria-label="Legend">
            {legend.map((l) => (
              <li key={l.label}>
                <span className={`chart-key is-${l.kind}`} aria-hidden="true" />
                {l.label}
              </li>
            ))}
          </ul>
        )}
      </div>
      {children}
      {caption && <p className="eval-caption">{caption}</p>}
      {(source || table) && (
        <div className="eval-card-foot">
          {source && <p className="mono eval-source">{source}</p>}
          {table && (
            <details className="eval-table">
              <summary>Show data table</summary>
              <div className="eval-table-scroll">
                <table>
                  <thead>
                    <tr>
                      {table.head.map((h) => (
                        <th key={h} scope="col">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {table.rows.map((row, i) => (
                      <tr key={i}>
                        {row.map((cell, j) =>
                          j === 0 ? (
                            <th key={j} scope="row">
                              {cell}
                            </th>
                          ) : (
                            <td key={j} className="mono">
                              {cell}
                            </td>
                          ),
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </div>
      )}
    </section>
  )
}
