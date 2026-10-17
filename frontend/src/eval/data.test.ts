import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadEvalData } from './data'
import type { EvalData, Loaded } from './data'

// Trimmed copies of the files the experiments write, in the same shape.
const recall = () => ({
  evaluated_at: '2026-10-13T15:50:54+00:00',
  questions: 2,
  max_k: 10,
  candidate_limit: 200,
  corpus_articles: 285,
  corpus_vectors: 3940,
  recall_at_10: 1,
  recall_at_1: 0.5,
  mrr: 0.75,
  misses_at_max_k: 0,
  evaluations: [
    { question_id: 'q1', question: 'What is overfitting?', first_relevant_rank: 1, relevant_titles: ['Overfitting'] },
    { question_id: 'q2', question: 'What is a GAN?', first_relevant_rank: null, relevant_titles: ['Generative adversarial network'] },
  ],
})

const indexVsBruteForce = () => ({
  executed_at: '2026-10-13T15:50:49+00:00',
  query: 'neural network training',
  limit: 5,
  runs: 50,
  warmup_runs: 5,
  vector_count: 3940,
  indexed: { summary_ms: { p50: 1.2, p95: 1.7, mean: 1.3 } },
  brute_force: { summary_ms: { p50: 231, p95: 236, mean: 231.7 } },
  speedup: 177.9,
})

const strategy = (key: string | null, p50: number) => ({
  latency: { p50_ms: p50, p95_ms: p50 * 1.3, mean_ms: p50 * 1.05 },
  execution_plan: [
    { table: '<derived2>', key: null, rows: 5 },
    { table: 'chunks', key, rows: 3185 },
  ],
})

const searchStrategies = () => ({
  query: 'neural network training',
  limit: 5,
  warmups: 5,
  runs: 50,
  hybrid_category: 'Machine learning',
  linked_source_title: 'Machine learning',
  dataset: { article_count: 285, vector_count: 3940 },
  semantic: strategy('ix_chunks_embedding', 1.4),
  hybrid: strategy('ix_chunks_embedding', 2.2),
  linked: strategy('ix_chunks_article_id', 85.6),
})

const mGroundTruth = () => ({
  evaluated_at: '2026-10-14T12:36:45+00:00',
  corpus: { articles: 285, vectors: 3940, questions: 40 },
  retrieval_methodology: { candidate_limit: 200 },
  vector_index: { production_m: 8 },
  results: [4, 8].map((m) => ({
    m,
    build_time_ms: m * 40,
    mean_query_ms: 15.5,
    median_query_ms: 15,
    p95_query_ms: 17,
    recall_at_1: 0.675,
    recall_at_10: 0.925,
    mrr: 0.782,
  })),
})

const mSweep = () => ({
  benchmark: { query: 'neural network training', limit: 5, warmup_runs: 5, measured_runs: 50 },
  results: [
    { m: 4, build_time_ms: 180, mean_ms: 1.16, median_ms: 1.08, p95_ms: 1.54, exact_overlap_at_k: 0.8 },
    { m: 32, build_time_ms: 3728, mean_ms: 1.18, median_ms: 1.12, p95_ms: 1.45, exact_overlap_at_k: 0.4 },
  ],
})

const RESULT_KEYS = ['recall', 'article_recall', 'index_vs_bruteforce', 'search_strategies', 'm_ground_truth', 'm_sweep']

function validFiles(): Record<string, unknown> {
  return {
    'manifest.json': {
      synced_at: '2026-10-14T16:00:00Z',
      files: Object.fromEntries(RESULT_KEYS.map((k) => [k, { source: `experiments/results/${k}_x.json`, file: `${k}.json` }])),
      index_config: { m: 8, distance: 'cosine', source: 'database/schema/002_vector_index.sql' },
      dataset: { source: 'data/manifest.json', file: 'dataset.json' },
    },
    'recall.json': recall(),
    'article_recall.json': recall(),
    'index_vs_bruteforce.json': indexVsBruteForce(),
    'search_strategies.json': searchStrategies(),
    'm_ground_truth.json': mGroundTruth(),
    'm_sweep.json': mSweep(),
    'dataset.json': {
      mariadb_version: '11.8.9-MariaDB-ubu2404',
      embedding_model: 'sentence-transformers/all-MiniLM-L6-v2',
      embedding_dimensions: 384,
    },
  }
}

// Serves eval/<name> from the map; a string is sent as a raw body, a missing name is a 404.
function serve(files: Record<string, unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const name = url.split('/eval/')[1]
      if (!(name in files)) return new Response('Not found', { status: 404 })
      const body = files[name]
      return new Response(typeof body === 'string' ? body : JSON.stringify(body), { status: 200 })
    }),
  )
}

function ok<T>(result: Loaded<T>): T {
  if (result.status !== 'ok') throw new Error(`expected ok, got ${JSON.stringify(result)}`)
  return result.data
}

