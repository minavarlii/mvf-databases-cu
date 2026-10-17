import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { ChartCard } from '../components/charts/ChartCard'
import { ColumnChart } from '../components/charts/ColumnChart'
import type { LegendItem } from '../components/charts/ChartCard'
import type { Column } from '../components/charts/ColumnChart'
import { LatencyChart } from '../components/charts/LatencyChart'
import { formatMs } from '../components/charts/scale'
import { ChartIcon, ClockIcon, CompareIcon, DatabaseIcon, SearchIcon, ServerIcon, SlidersIcon, WarningIcon } from '../components/icons'
import { LoadingCard } from '../components/LoadingCard'
import { Placeholder } from '../components/Placeholder'
import { StatusMessage } from '../components/StatusMessage'
import { paletteTone } from '../components/tones'
import { loadEvalData, RUN_COMMAND } from '../eval/data'
import type {
  EvalData,
  IndexConfig,
  IndexVsBruteForce,
  Loaded,
  MGroundTruth,
  MSweep,
  RecallResult,
  ResultKey,
  SearchStrategies,
} from '../eval/data'

type Load = { status: 'loading' } | { status: 'ok'; data: EvalData } | { status: 'no-manifest' } | { status: 'error'; message: string }

let request: Promise<EvalData | null> | null = null

