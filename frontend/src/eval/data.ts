import { VECTOR_INDEX } from '../api'

// Only fields the page uses are parsed; a file with another shape is reported, never patched up.

export type ResultKey =
  | 'recall'
  | 'article_recall'
  | 'index_vs_bruteforce'
  | 'search_strategies'
  | 'm_ground_truth'
  | 'm_sweep'

// The M experiments have no make target.
export const RUN_COMMAND: Record<ResultKey, string> = {
  recall: 'make recall',
  article_recall: 'make article-recall',
  index_vs_bruteforce: 'make benchmark',
  search_strategies: 'make benchmark',
  m_ground_truth: 'python3 -m experiments.vector_index_m_ground_truth',
  m_sweep: 'python3 -m experiments.vector_index_m_sweep',
}

export interface RecallResult {
  evaluatedAt: string
  questions: number
  maxK: number
  candidateLimit: number | null
  corpusArticles: number
  corpusVectors: number
  recallAt: { k: number; value: number }[]
  mrr: number
  misses: number
  // null: not in the top max_k
  evaluations: { id: string; question: string; rank: number | null; relevant: string[] }[]
}

interface LatencySummary {
  p50: number
  p95: number
  mean: number
}

export interface IndexVsBruteForce {
  executedAt: string
  query: string
  limit: number
  runs: number
  warmups: number
  vectors: number
  indexed: LatencySummary
  bruteForce: LatencySummary
  speedup: number
}

interface StrategyResult {
  latency: LatencySummary
  indexUsed: boolean
  plan: { table: string; key: string | null; rows: number | null }[]
}

export interface SearchStrategies {
  query: string
  limit: number
  runs: number
  warmups: number
  hybridCategory: string
  linkedSourceTitle: string
  articles: number
  vectors: number
  semantic: StrategyResult
  hybrid: StrategyResult
  linked: StrategyResult
}

export interface MGroundTruth {
  evaluatedAt: string
  questions: number
  articles: number
  vectors: number
  candidateLimit: number | null
  productionM: number | null
  rows: {
    m: number
    buildMs: number
    latency: LatencySummary
    recallAt: { k: number; value: number }[]
    mrr: number
  }[]
}

export interface MSweep {
  query: string
  limit: number
  runs: number
  warmups: number
  rows: { m: number; buildMs: number; latency: LatencySummary; overlap: number }[]
}

export interface Dataset {
  source: string
  mariadbVersion: string | null
  embeddingModel: string | null
  embeddingDimensions: number | null
}

export interface IndexConfig {
  m: number | null
  distance: string | null
  source: string
}

export type Loaded<T> =
  | { status: 'ok'; data: T; source: string }
  | { status: 'missing' }
  | { status: 'invalid'; source: string; reason: string }

export interface EvalData {
  syncedAt: string
  indexConfig: IndexConfig | null
  recall: Loaded<RecallResult>
  articleRecall: Loaded<RecallResult>
  indexVsBruteForce: Loaded<IndexVsBruteForce>
  searchStrategies: Loaded<SearchStrategies>
  mGroundTruth: Loaded<MGroundTruth>
  mSweep: Loaded<MSweep>
  dataset: Dataset | null
}

class ShapeError extends Error {}

type Obj = Record<string, unknown>

function obj(v: unknown, path: string): Obj {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) throw new ShapeError(`${path} is not an object`)
  return v as Obj
}

function num(o: Obj, key: string, path = key): number {
  const v = o[key]
  if (typeof v !== 'number' || !Number.isFinite(v)) throw new ShapeError(`${path} is not a number`)
  return v
}

function str(o: Obj, key: string, path = key): string {
  const v = o[key]
  if (typeof v !== 'string') throw new ShapeError(`${path} is not a string`)
  return v
}

function arr(o: Obj, key: string, path = key): unknown[] {
  const v = o[key]
  if (!Array.isArray(v)) throw new ShapeError(`${path} is not a list`)
  return v
}

function recallAtK(o: Obj, path: string): { k: number; value: number }[] {
  const recallAt = Object.keys(o)
    .map((key) => /^recall_at_(\d+)$/.exec(key))
    .filter((m) => m !== null)
    .map((m) => ({ k: Number(m[1]), value: num(o, m[0], `${path}${m[0]}`) }))
    .sort((a, b) => a.k - b.k)
  if (recallAt.length === 0) throw new ShapeError(`no ${path}recall_at_<k> values`)
  return recallAt
}

