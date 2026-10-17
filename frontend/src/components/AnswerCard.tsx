import type { ReactNode } from 'react'
import { SparkleIcon } from './icons'

interface Props {
  answer: string
  chunkCount: number
  meta: string
  onCite: (n: number) => void
}

// Citations outside 1..chunkCount stay plain text.
function renderWithCitations(answer: string, chunkCount: number, onCite: (n: number) => void) {
  const parts: ReactNode[] = []
  let last = 0
  let cited = false
  for (const m of answer.matchAll(/\[(\d+)\]/g)) {
    const n = Number(m[1])
    if (n < 1 || n > chunkCount) continue
    parts.push(answer.slice(last, m.index))
    parts.push(
      <a
        key={m.index}
        href={`#chunk-${n}`}
        className="mono cite"
        aria-label={`Chunk ${n}`}
        onClick={(e) => {
          e.preventDefault()
          onCite(n)
        }}
      >
        {n}
      </a>,
    )
    last = m.index + m[0].length
    cited = true
  }
  parts.push(answer.slice(last))
  return { parts, cited }
}

export function AnswerCard({ answer, chunkCount, meta, onCite }: Props) {
  const { parts, cited } = renderWithCitations(answer, chunkCount, onCite)
  return (
    <section className="answer" aria-labelledby="answer-title">
      <div className="answer-head">
        <h2 id="answer-title" className="section-title">
          <span className="icon-dot tone-butter">
            <SparkleIcon size={19} />
          </span>
          Answer
        </h2>
        <span className="mono answer-meta">{meta}</span>
      </div>
      <p className="answer-text">{parts}</p>
      {cited && (
        <p className="answer-note">Numbers point to the retrieved chunks. The LLM only saw those passages.</p>
      )}
    </section>
  )
}
