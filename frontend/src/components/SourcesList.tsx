import type { Chunk, SourceArticle } from '../api'
import { BookIcon, ExternalIcon } from './icons'
import { articleTones } from './tones'

interface Props {
  sources: SourceArticle[]
  chunks: Chunk[]
}

export function SourcesList({ sources, chunks }: Props) {
  if (sources.length === 0) return null
  const tones = articleTones(chunks)
  return (
    <section className="block" aria-labelledby="sources-title">
      <div className="block-head">
        <h2 id="sources-title" className="section-title">
          <span className="icon-dot tone-peach">
            <BookIcon size={17} />
          </span>
          Sources used
          <span className="mono count tone-peach">{sources.length}</span>
        </h2>
        <p className="block-caption">Wikipedia articles the retrieved chunks came from</p>
      </div>
      <ul className="sources">
        {sources.map((s) => {
          const own = chunks.filter((c) => c.article_id === s.article_id)
          const best = own.length ? Math.min(...own.map((c) => c.distance)) : null
          return (
            <li key={s.article_id}>
              <span className="source-name">
                <span className={`source-dot ink-${tones.get(s.article_id) ?? 'lav'}`} aria-hidden="true" />
                <a href={s.url} target="_blank" rel="noopener noreferrer">
                  {s.title}
                  <ExternalIcon size={14} />
                  <span className="sr-only"> (opens Wikipedia in a new tab)</span>
                </a>
              </span>
              <span className="mono source-meta">
                {own.length} {own.length === 1 ? 'chunk' : 'chunks'}
                {best !== null && ` · best ${best.toFixed(3)}`}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
