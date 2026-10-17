import { ApiError } from './errors'

import type {
  ApiClient,
  ApiErrorBody,
  ApiErrorCode,
  ArticleTitle,
  AskResponse,
  Category,
  Chunk,
  MariaDbDetails,
  PlanRow,
  SearchResponse,
  SourceArticle,
  Stats,
} from './types'

const BASE_URL = (
  import.meta.env.VITE_API_URL ??
  import.meta.env.VITE_API_BASE_URL ??
  'http://localhost:8000'
).replace(/\/+$/, '')

// ngrok's free plan answers browser requests with an HTML warning page unless this header is sent.
const EXTRA_HEADERS: Record<string, string> = BASE_URL.includes('ngrok')
  ? { 'ngrok-skip-browser-warning': 'true' }
  : {}

const TIMEOUT_MS = 60_000

// /api/articles caps limit at 100.
const ARTICLES_PAGE = 100

const DEFAULT_TOP_K = 5

// Name of the HNSW index in database/schema/002_vector_index.sql;
// its presence in EXPLAIN means it was used.
export const VECTOR_INDEX = 'ix_chunks_embedding'

interface BackendSearchResult {
  chunk_id: number
  article_id: number
  article_title: string
  chunk_index: number
  content: string
  token_count: number
  distance: number
}

interface BackendPlanRow {
  select_id: number
  select_type: string
  table: string
  access_type: string | null
  possible_keys: string | null
  key: string | null
  rows: number | null
  extra: string | null
}

interface BackendDebug {
  sql: string
  parameters: Record<string, string | number>
  embedding_ms: number
  search_ms: number
  explain_ms: number
  total_ms: number
  execution_plan: BackendPlanRow[]
}

interface BackendSearchResponse {
  results: BackendSearchResult[]
  debug: BackendDebug
}

interface BackendRagSource {
  article_id: number
  article_title: string
  chunk_index: number
  content: string
  distance: number
}

interface BackendRagResponse {
  answer: string
  sources: BackendRagSource[]
  debug: BackendDebug
}

interface BackendCategoryList {
  items: {
    id: number
    name: string
    article_count: number
  }[]
}

interface BackendArticleList {
  items: {
    id: number
    title: string
  }[]
  total: number
}

interface BackendStatsResponse {
  article_count: number
  chunk_count: number
  embedding_model: string
  vector_dimensions: number
  mariadb_version: string
}

interface BackendErrorBody {
  detail?: string | { loc?: (string | number)[]; msg?: string }[]
}

type Endpoint = 'rag' | 'search' | 'catalog'

function detailText(body: BackendErrorBody | null): string | null {
  const d = body?.detail

  if (typeof d === 'string') return d

  if (Array.isArray(d) && d.length > 0) {
    const field = d[0].loc?.filter((p) => p !== 'body').join('.')

    return field
      ? `${field}: ${d[0].msg ?? 'invalid'}`
      : (d[0].msg ?? null)
  }

  return null
}

function codeFor(status: number, endpoint: Endpoint): ApiErrorCode {
  // 502/503 from /api/rag mean the LLM failed or isn't configured;
  // retrieval may still work.
  if (endpoint === 'rag' && (status === 502 || status === 503)) {
    return 'LLM_FAILED'
  }

  if (status === 400 || status === 404 || status === 422) {
    return 'BAD_REQUEST'
  }

  return 'UNKNOWN'
}

