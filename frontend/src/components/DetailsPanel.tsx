import { useState } from 'react'
import { VECTOR_INDEX } from '../api'
import type { MariaDbDetails, PlanRow, SearchFilters } from '../api'
import { filterCount as countFilters, searchKind } from './filters'
import { CheckIcon, ChevronDownIcon, DatabaseIcon, SlidersIcon, WarningIcon } from './icons'
import { SqlBlock } from './SqlBlock'
import { paletteTone } from './tones'

interface Props {
  details: MariaDbDetails
  scope: 'answer' | 'search' | 'empty'
  filters: SearchFilters
}

const TOTAL_NOTES: Record<Props['scope'], string> = {
  answer: 'From pressing Ask to the finished answer, including embedding the question and the LLM.',
  search: 'From sending the question to getting the passages back, including embedding the question.',
  empty: 'From sending the question to getting the (empty) result back, including embedding the question.',
}

const CHUNK_NOTES: Record<Props['scope'], string> = {
  answer: 'Passages MariaDB returned for the LLM to answer from.',
  search: 'Passages MariaDB returned as the closest matches.',
  empty: 'MariaDB ran the query, but no rows matched.',
}

const ms = (millis: number) => `${millis.toFixed(1)} ms`
const duration = (millis: number) => (millis >= 1000 ? `${(millis / 1000).toFixed(2)} s` : `${Math.round(millis)} ms`)

