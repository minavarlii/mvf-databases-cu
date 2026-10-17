import { useEffect, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { flushSync } from 'react-dom'
import { api, userMessage } from '../api'
import type { ApiErrorCode, SearchFilters } from '../api'
import { AnswerCard } from '../components/AnswerCard'
import { AskForm } from '../components/AskForm'
import { ChunkList } from '../components/ChunkList'
import { CompareCallout, CompareView } from '../components/CompareView'
import type { Comparison, SideKey } from '../components/CompareView'
import { DetailsPanel } from '../components/DetailsPanel'
import { checkFilters, filterCount, NO_FILTERS, sameFilters } from '../components/filters'
import type { FilterDraft } from '../components/filters'
import { FiltersBar } from '../components/FiltersBar'
import { useMediaQuery } from '../components/useMediaQuery'
import { FlowSteps } from '../components/FlowSteps'
import { CompareIcon, DatabaseIcon, SearchIcon, SlidersIcon, ServerIcon, SparkleIcon, VectorSearchIcon } from '../components/icons'
import { LoadingCard } from '../components/LoadingCard'
import { Placeholder } from '../components/Placeholder'
import { SourcesList } from '../components/SourcesList'
import { StatusMessage } from '../components/StatusMessage'
import { errorDetail, flowFor, runQuestion } from './askFlow'
import type { View } from './askFlow'

// Checked against the real corpus, which has no Gradient descent, CNN or Reinforcement learning articles.
const EXAMPLES = [
  'What is overfitting?',
  'What does the learning rate control in gradient descent?',
  'How do agents balance exploration and exploitation?',
]

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`
const seconds = (millis: number) => `${(millis / 1000).toFixed(2)} s`
const hasChunks = (v: View) => v.status === 'success' || v.status === 'retrieved' || v.status === 'llm-failed'

const SCOPES = { success: 'answer', retrieved: 'search', 'llm-failed': 'search', empty: 'empty' } as const

function scrollParent(el: HTMLElement): HTMLElement | null {
  for (let p = el.parentElement; p; p = p.parentElement) {
    const { overflowY } = getComputedStyle(p)
    if ((overflowY === 'auto' || overflowY === 'scroll') && p.scrollHeight > p.clientHeight) return p
  }
  return null
}

const CHUNKS_PLACEHOLDER: Record<'idle' | 'loading' | 'error' | 'empty', { title: string; text: string }> = {
  idle: { title: 'Retrieved chunks appear here', text: 'The closest passages MariaDB finds, with cosine distance and similarity.' },
  loading: { title: 'Waiting for MariaDB…', text: 'Ranking chunks by cosine distance to your question.' },
  error: { title: 'No chunks retrieved', text: 'The request failed before MariaDB returned any passages.' },
  empty: { title: 'No chunks', text: 'MariaDB returned 0 chunks for this question.' },
}

const ERROR_TITLES: Partial<Record<ApiErrorCode, string>> = {
  BACKEND_UNAVAILABLE: 'Backend unavailable',
  DATABASE_UNAVAILABLE: 'Database unavailable',
}

export default function AskPage({ hidden = false }: { hidden?: boolean }) {
  const [question, setQuestion] = useState('')
  const [view, setView] = useState<View>({ status: 'idle' })
  const [highlighted, setHighlighted] = useState<number | null>(null)
  const [expandedChunks, setExpandedChunks] = useState<ReadonlySet<number>>(() => new Set())
  const [filterDraft, setFilterDraft] = useState<FilterDraft>(NO_FILTERS)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [sentFilters, setSentFilters] = useState<SearchFilters>({})
  const latestRequest = useRef(0)
  const lastRequest = useRef<{ question: string; filters: SearchFilters }>({ question: '', filters: {} })
  const mainRef = useRef<HTMLDivElement>(null)
  const centerRef = useRef<HTMLDivElement>(null)
  const rightRef = useRef<HTMLDivElement>(null)
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [comparing, setComparing] = useState(false)
  const compareRuns = useRef<Record<SideKey, number>>({ vector: 0, hybrid: 0 })
  const compareOpener = useRef<HTMLElement | null>(null)
  const returnFocus = useRef(false)

  useEffect(() => {
    const counter = latestRequest
    return () => {
      counter.current++ // ignore responses that arrive after unmount
    }
  }, [])

  useEffect(() => {
    if (view.status === 'idle' || view.status === 'loading') return
    for (const ref of [mainRef, centerRef, rightRef]) ref.current?.scrollTo({ top: 0 })
  }, [view])

  useEffect(() => {
    if (comparing || !returnFocus.current) return
    returnFocus.current = false
    if (compareOpener.current?.isConnected) compareOpener.current.focus()
  }, [comparing])

  const loading = view.status === 'loading'

  async function ask(q: string, filters: SearchFilters) {
    if (loading) return
    const id = ++latestRequest.current
    lastRequest.current = { question: q, filters }
    setHighlighted(null)
    setExpandedChunks(new Set())
    setSentFilters(filters)
    setView({ status: 'loading' })
    setComparison(null)
    setComparing(false)
    returnFocus.current = false

    const next = await runQuestion(api, q, filters)
    if (id === latestRequest.current) setView(next)
  }

  const checked = checkFilters(filterDraft)

  // Keep 860px / 760px in sync with the height media queries in index.css.
  const shortWindow = useMediaQuery('(max-height: 860px)')
  const veryShortWindow = useMediaQuery('(max-height: 760px)')
  const filtersSet = Object.values(filterDraft).some((v) => v.trim())
  const compactFlow = filtersOpen || (filtersSet && shortWindow) || veryShortWindow
  const filtersInvalid = Object.keys(checked.errors).length > 0

  const retry = () => void ask(lastRequest.current.question, lastRequest.current.filters)

  function applySearch() {
    const q = question.trim()
    if (!q || loading) return
    if (filtersInvalid) setFiltersOpen(true)
    else void ask(q, checked.filters)
  }

  function clearFiltersAndRerun() {
    setFilterDraft(NO_FILTERS)
    void ask(lastRequest.current.question, {})
  }

  async function runCompareSide(side: SideKey) {
    const { question: q, filters } = lastRequest.current
    const request = latestRequest.current
    const run = ++compareRuns.current[side]
    const isStale = () => request !== latestRequest.current || run !== compareRuns.current[side]
    setComparison((c) => c && { ...c, [side]: { status: 'loading' } })
    try {
      const res = await api.search(side === 'hybrid' ? { question: q, filters } : { question: q })
      if (isStale()) return
      setComparison((c) => c && { ...c, [side]: { status: 'done', chunks: res.chunks, details: res.details } })
    } catch (err) {
      if (isStale()) return
      setComparison(
        (c) => c && { ...c, [side]: { status: 'error', message: userMessage(err), detail: errorDetail(err) } },
      )
    }
  }

  function openComparison(e: MouseEvent<HTMLElement>) {
    compareOpener.current = e.currentTarget
    setComparing(true)
    if (comparison) {
      for (const side of ['vector', 'hybrid'] as const) {
        if (comparison[side].status === 'error') void runCompareSide(side)
      }
      return
    }
    setComparison({ filters: lastRequest.current.filters, vector: { status: 'loading' }, hybrid: { status: 'loading' } })
    void runCompareSide('vector')
    void runCompareSide('hybrid')
  }

  function closeComparison() {
    returnFocus.current = true
    setComparing(false)
  }

  function toggleChunk(chunkId: number) {
    setExpandedChunks((prev) => {
      const next = new Set(prev)
      if (!next.delete(chunkId)) next.add(chunkId)
      return next
    })
  }

  function showChunk(n: number) {
    // flushSync so the scroll below measures the expanded chunk.
    const cited = hasChunks(view) ? view.chunks[n - 1] : undefined
    flushSync(() => {
      setHighlighted(n)
      if (cited) setExpandedChunks((prev) => (prev.has(cited.chunk_id) ? prev : new Set(prev).add(cited.chunk_id)))
    })
    const el = document.getElementById(`chunk-${n}`)
    if (!el) return
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
    const container = scrollParent(el)
    if (container) {
      const offset = el.getBoundingClientRect().top - container.getBoundingClientRect().top
      container.scrollTo({ top: container.scrollTop + offset - 12, behavior })
    } else {
      window.scrollTo({ top: window.scrollY + el.getBoundingClientRect().top - 16, behavior })
    }
    el.focus({ preventScroll: true })
  }

  const chunks = hasChunks(view) ? view.chunks : null
  const chunksPlaceholder = hasChunks(view) ? null : CHUNKS_PLACEHOLDER[view.status]
  const filteredSearch = filterCount(sentFilters) > 0 && view.status !== 'idle'
  const canCompare = filteredSearch && (hasChunks(view) || view.status === 'empty')
  const showComparison = comparing && comparison !== null
  const filtersChanged =
    view.status !== 'idle' && view.status !== 'loading' && (filtersInvalid || !sameFilters(checked.filters, sentFilters))

  return (
    <main className="workspace" hidden={hidden}>
      <div className={['col col-left', compactFlow && 'flow-compact', filtersOpen && 'filters-open'].filter(Boolean).join(' ')}>
        <AskForm
          value={question}
          loading={loading}
          examples={EXAMPLES}
          onChange={setQuestion}
          onSubmit={(q) => void ask(q, checked.filters)}
          blockedReason={filtersInvalid ? 'Fix the filter values first' : null}
          onBlocked={() => setFiltersOpen(true)}
        />

        <FiltersBar
          draft={filterDraft}
          onChange={setFilterDraft}
          open={filtersOpen}
          onOpenChange={setFiltersOpen}
          apply={{
            label: view.status === 'idle' ? 'Search with filters' : 'Apply filters',
            onApply: applySearch,
            questionEmpty: !question.trim(),
            loading,
          }}
        />

        <FlowSteps states={flowFor(view, filteredSearch)} />
      </div>

      <div className="main" ref={mainRef}>
        {/* Answer columns stay mounted under the comparison, so going back keeps their state. */}
        {comparing && comparison && (
          <CompareView comparison={comparison} onBack={closeComparison} onRetry={(side) => void runCompareSide(side)} />
        )}

        <div className="col col-center" ref={centerRef} hidden={showComparison}>
          {filtersChanged && (
            <p className="filters-stale" role="status">
              <SlidersIcon size={15} />
              <span>
                Filters changed.{' '}
                {question.trim() ? (
                  <>
                    <button type="button" className="filters-stale-link" onClick={applySearch}>
                      Apply
                    </button>{' '}
                    to update results.
                  </>
                ) : (
                  'Type a question to apply them.'
                )}
              </span>
            </p>
          )}

          {filteredSearch && view.status !== 'error' && (
            <p className="block-caption">
              Filtered search shows retrieved chunks only. Clear the filter to get an AI answer.
            </p>
          )}

          {view.status === 'idle' && (
            <Placeholder icon={<SparkleIcon size={26} />} title="Ask something to get started" className="hide-phone">
              Type a question or pick an example. The answer, its Wikipedia sources and the passages MariaDB retrieved
              will show up here.
            </Placeholder>
          )}

          {view.status === 'loading' && <LoadingCard />}

          {view.status === 'error' && (
            <StatusMessage
              kind="error"
              icon={view.code === 'DATABASE_UNAVAILABLE' ? <DatabaseIcon size={24} /> : <ServerIcon size={24} />}
              title={(view.code && ERROR_TITLES[view.code]) ?? 'Request failed'}
              detail={view.detail}
              action={{ label: 'Try again', onClick: retry }}
            >
              {view.message}
            </StatusMessage>
          )}

          {view.status === 'empty' &&
            (filterCount(sentFilters) > 0 ? (
              <StatusMessage
                kind="empty"
                icon={<SearchIcon size={28} />}
                title="No passages match your filters"
                action={{ label: 'Clear filters', onClick: clearFiltersAndRerun }}
              >
                MariaDB ran the search, but no chunks passed the {plural(filterCount(sentFilters), 'filter')}. They may be
                too narrow. Clear them to search all articles again.
              </StatusMessage>
            ) : (
              <StatusMessage kind="empty" icon={<SearchIcon size={28} />} title="No matching passages">
                MariaDB returned no chunks for this question. Try rephrasing it.
              </StatusMessage>
            ))}

          {view.status === 'llm-failed' && (
            <>
              <StatusMessage
                kind="warning"
                icon={<SparkleIcon size={22} />}
                title="The answer couldn’t be generated"
                detail={view.detail}
                action={{ label: 'Retry answer', onClick: retry }}
              >
                {view.message} The passages MariaDB found are listed with the chunks.
              </StatusMessage>
              <SourcesList sources={view.sources} chunks={view.chunks} />
            </>
          )}

          {view.status === 'retrieved' && <SourcesList sources={view.sources} chunks={view.chunks} />}

          {view.status === 'success' && (
            <>
              <AnswerCard
                answer={view.answer}
                chunkCount={view.chunks.length}
                meta={`from ${plural(view.chunks.length, 'retrieved passage')} · ${seconds(view.details.total_response_ms)}`}
                onCite={showChunk}
              />
              <SourcesList sources={view.sources} chunks={view.chunks} />
            </>
          )}

          {canCompare && (
            <CompareCallout filterCount={filterCount(sentFilters)} onCompare={openComparison} />
          )}

          {(hasChunks(view) || view.status === 'empty') && (
            <DetailsPanel details={view.details} scope={SCOPES[view.status]} filters={sentFilters} />
          )}
        </div>

        <div className="col col-right" ref={rightRef} hidden={showComparison}>
          {chunks && (
            <ChunkList
              chunks={chunks}
              highlighted={highlighted}
              expanded={expandedChunks}
              onToggle={toggleChunk}
              action={
                canCompare && (
                  <button type="button" className="btn-soft cmp-chunks-btn desktop-only" onClick={openComparison}>
                    <CompareIcon size={15} /> Compare with vector-only
                  </button>
                )
              }
            />
          )}
          {chunksPlaceholder && (
            <Placeholder icon={<VectorSearchIcon size={26} />} title={chunksPlaceholder.title} className="desktop-only">
              {chunksPlaceholder.text}
            </Placeholder>
          )}
        </div>
      </div>
    </main>
  )
}
