import type { ReactNode } from 'react'

/** A collapsible "how do I…" box. Open by default for newcomers (open = true). */
export default function HelpBox({ title, children, open = false }: { title: string; children: ReactNode; open?: boolean }) {
  return (
    <details className="help" open={open}>
      <summary>{title}</summary>
      <div className="help-body">{children}</div>
    </details>
  )
}
