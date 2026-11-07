import { Card, Table, Tag } from 'antd'
import RoleTag from '@/components/common/RoleTag'
import ScoreBar from '@/components/common/ScoreBar'
import type { PrivacyRole } from '@/types/pipeline.types'
import { PET_META } from '@/utils/constants'
import type { ColumnUtility } from '@/features/evaluate/services/metrics'

export default function UtilityTable({ columns }: { columns: ColumnUtility[] }) {
  return (
    <Card
      size="small"
      title="Utility kept per column"
      extra={
        <span className="text-xs text-[var(--app-muted)]">
          fidelity = 1 − TVD after suppression · granularity = distinct values kept
        </span>
      }
    >
      <Table
        rowKey="column"
        size="small"
        pagination={false}
        dataSource={columns}
        scroll={{ x: 760 }}
        columns={[
          { title: 'Column', dataIndex: 'column', render: (c: string) => <span className="mono">{c}</span> },
          { title: 'Type', dataIndex: 'role', render: (r: PrivacyRole) => <RoleTag role={r} /> },
          {
            title: 'Treatment',
            dataIndex: 'treatment',
            render: (t: string) => <Tag className="!m-0">{PET_META[t as keyof typeof PET_META]?.label ?? t}</Tag>,
          },
          { title: 'Fidelity', dataIndex: 'fidelity', width: 150, render: (v: number) => <ScoreBar value={v} /> },
          { title: 'Granularity', dataIndex: 'granularity', width: 150, render: (v: number) => <ScoreBar value={v} /> },
          {
            title: 'Score',
            dataIndex: 'score',
            width: 150,
            sorter: (a, b) => a.score - b.score,
            render: (v: number) => <ScoreBar value={v} />,
          },
          {
            title: 'Note',
            dataIndex: 'note',
            render: (n: string) => <span className="text-xs text-[var(--app-muted)]">{n}</span>,
          },
        ]}
      />
    </Card>
  )
}