function parseRecall(raw: unknown): RecallResult {
  const o = obj(raw, 'file')
  const maxK = num(o, 'max_k')
  const recallAt = recallAtK(o, '')
  return {
    evaluatedAt: str(o, 'evaluated_at'),
    questions: num(o, 'questions'),
    maxK,
    candidateLimit: typeof o.candidate_limit === 'number' ? o.candidate_limit : null,
    corpusArticles: num(o, 'corpus_articles'),
    corpusVectors: num(o, 'corpus_vectors'),
    recallAt,
    mrr: num(o, 'mrr'),
    misses: num(o, 'misses_at_max_k'),
    evaluations: arr(o, 'evaluations').map((item, i) => {
      const e = obj(item, `evaluations[${i}]`)
      const rank = e.first_relevant_rank
      if (rank !== null && (typeof rank !== 'number' || !Number.isFinite(rank))) {
        throw new ShapeError(`evaluations[${i}].first_relevant_rank is not a number or null`)
      }
      return {
        id: str(e, 'question_id', `evaluations[${i}].question_id`),
        question: str(e, 'question', `evaluations[${i}].question`),
        rank,
        relevant: arr(e, 'relevant_titles', `evaluations[${i}].relevant_titles`).map(String),
      }
    }),
  }
}

// index_vs_bruteforce.py writes { p50, p95, mean, ... } in ms; search_strategies.py writes { p50_ms, p95_ms, mean_ms, ... }.
function latency(o: Obj, path: string, suffix: '' | '_ms'): LatencySummary {
  return {
    p50: num(o, `p50${suffix}`, `${path}.p50${suffix}`),
    p95: num(o, `p95${suffix}`, `${path}.p95${suffix}`),
    mean: num(o, `mean${suffix}`, `${path}.mean${suffix}`),
  }
}

function parseIndexVsBruteForce(raw: unknown): IndexVsBruteForce {
  const o = obj(raw, 'file')
  const summary = (key: string) => latency(obj(obj(o[key], key).summary_ms, `${key}.summary_ms`), `${key}.summary_ms`, '')
  return {
    executedAt: str(o, 'executed_at'),
    query: str(o, 'query'),
    limit: num(o, 'limit'),
    runs: num(o, 'runs'),
    warmups: num(o, 'warmup_runs'),
    vectors: num(o, 'vector_count'),
    indexed: summary('indexed'),
    bruteForce: summary('brute_force'),
    speedup: num(o, 'speedup'),
  }
}

function parseStrategy(raw: unknown, name: string): StrategyResult {
  const o = obj(raw, name)
  const plan = arr(o, 'execution_plan', `${name}.execution_plan`).map((item, i) => {
    const row = obj(item, `${name}.execution_plan[${i}]`)
    return {
      table: str(row, 'table', `${name}.execution_plan[${i}].table`),
      key: typeof row.key === 'string' ? row.key : null,
      rows: typeof row.rows === 'number' ? row.rows : null,
    }
  })
  return {
    latency: latency(obj(o.latency, `${name}.latency`), `${name}.latency`, '_ms'),
    indexUsed: plan.some((row) => row.key === VECTOR_INDEX),
    plan,
  }
}

function parseSearchStrategies(raw: unknown): SearchStrategies {
  const o = obj(raw, 'file')
  const dataset = obj(o.dataset, 'dataset')
  return {
    query: str(o, 'query'),
    limit: num(o, 'limit'),
    runs: num(o, 'runs'),
    warmups: num(o, 'warmups'),
    hybridCategory: str(o, 'hybrid_category'),
    linkedSourceTitle: str(o, 'linked_source_title'),
    articles: num(dataset, 'article_count', 'dataset.article_count'),
    vectors: num(dataset, 'vector_count', 'dataset.vector_count'),
    semantic: parseStrategy(o.semantic, 'semantic'),
    hybrid: parseStrategy(o.hybrid, 'hybrid'),
    linked: parseStrategy(o.linked, 'linked'),
  }
}

// Both M experiments rebuild the index once per M and write one result row per value.
function mRows(o: Obj): Obj[] {
  const rows = arr(o, 'results').map((item, i) => obj(item, `results[${i}]`))
  if (rows.length === 0) throw new ShapeError('results is empty')
  return rows
}

function parseMGroundTruth(raw: unknown): MGroundTruth {
  const o = obj(raw, 'file')
  const corpus = obj(o.corpus, 'corpus')
  const method = typeof o.retrieval_methodology === 'object' && o.retrieval_methodology !== null ? (o.retrieval_methodology as Obj) : {}
  const index = typeof o.vector_index === 'object' && o.vector_index !== null ? (o.vector_index as Obj) : {}
  return {
    evaluatedAt: str(o, 'evaluated_at'),
    questions: num(corpus, 'questions', 'corpus.questions'),
    articles: num(corpus, 'articles', 'corpus.articles'),
    vectors: num(corpus, 'vectors', 'corpus.vectors'),
    candidateLimit: typeof method.candidate_limit === 'number' ? method.candidate_limit : null,
    productionM: typeof index.production_m === 'number' ? index.production_m : null,
    rows: mRows(o).map((r, i) => {
      const path = `results[${i}].`
      return {
        m: num(r, 'm', `${path}m`),
        buildMs: num(r, 'build_time_ms', `${path}build_time_ms`),
        latency: {
          p50: num(r, 'median_query_ms', `${path}median_query_ms`),
          p95: num(r, 'p95_query_ms', `${path}p95_query_ms`),
          mean: num(r, 'mean_query_ms', `${path}mean_query_ms`),
        },
        recallAt: recallAtK(r, path),
        mrr: num(r, 'mrr', `${path}mrr`),
      }
    }),
  }
}

