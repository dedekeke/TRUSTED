import { Tag, Tooltip } from 'antd'
import type { PrivacyRole } from '@/types/pipeline.types'
import { ROLE_META } from '@/utils/constants'

export default function RoleTag({ role }: { role: PrivacyRole }) {
  const m = ROLE_META[role]
  return (
    <Tooltip title={m.hint}>
      <Tag color={m.color} className="!m-0">
        {m.label}
      </Tag>
    </Tooltip>
  )
}
