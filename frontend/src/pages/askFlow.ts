import { ApiError, userMessage } from '../api'
import type { ApiClient, ApiErrorCode, Chunk, MariaDbDetails, SearchFilters, SourceArticle } from '../api'
import { filterCount } from '../components/filters'
import type { FlowStates, StepStatus } from '../components/FlowSteps'

export type View =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; answer: string; sources: SourceArticle[]; chunks: Chunk[]; details: MariaDbDetails }
  // A filtered search: /api/rag takes no filters, so there is no answer, only what MariaDB retrieved.
  | { status: 'retrieved'; sources: SourceArticle[]; chunks: Chunk[]; details: MariaDbDetails }
  | { status: 'empty'; details: MariaDbDetails }
  | { status: 'error'; code: ApiErrorCode | null; message: string; detail: string | null }
  | {
      status: 'llm-failed'
      message: string
      detail: string | null
      sources: SourceArticle[]
      chunks: Chunk[]
      details: MariaDbDetails
    }

export function uniqueSources(chunks: Chunk[]): SourceArticle[] {
  const seen = new Map<number, SourceArticle>()
  for (const c of chunks) {
    if (!seen.has(c.article_id)) {
      seen.set(c.article_id, { article_id: c.article_id, title: c.article_title, url: c.article_url })
    }
  }
  return [...seen.values()]
}

export function errorDetail(err: unknown): string | null {
  if (err instanceof ApiError) return `${err.code} · ${err.message}`
  return err instanceof Error ? err.message : null
}

const failed = (err: unknown): View => ({
  status: 'error',
  code: err instanceof ApiError ? err.code : null,
  message: userMessage(err),
  detail: errorDetail(err),
})

// Filtered questions only run the filtered search; unfiltered ones ask /api/rag and, if the LLM fails, fall back
// to the plain search so the retrieved passages still show.
export async function runQuestion(api: ApiClient, question: string, filters: SearchFilters): Promise<View> {
  if (filterCount(filters) > 0) {
    try {
      const res = await api.search({ question, filters })
      if (res.chunks.length === 0) return { status: 'empty', details: res.details }
      return { status: 'retrieved', sources: uniqueSources(res.chunks), chunks: res.chunks, details: res.details }
    } catch (err) {
      return failed(err)
    }
  }

  try {
    const res = await api.ask({ question })
    if (res.chunks.length === 0) return { status: 'empty', details: res.details }
    return { status: 'success', answer: res.answer, sources: res.sources, chunks: res.chunks, details: res.details }
  } catch (err) {
    if (!(err instanceof ApiError && err.code === 'LLM_FAILED')) return failed(err)
    try {
      const res = await api.search({ question })
      if (res.chunks.length === 0) return { status: 'empty', details: res.details }
      return {
        status: 'llm-failed',
        message: userMessage(err),
        detail: errorDetail(err),
        sources: uniqueSources(res.chunks),
        chunks: res.chunks,
        details: res.details,
      }
    } catch (searchErr) {
      return failed(searchErr)
    }
  }
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`
const ms = (d: MariaDbDetails) => `${d.search_latency_ms.toFixed(1)} ms`
const step = (state: StepStatus['state'], note: string): StepStatus => ({ state, note })
const detailsStep = (d: MariaDbDetails): StepStatus =>
  d.vector_index_used === null
    ? step('done', 'Shown')
    : d.vector_index_used
      ? step('done', 'Index used')
      : { state: 'done', note: 'Index not used', warn: true }
const retrieved = (chunks: Chunk[]) =>
  `${plural(chunks.length, 'chunk')} · ${plural(uniqueSources(chunks).length, 'article')}`

// Without the llm step the flow ends at retrieval, which is what a filtered search does.
export function flowFor(view: View, filtered: boolean): FlowStates {
  const states = fullFlow(view)
  if (!filtered) return states
  const { question, search, sources, details } = states
  return { question, search, sources, details }
}

function fullFlow(view: View): FlowStates {
  const sent = step('done', 'Sent')
  const notRun = step('pending', 'Not run')
  switch (view.status) {
    case 'idle': {
      const waiting = step('pending', 'Waiting')
      return { question: step('pending', 'Ready'), search: waiting, sources: waiting, llm: waiting, details: waiting }
    }
    case 'loading': {
      const waiting = step('pending', 'Waiting')
      return { question: sent, search: step('active', 'Searching…'), sources: waiting, llm: waiting, details: waiting }
    }
    case 'success':
      return {
        question: sent,
        search: step('done', ms(view.details)),
        sources: step('done', retrieved(view.chunks)),
        llm: step('done', 'Answered'),
        details: detailsStep(view.details),
      }
    case 'retrieved':
      return {
        question: sent,
        search: step('done', ms(view.details)),
        sources: step('done', retrieved(view.chunks)),
        details: detailsStep(view.details),
      }
    case 'empty':
      return {
        question: sent,
        search: step('done', ms(view.details)),
        sources: step('done', '0 chunks'),
        llm: step('pending', 'Skipped'),
        details:
          view.details.vector_index_used === false
            ? { state: 'done', note: '0 rows · no index', warn: true }
            : step('done', '0 rows'),
      }
    case 'llm-failed':
      return {
        question: sent,
        search: step('done', ms(view.details)),
        sources: step('done', retrieved(view.chunks)),
        llm: step('failed', 'Failed'),
        details: detailsStep(view.details),
      }
    case 'error':
      if (view.code === 'BACKEND_UNAVAILABLE') {
        return { question: step('failed', 'API unreachable'), search: notRun, sources: notRun, llm: notRun, details: notRun }
      }
      return {
        question: sent,
        search: step('failed', view.code === 'DATABASE_UNAVAILABLE' ? 'No connection' : 'Failed'),
        sources: notRun,
        llm: notRun,
        details: notRun,
      }
  }
}
