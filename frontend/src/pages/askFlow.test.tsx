import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/errors'
import { mockApi } from '../api/mock'
import type { ApiClient, AskResponse, Chunk, MariaDbDetails, SearchResponse } from '../api/types'
import { FlowSteps } from '../components/FlowSteps'
import { flowFor, runQuestion } from './askFlow'
import type { View } from './askFlow'

const details: MariaDbDetails = {
  sql: 'SELECT 1',
  query_plan: [],
  search_latency_ms: 2.3,
  total_response_ms: 30,
  chunk_count: 1,
  vector_index_used: true,
}

const chunk: Chunk = {
  chunk_id: 554,
  article_id: 36,
  article_title: 'Bias–variance tradeoff',
  article_url: 'https://en.wikipedia.org/wiki/Bias%E2%80%93variance_tradeoff',
  chunk_index: 1,
  text: 'variance',
  distance: 0.2,
}

function stubApi(overrides: Partial<Pick<ApiClient, 'ask' | 'search'>> = {}) {
  const search = vi.fn(async (): Promise<SearchResponse> => ({ chunks: [chunk], details }))
  const ask = vi.fn(
    async (): Promise<AskResponse> => ({
      answer: 'An answer [1].',
      sources: [{ article_id: 36, title: chunk.article_title, url: chunk.article_url }],
      chunks: [chunk],
      details,
    }),
  )
  const api: ApiClient = {
    capabilities: { filters: { category: true, source_title: true } },
    ask,
    search,
    categories: vi.fn(),
    articles: vi.fn(),
    stats: vi.fn(),
    ...overrides,
  }
  return { api, ask, search }
}

const flowLabels = (filtered: boolean, view: View) =>
  renderToStaticMarkup(<FlowSteps states={flowFor(view, filtered)} />)

afterEach(() => {
  vi.useRealTimers()
})

describe('runQuestion with a filter', () => {
  it.each([{ category: 'Machine learning' }, { source_title: 'Overfitting' }])(
    'runs only the filtered search for %o, never /api/rag, and yields no answer',
    async (filters) => {
      const { api, ask, search } = stubApi()

      const view = await runQuestion(api, 'What is variance?', filters)

      expect(ask).not.toHaveBeenCalled()
      expect(search).toHaveBeenCalledExactlyOnceWith({ question: 'What is variance?', filters })
      // AskPage renders AnswerCard only for 'success'; a filtered search can't produce it.
      expect(view.status).toBe('retrieved')
      expect(view).not.toHaveProperty('answer')
      expect(view).toMatchObject({ chunks: [chunk], sources: [{ title: 'Bias–variance tradeoff' }] })
    },
  )

  it('reports an empty filtered result as empty and a failure as a search error', async () => {
    const empty = stubApi({ search: vi.fn(async () => ({ chunks: [], details })) })
    expect((await runQuestion(empty.api, 'q', { category: 'Deep learning' })).status).toBe('empty')

    const down = stubApi({
      search: vi.fn(async () => {
        throw new ApiError('DATABASE_UNAVAILABLE', 'down')
      }),
    })
    const view = await runQuestion(down.api, 'q', { source_title: 'Overfitting' })
    expect(view).toMatchObject({ status: 'error', code: 'DATABASE_UNAVAILABLE' })
    expect(down.ask).not.toHaveBeenCalled()
  })

  it('behaves the same with the mock API', async () => {
    vi.useFakeTimers()
    const ask = vi.spyOn(mockApi, 'ask')
    try {
      const pending = runQuestion(mockApi, 'What is overfitting?', { source_title: 'Overfitting' })
      await vi.runAllTimersAsync()
      const view = await pending
      expect(ask).not.toHaveBeenCalled()
      expect(view.status).toBe('retrieved')
    } finally {
      ask.mockRestore()
    }
  })
})

describe('runQuestion without a filter', () => {
  it('asks /api/rag and returns the answer', async () => {
    const { api, ask, search } = stubApi()
    const view = await runQuestion(api, 'q', {})
    expect(ask).toHaveBeenCalledExactlyOnceWith({ question: 'q' })
    expect(search).not.toHaveBeenCalled()
    expect(view).toMatchObject({ status: 'success', answer: 'An answer [1].' })
  })

  it('falls back to the plain search when the LLM fails', async () => {
    const { api, search } = stubApi({
      ask: vi.fn(async () => {
        throw new ApiError('LLM_FAILED', 'no LLM')
      }),
    })
    const view = await runQuestion(api, 'q', {})
    expect(search).toHaveBeenCalledExactlyOnceWith({ question: 'q' })
    expect(view.status).toBe('llm-failed')
  })
})

describe('flow steps', () => {
  const views: View[] = [
    { status: 'loading' },
    { status: 'retrieved', sources: [], chunks: [chunk], details },
    { status: 'empty', details },
  ]

  it('end at retrieval for a filtered search', () => {
    for (const view of views) {
      const html = flowLabels(true, view)
      expect(html).not.toContain('LLM answer')
      expect(html).toContain('MariaDB details')
    }
  })

  it('keep the LLM step for unfiltered questions', () => {
    expect(flowLabels(false, { status: 'idle' })).toContain('LLM answer')
    expect(flowLabels(false, { status: 'loading' })).toContain('LLM answer')
  })
})
