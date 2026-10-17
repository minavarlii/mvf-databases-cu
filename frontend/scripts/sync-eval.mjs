import { copyFile, mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = join(dirname(fileURLToPath(import.meta.url)), '..')
const repoDir = join(frontendDir, '..')
const resultsDir = join(repoDir, 'experiments', 'results')
const schemaFile = join(repoDir, 'database', 'schema', '002_vector_index.sql')
// Dataset metadata (MariaDB version, embedding model) written by the backend; not per run.
const datasetFile = join(repoDir, 'data', 'manifest.json')
const outDir = join(frontendDir, 'public', 'eval')

// Timestamped results: newest wins. search_strategies.json has no timestamp and is overwritten in place.
const SOURCES = {
  recall: /^recall_\d{8}T\d{6}Z\.json$/,
  article_recall: /^article_recall_\d{8}T\d{6}Z\.json$/,
  index_vs_bruteforce: /^index_vs_bruteforce_\d{8}T\d{6}Z\.json$/,
  search_strategies: /^search_strategies\.json$/,
  m_ground_truth: /^vector_index_m_ground_truth_\d{8}T\d{6}Z\.json$/,
  m_sweep: /^vector_index_m_sweep_\d{8}T\d{6}Z\.json$/,
}

async function listResults() {
  try {
    return await readdir(resultsDir)
  } catch {
    return []
  }
}

async function indexConfig() {
  let sql
  try {
    sql = await readFile(schemaFile, 'utf8')
  } catch {
    return null
  }
  const m = sql.match(/\bM\s*=\s*(\d+)/i)
  const distance = sql.match(/\bDISTANCE\s*=\s*(\w+)/i)
  if (!m && !distance) return null
  return {
    m: m ? Number(m[1]) : null,
    distance: distance ? distance[1].toLowerCase() : null,
    source: relative(repoDir, schemaFile),
  }
}

const names = (await listResults()).sort()
await rm(outDir, { recursive: true, force: true })
await mkdir(outDir, { recursive: true })

const files = {}
for (const [key, pattern] of Object.entries(SOURCES)) {
  const latest = names.filter((n) => pattern.test(n)).at(-1)
  if (!latest) {
    files[key] = null
    console.log(`sync-eval: ${key}: not found`)
    continue
  }
  await copyFile(join(resultsDir, latest), join(outDir, `${key}.json`))
  files[key] = { source: `experiments/results/${latest}`, file: `${key}.json` }
  console.log(`sync-eval: ${key}: ${latest}`)
}

async function dataset() {
  try {
    await copyFile(datasetFile, join(outDir, 'dataset.json'))
  } catch {
    console.log('sync-eval: dataset: not found')
    return null
  }
  console.log(`sync-eval: dataset: ${relative(repoDir, datasetFile)}`)
  return { source: relative(repoDir, datasetFile), file: 'dataset.json' }
}

const manifest = {
  synced_at: new Date().toISOString(),
  files,
  index_config: await indexConfig(),
  dataset: await dataset(),
}
await writeFile(join(outDir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`)
