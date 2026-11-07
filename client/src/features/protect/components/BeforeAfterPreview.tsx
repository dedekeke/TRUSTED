import { Segmented, Table, Tooltip } from 'antd'
import { useState } from 'react'
import type { Dataset, ProtectedResult } from '@/types/pipeline.types'

type View = 'Protected' | 'Original' | 'Changes'

export default function BeforeAfterPreview({ dataset, result }: { dataset: Dataset; result: ProtectedResult }) {
  const [view, setView] = useState<View>('Changes')
  const n = 25
  const cols = view === 'Original' ? dataset.columns : result.columns
  const data = Array.from({ length: Math.min(n, dataset.rows.length) }, (_, i) => ({ __i: i }))

  const columns = cols.map((c) => ({
    title: <span className="mono text-xs">{c}</span>,
    key: c,
    width: 160,
    ellipsis: true,
    render: (_: unknown, r: { __i: number }) => {
      const o = dataset.rows[r.__i][c] ?? ''
      const p = result.rows[r.__i]?.[c] ?? ''
      if (view === 'Original') return <span className="mono text-xs">{o}</span>
      if (view === 'Protected') return <span className="mono text-xs">{p}</span>
      const changed = o !== p
      return (
        <Tooltip title={changed ? `original: ${o || '∅'}` : undefined}>
          <span
            className={`mono rounded px-1 text-xs ${changed ? (p === '' ? 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200') : ''}`}
          >
            {p === '' && changed ? '∅' : p}
          </span>
        </Tooltip>
      )
    },
  }))
  const dropped = dataset.columns.filter((c) => !result.columns.includes(c))

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <Segmented<View> options={['Changes', 'Protected', 'Original']} value={view} onChange={setView} />
        <span className="text-xs text-[var(--app-muted)]">
          First {data.length} of {dataset.rows.length} rows ·{' '}
          {view === 'Changes' && (
            <>
              <span className="rounded bg-amber-100 px-1 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200">
                changed
              </span>{' '}
              <span className="rounded bg-red-100 px-1 text-red-700 dark:bg-red-500/20 dark:text-red-300">
                suppressed
              </span>{' '}
              ·{' '}
            </>
          )}
          {dropped.length} column(s) not released
        </span>
      </div>
      <Table
        rowKey="__i"
        size="small"
        columns={columns}
        dataSource={data}
        pagination={false}
        scroll={{ x: cols.length * 160 }}
      />
    </div>
  )
}
