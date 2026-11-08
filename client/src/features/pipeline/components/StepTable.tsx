import { Card, Input, Table, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMemo, useState } from 'react'
import RoleTag from '@/components/common/RoleTag'
import type { PrivacyRole } from '@/types/pipeline.types'
import type { Cell, ViewTable } from '@/types/job.types'
import { ROLE_META } from '@/utils/constants'

const ACTION_COLORS: Record<string, string> = {
  KEEP: 'green',
  DROP: 'red',
  HMAC: 'blue',
  GENERALISE: 'orange',
  DERIVE: 'gold',
  REDACT: 'purple',
  RELEASE: 'green',
  WITHHOLD: 'default',
}
const GOOD = new Set(['passed', 'validated', 'measured_ok', 'policy_valid', 'ok'])
const BAD = new Set(['failed', 'blocked', 'target_unmet', 'budget_exhausted', 'refused', 'validation_failed'])

function renderCell(key: string, v: Cell) {
  if (v === null || v === undefined || v === '') return <span className="text-[var(--app-muted)]">—</span>
  if (key === 'privacy_role' && typeof v === 'string' && v in ROLE_META) return <RoleTag role={v as PrivacyRole} />
  if (typeof v === 'boolean') {
    const positive = !['needs_review', 'blocking'].includes(key)
    return v ? (
      <Tag color={positive ? 'green' : 'gold'} className="!m-0">
        {positive ? 'yes' : key === 'blocking' ? 'blocking' : 'review'}
      </Tag>
    ) : (
      <span className="text-[var(--app-muted)]">{positive ? 'no' : '—'}</span>
    )
  }
  if (typeof v === 'number') {
    if (Number.isInteger(v)) return <span className="tabular-nums">{v.toLocaleString()}</span>
    return <span className="tabular-nums">{v.toFixed(Math.abs(v) < 10 ? 3 : 1)}</span>
  }
  if ((key === 'action' || key === 'decision') && v in ACTION_COLORS)
    return (
      <Tag color={ACTION_COLORS[v]} className="!m-0">
        {v}
      </Tag>
    )
  if (key === 'status' || key === 'result') {
    const color = GOOD.has(v) ? 'green' : BAD.has(v) ? 'red' : 'default'
    return (
      <Tag color={color} className="!m-0">
        {v}
      </Tag>
    )
  }
  if (['table', 'column', 'subtype', 'method', 'params', 'task', 'left', 'right', 'file', 'sha256'].includes(key))
    return <span className="mono text-xs break-all">{v}</span>
  if (v.length > 120)
    return (
      <Tooltip title={v}>
        <span className="text-xs">{v.slice(0, 117)}…</span>
      </Tooltip>
    )
  return <span className="text-xs">{v}</span>
}

function compare(a: Cell, b: Cell) {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a ?? '').localeCompare(String(b ?? ''))
}

export default function StepTable({ table, highlightFirst }: { table: ViewTable; highlightFirst?: boolean }) {
  const [q, setQ] = useState('')
  const rows = useMemo(() => {
    const all = table.rows.map((r, i) => ({ ...r, __key: i }))
    if (!q) return all
    const needle = q.toLowerCase()
    return all.filter((r) =>
      Object.values(r).some((v) =>
        String(v ?? '')
          .toLowerCase()
          .includes(needle),
      ),
    )
  }, [table.rows, q])

  const columns: ColumnsType<Record<string, Cell>> = table.columns.map((c) => {
    const values = [...new Set(table.rows.map((r) => r[c.key]).filter((v) => typeof v === 'string'))] as string[]
    const categorical = values.length > 1 && values.length <= 12 && table.rows.length > 8
    return {
      title: c.title,
      dataIndex: c.key,
      key: c.key,
      sorter: (a, b) => compare(a[c.key], b[c.key]),
      render: (v: Cell) => renderCell(c.key, v),
      ...(categorical && {
        filters: values.map((v) => ({ text: v, value: v })),
        onFilter: (value, r) => r[c.key] === value,
      }),
    }
  })

  return (
    <Card
      size="small"
      title={<span className="font-medium">{table.title}</span>}
      extra={
        table.rows.length > 10 && (
          <Input.Search
            allowClear
            size="small"
            placeholder="Search"
            className="!w-48"
            onChange={(e) => setQ(e.target.value)}
          />
        )
      }
    >
      {table.note && <div className="mb-2 text-xs text-[var(--app-muted)]">{table.note}</div>}
      <Table
        size="small"
        rowKey="__key"
        columns={columns}
        dataSource={rows}
        scroll={{ x: 'max-content' }}
        pagination={rows.length > 15 ? { pageSize: 15, size: 'small', showSizeChanger: false } : false}
        locale={{ emptyText: 'Nothing to show' }}
        rowClassName={(_, i) =>
          highlightFirst && i === 0 ? 'bg-[var(--app-accent-soft,rgba(37,99,235,0.08))] font-medium' : ''
        }
      />
    </Card>
  )
}