const pct = (v: number) => `${(v * 100).toFixed(1).replace(/\.0$/, '')}%`
const count = (n: number) => n.toLocaleString('en-US')
const plural = (n: number, word: string) => `${count(n)} ${word}${n === 1 ? '' : 's'}`
const times = (v: number) => `${v >= 10 ? v.toFixed(0) : v.toFixed(1)}×`
const when = (iso: string) => {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? iso
    : `${d.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' })} UTC`
}
// For files that only carry their run time in the name (..._20261014T122949Z.json).
const stampOf = (source: string) => {
  const m = /(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z\.json$/.exec(source)
  return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z` : null
}
const list = (items: string[]) =>
  items.length <= 1 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`

function Missing({ result, file }: { result: Loaded<unknown>; file: ResultKey }) {
  const sync = <code className="mono">npm run sync-eval</code>
  if (result.status === 'invalid') {
    return (
      <Placeholder icon={<WarningIcon size={24} />} title="This result file couldn’t be read">
        <span className="mono">{result.source}</span>: {result.reason}. Run{' '}
        <code className="mono">{RUN_COMMAND[file]}</code> to write a fresh one, then {sync}.
      </Placeholder>
    )
  }
  return (
    <Placeholder icon={<ChartIcon size={24} />} title={`Run ${RUN_COMMAND[file]} to generate this`}>
      No <span className="mono">{file}</span> result in <span className="mono">experiments/results/</span> yet. Run{' '}
      <code className="mono">{RUN_COMMAND[file]}</code> from the repo root (needs MariaDB and the index), then {sync}{' '}
      in <span className="mono">frontend/</span>.
    </Placeholder>
  )
}

function RecallCard({ recall, oracle }: { recall: Loaded<RecallResult>; oracle: Loaded<RecallResult> }) {
  const legend: LegendItem[] = [{ kind: 'bar', label: 'Chunk search (make recall)' }]
  if (recall.status !== 'ok') {
    return (
      <ChartCard title="Recall@k" icon={<SearchIcon size={17} />} tone={`tone-${paletteTone(0)}`}>
        <Missing result={recall} file="recall" />
      </ChartCard>
    )
  }
  const r = recall.data
  const oracleAt = new Map(oracle.status === 'ok' ? oracle.data.recallAt.map((p) => [p.k, p.value]) : [])
  const hasOracle = oracleAt.size > 0
  if (hasOracle) legend.push({ kind: 'marker', label: 'Exact article oracle (make article-recall)' })

  const columns: Column[] = r.recallAt.map((p) => {
    const o = oracleAt.get(p.k)
    return {
      label: `k = ${p.k}`,
      value: p.value,
      valueLabel: pct(p.value),
      marker: o ?? null,
      tooltip: `Recall@${p.k}: ${pct(p.value)}${o === undefined ? '' : ` (exact oracle ${pct(o)})`}`,
    }
  })

  const first = r.recallAt[0]
  const last = r.recallAt[r.recallAt.length - 1]
  const flat = r.recallAt.filter((p, i) => i > 0 && p.value === r.recallAt[i - 1].value)
  const differs = r.recallAt.filter((p) => oracleAt.has(p.k) && oracleAt.get(p.k) !== p.value)

  const caption: ReactNode = (
    <>
      Share of the {r.questions} test questions whose right Wikipedia article is among the first k results.{' '}
      {pct(first.value)} get it at k = {first.k}, rising to {pct(last.value)} at k = {last.k}
      {flat.length > 0 &&
        `; going from k = ${r.recallAt[r.recallAt.indexOf(flat[0]) - 1].k} to k = ${flat[0].k} adds nothing`}
      .{' '}
      {hasOracle &&
        (differs.length === 0
          ? 'The exact article-level oracle (dashes) lands on the same value at every k, so the misses come from the embedding ranking itself, not from how chunk results are grouped into articles.'
          : `The exact article-level oracle (dashes) differs at k = ${differs.map((p) => p.k).join(', ')}, so the chunk search's candidate pool is losing some articles there.`)}
      {!hasOracle && (
        <>
          Run <code className="mono">make article-recall</code> to compare with the exact article-level oracle.
        </>
      )}
    </>
  )

  return (
    <ChartCard
      title="Recall@k"
      icon={<SearchIcon size={17} />}
      tone={`tone-${paletteTone(0)}`}
      legend={legend}
      caption={caption}
      source={[recall.source, oracle.status === 'ok' ? oracle.source : null].filter(Boolean).join(' · ')}
      table={{
        head: ['k', 'Chunk search', ...(hasOracle ? ['Exact oracle'] : [])],
        rows: r.recallAt.map((p) => [
          `Recall@${p.k}`,
          pct(p.value),
          ...(hasOracle ? [oracleAt.has(p.k) ? pct(oracleAt.get(p.k)!) : '—'] : []),
        ]),
      }}
    >
      <ColumnChart
        title="Recall at k"
        description={r.recallAt.map((p) => `Recall@${p.k} ${pct(p.value)}`).join(', ')}
        columns={columns}
        yMax={1}
        yTicks={[0, 0.25, 0.5, 0.75, 1]}
        formatTick={(v) => `${v * 100}%`}
        yLabel="Questions answered (%)"
        xLabel="k = results looked at"
      />
    </ChartCard>
  )
}

function RankCard({ recall }: { recall: Loaded<RecallResult> }) {
  if (recall.status !== 'ok') {
    return (
      <ChartCard title="Rank of the right article and MRR" icon={<ChartIcon size={17} />} tone={`tone-${paletteTone(4)}`}>
        <Missing result={recall} file="recall" />
      </ChartCard>
    )
  }
  const r = recall.data
  const byRank = Array.from({ length: r.maxK }, (_, i) => r.evaluations.filter((e) => e.rank === i + 1).length)
  const missed = r.evaluations.filter((e) => e.rank === null)
  const atOne = byRank[0]
  const lower = byRank.slice(1).reduce((a, b) => a + b, 0)

  const columns: Column[] = [
    ...byRank.map((n, i) => ({
      label: String(i + 1),
      value: n,
      valueLabel: n ? String(n) : '',
      tooltip: `Rank ${i + 1}: ${plural(n, 'question')}`,
    })),
    {
      label: 'Miss',
      value: missed.length,
      valueLabel: String(missed.length),
      muted: true,
      tooltip: `Not in the top ${r.maxK}: ${plural(missed.length, 'question')}`,
    },
  ]

  return (
    <ChartCard
      title="Rank of the right article and MRR"
      icon={<ChartIcon size={17} />}
      tone={`tone-${paletteTone(4)}`}
      legend={[
        { kind: 'bar', label: 'Questions' },
        { kind: 'muted', label: `Not in top ${r.maxK}` },
      ]}
      caption={
        <>
          Where the right article first appears for each question. {atOne} of {r.questions} are found at rank 1,{' '}
          {lower} further down the top {r.maxK} and {missed.length} not at all. MRR is the average of 1 / rank (0 for a
          miss): {r.mrr.toFixed(3)}, of which the rank-1 hits alone contribute {(atOne / r.questions).toFixed(3)}, so
          moving near-misses up to rank 1 is what would raise it.
        </>
      }
      source={recall.source}
      table={{
        head: ['Rank', 'Questions'],
        rows: [...byRank.map((n, i) => [String(i + 1), n]), [`Not in top ${r.maxK}`, missed.length], ['MRR', r.mrr.toFixed(3)]],
      }}
    >
      <ColumnChart
        title="Rank of the first relevant article"
        description={`${atOne} at rank 1, ${lower} at ranks 2 to ${r.maxK}, ${missed.length} missed. MRR ${r.mrr.toFixed(3)}.`}
        columns={columns}
        yMax={Math.max(...columns.map((c) => c.value))}
        formatTick={(v) => String(v)}
        yLabel="Questions"
        xLabel="Rank of the first relevant article"
      />
      {missed.length > 0 && (
        <details className="eval-misses">
          <summary>
            The {plural(missed.length, 'question')} not found in the top {r.maxK}
          </summary>
          <ul>
            {missed.map((e) => (
              <li key={e.id}>
                <span>{e.question}</span>
                <span className="eval-misses-want">Expected: {e.relevant.join(', ')}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </ChartCard>
  )
}

function IndexCard({ result, max }: { result: Loaded<IndexVsBruteForce>; max: number | undefined }) {
  const title = 'Vector index vs brute force'
  if (result.status !== 'ok') {
    return (
      <ChartCard title={title} icon={<CompareIcon size={17} />} tone={`tone-${paletteTone(1)}`}>
        <Missing result={result} file="index_vs_bruteforce" />
      </ChartCard>
    )
  }
  const d = result.data
  const steady = d.indexed.p95 / d.indexed.p50 < 1.5 && d.bruteForce.p95 / d.bruteForce.p50 < 1.5
  return (
    <ChartCard
      title={title}
      icon={<CompareIcon size={17} />}
      tone={`tone-${paletteTone(1)}`}
      legend={[
        { kind: 'bar', label: 'Median (p50)' },
        { kind: 'whisker', label: 'p95' },
      ]}
      caption={
        <>
          The same vector query, once using the vector index and once with the index set to IGNORED so MariaDB computes
          the cosine distance for all {count(d.vectors)} vectors. Median {formatMs(d.indexed.p50)} ms against{' '}
          {formatMs(d.bruteForce.p50)} ms: the index is {times(d.speedup)} faster on the mean
          {steady && ', and p95 stays close to the median for both, so the gap holds on every run, not just on average'}.
          One query, {d.runs} runs after {d.warmups} warm-ups, database time only (the question is embedded before
          timing).
        </>
      }
      source={result.source}
      table={{
        head: ['Mode', 'p50 (ms)', 'p95 (ms)', 'Mean (ms)'],
        rows: [
          ['Vector index', formatMs(d.indexed.p50), formatMs(d.indexed.p95), formatMs(d.indexed.mean)],
          ['Brute force', formatMs(d.bruteForce.p50), formatMs(d.bruteForce.p95), formatMs(d.bruteForce.mean)],
        ],
      }}
    >
      <LatencyChart
        title="Vector search latency with and without the vector index"
        description={`Vector index p50 ${formatMs(d.indexed.p50)} ms, p95 ${formatMs(d.indexed.p95)} ms. Brute force p50 ${formatMs(d.bruteForce.p50)} ms, p95 ${formatMs(d.bruteForce.p95)} ms.`}
        rows={[
          { label: 'Vector index', p50: d.indexed.p50, p95: d.indexed.p95 },
          { label: 'Brute force', p50: d.bruteForce.p50, p95: d.bruteForce.p95, note: 'index IGNORED' },
        ]}
        max={max}
        xLabel="Milliseconds per query (lower is better)"
      />
    </ChartCard>
  )
}

function StrategiesCard({ result, max }: { result: Loaded<SearchStrategies>; max: number | undefined }) {
  const title = 'Semantic, hybrid and linked search'
  if (result.status !== 'ok') {
    return (
      <ChartCard title={title} icon={<ClockIcon size={17} />} tone={`tone-${paletteTone(3)}`}>
        <Missing result={result} file="search_strategies" />
      </ChartCard>
    )
  }
  const d = result.data
  const indexNote = (used: boolean) => (used ? 'uses vector index' : 'no vector index')
  const slower = (['hybrid', 'linked'] as const).filter((k) => !d[k].indexUsed)
  const ratio = (k: 'hybrid' | 'linked') => times(d[k].latency.p50 / d.semantic.latency.p50)
  return (
    <ChartCard
      title={title}
      icon={<ClockIcon size={17} />}
      tone={`tone-${paletteTone(3)}`}
      legend={[
        { kind: 'bar', label: 'Median (p50)' },
        { kind: 'whisker', label: 'p95' },
      ]}
      caption={
        <>
          Semantic is plain vector search. Hybrid adds a category filter (“{d.hybridCategory}”) and linked keeps only
          articles linked from “{d.linkedSourceTitle}”. Hybrid takes {ratio('hybrid')} and linked {ratio('linked')}{' '}
          as long as semantic at the median.{' '}
          {slower.length > 0 &&
            `In EXPLAIN, ${slower.join(' and ')} ${slower.length === 1 ? 'starts' : 'start'} from the relational tables and reads chunks per article without the vector index, which is where the extra time goes.`}{' '}
          Same query and settings as the index benchmark ({d.runs} runs, {d.warmups} warm-ups).
        </>
      }
      source={result.source}
      table={{
        head: ['Strategy', 'p50 (ms)', 'p95 (ms)', 'Mean (ms)', 'Vector index'],
        rows: (['semantic', 'hybrid', 'linked'] as const).map((k) => [
          k[0].toUpperCase() + k.slice(1),
          formatMs(d[k].latency.p50),
          formatMs(d[k].latency.p95),
          formatMs(d[k].latency.mean),
          d[k].indexUsed ? 'used' : 'not used',
        ]),
      }}
    >
      <LatencyChart
        title="Latency by search strategy"
        description={(['semantic', 'hybrid', 'linked'] as const)
          .map((k) => `${k} p50 ${formatMs(d[k].latency.p50)} ms, p95 ${formatMs(d[k].latency.p95)} ms, ${indexNote(d[k].indexUsed)}`)
          .join('. ')}
        rows={[
          { label: 'Semantic', ...d.semantic.latency, note: indexNote(d.semantic.indexUsed) },
          { label: 'Hybrid', ...d.hybrid.latency, note: indexNote(d.hybrid.indexUsed) },
          { label: 'Linked', ...d.linked.latency, note: indexNote(d.linked.indexUsed) },
        ]}
        max={max}
        xLabel="Milliseconds per query (lower is better)"
      />
    </ChartCard>
  )
}

const indexLabel = (c: IndexConfig) =>
  [c.m !== null && `M = ${c.m}`, c.distance && `${c.distance} distance`].filter(Boolean).join(', ')

interface MRow {
  m: number
  buildMs: number
  latency: { p50: number; p95: number }
}

function MSweepCard({
  groundTruth,
  sweep,
  indexConfig,
}: {
  groundTruth: Loaded<MGroundTruth>
  sweep: Loaded<MSweep>
  indexConfig: IndexConfig | null
}) {
  const title = 'Vector index M: recall and latency'
  const gt = groundTruth.status === 'ok' ? groundTruth.data : null
  const sw = sweep.status === 'ok' ? sweep.data : null
  if (!gt && !sw) {
    return (
      <ChartCard title={title} icon={<SlidersIcon size={17} />} tone={`tone-${paletteTone(5)}`}>
        <Missing result={groundTruth} file="m_ground_truth" />
      </ChartCard>
    )
  }

  const inUse = gt?.productionM ?? indexConfig?.m ?? null
  const mLabel = (m: number) => (m === inUse ? `M = ${m} (in use)` : `M = ${m}`)
  // Recall and per-question latency come from the same ground-truth run; the single-query sweep is the fallback.
  const timed: MRow[] = gt ? gt.rows : sw!.rows
  const overlapAt = new Map(sw ? sw.rows.map((r) => [r.m, r.overlap]) : [])
  const maxK = gt ? gt.rows[0].recallAt[gt.rows[0].recallAt.length - 1].k : null
  const recallAt = (r: MGroundTruth['rows'][number], k: number) => r.recallAt.find((p) => p.k === k)?.value ?? null

  const byBuild = [...timed].sort((a, b) => a.m - b.m)
  const cheap = byBuild[0]
  const dear = byBuild[byBuild.length - 1]
  const medians = timed.map((r) => r.latency.p50)
  // MRR is compared at the 3 decimals shown: one rank swap moves it by ~0.0003.
  const flatRecall =
    gt !== null &&
    gt.rows.every(
      (r) => r.mrr.toFixed(3) === gt.rows[0].mrr.toFixed(3) && r.recallAt.every((p, i) => p.value === gt.rows[0].recallAt[i]?.value),
    )

  const columns: Column[] = gt
    ? gt.rows.map((r) => {
        const top = recallAt(r, maxK!) ?? 0
        const first = recallAt(r, 1)
        return {
          label: r.m === inUse ? `${r.m} (in use)` : String(r.m),
          value: top,
          valueLabel: pct(top),
          marker: first,
          tooltip: `${mLabel(r.m)}: Recall@${maxK} ${pct(top)}${first === null ? '' : `, Recall@1 ${pct(first)}`}, MRR ${r.mrr.toFixed(3)}`,
        }
      })
    : []

  const overlaps = sw ? sw.rows.map((r) => r.overlap) : []
  const caption: ReactNode = (
    <>
      Each M rebuilds the vector index on the same corpus; a larger M gives every vector more neighbours in the HNSW
      graph.{' '}
      {gt &&
        (flatRecall
          ? `Recall@k is identical for every M (Recall@${maxK} ${pct(recallAt(gt.rows[0], maxK!) ?? 0)} over ${gt.questions} questions) and MRR rounds to ${gt.rows[0].mrr.toFixed(3)} for all of them, so a denser graph finds no more right articles on this corpus. `
          : `Recall@${maxK} goes ${list(gt.rows.map((r) => `${pct(recallAt(r, maxK!) ?? 0)} at M = ${r.m}`))} over ${gt.questions} questions. `)}
      Median query time stays between {formatMs(Math.min(...medians))} and {formatMs(Math.max(...medians))} ms, while
      building the index grows from {formatMs(cheap.buildMs)} ms at M = {cheap.m} to {formatMs(dear.buildMs)} ms at M ={' '}
      {dear.m} ({times(dear.buildMs / cheap.buildMs)}).
      {gt && gt.candidateLimit !== null && ` Query times are per question, fetching ${gt.candidateLimit} candidate chunks.`}
      {sw &&
        new Set(overlaps).size > 1 &&
        ` On the single benchmark query “${sw.query}”, the top ${sw.limit} matched exact search ${list(sw.rows.map((r) => `${pct(r.overlap)} at M = ${r.m}`))}.`}
      {inUse !== null && ` The schema uses M = ${inUse}.`}
    </>
  )

  const head = ['M', 'Build (ms)', 'Median query (ms)', 'p95 query (ms)']
  if (gt) head.push('Recall@1', `Recall@${maxK}`, 'MRR')
  if (sw && gt) head.push(`Top-${sw.limit} overlap, 1 query`)
  const rows = timed.map((r) => {
    const g = gt?.rows.find((x) => x.m === r.m)
    const o = overlapAt.get(r.m)
    return [
      mLabel(r.m),
      formatMs(r.buildMs),
      formatMs(r.latency.p50),
      formatMs(r.latency.p95),
      ...(gt ? [g ? pct(recallAt(g, 1) ?? 0) : '—', g ? pct(recallAt(g, maxK!) ?? 0) : '—', g ? g.mrr.toFixed(3) : '—'] : []),
      ...(sw && gt ? [o === undefined ? '—' : pct(o)] : []),
    ]
  })

  return (
    <ChartCard
      title={title}
      icon={<SlidersIcon size={17} />}
      tone={`tone-${paletteTone(5)}`}
      legend={[
        ...(gt
          ? [
              { kind: 'bar' as const, label: `Recall@${maxK}` },
              { kind: 'marker' as const, label: 'Recall@1' },
            ]
          : []),
        { kind: 'whisker', label: 'p95 query time' },
      ]}
      caption={caption}
      source={[groundTruth.status === 'ok' ? groundTruth.source : null, sweep.status === 'ok' ? sweep.source : null]
        .filter(Boolean)
        .join(' · ')}
      table={{ head, rows }}
    >
      {gt && (
        <ColumnChart
          title="Recall by vector index M"
          description={gt.rows
            .map((r) => `M ${r.m}: Recall@${maxK} ${pct(recallAt(r, maxK!) ?? 0)}, Recall@1 ${pct(recallAt(r, 1) ?? 0)}`)
            .join('. ')}
          columns={columns}
          yMax={1}
          yTicks={[0, 0.25, 0.5, 0.75, 1]}
          formatTick={(v) => `${v * 100}%`}
          yLabel="Questions answered (%)"
          xLabel="Index M"
        />
      )}
      <LatencyChart
        title="Query latency by vector index M"
        description={timed
          .map((r) => `M ${r.m}: p50 ${formatMs(r.latency.p50)} ms, p95 ${formatMs(r.latency.p95)} ms, build ${formatMs(r.buildMs)} ms`)
          .join('. ')}
        rows={timed.map((r) => ({ label: mLabel(r.m), p50: r.latency.p50, p95: r.latency.p95, note: `build ${formatMs(r.buildMs)} ms` }))}
        xLabel="Milliseconds per query (lower is better)"
      />
    </ChartCard>
  )
}

function SettingsCard({ data }: { data: EvalData }) {
  const ds = data.dataset
  const rows: { label: string; value: ReactNode }[] = [
    { label: 'Machine', value: 'Not recorded in the result files' },
    {
      label: 'MariaDB version',
      value: ds?.mariadbVersion ? (
        <>
          <span className="mono">{ds.mariadbVersion}</span> (from <span className="mono">{ds.source}</span>)
        </>
      ) : (
        'Not recorded'
      ),
    },
  ]
  if (ds?.embeddingModel) {
    rows.push({
      label: 'Embedding model',
      value: `${ds.embeddingModel}${ds.embeddingDimensions ? `, ${ds.embeddingDimensions} dimensions` : ''}`,
    })
  }
  if (data.indexConfig) rows.push({ label: 'Vector index', value: indexLabel(data.indexConfig) })

  const corpus = new Set<string>()
  for (const r of [data.recall, data.articleRecall]) {
    if (r.status === 'ok') corpus.add(`${count(r.data.corpusArticles)} articles / ${count(r.data.corpusVectors)} vectors`)
  }
  if (data.searchStrategies.status === 'ok') {
    const s = data.searchStrategies.data
    corpus.add(`${count(s.articles)} articles / ${count(s.vectors)} vectors`)
  }
  if (data.mGroundTruth.status === 'ok') {
    const g = data.mGroundTruth.data
    corpus.add(`${count(g.articles)} articles / ${count(g.vectors)} vectors`)
  }
  if (data.indexVsBruteForce.status === 'ok') corpus.add(`${count(data.indexVsBruteForce.data.vectors)} vectors`)
  const full = [...corpus].filter((c) => c.includes('articles'))
  const corpusLines = full.length === 1 && [...corpus].every((c) => full[0].endsWith(c)) ? full : [...corpus]
  if (corpusLines.length) rows.push({ label: 'Corpus', value: corpusLines.join(' · ') })

  if (data.recall.status === 'ok') {
    const r = data.recall.data
    rows.push({
      label: 'Recall run',
      value: `${when(r.evaluatedAt)} · ${r.questions} questions, top ${r.maxK}${r.candidateLimit ? `, ${r.candidateLimit} candidate chunks` : ''}`,
    })
  }
  if (data.articleRecall.status === 'ok') {
    const r = data.articleRecall.data
    rows.push({ label: 'Oracle run', value: `${when(r.evaluatedAt)} · ${r.questions} questions, top ${r.maxK}` })
  }
  if (data.indexVsBruteForce.status === 'ok') {
    const d = data.indexVsBruteForce.data
    rows.push({
      label: 'Index benchmark',
      value: `${when(d.executedAt)} · “${d.query}”, limit ${d.limit}, ${d.runs} runs, ${d.warmups} warm-ups`,
    })
  }
  if (data.searchStrategies.status === 'ok') {
    const d = data.searchStrategies.data
    rows.push({
      label: 'Strategy benchmark',
      value: `Time not recorded · “${d.query}”, limit ${d.limit}, ${d.runs} runs, ${d.warmups} warm-ups`,
    })
  }
  if (data.mGroundTruth.status === 'ok') {
    const g = data.mGroundTruth.data
    rows.push({
      label: 'M study',
      value: `${when(g.evaluatedAt)} · M = ${g.rows.map((r) => r.m).join(', ')}, ${g.questions} questions${g.candidateLimit ? `, ${g.candidateLimit} candidate chunks` : ''}`,
    })
  }
  if (data.mSweep.status === 'ok') {
    const d = data.mSweep.data
    const stamp = stampOf(data.mSweep.source)
    rows.push({
      label: 'M latency sweep',
      value: `${stamp ? when(stamp) : 'Time not recorded'} · “${d.query}”, limit ${d.limit}, ${d.runs} runs, ${d.warmups} warm-ups`,
    })
  }

  return (
    <ChartCard
      title="Measured on"
      icon={<ServerIcon size={17} />}
      tone={`tone-${paletteTone(2)}`}
      caption={
        <>
          Taken from the result files.{' '}
          {ds?.mariadbVersion
            ? 'The MariaDB version and embedding model come from the dataset manifest, which describes the corpus rather than each run, and no file records the hardware'
            : 'They don’t record the hardware or MariaDB version'}
          , so compare numbers across machines with care. The live database in the top bar may differ from the one these
          were measured on.
        </>
      }
    >
      <dl className="eval-settings">
        {rows.map((r) => (
          <div key={r.label}>
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
    </ChartCard>
  )
}

function Tiles({ data }: { data: EvalData }) {
  const tiles: { label: string; value: string; note: string }[] = []
  if (data.recall.status === 'ok') {
    const r = data.recall.data
    const last = r.recallAt[r.recallAt.length - 1]
    tiles.push({ label: `Recall@${last.k}`, value: pct(last.value), note: `right article in the top ${last.k}` })
    tiles.push({ label: 'MRR', value: r.mrr.toFixed(3), note: '1 = always ranked first' })
    tiles.push({ label: `Misses@${r.maxK}`, value: `${r.misses} / ${r.questions}`, note: 'questions not found' })
  }
  if (data.indexVsBruteForce.status === 'ok') {
    tiles.push({ label: 'Index speedup', value: times(data.indexVsBruteForce.data.speedup), note: 'vs brute force, mean' })
  }
  if (tiles.length === 0) return null
  return (
    <dl className="eval-tiles">
      {tiles.map((t, i) => (
        <div key={t.label} className={`eval-tile tone-${paletteTone(i)}`}>
          <dt>{t.label}</dt>
          <dd className="mono">{t.value}</dd>
          <dd className="eval-tile-note">{t.note}</dd>
        </div>
      ))}
    </dl>
  )
}

export default function EvalPage() {
  const [load, setLoad] = useState<Load>({ status: 'loading' })

  useEffect(() => {
    let active = true
    request ??= loadEvalData()
    request.then(
      (data) => active && setLoad(data ? { status: 'ok', data } : { status: 'no-manifest' }),
      (err: unknown) => {
        request = null
        if (active) setLoad({ status: 'error', message: err instanceof Error ? err.message : String(err) })
      },
    )
    return () => {
      active = false
    }
  }, [])

  return (
    <main className="eval" aria-labelledby="eval-title">
      <header className="eval-head">
        <h2 id="eval-title">
          Evaluation results
        </h2>
        <p>
          Retrieval quality and latency from the experiments in <span className="mono">experiments/results/</span>,
          copied as they are by <code className="mono">npm run sync-eval</code>
          {load.status === 'ok' && load.data.syncedAt && ` (last synced ${when(load.data.syncedAt)})`}.
        </p>
      </header>

      {load.status === 'loading' && <LoadingCard title="Loading evaluation results…" sub="Reading the synced files in eval/" />}

      {load.status === 'no-manifest' && (
        <StatusMessage kind="empty" icon={<DatabaseIcon size={26} />} title="No evaluation results synced">
          Run <code className="mono">npm run sync-eval</code> in <span className="mono">frontend/</span> to copy the
          results from <span className="mono">experiments/results/</span>, then reload. It also runs before{' '}
          <code className="mono">npm run dev</code> and <code className="mono">npm run build</code>.
        </StatusMessage>
      )}

      {load.status === 'error' && (
        <StatusMessage kind="error" icon={<WarningIcon size={24} />} title="Couldn’t load the results" detail={load.message}>
          The synced result files couldn’t be fetched.
        </StatusMessage>
      )}

      {load.status === 'ok' && <Results data={load.data} />}
    </main>
  )
}

function Results({ data }: { data: EvalData }) {
  const ivb = data.indexVsBruteForce.status === 'ok' ? data.indexVsBruteForce.data : null
  const strategies = data.searchStrategies.status === 'ok' ? data.searchStrategies.data : null
  const p95s = [
    ...(ivb ? [ivb.indexed.p95, ivb.bruteForce.p95] : []),
    ...(strategies ? [strategies.semantic, strategies.hybrid, strategies.linked].map((s) => s.latency.p95) : []),
  ]
  const max = p95s.length ? Math.max(...p95s) : undefined
  return (
    <>
      <Tiles data={data} />
      <div className="eval-grid">
        <RecallCard recall={data.recall} oracle={data.articleRecall} />
        <RankCard recall={data.recall} />
        <IndexCard result={data.indexVsBruteForce} max={max} />
        <StrategiesCard result={data.searchStrategies} max={max} />
        <MSweepCard groundTruth={data.mGroundTruth} sweep={data.mSweep} indexConfig={data.indexConfig} />
        <SettingsCard data={data} />
      </div>
    </>
  )
}
