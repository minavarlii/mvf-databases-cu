import { VectorSearchIcon } from './icons'

interface Props {
  title?: string
  sub?: string
}

export function LoadingCard({
  title = 'Searching MariaDB for relevant passages…',
  sub = 'Embedding the question, ranking chunks by cosine distance, then generating an answer',
}: Props) {
  return (
    <section className="card loading-card" role="status" aria-live="polite">
      <div className="loading-head">
        <span className="loading-icon tone-sky bob">
          <VectorSearchIcon size={28} />
        </span>
        <p className="loading-title">{title}</p>
        <p className="mono loading-sub">{sub}</p>
      </div>
      <div className="skeleton" aria-hidden="true">
        <div className="skeleton-row">
          <span className="shimmer sk-dot" />
          <span className="shimmer sk-line" style={{ width: 140 }} />
        </div>
        <span className="shimmer sk-line" />
        <span className="shimmer sk-line" style={{ width: '94%' }} />
        <span className="shimmer sk-line" style={{ width: '62%' }} />
      </div>
    </section>
  )
}
