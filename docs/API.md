# MVF API Reference

This document defines the HTTP contract between the MVF FastAPI backend and the frontend.

## Base URL

Development:

```text
http://localhost:8000
```

All application endpoints except the health check are prefixed with:

```text
/api
```

Interactive OpenAPI documentation is available at:

```text
http://localhost:8000/docs
```

## Content Type

POST requests use:

```http
Content-Type: application/json
```

## Authentication

The current API does not require frontend authentication.

Backend secrets such as database credentials and `OPENAI_API_KEY` must never be exposed to the frontend.

---

# Endpoint Summary

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Backend health check |
| `GET` | `/api/articles` | Paginated article list |
| `GET` | `/api/articles/{article_id}` | Full article details |
| `GET` | `/api/categories` | Available article categories |
| `POST` | `/api/search` | Semantic vector search |
| `POST` | `/api/search/hybrid` | Category-filtered vector search |
| `POST` | `/api/search/linked` | Link-constrained vector search |
| `POST` | `/api/rag` | Retrieval-Augmented Generation |

---

# Shared Types

## Search Result

```ts
export interface SearchResult {
  chunk_id: number;
  article_id: number;
  article_title: string;
  chunk_index: number;
  content: string;
  token_count: number;
  distance: number;
}
```

`distance` is cosine distance. Lower values represent closer semantic matches.

## Query Plan Row

```ts
export interface QueryPlanRow {
  select_id: number;
  select_type: string;
  table: string;
  access_type: string | null;
  possible_keys: string | null;
  key: string | null;
  rows: number | null;
  extra: string | null;
}
```

## Query Debug

```ts
export interface QueryDebug {
  sql: string;
  parameters: Record<string, string | number>;
  embedding_ms: number;
  search_ms: number;
  explain_ms: number;
  total_ms: number;
  execution_plan: QueryPlanRow[];
}
```

All search endpoints and the RAG endpoint return this debug structure.

---

# Health

## `GET /health`

Returns backend availability.

### Response

**200 OK**

```json
{
  "status": "ok"
}
```

Type:

```ts
export interface HealthResponse {
  status: string;
}
```

---

# Articles

## `GET /api/articles`

Returns paginated article summaries.

### Query Parameters

| Parameter | Type | Default | Validation |
|---|---|---:|---|
| `limit` | integer | `20` | `1 <= limit <= 100` |
| `offset` | integer | `0` | `offset >= 0` |

### Example Request

```http
GET /api/articles?limit=20&offset=0
```

### Response

**200 OK**

```json
{
  "items": [
    {
      "id": 1,
      "wikipedia_page_id": 233488,
      "title": "Machine learning",
      "url": "https://en.wikipedia.org/wiki/Machine_learning",
      "summary": "Machine learning is ...",
      "word_count": 10432
    }
  ],
  "total": 285,
  "limit": 20,
  "offset": 0
}
```

Types:

```ts
export interface ArticleSummary {
  id: number;
  wikipedia_page_id: number;
  title: string;
  url: string;
  summary: string | null;
  word_count: number;
}

export interface ArticleListResponse {
  items: ArticleSummary[];
  total: number;
  limit: number;
  offset: number;
}
```

---

## `GET /api/articles/{article_id}`

Returns one article by its internal MVF database ID.

### Path Parameter

| Parameter | Type |
|---|---|
| `article_id` | integer |

### Example Request

```http
GET /api/articles/1
```

### Response

**200 OK**

```json
{
  "id": 1,
  "wikipedia_page_id": 233488,
  "revision_id": 123456789,
  "title": "Machine learning",
  "url": "https://en.wikipedia.org/wiki/Machine_learning",
  "summary": "Machine learning is ...",
  "content": "Full stored article content ...",
  "word_count": 10432,
  "categories": [
    "Machine learning",
    "Artificial intelligence"
  ]
}
```

Type:

```ts
export interface ArticleDetails {
  id: number;
  wikipedia_page_id: number;
  revision_id: number;
  title: string;
  url: string;
  summary: string | null;
  content: string;
  word_count: number;
  categories: string[];
}
```

### Errors

**404 Not Found**

```json
{
  "detail": "Article not found."
}
```

---

# Categories

## `GET /api/categories`

Returns all available categories.

