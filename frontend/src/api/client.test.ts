import { afterEach, describe, expect, it, vi } from 'vitest'

import { realApi } from './client'

import { ApiError } from './errors'

import type { ApiErrorCode } from './types'

type Handler = (body: unknown) => Response | Promise<Response>

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })

// Routes requests by "METHOD /path" (query string included); anything unrouted fails the test.

function route(routes: Record<string, Handler>) {

  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {

    const key = `${init?.method ?? 'GET'} ${new URL(url).pathname}${new URL(url).search}`

    const handler = routes[key]

    if (!handler) throw new Error(`unexpected request: ${key}`)

    return handler(init?.body ? JSON.parse(String(init.body)) : undefined)

  })

  vi.stubGlobal('fetch', fetchMock)

  return fetchMock

}

const planRow = (table: string, key: string | null) => ({

  select_id: 2,

  select_type: 'DERIVED',

  table,

  access_type: key ? 'index' : 'ALL',

  possible_keys: null,

  key,

  rows: 3185,

  extra: '',

})

const debug = (plan: ReturnType<typeof planRow>[]) => ({

  sql: '\nSELECT ...\n',

  parameters: { limit: 5 },

  embedding_ms: 25.1,

  search_ms: 2.3,

  explain_ms: 1,

  total_ms: 28.4,

  execution_plan: plan,

})

const result = (chunk_id: number, article_id: number, article_title: string, chunk_index: number) => ({

  chunk_id,

  article_id,

  article_title,

  chunk_index,

  content: `chunk ${chunk_id}`,

  token_count: 220,

  distance: chunk_id / 10_000,

})

afterEach(() => {

  vi.unstubAllGlobals()

  vi.unstubAllEnvs()

})

describe('realApi.search', () => {

  it('maps a semantic search response and reads index use from the EXPLAIN plan', async () => {

    const fetchMock = route({

      'POST /api/search': () =>

        json({

          query: 'q',

          results: [result(554, 36, 'Bias–variance tradeoff', 1)],

          debug: debug([planRow('<derived2>', null), planRow('chunks', 'ix_chunks_embedding')]),

        }),

    })

    const res = await realApi.search({ question: 'What is variance?' })

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ query: 'What is variance?', limit: 5 })

    expect(res.chunks).toEqual([

      {

        chunk_id: 554,

        article_id: 36,

        article_title: 'Bias–variance tradeoff',

        article_url: 'https://en.wikipedia.org/wiki/Bias%E2%80%93variance_tradeoff',

        chunk_index: 1,

        text: 'chunk 554',

        distance: 0.0554,

      },

    ])

    expect(res.details).toMatchObject({ sql: '\nSELECT ...\n', search_latency_ms: 2.3, chunk_count: 1, vector_index_used: true })

    expect(res.details.query_plan.map((r) => [r.table, r.key])).toEqual([

      ['<derived2>', null],

      ['chunks', 'ix_chunks_embedding'],

    ])

  })

  it('sends a category filter to /api/search/hybrid and reports a plan without the vector index as not used', async () => {

    const fetchMock = route({

      'POST /api/search/hybrid': () =>

        json({ query: 'q', category: 'Machine learning', results: [], debug: debug([planRow('chunks', 'ix_chunks_article_id')]) }),

    })

    const res = await realApi.search({ question: 'q', top_k: 3, filters: { category: 'Machine learning' } })

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ query: 'q', category: 'Machine learning', limit: 3 })

    expect(res.details.vector_index_used).toBe(false)

  })

  it('reports index use as unknown when the backend sends no plan', async () => {

    route({ 'POST /api/search': () => json({ query: 'q', results: [], debug: debug([]) }) })

    expect((await realApi.search({ question: 'q' })).details.vector_index_used).toBeNull()

  })

  it('sends a linked-article filter to /api/search/linked and keeps the relational-first plan', async () => {

    const fetchMock = route({

      'POST /api/search/linked': () =>

        json({

          query: 'q',

          source_title: 'Overfitting',

          results: [result(554, 36, 'Bias–variance tradeoff', 1)],

          debug: debug([planRow('al', 'PRIMARY'), planRow('c', 'ix_chunks_article_id')]),

        }),

    })

    const res = await realApi.search({ question: 'q', filters: { source_title: 'Overfitting' } })

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ query: 'q', source_title: 'Overfitting', limit: 5 })

    expect(res.chunks.map((c) => c.article_title)).toEqual(['Bias–variance tradeoff'])

    expect(res.details.vector_index_used).toBe(false)

  })

  it('rejects category and linked article together instead of dropping one', async () => {

    const fetchMock = route({})

    await expect(

      realApi.search({ question: 'q', filters: { category: 'Machine learning', source_title: 'Overfitting' } }),

    ).rejects.toMatchObject({ code: 'BAD_REQUEST', message: expect.stringContaining('One filter at a time') })

    expect(fetchMock).not.toHaveBeenCalled()

  })

})

