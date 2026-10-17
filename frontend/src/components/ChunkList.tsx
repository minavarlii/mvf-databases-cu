import { useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { Chunk } from '../api'
import { ChevronDownIcon, VectorSearchIcon } from './icons'
import { articleTones } from './tones'
import type { Tone } from './tones'

interface Props {
  chunks: Chunk[]
  highlighted: number | null // 1-based
  expanded: ReadonlySet<number>
  onToggle: (chunkId: number) => void
  action?: ReactNode
}

export function ChunkList({ chunks, highlighted, expanded, onToggle, action }: Props) {
  if (chunks.length === 0) return null
  const tones = articleTones(chunks)
  return (
    <section className="block" aria-labelledby="chunks-title">
      <div className="block-head">
        <h2 id="chunks-title" className="section-title">
          <span className="icon-dot tone-sky">
            <VectorSearchIcon size={17} />
          </span>
          Retrieved chunks
          <span className="mono count tone-sky">{chunks.length}</span>
        </h2>
        {action}
        <p className="block-caption">Cosine distance: lower is closer. Similarity = 1 − distance.</p>
      </div>
      <ol className="chunks">
        {chunks.map((c, i) => (
          <ChunkItem
            key={c.chunk_id}
            chunk={c}
            position={i + 1}
            tone={tones.get(c.article_id) ?? 'lav'}
            highlighted={highlighted === i + 1}
            expanded={expanded.has(c.chunk_id)}
            onToggle={() => onToggle(c.chunk_id)}
          />
        ))}
      </ol>
    </section>
  )
}

interface ItemProps {
  chunk: Chunk
  position: number
  tone: Tone
  highlighted: boolean
  expanded: boolean
  onToggle: () => void
}

function ChunkItem({ chunk: c, position, tone, highlighted, expanded, onToggle }: ItemProps) {
  const textRef = useRef<HTMLParagraphElement>(null)
  const [overflows, setOverflows] = useState(false)

  // Measured while clamped (the overflow is only knowable then); while expanded the last result stands.
  useLayoutEffect(() => {
    const el = textRef.current
    if (!el || expanded) return
    const measure = () => setOverflows(el.scrollHeight > el.clientHeight + 1)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [expanded, c.text])

  const similarity = 1 - c.distance
  const pct = Math.max(0, Math.min(1, similarity)) * 100
  const textId = `chunk-${position}-text`

  return (
    <li id={`chunk-${position}`} tabIndex={-1} className={highlighted ? 'chunk is-highlighted' : 'chunk'}>
      <div className="chunk-head">
        <div className="chunk-title">
          <span className={`mono chunk-num tone-${tone}`}>{position}</span>
          <span className="chunk-article">{c.article_title}</span>
          <span className="mono pill">chunk {c.chunk_index}</span>
        </div>
        <div className="chunk-scores mono">
          <span>
            distance <b>{c.distance.toFixed(3)}</b>
          </span>
          <span>
            similarity <b>{similarity.toFixed(3)}</b>
          </span>
          <span className="sim-bar" aria-hidden="true">
            <span style={{ width: `${pct}%` }} />
          </span>
        </div>
      </div>
      <p id={textId} ref={textRef} className={expanded ? 'chunk-text' : 'chunk-text is-clamped'}>
        {c.text}
      </p>
      {overflows && (
        <button
          type="button"
          className={expanded ? 'chunk-more is-open' : 'chunk-more'}
          aria-expanded={expanded}
          aria-controls={textId}
          onClick={onToggle}
        >
          {expanded ? 'Show less' : 'Show more'}
          <ChevronDownIcon size={15} />
        </button>
      )}
    </li>
  )
}