### Response

**200 OK**

```json
{
  "items": [
    {
      "id": 1,
      "name": "Machine learning",
      "article_count": 285
    }
  ]
}
```

Types:

```ts
export interface Category {
  id: number;
  name: string;
  article_count: number;
}

export interface CategoryListResponse {
  items: Category[];
}
```

---

The timing values in this document are illustrative response-shape examples,
not fixed performance guarantees. On the documented 285-article / 3,940-vector
benchmark corpus, the optimized `Machine learning` hybrid workload uses
`ix_chunks_embedding` and measures approximately 2–3 ms at the database-search
layer. Absolute latency varies by machine, cache state, and workload.

# Semantic Search

## `POST /api/search`

Performs MariaDB-native semantic vector search over stored chunks.

### Request Body

```json
{
  "query": "What is supervised learning?",
  "limit": 5
}
```

### Validation

| Field | Type | Required | Validation |
|---|---|---|---|
| `query` | string | yes | trimmed, 1–1000 characters |
| `limit` | integer | no | default `5`, `1 <= limit <= 50` |

Whitespace-only `query` values are rejected.

### Response

**200 OK**

```json
{
  "query": "What is supervised learning?",
  "results": [
    {
      "chunk_id": 123,
      "article_id": 1,
      "article_title": "Machine learning",
      "chunk_index": 7,
      "content": "Supervised learning is ...",
      "token_count": 220,
      "distance": 0.2134
    }
  ],
  "debug": {
    "sql": "SELECT ...",
    "parameters": {
      "embedding": "[...]",
      "limit": 5
    },
    "embedding_ms": 28.4,
    "search_ms": 2.3,
    "explain_ms": 1.1,
    "total_ms": 31.8,
    "execution_plan": []
  }
}
```

Type:

```ts
export interface SearchResponse {
  query: string;
  results: SearchResult[];
  debug: QueryDebug;
}
```

---

# Hybrid Search

## `POST /api/search/hybrid`

Performs semantic vector search constrained by a category.

### Request Body

```json
{
  "query": "image classification dataset",
  "category": "Datasets in computer vision",
  "limit": 5
}
```

### Validation

| Field | Type | Required | Validation |
|---|---|---|---|
| `query` | string | yes | trimmed, 1–1000 characters |
| `category` | string | yes | trimmed, 1–255 characters |
| `limit` | integer | no | default `5`, `1 <= limit <= 50` |

Whitespace-only text values are rejected.

### Response

**200 OK**

```json
{
  "query": "image classification dataset",
  "category": "Datasets in computer vision",
  "results": [
    {
      "chunk_id": 456,
      "article_id": 3,
      "article_title": "80 Million Tiny Images",
      "chunk_index": 1,
      "content": "80 Million Tiny Images is ...",
      "token_count": 220,
      "distance": 0.2871
    }
  ],
  "debug": {
    "sql": "SELECT ...",
    "parameters": {
      "embedding": "[...]",
      "category": "Datasets in computer vision",
      "limit": 5
    },
    "embedding_ms": 25.1,
    "search_ms": 2.3,
    "explain_ms": 1.0,
    "total_ms": 28.4,
    "execution_plan": []
  }
}
```

Type:

```ts
export interface HybridSearchResponse {
  query: string;
  category: string;
  results: SearchResult[];
  debug: QueryDebug;
}
```

---

# Linked Search

## `POST /api/search/linked`

Performs vector search over chunks belonging to articles linked from a source article.

### Request Body

```json
{
  "query": "neural network training",
  "source_title": "Machine learning",
  "limit": 5
}
```

### Validation

| Field | Type | Required | Validation |
|---|---|---|---|
| `query` | string | yes | trimmed, 1–1000 characters |
| `source_title` | string | yes | trimmed, 1–512 characters |
| `limit` | integer | no | default `5`, `1 <= limit <= 50` |

Whitespace-only text values are rejected.

### Response

**200 OK**