function parseMSweep(raw: unknown): MSweep {
  const o = obj(raw, 'file')
  const bench = obj(o.benchmark, 'benchmark')
  return {
    query: str(bench, 'query', 'benchmark.query'),
    limit: num(bench, 'limit', 'benchmark.limit'),
    runs: num(bench, 'measured_runs', 'benchmark.measured_runs'),
    warmups: num(bench, 'warmup_runs', 'benchmark.warmup_runs'),
    rows: mRows(o).map((r, i) => {
      const path = `results[${i}].`
      return {
        m: num(r, 'm', `${path}m`),
        buildMs: num(r, 'build_time_ms', `${path}build_time_ms`),
        latency: {
          p50: num(r, 'median_ms', `${path}median_ms`),
          p95: num(r, 'p95_ms', `${path}p95_ms`),
          mean: num(r, 'mean_ms', `${path}mean_ms`),
        },
        overlap: num(r, 'exact_overlap_at_k', `${path}exact_overlap_at_k`),
      }
    }),
  }
}

const base = `${import.meta.env.BASE_URL}eval/`

// A 404 or a non-JSON body (the dev server answers unknown paths with index.html) gives null.
async function fetchJson(file: string): Promise<unknown> {
  const res = await fetch(base + file, { cache: 'no-cache' })
  if (!res.ok) return null
  try {
    return await res.json()
  } catch {
    return null
  }
}

interface ManifestEntry {
  source: string
  file: string
}

async function loadResult<T>(entry: unknown, parse: (raw: unknown) => T): Promise<Loaded<T>> {
  if (typeof entry !== 'object' || entry === null) return { status: 'missing' }
  const { source, file } = entry as ManifestEntry
  if (typeof source !== 'string' || typeof file !== 'string') return { status: 'missing' }
  const raw = await fetchJson(file)
  if (raw === null) return { status: 'invalid', source, reason: 'file could not be read as JSON' }
  try {
    return { status: 'ok', data: parse(raw), source }
  } catch (err) {
    if (err instanceof ShapeError) return { status: 'invalid', source, reason: err.message }
    throw err
  }
}

function parseIndexConfig(raw: unknown): IndexConfig | null {
  if (typeof raw !== 'object' || raw === null) return null
  const o = raw as Obj
  if (typeof o.source !== 'string') return null
  return {
    m: typeof o.m === 'number' ? o.m : null,
    distance: typeof o.distance === 'string' ? o.distance : null,
    source: o.source,
  }
}

async function loadDataset(entry: unknown): Promise<Dataset | null> {
  if (typeof entry !== 'object' || entry === null) return null
  const { source, file } = entry as ManifestEntry
  if (typeof source !== 'string' || typeof file !== 'string') return null
  const raw = await fetchJson(file)
  if (typeof raw !== 'object' || raw === null) return null
  const o = raw as Obj
  return {
    source,
    mariadbVersion: typeof o.mariadb_version === 'string' ? o.mariadb_version : null,
    embeddingModel: typeof o.embedding_model === 'string' ? o.embedding_model : null,
    embeddingDimensions: typeof o.embedding_dimensions === 'number' ? o.embedding_dimensions : null,
  }
}

export async function loadEvalData(): Promise<EvalData | null> {
  const manifest = await fetchJson('manifest.json')
  if (typeof manifest !== 'object' || manifest === null) return null
  const m = manifest as Obj
  const files = typeof m.files === 'object' && m.files !== null ? (m.files as Obj) : {}
  const [recall, articleRecall, indexVsBruteForce, searchStrategies, mGroundTruth, mSweep, dataset] = await Promise.all([
    loadResult(files.recall, parseRecall),
    loadResult(files.article_recall, parseRecall),
    loadResult(files.index_vs_bruteforce, parseIndexVsBruteForce),
    loadResult(files.search_strategies, parseSearchStrategies),
    loadResult(files.m_ground_truth, parseMGroundTruth),
    loadResult(files.m_sweep, parseMSweep),
    loadDataset(m.dataset),
  ])
  return {
    syncedAt: typeof m.synced_at === 'string' ? m.synced_at : '',
    indexConfig: parseIndexConfig(m.index_config),
    recall,
    articleRecall,
    indexVsBruteForce,
    searchStrategies,
    mGroundTruth,
    mSweep,
    dataset,
  }
}
