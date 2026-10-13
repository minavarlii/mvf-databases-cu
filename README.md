A project for area 4, "Vector search and RAG, natively" for the [MariaDB student database projects, 2026-09](https://mariadb.org/bachelor_hackathon_2026-09/).

# MVF — MariaDB Vector Finder

MVF is a MariaDB-native vector search and Retrieval-Augmented Generation (RAG) system built around a reproducible Wikipedia corpus.

The project explores how semantic retrieval, relational filtering, graph-constrained search, and RAG can be implemented while keeping vector storage, similarity computation, indexing, and query planning inside MariaDB.

MariaDB is used as an active retrieval engine rather than only as an application datastore. MVF directly uses:

```sql
VECTOR(384)
VECTOR INDEX
VEC_FromText(...)
VEC_DISTANCE_COSINE(...)
```

The current corpus contains:

- **285 Wikipedia articles**
- **3,940 vector chunks**
- **2,710 directed local article links**
- **40 manually prepared retrieval-evaluation questions**

On the current corpus, MariaDB's native vector index provides an observed **177.92× speedup** over brute-force cosine search for the benchmark query.

---

## Key Features

- MariaDB-native `VECTOR(384)` storage
- Native cosine `VECTOR INDEX`
- Semantic vector search
- Relationally filtered hybrid search
- Graph-constrained vector search through Wikipedia links
- Retrieval-Augmented Generation
- FastAPI backend
- Async SQLAlchemy database access
- Reproducible Wikipedia ingestion through the MediaWiki API
- Deterministic token-based chunking
- Incremental and self-healing vector indexing
- Raw Wikipedia snapshots
- MariaDB `EXPLAIN` integration
- Search timing diagnostics
- Recall@K and MRR evaluation
- Exact article-level retrieval evaluation
- Vector-index vs brute-force benchmarks
- Ruff, mypy, and pytest quality checks

---

# Architecture

```mermaid
flowchart TD
    MW[MediaWiki API]

    MW --> ING[Ingestion Service]

    ING --> RAW[Raw JSON Snapshots]
    ING --> ART[(articles)]
    ING --> CAT[(categories)]
    ING --> AC[(article_categories)]
    ING --> LINKS[(article_links)]

    ART --> CHUNK[Chunking Service]
    CHUNK --> EMB[Embedding Service]
    EMB --> VEC[(chunks / VECTOR 384)]

    VEC --> SEM[Semantic Search]

    CAT --> HYB[Hybrid Search]
    AC --> HYB
    VEC --> HYB

    LINKS --> LINKED[Linked Search]
    VEC --> LINKED

    SEM --> RAG[RAG Service]
    RAG --> GEN[Text Generator]

    SEM --> API[FastAPI]
    HYB --> API
    LINKED --> API
    RAG --> API
```

MVF intentionally separates corpus ingestion from vector indexing.

### Stage 1 — Corpus ingestion

```text
MediaWiki API
      ↓
articles
categories
article_categories
article_links
raw JSON snapshots
```

### Stage 2 — Vector indexing

```text
articles.content
      ↓
token-based chunking
      ↓
sentence-transformers
      ↓
384-dimensional embeddings
      ↓
MariaDB VECTOR(384)
      ↓
VECTOR INDEX
```

This two-stage design allows the corpus to be re-indexed without downloading the source data again.

---

# Technology Stack

```text
Python 3.12+
FastAPI
SQLAlchemy Async
asyncmy
MariaDB 11.8
Pydantic v2
httpx
sentence-transformers
Docker Compose
pytest
pytest-asyncio
Ruff
mypy
```

The project has been developed and verified against MariaDB **11.8.9**.

---

# Database Model

MVF combines relational metadata, article relationships, and native vectors inside one MariaDB database.

## `articles`

Stores Wikipedia article metadata and source text, including Wikipedia page ID, revision ID, title, URL, summary, full content, word count, and timestamps.

## `categories`

Stores unique Wikipedia category names.

## `article_categories`

Many-to-many relation between articles and categories. This relation is used by hybrid vector search.

## `article_links`

Stores directed links between articles that are both present in the local MVF corpus.

```text
source article
      ↓
article_links
      ↓
target article
```

Links to Wikipedia pages outside the local corpus are intentionally excluded, so the table represents the directed graph induced by the locally ingested articles.

## `chunks`

Stores token-based article chunks and their native MariaDB embeddings.

```sql
embedding VECTOR(384) NOT NULL
```

Each article has a unique `(article_id, chunk_index)` pair.

The vector index is created with cosine distance:

```sql
CREATE VECTOR INDEX IF NOT EXISTS ix_chunks_embedding
ON chunks (embedding)
M = 8
DISTANCE = cosine;
```

---

# Embedding Configuration

MVF currently uses:

```text
Model:                 sentence-transformers/all-MiniLM-L6-v2
Embedding dimensions:  384
Chunk size:            220 tokens
Chunk overlap:         40 tokens
Embedding normalization: L2 normalized
Vector distance:       cosine
```

Chunking uses the tokenizer associated with the embedding model rather than approximate character-based splitting.

---

# MariaDB-Native Semantic Search

The embedding for the user's query is generated in Python. The vector retrieval itself is executed by MariaDB.

```sql
SELECT
    c.chunk_id,
    c.article_id,
    a.title AS article_title,
    c.chunk_index,
    c.content,
    c.token_count,
    c.distance
FROM (
    SELECT
        id AS chunk_id,
        article_id,
        chunk_index,
        content,
        token_count,
        VEC_DISTANCE_COSINE(
            embedding,
            VEC_FromText(:embedding)
        ) AS distance
    FROM chunks
    ORDER BY distance ASC
    LIMIT :limit
) AS c
INNER JOIN articles AS a
    ON a.id = c.article_id
ORDER BY c.distance ASC;
```

MariaDB therefore handles vector storage, vector indexing, cosine-distance evaluation, ranking, limiting, and query optimization.

MariaDB-specific vector SQL is centralized in:

```text
backend/app/db/queries/vector.py
```

Normal relational persistence is separated into repository classes.

---

# Search Strategies

## Semantic Search

Global nearest-neighbor search over article chunks:

```text
query
  ↓
embedding
  ↓
VECTOR INDEX
  ↓
nearest chunks
```

For the current corpus, MariaDB selects `ix_chunks_embedding`.

## Hybrid Search

Hybrid search combines a relational category constraint with semantic vector ranking.

The category restriction is placed inside the vector candidate query so the
database can optimize the filtered top-k directly:

```sql
SELECT
    c.chunk_id,
    c.article_id,
    a.title AS article_title,
    c.chunk_index,
    c.content,
    c.token_count,
    c.distance
FROM (
    SELECT
        id AS chunk_id,
        article_id,
        chunk_index,
        content,
        token_count,
        VEC_DISTANCE_COSINE(
            embedding,
            VEC_FromText(:embedding)
        ) AS distance
    FROM chunks
    WHERE article_id IN (
        SELECT ac.article_id
        FROM article_categories AS ac
        INNER JOIN categories AS cat
            ON cat.id = ac.category_id
        WHERE cat.name = :category
    )
    ORDER BY distance ASC
    LIMIT :limit
) AS c
INNER JOIN articles AS a
    ON a.id = c.article_id
ORDER BY c.distance ASC;
```

For the benchmark category `Machine learning`, this shape uses
`ix_chunks_embedding` and reduces mean database latency from roughly **227 ms**
for the previous relational-first form to **2.359 ms**, while preserving the
checked top-k results.

For smaller filtered candidate sets, MariaDB may still prefer
`ix_chunks_article_id`, which can be cheaper.


## Linked Search

Linked search combines Wikipedia's directed article graph with semantic vector ranking:

```text
source article
      ↓
article_links
      ↓
target articles
      ↓
target chunks
      ↓
cosine ranking
```

The query combines relational joins, graph constraints, and vector similarity inside MariaDB.

A vector-first derived-table rewrite was benchmarked separately and did not improve this workload (approximately 87.4 ms current vs. 88.4 ms proposed). The production linked query therefore intentionally remains relational-first and uses `ix_chunks_article_id`.

---

# Optimizer Statistics

Bulk ingestion and vector indexing materially change table cardinalities. MVF
therefore refreshes MariaDB optimizer statistics after both data-loading
workflows:

```sql
ANALYZE TABLE
    articles,
    chunks,
    article_categories,
    categories,
    article_links;
```

The maintenance logic is centralized in:

```text
backend/app/db/maintenance.py
```

and is called after the main work in:

```text
scripts/ingest.py
scripts/build_embeddings.py
```

This keeps optimizer decisions reproducible after corpus growth or vector
rebuilds.

---

# RAG

MVF implements Retrieval-Augmented Generation on top of MariaDB semantic retrieval.

```text
question
   ↓
EmbeddingService
   ↓
MariaDB retrieval
   ↓
retrieved chunks
   ↓
grounded prompt
   ↓
text generator
   ↓
answer + sources
```

Generation is optional. If no OpenAI API key is configured, the application can still run and retrieval endpoints remain available.

The RAG layer is deliberately separated from retrieval so retrieval latency and retrieval quality can be evaluated independently of generation time.

---

# Query Transparency

Search responses expose diagnostic information so MariaDB behavior is visible rather than hidden behind the application layer.

Debug information includes:

- executed SQL
- query parameters
- embedding latency
- database search latency
- `EXPLAIN` latency
- total retrieval latency
- MariaDB execution plan

---

# Current Dataset

| Metric | Value |
|---|---:|
| Wikipedia articles | 285 |
| Vector chunks | 3,940 |
| Directed local article links | 2,710 |
| Embedding dimensions | 384 |
| Ground-truth questions | 40 |
| Articles without chunks | 0 |

The corpus is currently centered on Wikipedia's machine-learning category.

---

# Performance

Benchmarks below measure database retrieval latency. Query-embedding generation is performed before the timed database operation.

Current benchmark configuration:

```text
Corpus:         285 articles / 3,940 vectors
Query:          neural network training
Result limit:   5
Warm-up runs:   5
Measured runs:  50
```

## Search Strategy Benchmark

| Strategy | Mean | Median | P95 | Main retrieval index |
|---|---:|---:|---:|---|
| Semantic | **1.393 ms** | 1.304 ms | 1.816 ms | `ix_chunks_embedding` |
| Hybrid | **2.359 ms** | 2.238 ms | 3.017 ms | `ix_chunks_embedding` |
| Linked | 87.914 ms | 87.590 ms | 89.727 ms | `ix_chunks_article_id` |

Semantic and hybrid retrieval use the native vector index for the benchmark
workload. Linked search remains relational-first because its graph constraint
creates a different candidate set and the measured alternative plan was not
faster.

The latest machine-readable strategy result is stored in:

```text
experiments/results/search_strategies.json
```


---

# VECTOR INDEX vs Brute Force

| Mode | Mean | P95 |
|---|---:|---:|
| MariaDB `VECTOR INDEX` | **1.302 ms** | 1.688 ms |
| Brute-force cosine search | 231.728 ms | 236.068 ms |

Measured speedup:

```text
177.92×
```

At approximately four thousand vectors, native MariaDB vector indexing is
already dramatically faster than evaluating cosine distance against the full
vector table.

Current benchmark artifact:

```text
experiments/results/index_vs_bruteforce_20261013T155049Z.json
```


---

# Scaling Observation

| Corpus | Vectors | Semantic Mean | VECTOR INDEX Speedup |
|---|---:|---:|---:|
| 100 articles | 1,426 | ~1.94 ms | ~47× |
| 285 articles | 3,940 | ~1.39 ms | ~178× |

As the corpus grew, indexed semantic latency increased only modestly while brute-force search became substantially more expensive.

---

# Retrieval Quality

The production retrieval evaluation uses 40 manually prepared conceptual and
paraphrased questions and exercises the same MariaDB vector-index path used by
semantic search.

| Metric | Result |
|---|---:|
| Recall@1 | **67.5%** |
| Recall@3 | **87.5%** |
| Recall@5 | **87.5%** |
| Recall@10 | **95.0%** |
| MRR | **0.784** |
| Misses@10 | **2 / 40** |

Ground truth is stored in:

```text
data/ground_truth/questions.jsonl
```

Current production-evaluation artifact:

```text
experiments/results/recall_20261013T155054Z.json
```


---

# Exact Article-Level Evaluation

MVF also implements an exhaustive article-level reference evaluation. Each
article receives the distance of its closest chunk:

```sql
MIN(
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(:embedding)
    )
)
```

The exact reference produces:

```text
Recall@1  = 67.5%
Recall@3  = 87.5%
Recall@5  = 87.5%
Recall@10 = 92.5%
MRR       = 0.782
Misses@10 = 3 / 40
```

The production vector-index path and the exhaustive article-level reference are
reported separately because they evaluate different retrieval paths and may
differ slightly around the cutoff. In the current run,
`Fine-tuning (deep learning)` is rank 10 in production retrieval and rank 11 in
the exhaustive article-level ranking.

Current exact-evaluation artifact:

```text
experiments/results/article_recall_20261013T155110Z.json
```


---

# Incremental Vector Indexing

The vector-indexing pipeline is incremental and self-healing.

Possible outcomes include:

```text
INDEXED
REBUILT
SKIPPED
EMPTY
CLEARED
```

After expanding the corpus from 100 to 285 articles:

```text
Articles scanned:  285
Indexed now:       185
Rebuilt:           0
Already valid:     100
Empty articles:    0
Stale cleared:     0
Chunks written:    2514
```

Immediately running the indexing pipeline again produced:

```text
Articles scanned:  285
Indexed now:       0
Rebuilt:           0
Already valid:     285
Empty articles:    0
Stale cleared:     0
Chunks written:    0
```

---

# Repository Structure

```text
mvf-databases-cu/
├── .github/
│   └── workflows/
│       └── ci.yml
├── backend/
│   └── app/
│       ├── api/
│       │   ├── routes/
│       │   ├── dependencies.py
│       │   ├── router.py
│       │   └── schemas.py
│       ├── clients/
│       ├── core/
│       ├── db/
│       │   ├── models/
│       │   ├── queries/
│       │   ├── repositories/
│       │   └── maintenance.py
│       ├── generators/
│       ├── services/
│       └── main.py
├── data/
│   ├── ground_truth/
│   ├── processed/
│   └── raw/
├── database/
│   └── schema/
│       ├── 001_schema.sql
│       └── 002_vector_index.sql
├── docs/
│   └── API.md
├── experiments/
│   ├── results/
│   ├── article_recall.py
│   ├── diagnose_misses.py
│   ├── explain.py
│   ├── index_vs_bruteforce.py
│   ├── latency.py
│   ├── linked_optimizer_probe.py
│   ├── optimizer_probe.py
│   ├── recall.py
│   └── search_strategies.py
├── scripts/
├── tests/
│   ├── integration/
│   └── unit/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Makefile
├── pyproject.toml
└── README.md
```

---

# Local Setup

## 1. Clone

```bash
git clone <repository-url>
cd mvf-databases-cu
```

## 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Install

```bash
make install-dev
```

Equivalent:

```bash
python3 -m pip install -e ".[dev]"
```

## 4. Configure environment

```bash
cp .env.example .env
```

Update the database password and optional OpenAI configuration if required.

## 5. Start MariaDB

```bash
make db-up
```

## 6. Apply schema

```bash
make db-init
```

## 7. Verify MariaDB

```bash
make db-verify
```

Expected output includes:

```text
MariaDB version: 11.8.x
Tables: articles, article_categories, article_links, categories, chunks
Chunk embedding type: vector(384)
```

---

# Build the Corpus

```bash
make ingest
```

Equivalent:

```bash
python3 -m scripts.ingest \
  --category "Machine learning" \
  --limit 300 \
  --concurrency 5
```

MediaWiki may return fewer pages than the requested maximum. The current ingestion produced 285 stored articles.

---

# Build Vector Embeddings

```bash
make index
```

Force a complete rebuild:

```bash
make index-force
```

---

# Run the API

```bash
make api
```

Equivalent:

```bash
uvicorn backend.app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
```

API:

```text
http://localhost:8000
```

Interactive OpenAPI documentation:

```text
http://localhost:8000/docs
```

Health endpoint:

```text
GET http://localhost:8000/health
```

For the exact frontend-facing contract, see [`docs/API.md`](docs/API.md).

---

# Experiments

Main benchmark:

```bash
make benchmark
```

Retrieval quality:

```bash
make recall
```

Exact article-level retrieval:

```bash
make article-recall
```

Difficult-query diagnostics:

```bash
python3 -m experiments.diagnose_misses
```

Experiment results are written under:

```text
experiments/results/
```

---

# Code Quality

Run all checks:

```bash
make quality
```

The quality gate runs:

```bash
ruff check backend scripts tests experiments
ruff format --check backend scripts tests experiments
mypy backend scripts experiments tests
pytest -v
```

The current local quality gate is green: Ruff passes, mypy passes, and **27 / 27 automated tests** pass. The suite covers API integration, semantic/hybrid/linked retrieval, RAG behavior, chunking, and embedding behavior.

---

# Useful Make Commands

```text
make install-dev     Install project and development dependencies
make db-up           Start MariaDB
make db-down         Stop MariaDB
make db-reset        Recreate the MariaDB Docker volume
make db-init         Apply schema and vector index
make db-verify       Verify MariaDB setup
make ingest          Ingest Wikipedia corpus
make index           Incrementally build embeddings
make index-force     Force vector rebuild
make api             Run FastAPI
make test            Run pytest
make lint            Run Ruff
make format          Format source files
make typecheck       Run mypy
make quality         Run complete quality gate
make benchmark       Run main search benchmarks
make recall          Run retrieval evaluation
make article-recall  Run exact article-level evaluation
make clean           Remove local Python caches
```

---

# Reproducibility

Important retrieval parameters are fixed and documented:

```text
MariaDB version
embedding model
embedding dimensionality
chunk size
chunk overlap
vector distance metric
vector-index configuration
corpus size
benchmark warm-ups
benchmark runs
ground-truth questions
```

Raw Wikipedia snapshots are preserved separately from vector generation, and experiment outputs are stored as machine-readable JSON.

---

# Current Limitations

The corpus is focused on machine-learning-related Wikipedia articles rather than general web search.

The lightweight `all-MiniLM-L6-v2` embedding model does not produce perfect ranking for every semantic query. Current production Recall@10 is **95.0%**; the exhaustive article-level reference reaches **92.5%** at the same cutoff.

Hybrid search now uses the native vector index efficiently for the benchmark category. Linked graph-constrained search remains relational-first because controlled optimizer experiments showed that this is the cheaper plan for that candidate set.

These behaviors are measured and documented rather than hidden because optimizer behavior and retrieval trade-offs are central to the project.

---

# Future Work

Potential extensions include:

- larger corpus experiments
- additional embedding-model comparisons
- lexical + vector fusion
- reranking
- query expansion
- deeper graph traversal
- larger human-reviewed ground truth
- frontend visualization of SQL, timings, and `EXPLAIN`
- generation-latency instrumentation
- complete application containerization

---

# Project Status

The backend currently provides:

```text
Wikipedia ingestion
incremental vector indexing
semantic search
hybrid search
linked search
RAG
catalog APIs
MariaDB EXPLAIN diagnostics
latency benchmarking
index-vs-brute-force benchmarking
retrieval evaluation
exact article-level evaluation
integration and unit tests
```

The MariaDB retrieval layer has been validated with query-plan inspection, optimizer-statistics refresh, performance benchmarking, retrieval evaluation, and automated regression tests. The next stage is frontend integration and final end-to-end application validation.
