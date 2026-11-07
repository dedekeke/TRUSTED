import { Card, Table, Tooltip } from 'antd'
import ScoreBar from '@/components/common/ScoreBar'
import type { RiskComponent } from '@/features/evaluate/services/metrics'

export default function RiskTable({ risks }: { risks: RiskComponent[] }) {
  return (
    <Card
      size="small"
      title="Re-identification risk: before vs after"
      extra={<span className="text-xs text-[var(--app-muted)]">0 = no risk</span>}
    >
      <Table
        rowKey="key"
        size="small"
        pagination={false}
        dataSource={risks}
        columns={[
          {
            title: 'Risk component',
            dataIndex: 'label',
            render: (l: string, r) => (
              <Tooltip title={r.explain}>
                <span className="cursor-help">{l}</span>
              </Tooltip>
            ),
          },
          {
            title: 'Before',
            dataIndex: 'before',
            width: '28%',
            render: (v: number) => <ScoreBar value={v} kind="risk" />,
          },
          {
            title: 'After',
            dataIndex: 'after',
            width: '28%',
            render: (v: number) => <ScoreBar value={v} kind="risk" />,
          },
        ]}
      />
    </Card>
  )
}
