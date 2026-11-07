import { CheckCircleTwoTone, CloseCircleTwoTone, RobotOutlined } from '@ant-design/icons'
import { Button, Popover, Progress, Select, Table, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import RoleTag from '@/components/common/RoleTag'
import { usePipeline } from '@/hooks/usePipeline'
import type { CatalogEntry } from '@/types/data.types'
import type { ColumnDetection, PrivacyRole } from '@/types/pipeline.types'
import { ROLE_META, ROLES, SUBTYPES } from '@/utils/constants'

interface Props {
  gold: Map<string, CatalogEntry>
  aiAvailable: boolean
  aiBusy: string | null
  onAskAI: (d: ColumnDetection) => void
}

export default function DetectionTable({ gold, aiAvailable, aiBusy, onAskAI }: Props) {
  const { detections, updateDetection } = usePipeline()

  const columns: ColumnsType<ColumnDetection> = [
    {
      title: 'Column',
      dataIndex: 'column',
      fixed: 'left',
      width: 200,
      render: (c: string, d) => (
        <Popover
          title={<span className="mono">{c}</span>}
          content={
            <div className="max-w-xs space-y-1 text-xs">
              <div>
                {d.stats.distinct.toLocaleString()} distinct of {d.stats.nonEmpty.toLocaleString()} non-empty · avg
                length {d.stats.avgLength.toFixed(1)}
              </div>
              <div className="flex flex-wrap gap-1">
                {d.stats.examples.slice(0, 8).map((e) => (
                  <Tag key={e} className="mono !m-0 max-w-[16rem] truncate">
                    {e}
                  </Tag>
                ))}
              </div>
            </div>
          }
        >
          <div className="cursor-help">
            <div className="mono font-medium">{c}</div>
            <div className="max-w-[180px] truncate text-xs text-[var(--app-muted)]">
              {d.stats.examples.slice(0, 3).join(' · ') || '(empty)'}
            </div>
          </div>
        </Popover>
      ),
    },
    {
      title: 'Privacy role',
      dataIndex: 'role',
      width: 210,
      filters: ROLES.map((r) => ({ text: ROLE_META[r].label, value: r })),
      onFilter: (v, d) => d.role === v,
      render: (role: PrivacyRole, d) => (
        <Select
          size="small"
          value={role}
          variant="borderless"
          className="w-full"
          popupMatchSelectWidth={false}
          onChange={(r) =>
            updateDetection(d.column, {
              role: r,
              confidence: 1,
              reasons: ['set manually by the analyst', ...d.reasons],
            })
          }
          options={ROLES.map((r) => ({ value: r, label: <RoleTag role={r} /> }))}
        />
      ),
    },
    {
      title: 'Subtype',
      dataIndex: 'subtype',
      width: 170,
      render: (st: string, d) => (
        <Select
          size="small"
          showSearch
          value={st}
          variant="borderless"
          className="mono w-full"
          popupMatchSelectWidth={false}
          onChange={(s) => updateDetection(d.column, { subtype: s })}
          options={SUBTYPES.map((s) => ({ value: s, label: <span className="mono text-xs">{s}</span> }))}
        />
      ),
    },
    {
      title: 'Confidence',
      dataIndex: 'confidence',
      width: 120,
      sorter: (a, b) => a.confidence - b.confidence,
      render: (c: number) => (
        <Progress
          percent={Math.round(c * 100)}
          size="small"
          strokeColor={c >= 0.75 ? '#52c41a' : c >= 0.5 ? '#faad14' : '#ff4d4f'}
        />
      ),
    },
    {
      title: 'Why',
      dataIndex: 'reasons',
      render: (rs: string[], d) => (
        <div className="text-xs leading-relaxed">
          {d.source !== 'rules' && (
            <Tag color={d.source === 'manual' ? 'default' : 'geekblue'} className="!mr-1 !mb-1">
              {d.source}
            </Tag>
          )}
          {rs.slice(0, 2).join('; ')}
        </div>
      ),
    },
    ...(gold.size
      ? [
          {
            title: (
              <Tooltip title="Compared with metadata/field_catalog.csv (the answer key the baselines peek at)">
                Gold
              </Tooltip>
            ),
            key: 'gold',
            width: 70,
            align: 'center' as const,
            render: (_: unknown, d: ColumnDetection) => {
              const g = gold.get(d.column)
              if (!g) return '–'
              const ok = g.privacy_role === d.role
              return (
                <Tooltip title={`${ROLE_META[g.privacy_role]?.label} · ${g.subtype} — ${g.description}`}>
                  {ok ? <CheckCircleTwoTone twoToneColor="#52c41a" /> : <CloseCircleTwoTone twoToneColor="#ff4d4f" />}
                </Tooltip>
              )
            },
          },
        ]
      : []),
    ...(aiAvailable
      ? [
          {
            title: '',
            key: 'ai',
            width: 56,
            render: (_: unknown, d: ColumnDetection) => (
              <Tooltip title="Ask Gemini Nano (on-device)">
                <Button
                  size="small"
                  type="text"
                  icon={<RobotOutlined />}
                  loading={aiBusy === d.column}
                  onClick={() => onAskAI(d)}
                />
              </Tooltip>
            ),
          },
        ]
      : []),
  ]

  return (
    <Table
      rowKey="column"
      size="small"
      columns={columns}
      dataSource={detections}
      pagination={false}
      scroll={{ x: 1000 }}
      rowClassName={(d) => (d.confidence < 0.5 ? 'bg-amber-50/60 dark:bg-amber-500/5' : '')}
    />
  )
}