```json
{
  "query": "neural network training",
  "source_title": "Machine learning",
  "results": [
    {
      "chunk_id": 789,
      "article_id": 96,
      "article_title": "Federated learning",
      "chunk_index": 2,
      "content": "Federated learning ...",
      "token_count": 220,
      "distance": 0.3012
    }
  ],
  "debug": {
    "sql": "SELECT ...",
    "parameters": {
      "embedding": "[...]",
      "source_title": "Machine learning",
      "limit": 5
    },
    "embedding_ms": 25.0,
    "search_ms": 88.0,
    "explain_ms": 1.0,
    "total_ms": 114.0,
    "execution_plan": []
  }
}
```

Type:

```ts
export interface LinkedSearchResponse {
  query: string;
  source_title: string;
  results: SearchResult[];
  debug: QueryDebug;
}
```

---

# RAG

## `POST /api/rag`

Retrieves relevant MariaDB chunks and generates a grounded answer using the configured text generator.

### Request Body

```json
{
  "question": "What is federated learning and why can it preserve data locality?",
  "top_k": 5
}
```

### Validation

| Field | Type | Required | Validation |
|---|---|---|---|
| `question` | string | yes | trimmed, 1–2000 characters |
| `top_k` | integer | no | default `5`, `1 <= top_k <= 20` |

Whitespace-only questions are rejected.

### Response

**200 OK**

```json
{
  "question": "What is federated learning and why can it preserve data locality?",
  "answer": "Federated learning is ...",
  "sources": [
    {
      "article_id": 96,
      "article_title": "Federated learning",
      "chunk_index": 1,
      "content": "Federated learning is a machine learning technique ...",
      "distance": 0.1823
    }
  ],
  "debug": {
    "sql": "SELECT ...",
    "parameters": {
      "embedding": "[...]",
      "limit": 5
    },
    "embedding_ms": 26.1,
    "search_ms": 2.4,
    "explain_ms": 1.0,
    "total_ms": 29.5,
    "execution_plan": []
  }
}
```

Types:

```ts
export interface RagSource {
  article_id: number;
  article_title: string;
  chunk_index: number;
  content: string;
  distance: number;
}

export interface RagResponse {
  question: string;
  answer: string;
  sources: RagSource[];
  debug: QueryDebug;
}
```

### Errors

The route explicitly maps service failures to:

**422 Unprocessable Entity**

```json
{
  "detail": "..."
}
```

**502 Bad Gateway**

```json
{
  "detail": "..."
}
```

---

# Validation Errors

FastAPI/Pydantic request-validation failures return HTTP `422`.

Example structure:

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "query"],
      "msg": "String should have at least 1 character",
      "input": ""
    }
  ]
}
```

The exact validation object may vary by error.

Generic frontend type:

```ts
export interface ApiError {
  detail: unknown;
}
```

---

# CORS

The allowed frontend origin is configured by:

```dotenv
FRONTEND_ORIGIN=http://localhost:5173
```

If the frontend runs on another origin, update `FRONTEND_ORIGIN` in the backend `.env` and restart the API.

---

# Frontend Environment

Recommended frontend variable:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

Do not expose backend-only environment variables to the frontend.

---

# Minimal API Client

```ts
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function apiRequest<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let detail: unknown = `HTTP ${response.status}`;

    try {
      const payload = (await response.json()) as {
        detail?: unknown;
      };

      if ("detail" in payload) {
        detail = payload.detail;
      }
    } catch {
      // Preserve fallback error text.
    }

    throw new Error(
      typeof detail === "string"
        ? detail
        : JSON.stringify(detail),
    );
  }

  return (await response.json()) as T;
}
```

---

# Guided CLI Demo

The repository also provides a non-HTTP worked example:

```bash
make demo
```

It runs semantic, hybrid, and linked search and prints the executed SQL, bound
parameters, timings, and MariaDB `EXPLAIN` plans. It requires the indexed corpus
but does not require an OpenAI API key.

For machine-readable output:

```bash
python3 -m scripts.demo --json
```

This is useful for validating backend retrieval behavior before frontend
integration.

---

# Integration Checklist

Before finalizing frontend integration, verify:

```text
GET  /health
GET  /api/articles
GET  /api/articles/{article_id}
GET  /api/categories
POST /api/search
POST /api/search/hybrid
POST /api/search/linked
POST /api/rag
```

Also verify that:

```text
CORS succeeds from the frontend origin
422 validation errors are handled
404 article errors are handled
502 RAG errors are handled
search result order is preserved
debug fields deserialize correctly
```
