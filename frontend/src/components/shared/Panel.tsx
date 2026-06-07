import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

type PanelProps = {
  title: string
  eyebrow: string
  bodyClassName?: string
  children: ReactNode
  className?: string
  description?: string
}

export function Panel({
  title,
  eyebrow,
  bodyClassName,
  children,
  className,
  description,
}: PanelProps) {
  return (
    <section className={cn('page-panel', className)}>
      <div className="panel-header">
        <span className="panel-accent" aria-hidden="true" />
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
          {description && <p className="panel-description">{description}</p>}
        </div>
      </div>
      <div className={cn('panel-body', bodyClassName)}>{children}</div>
    </section>
  )
}