function PlanTable({ plan, linked }: { plan: PlanRow[]; linked: boolean }) {
  return (
    <div className="plan">
      <h3 className="sql-title">Query plan (EXPLAIN)</h3>
      <p className="sql-caption">
        How MariaDB ran the query above, one row per table it read.{' '}
        {linked && (
          <>
            It starts from the source article (<span className="mono">source</span>), follows{' '}
            <span className="mono">article_links</span> (<span className="mono">al</span>) to the linked articles, then
            reads only their chunks (<span className="mono">c</span>).{' '}
          </>
        )}
        {plan.some((r) => r.key === VECTOR_INDEX) && (
          <>
            The <span className="plan-legend">highlighted row</span> reads <span className="mono">chunks</span> through
            the vector index <span className="mono">{VECTOR_INDEX}</span>.
          </>
        )}
      </p>
      <div className="plan-scroll" tabIndex={0} role="region" aria-label="Query plan">
        <table className="plan-table mono">
          <thead>
            <tr>
              <th scope="col">id</th>
              <th scope="col">select_type</th>
              <th scope="col">table</th>
              <th scope="col">type</th>
              <th scope="col">key</th>
              <th scope="col">rows</th>
              <th scope="col">Extra</th>
            </tr>
          </thead>
          <tbody>
            {plan.map((r, i) => (
              <tr key={i} className={r.key === VECTOR_INDEX ? 'is-index' : undefined}>
                <td>{r.select_id}</td>
                <td>{r.select_type}</td>
                <td>{r.table}</td>
                <td>{r.access_type ?? 'NULL'}</td>
                <td>{r.key ?? 'NULL'}</td>
                <td>{r.rows ?? 'NULL'}</td>
                <td>{r.extra || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function DetailsPanel({ details, scope, filters }: Props) {
  const filterCount = countFilters(filters)
  const linked = searchKind(filters) === 'linked'
  const [open, setOpen] = useState(true)
  // Reset during render when the result changes (no effect needed).
  const [shownFor, setShownFor] = useState(details)
  if (shownFor !== details) {
    setShownFor(details)
    setOpen(true)
  }

  const indexUsed = details.vector_index_used
  const noIndex = indexUsed === false
  const indexLabel = indexUsed === null ? 'index: unknown' : indexUsed ? 'index used' : 'index not used'
  const summary = `${ms(details.search_latency_ms)} search · ${indexLabel}`

  const tiles = [
    {
      tone: noIndex ? 'is-warn' : `tone-${paletteTone(1)}`,
      label: 'Search latency',
      value: ms(details.search_latency_ms),
      note: 'How long MariaDB took to run the vector query below.',
    },
    {
      tone: `tone-${paletteTone(3)}`,
      label: 'Total response time',
      value: duration(details.total_response_ms),
      note: TOTAL_NOTES[scope],
    },
    {
      tone: `tone-${paletteTone(2)}`,
      label: 'Chunks retrieved',
      value: String(details.chunk_count),
      note: CHUNK_NOTES[scope],
    },
  ]

  return (
    <section
      className={noIndex ? 'card details is-warn' : 'card details'}
      aria-labelledby="details-title"
    >
      <div className="details-head">
        <div className="details-title">
          <h2 id="details-title" className="section-title">
            <span className="icon-dot details-dot">
              <DatabaseIcon size={17} />
            </span>
            MariaDB details
          </h2>
          <div className="details-pills">
            <span className={noIndex ? 'mono details-summary is-warn' : 'mono details-summary'}>
              {indexUsed && <CheckIcon size={13} />}
              {noIndex && <WarningIcon size={13} />}
              {summary}
            </span>
            {filterCount > 0 && (
              <span className="mono details-filters">
                <SlidersIcon size={13} />
                {filterCount} SQL {filterCount === 1 ? 'filter' : 'filters'} applied
              </span>
            )}
          </div>
        </div>
        <button
          type="button"
          className="details-toggle"
          aria-expanded={open}
          aria-controls="details-body"
          onClick={() => setOpen((o) => !o)}
        >
          {open ? 'Hide' : 'Show'}
          <span className="sr-only"> MariaDB details</span>
          <ChevronDownIcon size={15} />
        </button>
      </div>

      <div id="details-body" className="details-body" hidden={!open}>
        {noIndex && (
          <div className="details-warning">
            <span className="details-warning-icon">
              <WarningIcon size={18} />
            </span>
            {linked ? (
              <div>
                <h3>Vector index not used: only linked articles are ranked</h3>
                <p>
                  MariaDB first found the articles linked from <b>{filters.source_title}</b> through{' '}
                  <span className="mono">article_links</span>, then computed the exact cosine distance for each of
                  their chunks, read through <span className="mono">ix_chunks_article_id</span>. With that few
                  candidates, this is cheaper than the HNSW index, so the backend keeps this plan on purpose.
                </p>
              </div>
            ) : (
              <div>
                <h3>Vector index not used for this query</h3>
                <p>
                  MariaDB compared your question against every {filterCount > 0 ? 'row that passed the filters' : 'row'},
                  one by one (a brute-force scan), instead of using the HNSW vector index to jump to the nearest ones.
                  Results are still exact, but this gets much slower as the table grows.
                </p>
              </div>
            )}
          </div>
        )}

        <dl className="metrics">
          {tiles.map((t) => (
            <div key={t.label} className={`metric ${t.tone}`}>
              <dt>{t.label}</dt>
              <dd className="mono metric-value">{t.value}</dd>
              <dd className="metric-note">{t.note}</dd>
            </div>
          ))}
          <div className={noIndex ? 'metric is-warn' : `metric tone-${paletteTone(0)}`}>
            <dt>Vector index used</dt>
            <dd className="mono metric-value">
              {indexUsed && <CheckIcon size={18} />}
              {noIndex && <WarningIcon size={18} />}
              {indexUsed === null ? '—' : indexUsed ? 'Yes' : 'No'}
            </dd>
            <dd className="metric-note">
              {indexUsed === null
                ? 'Unknown: the backend didn’t send the query plan for this request.'
                : indexUsed
                  ? 'MariaDB used its vector index to go straight to the closest chunks instead of checking every row.'
                  : linked
                    ? 'MariaDB ranked only the chunks of the linked articles, computing each distance exactly.'
                    : 'MariaDB checked every stored vector (full scan). Fine for small tables, slow for big ones.'}
            </dd>
          </div>
        </dl>

        <SqlBlock sql={details.sql} markFilters={filterCount > 0} />
        {details.query_plan.length > 0 && <PlanTable plan={details.query_plan} linked={linked} />}
      </div>
    </section>
  )
}
