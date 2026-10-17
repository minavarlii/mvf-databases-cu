import type { ReactNode } from 'react'

interface Props {
  icon: ReactNode
  title: string
  children: ReactNode
  className?: string
}

export function Placeholder({ icon, title, children, className }: Props) {
  return (
    <div className={className ? `placeholder ${className}` : 'placeholder'}>
      <span className="placeholder-icon">{icon}</span>
      <p className="placeholder-title">{title}</p>
      <p className="placeholder-text">{children}</p>
    </div>
  )
}