describe('realApi.ask', () => {

  it('maps a RAG response, normalising [Source N] citations to [N]', async () => {

    const fetchMock = route({

      'POST /api/rag': () =>

        json({

          answer: 'A [Source 1]. B [Source 1, Source 3]. C [Sources 2 and 3]. D [source 2].',

          sources: [

            { article_id: 206, article_title: 'Overfitting', chunk_index: 0, content: 'a', distance: 0.29 },

            { article_id: 206, article_title: 'Overfitting', chunk_index: 1, content: 'b', distance: 0.31 },

            { article_id: 1, article_title: 'Machine learning', chunk_index: 47, content: 'c', distance: 0.47 },

          ],

          debug: debug([planRow('chunks', 'ix_chunks_embedding')]),

        }),

    })

    const res = await realApi.ask({ question: 'What is overfitting?', top_k: 3 })

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ question: 'What is overfitting?', top_k: 3 })

    expect(res.answer).toBe('A [1]. B [1][3]. C [2][3]. D [2].')

    expect(res.sources).toEqual([

      { article_id: 206, title: 'Overfitting', url: 'https://en.wikipedia.org/wiki/Overfitting' },

      { article_id: 1, title: 'Machine learning', url: 'https://en.wikipedia.org/wiki/Machine_learning' },

    ])

// RAG sources have no chunk_id, so the adapter derives unique negative ones.

    const ids = res.chunks.map((c) => c.chunk_id)

    expect(new Set(ids).size).toBe(3)

    expect(ids.every((id) => id < 0)).toBe(true)

    expect(res.details.vector_index_used).toBe(true)

  })

})

describe('backend errors', () => {

  const cases: { name: string; call: 'ask' | 'search'; status: number; body: unknown; code: ApiErrorCode; message: string }[] = [

    {

      name: '/api/rag 503 (no LLM configured)',

      call: 'ask',

      status: 503,

      body: { detail: 'RAG generation is unavailable because no LLM provider is configured.' },

      code: 'LLM_FAILED',

      message: 'RAG generation is unavailable because no LLM provider is configured. (HTTP 503)',

    },

    { name: '/api/rag 502 (LLM call failed)', call: 'ask', status: 502, body: { detail: 'Bad gateway' }, code: 'LLM_FAILED', message: 'Bad gateway (HTTP 502)' },

    {

      name: '422 validation error names the field',

      call: 'search',

      status: 422,

      body: { detail: [{ loc: ['body', 'query'], msg: 'String should have at least 1 character' }] },

      code: 'BAD_REQUEST',

      message: 'query: String should have at least 1 character (HTTP 422)',

    },

    { name: '404', call: 'search', status: 404, body: { detail: 'Not Found' }, code: 'BAD_REQUEST', message: 'Not Found (HTTP 404)' },

    { name: '503 from search is not an LLM failure', call: 'search', status: 503, body: null, code: 'UNKNOWN', message: 'Request failed with status 503 (HTTP 503)' },

    {

      name: 'explicit error code in the body wins',

      call: 'search',

      status: 500,

      body: { error: { code: 'DATABASE_UNAVAILABLE', message: 'MariaDB is down' } },

      code: 'DATABASE_UNAVAILABLE',

      message: 'MariaDB is down (HTTP 500)',

    },

  ]

  it.each(cases)('$name → $code', async ({ call, status, body, code, message }) => {

    const path = call === 'ask' ? 'POST /api/rag' : 'POST /api/search'

    route({ [path]: () => (body === null ? new Response('oops', { status }) : json(body, status)) })

    const err = await realApi[call]({ question: 'q' }).catch((e: unknown) => e)

    expect(err).toBeInstanceOf(ApiError)

    expect(err).toMatchObject({ code, message })

  })

  it('a network error with /health down is BACKEND_UNAVAILABLE', async () => {

    route({

      'POST /api/search': () => Promise.reject(new TypeError('Failed to fetch')),

      'GET /health': () => Promise.reject(new TypeError('Failed to fetch')),

    })

    await expect(realApi.search({ question: 'q' })).rejects.toMatchObject({ code: 'BACKEND_UNAVAILABLE' })

  })

  it('a network error with /health up is an internal error (500 without CORS headers)', async () => {

    route({

      'POST /api/search': () => Promise.reject(new TypeError('Failed to fetch')),

      'GET /health': () => json({ status: 'ok' }),

    })

    await expect(realApi.search({ question: 'q' })).rejects.toMatchObject({

      code: 'UNKNOWN',

      message: expect.stringContaining('internal error'),

    })

  })

})

