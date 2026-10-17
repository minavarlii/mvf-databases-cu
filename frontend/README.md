# MVF frontend

A React app for asking questions over the MVF Wikipedia corpus. MariaDB finds the closest chunks with native vector search, the backend's LLM answers from them, and the app shows the exact SQL and EXPLAIN plan behind every result. With a filter set, you can see MariaDB run vector search and ordinary SQL predicates in the same statement.

## Features

- Ask page: an answer with `[N]` citations that jump to the cited chunk, the source articles, and the retrieved chunks with cosine distance and similarity.
- Filters: category (hybrid search through `/api/search/hybrid`) or linked from article (link graph search through `/api/search/linked`). One at a time. A filtered search shows retrieved chunks only, because `/api/rag` takes no filters.
- Details panel: search latency, total response time, whether the vector index was used, the executed SQL with the filter lines highlighted, and the EXPLAIN plan.
- Compare view: the same question run vector-only and with the filter, side by side, showing which chunks the filter removed and which moved up.
- Evaluation dashboard (`#/eval`): recall@k, rank of the right article and MRR, index vs brute force latency, latency by search strategy, and the vector index `M` study, all read from the committed benchmark results.
- Stats strip: article count, chunks, embedding model, dimensions and MariaDB version. The backend has no stats endpoint yet, so with the real backend only the article count is filled in.
- Light and dark theme, following the system setting.

## How the UI maps to the evaluation criteria

| Criterion | Where a reader sees it |
|---|---|
| A VECTOR column with an index over a real Wikipedia corpus, queried with VEC_DISTANCE_COSINE | Details panel: the SQL calls `VEC_DISTANCE_COSINE` and the EXPLAIN row for `chunks` uses `ix_chunks_embedding` (highlighted) |
| Semantic search and ordinary SQL predicates in the same statement, joined back to relational tables | Category and linked filters. Their lines in the SQL are highlighted. Article titles in the results come from the join back to `articles` |
| Recall and latency against a ground-truth set | Evaluation dashboard. The stats strip shows the corpus it was measured on |
| An ingest that runs from the README and a query interface a reader can try | This app, plus mock mode to try it without a backend. The ingest is in the [root README](../README.md#build-the-corpus) |
| What the database-native approach gave you | One SQL statement does the vector search, the filter and the join, with no second store to keep in sync |

Chunk size, embedding model and index parameters are documented in the [root README](../README.md#embedding-configuration).

## Query walkthrough

Ask "What is overfitting?" with the category filter set to Machine learning. The app sends:

```http
POST /api/search/hybrid
{"query": "What is overfitting?", "category": "Machine learning", "limit": 5}
```

The backend embeds the question and runs this statement (`HYBRID_SEARCH_SQL` in `backend/app/db/queries/vector.py`, a few columns left out):

```sql
SELECT c.chunk_id, c.article_id, a.title AS article_title, c.chunk_index, c.content, c.distance
FROM (
    SELECT id AS chunk_id, article_id, chunk_index, content,
           VEC_DISTANCE_COSINE(embedding, VEC_FromText(:embedding)) AS distance
    FROM chunks
    WHERE article_id IN (
        SELECT ac.article_id
        FROM article_categories AS ac
        INNER JOIN categories AS cat ON cat.id = ac.category_id
        WHERE cat.name = :category
    )
    ORDER BY distance ASC
    LIMIT :limit
) AS c
INNER JOIN articles AS a ON a.id = c.article_id
ORDER BY c.distance ASC
```

The response carries the results plus `debug`: the SQL, parameters, timings and `execution_plan`. In the committed benchmark plan, `chunks` is read through `ix_chunks_embedding`, `cat` through `uq_categories_name` and `ac` through `fk_article_categories_category`. The app marks the index as used when any plan row has `key = ix_chunks_embedding`.

The chunks render on the right, ranked by distance, with similarity shown as 1 minus distance. The sources list groups them by article. The details panel shows the full SQL with the category lines highlighted and the EXPLAIN table below it.

Without a filter, the app calls `POST /api/rag` with `{"question": ..., "top_k": 5}` and shows the answer above the same sources, chunks and details. Linked search reads chunks through `ix_chunks_article_id` instead of the vector index, because the link join leaves few candidates. The details panel says so.

## Endpoints used

| Method | Path | Used for |
|---|---|---|
| POST | `/api/rag` | Answer with sources (unfiltered questions) |
| POST | `/api/search` | Vector-only search: LLM fallback and the compare view |
| POST | `/api/search/hybrid` | Search with a category filter |
| POST | `/api/search/linked` | Search within articles linked from a source article |
| GET | `/api/categories` | Category filter options with article counts |
| GET | `/api/articles` | Article titles for the linked picker (all pages, `limit=100`) and the article count |
| GET | `/health` | Telling a stopped backend apart from a failed request |

## Setup

Requires Node 22 and the backend running (see the [root README](../README.md#run-the-api)).

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

`.env` has two settings:

- `VITE_API_URL`: the backend URL, `http://localhost:8000` by default.
- `VITE_USE_MOCK`: `true` serves canned data instead of calling the backend.

The dev server runs on http://localhost:5173. Keep that port: the backend's CORS only allows `FRONTEND_ORIGIN`, which defaults to `http://localhost:5173`.

LLM answers need `OPENAI_API_KEY` in the backend's `.env`. Never put it in the frontend `.env`, since every `VITE_` variable ends up in the browser bundle. Without the key, search still works and the app shows the retrieved chunks with a note that the answer couldn't be generated.

## Mock mode

Set `VITE_USE_MOCK=true` in `.env` and restart `npm run dev`. A MOCK DATA badge appears in the header. Search results, plans and stats are canned but shaped like the real backend's.

Type these into the question, or add them to the URL, to see each state:

| Trigger | Effect |
|---|---|
| `!offline` | Backend unreachable |
| `!db` | Database unavailable |
| `!llm` | Answer generation fails, chunks still shown |
| `!empty` | No chunks returned |
| `!noindex` | Plan without the vector index (brute force) |
| `!failhybrid` | Filtered side of the compare view fails (needs a filter) |
| `!failvector` | Vector-only side of the compare view fails |
| `?nocategories` | Category list fails to load (URL parameter) |
| `?noarticles` | Article list for the linked picker fails to load (URL parameter) |

Category Deep learning or Artificial intelligence returns no chunks. So does a linked article without mock links, such as Machine learning in earth sciences.

## Scripts

```bash
npm run dev        # sync-eval, then the Vite dev server
npm run build      # sync-eval, type check (tsc -b), production build into dist/
npm test           # Vitest, once
npm run lint       # ESLint
npm run sync-eval  # copy the newest experiments/results files and data/manifest.json into public/eval
```

`sync-eval` also reads `M` and `DISTANCE` from `database/schema/002_vector_index.sql`. Lint, tests and build run in CI in the `frontend` job of `.github/workflows/ci.yml`.

## Project structure

```text
src/
├── App.tsx            header, stats strip, page tabs
├── api/               client.ts (real backend), mock.ts, types.ts, errors.ts
├── pages/
│   ├── AskPage.tsx    ask page layout and state
│   ├── askFlow.ts     which endpoint a question goes to, flow steps
│   └── EvalPage.tsx   evaluation dashboard
├── components/        answer, sources, chunks, filters, details, compare view, SQL block
│   └── charts/        inline SVG charts
├── eval/data.ts       loads and checks the files in public/eval
└── index.css          all styles and theme tokens
```

## Tech stack

React 19, TypeScript, Vite, plain CSS, native `fetch`, Vitest and ESLint. Charts are inline SVG. No UI or chart libraries.
