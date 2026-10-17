import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Stats } from '../api'
import { paletteTone } from './tones'

type Load = { status: 'loading' } | { status: 'ok'; stats: Stats } | { status: 'error' }

// Module-level, so StrictMode's double effect still fetches once per page load.
let statsRequest: Promise<Stats> | null = null
const loadStats = () => (statsRequest ??= api.stats())

const versionLabel = (v: string) => {
  const m = v.match(/^\d+(?:\.\d+)*/)
  return m ? `MariaDB ${m[0]}` : v
}

const count = (n: number | null) => (n === null ? null : n.toLocaleString('en-US'))

const FIELDS: {
  key: string
  label: string
  wide?: boolean
  value: (s: Stats) => string | null
  title?: (s: Stats) => string | null
}[] = [
  {
    key: 'articles',
    label: 'Articles',
    value: (s) => count(s.article_count),
  },
  {
    key: 'chunks',
    label: 'Chunks / vectors',
    value: (s) => count(s.chunk_count),
  },
  {
    key: 'model',
    label: 'Embedding model',
    wide: true,
    value: (s) => s.embedding_model?.split('/').at(-1) ?? null,
    title: (s) => s.embedding_model,
  },
  {
    key: 'dims',
    label: 'Dimensions',
    value: (s) => count(s.vector_dimensions),
  },
  {
    key: 'db',
    label: 'Database',
    value: (s) =>
      s.mariadb_version ? versionLabel(s.mariadb_version) : null,
    title: (s) => s.mariadb_version,
  },
]

export function StatsStrip() {
  const [load, setLoad] = useState<Load>({ status: 'loading' })

  useEffect(() => {
    let active = true
    loadStats().then(
      (stats) => active && setLoad({ status: 'ok', stats }),
      () => active && setLoad({ status: 'error' }),
    )
    return () => {
      active = false
    }
  }, [])

  return (
    <dl
      className="topbar-stats stats"
      aria-label={load.status === 'error' ? 'Database stats (could not be loaded)' : 'Database stats'}
      aria-busy={load.status === 'loading'}
    >
      {FIELDS.map((f, i) => {
        const value = load.status === 'ok' ? f.value(load.stats) : null
        const title = load.status === 'ok' ? (f.title?.(load.stats) ?? value ?? undefined) : undefined
        return (
          <div key={f.key} className={`stat tone-${paletteTone(i)}${f.wide ? ' is-wide' : ''}`}>
            <dt>{f.label}</dt>
            <dd className="mono" title={title}>
              {load.status === 'loading' && (
                <>
                  <span className="shimmer stat-sk" aria-hidden="true" />
                  <span className="sr-only">Loading</span>
                </>
              )}
              {(load.status === 'error' || (load.status === 'ok' && value === null)) && (
                <>
                  <span aria-hidden="true">—</span>
                  <span className="sr-only">{load.status === 'error' ? 'Unavailable' : 'Not provided by the backend'}</span>
                </>
              )}
              {value}
            </dd>
          </div>
        )
      })}
    </dl>
  )
}
