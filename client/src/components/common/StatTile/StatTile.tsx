import type { ReactNode } from 'react'
import { Card } from 'antd'

interface Props {
  title: string
  value: ReactNode
  hint?: ReactNode
  accent?: string
  icon?: ReactNode
}

export default function StatTile({ title, value, hint, accent, icon }: Props) {
  return (
    <Card size="small" className="h-full">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-medium tracking-wide text-[var(--app-muted)] uppercase">{title}</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums" style={accent ? { color: accent } : undefined}>
            {value}
          </div>
          {hint && <div className="mt-1 text-xs text-[var(--app-muted)]">{hint}</div>}
        </div>
        {icon && <div className="text-xl text-[var(--app-accent)]">{icon}</div>}
      </div>
    </Card>
  )
}