describe('realApi catalog', () => {

  it('loads live corpus and MariaDB metadata from /api/stats', async () => {
    const fetchMock = route({
      'GET /api/stats': () =>
        json({
          article_count: 285,
          chunk_count: 3940,
          embedding_model: 'sentence-transformers/all-MiniLM-L6-v2',
          vector_dimensions: 384,
          mariadb_version: '11.8.9-MariaDB-ubu2404',
        }),
    })

    await expect(realApi.stats()).resolves.toEqual({
      article_count: 285,
      chunk_count: 3940,
      embedding_model: 'sentence-transformers/all-MiniLM-L6-v2',
      vector_dimensions: 384,
      mariadb_version: '11.8.9-MariaDB-ubu2404',
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(new URL(fetchMock.mock.calls[0][0]).pathname).toBe('/api/stats')
  })

  it('loads every page of /api/articles (limit 100) and sorts the titles', async () => {

    const page = (offset: number, n: number) =>

      Array.from({ length: n }, (_, i) => ({ id: offset + i + 1, title: `Article ${String(offset + i + 1).padStart(3, '0')}` }))

    const fetchMock = route({

      'GET /api/articles?limit=100&offset=0': () => json({ items: page(0, 100).reverse(), total: 205, limit: 100, offset: 0 }),

      'GET /api/articles?limit=100&offset=100': () => json({ items: page(100, 100), total: 205, limit: 100, offset: 100 }),

      'GET /api/articles?limit=100&offset=200': () => json({ items: page(200, 5), total: 205, limit: 100, offset: 200 }),

    })

    const articles = await realApi.articles()

    expect(fetchMock).toHaveBeenCalledTimes(3)

    expect(articles).toHaveLength(205)

    expect(articles[0]).toEqual({ id: 1, title: 'Article 001' })

    expect(articles.at(-1)).toEqual({ id: 205, title: 'Article 205' })

  })

  it('maps categories', async () => {

    route({ 'GET /api/categories': () => json({ items: [{ id: 7, name: 'Machine learning', article_count: 282 }] }) })

    expect(await realApi.categories()).toEqual([{ name: 'Machine learning', article_count: 282 }])

  })

})

describe('ngrok', () => {

// BASE_URL is read when the module loads, so each case imports a fresh copy.

  async function clientFor(url: string) {

    vi.stubEnv('VITE_API_URL', url)

    vi.resetModules()

    return (await import('./client')).realApi

  }

  const headersOf = (init: RequestInit | undefined) => new Headers(init?.headers)

  it('sends ngrok-skip-browser-warning on every request, /health included, when the API URL is an ngrok one', async () => {

    const api = await clientFor('https://abc123.ngrok-free.app')

    const fetchMock = route({

      'POST /api/search': () => Promise.reject(new TypeError('Failed to fetch')),

      'GET /health': () => json({ status: 'ok' }),

    })

    await api.search({ question: 'q' }).catch(() => undefined)

    expect(fetchMock.mock.calls.map(([url]) => new URL(url).pathname)).toEqual(['/api/search', '/health'])

    for (const [, init] of fetchMock.mock.calls) {

      expect(headersOf(init).get('ngrok-skip-browser-warning')).toBe('true')

    }

    expect(headersOf(fetchMock.mock.calls[0][1]).get('content-type')).toBe('application/json')

  })

  it('leaves the header out for other API URLs', async () => {

    const api = await clientFor('http://localhost:8000')

    const fetchMock = route({ 'GET /api/categories': () => json({ items: [] }) })

    await api.categories()

    expect(headersOf(fetchMock.mock.calls[0][1]).has('ngrok-skip-browser-warning')).toBe(false)

  })

})
