import { Select, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import RoleTag from '@/components/common/RoleTag'
import { usePipeline } from '@/hooks/usePipeline'
import type { ColumnPolicy, PetId } from '@/types/pipeline.types'
import { PET_META } from '@/utils/constants'

const PET_OPTIONS = (Object.keys(PET_META) as PetId[]).map((p) => ({
  value: p,
  label: (
    <span>
      {PET_META[p].label} <span className="text-xs text-[var(--app-muted)]">· {PET_META[p].family}</span>
    </span>
  ),
}))

const SOURCE_COLOR = { policy: 'default', manual: 'blue', 'k-anonymity': 'orange' } as const

export default function PolicyTable() {
  const { detections, policies, updatePolicy, result } = usePipeline()
  const det = new Map(detections.map((d) => [d.column, d]))
  // after a run, show the policies actually applied (k-anonymity may have escalated levels)
  const rows = result?.policies ?? policies

  const columns: ColumnsType<ColumnPolicy> = [
    {
      title: 'Column',
      dataIndex: 'column',
      width: 180,
      fixed: 'left',
      render: (c: string) => <span className="mono font-medium">{c}</span>,
    },
    {
      title: 'Data type',
      key: 'role',
      width: 200,
      render: (_, p) => {
        const d = det.get(p.column)
        return d ? (
          <div className="flex flex-col items-start gap-0.5">
            <RoleTag role={d.role} />
            <span className="mono text-[11px] text-[var(--app-muted)]">{d.subtype}</span>
          </div>
        ) : null
      },
    },
    {
      title: 'PET',
      dataIndex: 'pet',
      width: 250,
      render: (pet: PetId, p) => (
        <Select
          size="small"
          value={pet}
          className="w-full"
          popupMatchSelectWidth={false}
          options={PET_OPTIONS}
          onChange={(v) => updatePolicy(p.column, { pet: v, level: 0 })}
        />
      ),
    },
    {
      title: 'Level',
      dataIndex: 'level',
      width: 170,
      render: (level: number, p) => {
        const levels = PET_META[p.pet].levels
        return levels.length ? (
          <Select
            size="small"
            value={level}
            className="w-full"
            popupMatchSelectWidth={false}
            options={levels.map((l, i) => ({ value: i, label: l }))}
            onChange={(v) => updatePolicy(p.column, { level: v })}
          />
        ) : (
          <span className="text-xs text-[var(--app-muted)]">—</span>
        )
      },
    },
    {
      title: 'Why this PET',
      dataIndex: 'rationale',
      render: (r: string, p) => (
        <div className="text-xs leading-relaxed">
          {p.source !== 'policy' && (
            <Tag color={SOURCE_COLOR[p.source]} className="!mr-1 !mb-1">
              {p.source}
            </Tag>
          )}
          {r}
        </div>
      ),
    },
  ]

  return (
    <Table rowKey="column" size="small" columns={columns} dataSource={rows} pagination={false} scroll={{ x: 1000 }} />
  )
}
