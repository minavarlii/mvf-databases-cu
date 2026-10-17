// At most one is set: category goes to /api/search/hybrid, source_title to /api/search/linked.
export interface SearchFilters {
  category?: string
  source_title?: string
}

export interface SearchRequest {
  question: string
  top_k?: number
  filters?: SearchFilters
}

// /api/rag takes no filters, so filtered questions only run search().
export type AskRequest = Omit<SearchRequest, 'filters'>

export interface Chunk {
  chunk_id: number
  article_id: number
  article_title: string
  article_url: string
  chunk_index: number
  text: string
  distance: number
}

export interface SourceArticle {
  article_id: number
  title: string
  url: string
}

// One row of MariaDB's EXPLAIN for the executed query.
export interface PlanRow {
  select_id: number
  select_type: string
  table: string
  access_type: string | null
  key: string | null
  rows: number | null
  extra: string | null
}

export interface MariaDbDetails {
  sql: string
  query_plan: PlanRow[] // empty: the backend sent no plan
  search_latency_ms: number
  total_response_ms: number
  chunk_count: number
  vector_index_used: boolean | null // null: no query plan reported, so unknown (not false)
}

export interface SearchResponse {
  chunks: Chunk[]
  details: MariaDbDetails
}

export interface AskResponse extends SearchResponse {
  answer: string
  sources: SourceArticle[]
}

export interface Category {
  name: string
  article_count: number
}

export interface ArticleTitle {
  id: number
  title: string
}

export interface Stats {
  article_count: number | null
  chunk_count: number | null
  embedding_model: string | null
  vector_dimensions: number | null
  mariadb_version: string | null
}

interface ApiCapabilities {
  filters: Record<keyof SearchFilters, boolean>
}

export type ApiErrorCode =
  | 'BACKEND_UNAVAILABLE'
  | 'DATABASE_UNAVAILABLE'
  | 'LLM_FAILED'
  | 'BAD_REQUEST'
  | 'UNKNOWN'

export interface ApiErrorBody {
  error?: {
    code?: ApiErrorCode
    message?: string
  }
}

export interface ApiClient {
  capabilities: ApiCapabilities
  ask(req: AskRequest): Promise<AskResponse>
  search(req: SearchRequest): Promise<SearchResponse>
  categories(): Promise<Category[]>
  articles(): Promise<ArticleTitle[]>
  stats(): Promise<Stats>
}