import { CloseOutlined } from '@ant-design/icons'
import { Card, Empty, Segmented, Table, Tag } from 'antd'
import { useState } from 'react'
import MetricBars, { type MetricSeries } from '@/components/common/MetricBars'
import ScoreBar from '@/components/common/ScoreBar'
import { BENCHMARK } from '@/data/benchmark'
import type { Scorecard } from '@/types/data.types'
import { useUploadedScorecards } from '@/features/benchmark/hooks/useUploadedScorecards'
import ScorecardUpload from './ScorecardUpload'

export default function BenchmarkView() {
  const datasets = Object.keys(BENCHMARK)
  const [ds, setDs] = useState('health')
  const { items, add, remove } = useUploadedScorecards()

  const cards: [string, Scorecard, boolean][] = [
    ...Object.entries(BENCHMARK[ds] ?? {}).map(([k, v]) => [k, v, false] as [string, Scorecard, boolean]),
    ...items.filter((u) => u.dataset === ds).map((u) => [u.name, u.scorecard, true] as [string, Scorecard, boolean]),
  ]
  const series: MetricSeries[] = cards.map(([name, sc, ours]) => ({
    name,
    highlight: ours,
    values: { Privacy: sc.summary.privacy, Utility: sc.summary.utility, Composite: sc.summary.composite },
  }))

  const riskKeys = [...new Set(cards.flatMap(([, sc]) => Object.keys(sc.risk_components)))]
  const taskIds = [...new Set(cards.flatMap(([, sc]) => sc.utility.map((u) => u.id)))]
  const taskDesc = new Map(cards.flatMap(([, sc]) => sc.utility.map((u) => [u.id, u.description] as const)))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="max-w-full overflow-x-auto">
          <Segmented options={datasets} value={ds} onChange={setDs} />
        </div>
        <ScorecardUpload
          onAdd={(u) => {
            add(u)
            setDs(u.dataset)
          }}
        />
      </div>
      {items.filter((u) => u.dataset === ds).length > 0 && (
        <div className="flex flex-wrap gap-1">
          {items
            .filter((u) => u.dataset === ds)
            .map((u) => (
              <Tag
                key={u.name}
                color="geekblue"
                closable
                closeIcon={<CloseOutlined />}
                onClose={() => remove(u.name, u.dataset)}
              >
                {u.name}
              </Tag>
            ))}
        </div>
      )}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,380px)_1fr]">
        <Card size="small" title="Scores (pets-eval self-assessment)">
          <MetricBars metrics={['Privacy', 'Utility', 'Composite']} series={series} />
          <div className="mt-4 text-xs text-[var(--app-muted)]">
            B0 drops direct identifiers · B2 classic SDC · B2-k adds k ≥ 5 suppression. Baselines read the answer key
            for detection.
          </div>
        </Card>
        <Card size="small" title="Risk components (lower is better)">
          <Table
            rowKey="key"
            size="small"
            pagination={false}
            scroll={{ x: 200 + cards.length * 150 }}
            dataSource={riskKeys.map((key) => ({ key }))}
            columns={[
              { title: 'Component', dataIndex: 'key', render: (k: string) => <span className="text-xs">{k}</span> },
              ...cards.map(([name, sc, ours]) => ({
                title: <span className={ours ? 'text-[var(--app-accent)]' : ''}>{name}</span>,
                key: name,
                width: 150,
                render: (_: unknown, r: { key: string }) =>
                  r.key in sc.risk_components ? (
                    <ScoreBar value={sc.risk_components[r.key]} kind="risk" />
                  ) : (
                    <span className="text-xs text-[var(--app-muted)]">—</span>
                  ),
              })),
            ]}
          />
        </Card>
      </div>
      <Card size="small" title="Utility tasks (higher is better)">
        {taskIds.length ? (
          <Table
            rowKey="id"
            size="small"
            pagination={false}
            scroll={{ x: 320 + cards.length * 150 }}
            dataSource={taskIds.map((id) => ({ id }))}
            columns={[
              {
                title: 'Task',
                dataIndex: 'id',
                render: (id: string) => (
                  <div>
                    <span className="mono text-xs font-semibold">{id}</span>
                    <div className="text-xs text-[var(--app-muted)]">{taskDesc.get(id)}</div>
                  </div>
                ),
              },
              ...cards.map(([name, sc]) => ({
                title: name,
                key: name,
                width: 150,
                render: (_: unknown, r: { id: string }) => {
                  const u = sc.utility.find((x) => x.id === r.id)
                  return u ? <ScoreBar value={u.score} /> : <span className="text-xs text-[var(--app-muted)]">—</span>
                },
              })),
            ]}
          />
        ) : (
          <Empty />
        )}
      </Card>
    </div>
  )
}
