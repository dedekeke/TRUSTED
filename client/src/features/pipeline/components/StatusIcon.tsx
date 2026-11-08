import type { StepStatus } from '@/types/job.types'
import { STATUS_META } from '../stepMeta'

export default function StatusIcon({ status, size = 18 }: { status: StepStatus; size?: number }) {
  const m = STATUS_META[status]
  return (
    <span style={{ color: m.color, fontSize: size }} aria-label={m.label} title={m.label}>
      {m.icon}
    </span>
  )
}