// DB errors reach the browser as a 500 without CORS headers, i.e. a network
// error; /health tells that apart from a down backend.
async function backendIsUp(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/health`, {
      headers: EXTRA_HEADERS,
      signal: AbortSignal.timeout(3000),
    })

    return res.ok
  } catch {
    return false
  }
}

async function request<T>(
  path: string,
  endpoint: Endpoint,
  init?: RequestInit,
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)

  let res: Response

  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...EXTRA_HEADERS,
        ...init?.headers,
      },
      signal: controller.signal,
    })
  } catch {
    if (controller.signal.aborted) {
      throw new ApiError(
        'BACKEND_UNAVAILABLE',
        `No response from the backend within ${TIMEOUT_MS / 1000} s.`,
      )
    }

    if (await backendIsUp()) {
      throw new ApiError(
        'UNKNOWN',
        'The backend is running but this request failed with an internal error. Check the backend log (is MariaDB up?).',
      )
    }

    throw new ApiError(
      'BACKEND_UNAVAILABLE',
      `Could not reach the backend at ${BASE_URL}.`,
    )
  } finally {
    clearTimeout(timer)
  }

  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as
      | (BackendErrorBody & ApiErrorBody)
      | null

    const code = body?.error?.code ?? codeFor(res.status, endpoint)
    const message =
      body?.error?.message ??
      detailText(body) ??
      `Request failed with status ${res.status}`

    throw new ApiError(code, `${message} (HTTP ${res.status})`)
  }

  return (await res.json()) as T
}

const post = <T>(
  path: string,
  endpoint: Endpoint,
  body: unknown,
): Promise<T> =>
  request<T>(path, endpoint, {
    method: 'POST',
    body: JSON.stringify(body),
  })

// Search results carry no URL; the corpus is English Wikipedia,
// so derive it from the title.
const wikipediaUrl = (title: string) =>
  `https://en.wikipedia.org/wiki/${encodeURIComponent(
    title.replace(/ /g, '_'),
  )}`

function toChunk(r: BackendSearchResult): Chunk {
  return {
    chunk_id: r.chunk_id,
    article_id: r.article_id,
    article_title: r.article_title,
    article_url: wikipediaUrl(r.article_title),
    chunk_index: r.chunk_index,
    text: r.content,
    distance: r.distance,
  }
}

// RAG sources have no chunk_id; (article_id, chunk_index) is unique,
// so a negative id from it can't collide.
function ragSourceToChunk(s: BackendRagSource): Chunk {
  return {
    chunk_id: -(s.article_id * 100_000 + s.chunk_index),
    article_id: s.article_id,
    article_title: s.article_title,
    article_url: wikipediaUrl(s.article_title),
    chunk_index: s.chunk_index,
    text: s.content,
    distance: s.distance,
  }
}

function toSources(chunks: Chunk[]): SourceArticle[] {
  const seen = new Map<number, SourceArticle>()

  for (const c of chunks) {
    if (!seen.has(c.article_id)) {
      seen.set(c.article_id, {
        article_id: c.article_id,
        title: c.article_title,
        url: c.article_url,
      })
    }
  }

  return [...seen.values()]
}

const toPlanRow = (r: BackendPlanRow): PlanRow => ({
  select_id: r.select_id,
  select_type: r.select_type,
  table: r.table,
  access_type: r.access_type,
  key: r.key,
  rows: r.rows,
  extra: r.extra,
})

function indexUsed(plan: BackendPlanRow[]): boolean | null {
  if (plan.length === 0) return null

  return plan.some((row) => row.key === VECTOR_INDEX)
}

// Measured client-side, so for /api/rag total_response_ms includes the LLM.
function toDetails(
  debug: BackendDebug,
  chunkCount: number,
  startedAt: number,
): MariaDbDetails {
  return {
    sql: debug.sql,
    query_plan: debug.execution_plan.map(toPlanRow),
    search_latency_ms: debug.search_ms,
    total_response_ms: performance.now() - startedAt,
    chunk_count: chunkCount,
    vector_index_used: indexUsed(debug.execution_plan),
  }
}

// The backend cites as [Source N], [Source 1, Source 3] or
// [Sources 1 and 3]; the answer card links [N].
const normalizeCitations = (answer: string) =>
  answer.replace(
    /\[Sources?\s*((?:\d+|Source|,|and|\s)+)\]/gi,
    (whole: string, list: string) => {
      const nums = list.match(/\d+/g)
      return nums ? nums.map((n) => `[${n}]`).join('') : whole
    },
  )

export const realApi: ApiClient = {
  capabilities: {
    filters: {
      category: true,
      source_title: true,
    },
  },

  async ask(req): Promise<AskResponse> {
    const startedAt = performance.now()

    const res = await post<BackendRagResponse>('/api/rag', 'rag', {
      question: req.question,
      top_k: req.top_k ?? DEFAULT_TOP_K,
    })

    const chunks = res.sources.map(ragSourceToChunk)

    return {
      answer: normalizeCitations(res.answer),
      sources: toSources(chunks),
      chunks,
      details: toDetails(res.debug, chunks.length, startedAt),
    }
  },

  async search(req): Promise<SearchResponse> {
    const { category, source_title } = req.filters ?? {}

    // Separate endpoints, so sending both would silently drop one.
    if (category && source_title) {
      throw new ApiError(
        'BAD_REQUEST',
        'One filter at a time: category or linked article.',
      )
    }

    const limit = req.top_k ?? DEFAULT_TOP_K
    const startedAt = performance.now()

    const res = category
      ? await post<BackendSearchResponse>(
          '/api/search/hybrid',
          'search',
          {
            query: req.question,
            category,
            limit,
          },
        )
      : source_title
        ? await post<BackendSearchResponse>(
            '/api/search/linked',
            'search',
            {
              query: req.question,
              source_title,
              limit,
            },
          )
        : await post<BackendSearchResponse>(
            '/api/search',
            'search',
            {
              query: req.question,
              limit,
            },
          )

    const chunks = res.results.map(toChunk)

    return {
      chunks,
      details: toDetails(res.debug, chunks.length, startedAt),
    }
  },

  async categories(): Promise<Category[]> {
    const res = await request<BackendCategoryList>(
      '/api/categories',
      'catalog',
    )

    return res.items.map((c) => ({
      name: c.name,
      article_count: c.article_count,
    }))
  },

  async articles(): Promise<ArticleTitle[]> {
    const titles: ArticleTitle[] = []

    for (let offset = 0; ; offset += ARTICLES_PAGE) {
      const page = await request<BackendArticleList>(
        `/api/articles?limit=${ARTICLES_PAGE}&offset=${offset}`,
        'catalog',
      )

      titles.push(
        ...page.items.map((a) => ({
          id: a.id,
          title: a.title,
        })),
      )

      if (
        page.items.length === 0 ||
        offset + ARTICLES_PAGE >= page.total
      ) {
        break
      }
    }

    return titles.sort((a, b) => a.title.localeCompare(b.title))
  },

  async stats(): Promise<Stats> {
    const res = await request<BackendStatsResponse>(
      '/api/stats',
      'catalog',
    )

    return {
      article_count: res.article_count,
      chunk_count: res.chunk_count,
      embedding_model: res.embedding_model,
      vector_dimensions: res.vector_dimensions,
      mariadb_version: res.mariadb_version,
    }
  },
}
