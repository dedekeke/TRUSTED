import type { ReactNode } from 'react'
import { Typography } from 'antd'

interface Props {
  step?: string
  title: string
  description?: ReactNode
  extra?: ReactNode
}

export default function PageHeader({ step, title, description, extra }: Props) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {step && <div className="text-xs font-semibold tracking-widest text-[var(--app-accent)] uppercase">{step}</div>}
        <Typography.Title level={3} className="!mt-0.5 !mb-1">
          {title}
        </Typography.Title>
        {description && <Typography.Text type="secondary">{description}</Typography.Text>}
      </div>
      {extra && <div className="flex flex-wrap gap-2">{extra}</div>}
    </div>
  )
}
