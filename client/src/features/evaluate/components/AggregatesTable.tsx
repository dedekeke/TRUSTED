import { Card, Table, Tag } from 'antd'
import type { AggregateComparison } from '@/features/evaluate/services/metrics'
import { pct } from '@/utils/format'

export default function AggregatesTable({ rows }: { rows: AggregateComparison[] }) {
  return (
    <Card size="small" title="What an analyst would compute: before vs after">
      <Table
        rowKey="column"
        size="small"
        pagination={false}
        dataSource={rows}
        scroll={{ x: 700 }}
        columns={[
          {
            title: 'Column',
            dataIndex: 'column',
            render: (c: string, r) => (
              <span>
                <span className="mono">{c}</span> <Tag className="!ml-1">{r.kind}</Tag>
              </span>
            ),
          },
          { title: 'Original', dataIndex: 'before', render: (v: string) => <span className="mono text-xs">{v}</span> },
          { title: 'Protected', dataIndex: 'after', render: (v: string) => <span className="mono text-xs">{v}</span> },
          {
            title: 'Error',
            dataIndex: 'error',
            width: 90,
            render: (e: number) => (
              <span
                className={`mono text-xs ${e <= 0.05 ? 'text-green-600' : e <= 0.2 ? 'text-amber-600' : 'text-red-600'}`}
              >
                {pct(e)}
              </span>
            ),
          },
        ]}
      />
    </Card>
  )
}
