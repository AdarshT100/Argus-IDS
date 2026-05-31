import type { ReactNode } from 'react'

type PanelProps = {
  title: string
  eyebrow: string
  children: ReactNode
}

export function Panel({ title, eyebrow, children }: PanelProps) {
  return (
    <section className="page-panel">
      <div className="panel-header">
        <span className="panel-accent" aria-hidden="true" />
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="panel-body">{children}</div>
    </section>
  )
}