async function load(files: Record<string, unknown>): Promise<EvalData> {
  serve(files)
  const data = await loadEvalData()
  if (!data) throw new Error('no manifest')
  return data
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('loadEvalData with valid result files', () => {
  it('parses recall, sorting recall_at_<k> by k and keeping misses as null ranks', async () => {
    const r = ok((await load(validFiles())).recall)
    expect(r.recallAt).toEqual([
      { k: 1, value: 0.5 },
      { k: 10, value: 1 },
    ])
    expect(r.candidateLimit).toBe(200)
    expect(r.evaluations.map((e) => e.rank)).toEqual([1, null])
  })

  it('parses both latency formats and derives index use from the EXPLAIN plan', async () => {
    const data = await load(validFiles())
    expect(ok(data.indexVsBruteForce).bruteForce).toEqual({ p50: 231, p95: 236, mean: 231.7 })
    const s = ok(data.searchStrategies)
    expect(s.semantic.latency.p50).toBe(1.4)
    expect(s.hybrid.indexUsed).toBe(true)
    expect(s.linked.indexUsed).toBe(false)
  })

  it('parses the vector index M study, sweep and dataset metadata', async () => {
    const data = await load(validFiles())
    const gt = ok(data.mGroundTruth)
    expect(gt.productionM).toBe(8)
    expect(gt.rows.map((r) => [r.m, r.buildMs, r.latency.p50])).toEqual([
      [4, 160, 15],
      [8, 320, 15],
    ])
    expect(gt.rows[0].recallAt.at(-1)).toEqual({ k: 10, value: 0.925 })
    expect(ok(data.mSweep).rows.map((r) => r.overlap)).toEqual([0.8, 0.4])
    expect(data.dataset).toEqual({
      source: 'data/manifest.json',
      mariadbVersion: '11.8.9-MariaDB-ubu2404',
      embeddingModel: 'sentence-transformers/all-MiniLM-L6-v2',
      embeddingDimensions: 384,
    })
    expect(data.indexConfig).toEqual({ m: 8, distance: 'cosine', source: 'database/schema/002_vector_index.sql' })
  })

  it('reports a result absent from the manifest as missing, not invalid', async () => {
    const files = validFiles()
    ;(files['manifest.json'] as { files: Record<string, unknown> }).files.m_sweep = null
    expect((await load(files)).mSweep).toEqual({ status: 'missing' })
  })

  it('returns null when nothing has been synced', async () => {
    serve({})
    expect(await loadEvalData()).toBeNull()
  })
})

describe('loadEvalData rejects malformed files and names the field', () => {
  const cases: { name: string; key: keyof EvalData; file: string; body: () => unknown; reason: string }[] = [
    {
      name: 'missing evaluation field',
      key: 'recall',
      file: 'recall.json',
      body: () => {
        const r = recall()
        delete (r.evaluations[1] as Partial<(typeof r.evaluations)[number]>).question_id
        return r
      },
      reason: 'evaluations[1].question_id is not a string',
    },
    {
      name: 'wrong type for a top-level number',
      key: 'recall',
      file: 'recall.json',
      body: () => ({ ...recall(), mrr: '0.75' }),
      reason: 'mrr is not a number',
    },
    {
      name: 'no recall_at_<k> keys',
      key: 'articleRecall',
      file: 'article_recall.json',
      body: () => {
        const r: Partial<ReturnType<typeof recall>> = recall()
        delete r.recall_at_1
        delete r.recall_at_10
        return r
      },
      reason: 'no recall_at_<k> values',
    },
    {
      name: 'missing nested latency summary',
      key: 'indexVsBruteForce',
      file: 'index_vs_bruteforce.json',
      body: () => ({ ...indexVsBruteForce(), brute_force: {} }),
      reason: 'brute_force.summary_ms is not an object',
    },
    {
      name: 'missing strategy latency',
      key: 'searchStrategies',
      file: 'search_strategies.json',
      body: () => ({ ...searchStrategies(), hybrid: { execution_plan: [] } }),
      reason: 'hybrid.latency is not an object',
    },
    {
      name: 'wrong type inside an M result row',
      key: 'mGroundTruth',
      file: 'm_ground_truth.json',
      body: () => {
        const g = mGroundTruth()
        ;(g.results[1] as Record<string, unknown>).build_time_ms = 'slow'
        return g
      },
      reason: 'results[1].build_time_ms is not a number',
    },
    {
      name: 'empty M sweep',
      key: 'mSweep',
      file: 'm_sweep.json',
      body: () => ({ ...mSweep(), results: [] }),
      reason: 'results is empty',
    },
    {
      name: 'file that is not JSON',
      key: 'mSweep',
      file: 'm_sweep.json',
      body: () => '<!doctype html>',
      reason: 'file could not be read as JSON',
    },
  ]

  it.each(cases)('$name', async ({ key, file, body, reason }) => {
    const data = await load({ ...validFiles(), [file]: body() })
    expect(data[key]).toEqual({ status: 'invalid', source: `experiments/results/${file.replace('.json', '')}_x.json`, reason })
    // One bad file doesn't take the others down.
    expect(data.mGroundTruth.status === 'ok' || key === 'mGroundTruth').toBe(true)
  })
})
