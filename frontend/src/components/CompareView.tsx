import { useEffect, useId, useRef, useState } from 'react'
import type { MouseEventHandler, ReactNode } from 'react'
import type { Chunk, MariaDbDetails, SearchFilters } from '../api'
import { filterLabels, searchKind } from './filters'
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckIcon,
  ChevronDownIcon,
  CompareIcon,
  DatabaseIcon,
  SearchIcon,
  SlidersIcon,
  VectorSearchIcon,
  WarningIcon,
} from './icons'
import { LoadingCard } from './LoadingCard'
import { SqlBlock } from './SqlBlock'
import { StatusMessage } from './StatusMessage'
import { articleTones } from './tones'
import type { Tone } from './tones'
import { useMediaQuery } from './useMediaQuery'

type CompareSide =
  | { status: 'loading' }
  | { status: 'done'; chunks: Chunk[]; details: MariaDbDetails }
  | { status: 'error'; message: string; detail: string | null }

export type SideKey = 'vector' | 'hybrid'

export interface Comparison {
  filters: SearchFilters // sent with the filtered ('hybrid' key: category or linked) search only
  vector: CompareSide
  hybrid: CompareSide
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`
const ms = (millis: number) => `${millis.toFixed(1)} ms`

type Mark =
  | { kind: 'both'; twinRank: number } // 1-based
  | { kind: 'out'; reason: string }
  | { kind: 'dropped' } // its article is in the filtered result, so no filter excluded it
  | { kind: 'new' }
  | { kind: 'none' }

interface Diff {
  vector: Mark[]
  hybrid: Mark[]
  removed: number
  added: number
  postFiltered: number
}

function diff(vector: Chunk[], hybrid: Chunk[], filters: SearchFilters): Diff {
  const vRank = new Map(vector.map((c, i) => [c.chunk_id, i + 1]))
  const hRank = new Map(hybrid.map((c, i) => [c.chunk_id, i + 1]))
  const hybridArticles = new Set(hybrid.map((c) => c.article_id))
  // Filters apply per article, so with exactly one filter a missing article was excluded by it.
  const labels = filterLabels(filters)
  const reason = filters.source_title
    ? `Not linked from ${filters.source_title}`
    : labels.length === 1
      ? `Excluded by ${labels[0]}`
      : `Not in ${filteredName(filters)}`

  const vMarks = vector.map((c): Mark => {
    const twin = hRank.get(c.chunk_id)
    if (twin) return { kind: 'both', twinRank: twin }
    return hybridArticles.has(c.article_id) ? { kind: 'dropped' } : { kind: 'out', reason }
  })
  const hMarks = hybrid.map((c): Mark => {
    const twin = vRank.get(c.chunk_id)
    return twin ? { kind: 'both', twinRank: twin } : { kind: 'new' }
  })

  return {
    vector: vMarks,
    hybrid: hMarks,
    removed: vMarks.filter((m) => m.kind !== 'both').length,
    added: hMarks.filter((m) => m.kind === 'new').length,
    postFiltered: vMarks.filter((m) => m.kind !== 'out').length,
  }
}

// What the filtered side is called: category filters run as hybrid search, a linked article as linked search.
const filteredName = (filters: SearchFilters) => (searchKind(filters) === 'linked' ? 'linked' : 'hybrid')

function summaryText(c: Comparison, d: Diff | null): { main: string; extra?: string } {
  const { vector, hybrid } = c
  if (vector.status === 'error' || hybrid.status === 'error') {
    if (vector.status === 'error' && hybrid.status === 'error') return { main: 'Both searches failed, so there is nothing to compare yet.' }
    return {
      main: `The ${vector.status === 'error' ? 'vector-only' : filteredName(c.filters)} search failed, so the two can’t be compared yet.`,
    }
  }
  if (vector.status !== 'done' || hybrid.status !== 'done' || !d) {
    return { main: 'Running both searches for the same question: one without filters, one with them…' }
  }

  const v = vector.chunks.length
  const h = hybrid.chunks.length
  const single = 'Each ran as a single MariaDB query.'
  if (v === 0 && h === 0) return { main: 'Neither search returned any rows for this question.' }
  if (h === 0) {
    return {
      main: `The filters left no rows: none of the ${plural(v, 'vector-only chunk')}, and no other row, passed them.`,
      extra: single,
    }
  }
  if (d.removed === 0 && d.added === 0) {
    return { main: `The filters didn’t change the result: the same ${plural(v, 'chunk')} in both.`, extra: single }
  }

  const brought = d.added === 0 ? 'brought in no new ones' : `brought in ${d.added} new ${d.added === 1 ? 'one' : 'ones'}`
  const main = `Filters removed ${d.removed} of ${plural(v, 'chunk')} and ${brought}.`
  const extra =
    d.postFiltered < h
      ? `${single} Filtering the vector-only results afterwards would have left only ${d.postFiltered}.`
      : single
  return { main, extra }
}

interface ColumnInfo {
  key: SideKey
  name: string // in running text: vector-only, hybrid or linked
  title: string
  other: string
  icon: ReactNode
  iconTone: string
}

function columns(filters: SearchFilters): Record<SideKey, ColumnInfo> {
  const linked = searchKind(filters) === 'linked'
  return {
    vector: {
      key: 'vector',
      name: 'vector-only',
      title: 'Vector-only',
      other: filteredName(filters),
      icon: <VectorSearchIcon size={17} />,
      iconTone: 'tone-sky',
    },
    hybrid: {
      key: 'hybrid',
      name: filteredName(filters),
      title: linked ? 'Linked (vector + article links)' : 'Hybrid (vector + SQL filters)',
      other: 'vector-only',
      icon: <SlidersIcon size={17} />,
      iconTone: 'details-dot',
    },
  }
}

interface Props {
  comparison: Comparison
  onBack: () => void
  onRetry: (side: SideKey) => void
}

export function CompareView({ comparison, onBack, onRetry }: Props) {
  const { vector, hybrid, filters } = comparison
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [linked, setLinked] = useState<number | null>(null)
  const uid = useId()

  useEffect(() => headingRef.current?.focus(), [])

  const d = vector.status === 'done' && hybrid.status === 'done' ? diff(vector.chunks, hybrid.chunks, filters) : null
  const tones = articleTones([
    ...(vector.status === 'done' ? vector.chunks : []),
    ...(hybrid.status === 'done' ? hybrid.chunks : []),
  ])
  const summary = summaryText(comparison, d)
  const labels = filterLabels(filters)
  const cols = columns(filters)
  const linkedFrom = filters.source_title

  return (
    <div className="compare">
      <section className="card cmp-summary" aria-labelledby={`${uid}-title`}>
        <button type="button" className="btn-soft cmp-back" onClick={onBack}>
          <ArrowLeftIcon size={16} /> Back to answer
        </button>
        <div className="cmp-summary-body">
          <h2 id={`${uid}-title`} ref={headingRef} tabIndex={-1} className="section-title">
            <span className="icon-dot tone-butter">
              <CompareIcon size={17} />
            </span>
            Vector-only vs {filteredName(filters)}
          </h2>
          <p className="cmp-summary-text" aria-live="polite">
            <b>{summary.main}</b>
            {summary.extra && <> {summary.extra}</>}
          </p>
        </div>
      </section>

      <CompareColumn
        info={cols.vector}
        caption="The same question with no SQL filters: the nearest chunks across all articles."
        side={vector}
        marks={d?.vector}
        tones={tones}
        linked={linked}
        onLink={setLinked}
        onRetry={() => onRetry('vector')}
        uid={uid}
        filterCount={0}
      />
      <CompareColumn
        info={cols.hybrid}
        caption={
          linkedFrom
            ? `One query that joins article_links: only chunks of articles linked from ${linkedFrom} are ranked.`
            : 'Vector search and SQL filters in one query: only rows that pass the filters are ranked.'
        }
        pills={labels}
        side={hybrid}
        marks={d?.hybrid}
        tones={tones}
        linked={linked}
        onLink={setLinked}
        onRetry={() => onRetry('hybrid')}
        uid={uid}
        filterCount={labels.length}
      />
    </div>
  )
}

interface ColumnProps {
  info: ColumnInfo
  caption: string
  pills?: string[]
  side: CompareSide
  marks: Mark[] | undefined
  tones: Map<number, Tone>
  linked: number | null
  onLink: (id: number | null) => void
  onRetry: () => void
  uid: string
  filterCount: number
}

function CompareColumn({ info, caption, pills, side, marks, tones, linked, onLink, onRetry, uid, filterCount }: ColumnProps) {
  const titleId = `${uid}-${info.key}`
  const otherKey: SideKey = info.key === 'vector' ? 'hybrid' : 'vector'
  const { name } = info
  const sideBySide = useMediaQuery('(min-width: 1100px)')
  const done = side.status === 'done' ? side : null

  function link(c: Chunk, mark: Mark, focused: boolean) {
    onLink(c.chunk_id)
    if (!focused || !sideBySide || mark.kind !== 'both') return
    document.getElementById(`${uid}-${otherKey}-${c.chunk_id}`)?.scrollIntoView({ block: 'nearest' })
  }

  return (
    <section className={`compare-col cmp-${info.key}`} aria-labelledby={titleId}>
      <header className="card cmp-head">
        <h2 id={titleId} className="section-title">
          <span className={`icon-dot ${info.iconTone}`}>{info.icon}</span>
          {info.title}
        </h2>
        <p className="cmp-caption">{caption}</p>
        {pills && pills.length > 0 && (
          <ul className="cmp-pills" aria-label="Filters applied">
            {pills.map((p) => (
              <li key={p} className="mono details-filters">
                {p}
              </li>
            ))}
          </ul>
        )}
        <dl className="cmp-stats">
          <div>
            <dt>Chunks</dt>
            <dd className="mono">{done ? done.chunks.length : '–'}</dd>
          </div>
          <div>
            <dt>Search latency</dt>
            <dd className="mono">{done ? ms(done.details.search_latency_ms) : '–'}</dd>
          </div>
          <div className={done?.details.vector_index_used === false ? 'is-warn' : undefined}>
            <dt>Vector index</dt>
            <dd className="mono">
              {!done || done.details.vector_index_used === null ? (
                '–'
              ) : (
                <>
                  {done.details.vector_index_used ? <CheckIcon size={14} /> : <WarningIcon size={14} />}
                  {done.details.vector_index_used ? 'Used' : 'Not used'}
                </>
              )}
            </dd>
          </div>
        </dl>
      </header>

      {side.status === 'loading' && (
        <LoadingCard
          title={`Running the ${name} search…`}
          sub={
            info.key === 'vector'
              ? 'Ranking all chunks by cosine distance, no SQL filters'
              : `Ranking chunks by cosine distance, with ${plural(filterCount, 'SQL filter')} in the same query`
          }
        />
      )}

      {side.status === 'error' && (
        <StatusMessage
          kind="error"
          icon={<DatabaseIcon size={24} />}
          title={`${name[0].toUpperCase()}${name.slice(1)} search failed`}
          detail={side.detail}
          action={{ label: 'Try again', onClick: onRetry }}
        >
          {side.message}
        </StatusMessage>
      )}

      {done && done.chunks.length === 0 && (
        <StatusMessage
          kind="empty"
          icon={<SearchIcon size={28} />}
          title={info.key === 'hybrid' ? 'The filters left no rows' : 'No chunks'}
        >
          {info.key === 'hybrid'
            ? `MariaDB ran the ${name} query, but no chunk passed the ${plural(filterCount, 'filter')}. The vector-only results show what the search finds without them.`
            : 'MariaDB returned no chunks for this question, even without filters.'}
        </StatusMessage>
      )}

      {done && done.chunks.length > 0 && (
        <ol className="cmp-chunks">
          {done.chunks.map((c, i) => {
            const mark = marks?.[i] ?? { kind: 'none' }
            const similarity = 1 - c.distance
            const pct = Math.max(0, Math.min(1, similarity)) * 100
            const cls = ['cmp-chunk', `is-${mark.kind}`, mark.kind === 'both' && linked === c.chunk_id && 'is-linked']
              .filter(Boolean)
              .join(' ')
            return (
              <li
                key={c.chunk_id}
                id={`${uid}-${info.key}-${c.chunk_id}`}
                className={cls}
                tabIndex={0}
                onMouseEnter={() => link(c, mark, false)}
                onMouseLeave={() => onLink(null)}
                onFocus={() => link(c, mark, true)}
                onBlur={() => onLink(null)}
              >
                <div className="cmp-chunk-head">
                  <span className={`mono chunk-num tone-${tones.get(c.article_id) ?? 'lav'}`}>{i + 1}</span>
                  <span className="cmp-chunk-article">{c.article_title}</span>
                  <span className="mono pill">chunk {c.chunk_index}</span>
                  <MarkBadge mark={mark} other={info.other} />
                </div>
                <div className="chunk-scores mono">
                  <span>
                    distance <b>{c.distance.toFixed(3)}</b>
                  </span>
                  <span>
                    similarity <b>{similarity.toFixed(3)}</b>
                  </span>
                  <span className="sim-bar" aria-hidden="true">
                    <span style={{ width: `${pct}%` }} />
                  </span>
                </div>
                <p className="cmp-chunk-text">{c.text}</p>
                {mark.kind === 'out' && <p className="cmp-note">{mark.reason}</p>}
                {mark.kind === 'dropped' && (
                  <p className="cmp-note">Its article passed the filters, but this chunk ranked below the cut-off.</p>
                )}
                {mark.kind === 'new' && <p className="cmp-note">Moved up: closer rows were filtered out.</p>}
              </li>
            )
          })}
        </ol>
      )}

      {done && <CollapsibleSql sql={done.details.sql} markFilters={filterCount > 0} />}
    </section>
  )
}

function MarkBadge({ mark, other }: { mark: Mark; other: string }) {
  switch (mark.kind) {
    case 'both':
      return (
        <span className="mono cmp-badge is-both">
          #{mark.twinRank} in {other}
        </span>
      )
    case 'out':
      return <span className="mono cmp-badge is-out">Filtered out</span>
    case 'dropped':
      return <span className="mono cmp-badge is-out">Not in {other}</span>
    case 'new':
      return <span className="mono cmp-badge is-new">New</span>
    case 'none':
      return null
  }
}

function CollapsibleSql({ sql, markFilters }: { sql: string; markFilters: boolean }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <div className="card cmp-sql">
      <button
        type="button"
        className="details-toggle cmp-sql-toggle"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? 'Hide' : 'Show'} executed SQL
        <ChevronDownIcon size={15} />
      </button>
      <div id={id} hidden={!open}>
        <SqlBlock sql={sql} markFilters={markFilters} />
      </div>
    </div>
  )
}

export function CompareCallout({
  filterCount,
  onCompare,
}: {
  filterCount: number
  onCompare: MouseEventHandler<HTMLButtonElement>
}) {
  return (
    <section className="card cmp-callout" aria-label="Compare with vector-only search">
      <span className="icon-dot tone-butter">
        <CompareIcon size={17} />
      </span>
      <p className="cmp-callout-text">
        <b>
          Your {plural(filterCount, 'filter')} ran in the same query as the vector search.
        </b>{' '}
        See which chunks {filterCount === 1 ? 'it' : 'they'} removed and which moved up.
      </p>
      <button type="button" className="btn-soft cmp-callout-btn" onClick={onCompare}>
        Compare with vector-only
        <ArrowRightIcon size={16} />
      </button>
    </section>
  )
}
