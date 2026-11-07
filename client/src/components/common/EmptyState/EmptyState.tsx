import { Button, Empty } from 'antd'
import { useNavigate } from 'react-router-dom'

interface Props {
  title: string
  description?: string
  actionLabel?: string
  to?: string
}

export default function EmptyState({ title, description, actionLabel, to }: Props) {
  const navigate = useNavigate()
  return (
    <div className="rounded-xl border border-dashed border-[var(--app-border)] bg-[var(--app-surface)] py-14">
      <Empty
        description={
          <div>
            <div className="font-medium">{title}</div>
            {description && <div className="text-sm text-[var(--app-muted)]">{description}</div>}
          </div>
        }
      >
        {actionLabel && to && (
          <Button type="primary" onClick={() => navigate(to)}>
            {actionLabel}
          </Button>
        )}
      </Empty>
    </div>
  )
}
