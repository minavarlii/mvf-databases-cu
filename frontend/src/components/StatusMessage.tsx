import type { ReactNode } from 'react'
import { RetryIcon } from './icons'

type Kind = 'error' | 'warning' | 'empty'

interface Props {
  kind: Kind
  icon: ReactNode
  title: string
  children: ReactNode
  detail?: string | null
  action?: { label: string; onClick: () => void }
}

export function StatusMessage({ kind, icon, title, children, detail, action }: Props) {
  return (
    <section
      className={`status status-${kind}`}
      role={kind === 'empty' ? 'status' : 'alert'}
    >
      <span className="status-icon">{icon}</span>
      <div className="status-body">
        <h2>{title}</h2>
        <p>{children}</p>
        {detail && <p className="mono status-detail">{detail}</p>}
        {action && (
          <div>
            <button type="button" className="btn-soft" onClick={action.onClick}>
              <RetryIcon size={16} /> {action.label}
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
