import { ArrowRightOutlined, CheckOutlined, ScanOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Select, Table, Tag } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import EmptyState from '@/components/common/EmptyState'
import PageHeader from '@/components/common/PageHeader'
import RoleTag from '@/components/common/RoleTag'
import { useFetch } from '@/hooks/useFetch'
import { backend } from '@/services/api'
import type { RunLabel } from '@/types/run.types'
import RunError from './RunError'
import { useRun } from '../hooks/useRun'

const LABEL_COLUMNS = [
  { title: 'Table', dataIndex: 'table', render: (t: string) => <span className="mono">{t}</span> },
  { title: 'Column', dataIndex: 'column', render: (c: string) => <span className="mono font-medium">{c}</span> },
  { title: 'Privacy role', dataIndex: 'privacy_role', render: (r: RunLabel['privacy_role']) => <RoleTag role={r} /> },
  { title: 'Subtype', dataIndex: 'subtype', render: (s: string) => <span className="mono text-xs">{s}</span> },
  {
    title: 'Confidence',
    dataIndex: 'confidence',
    sorter: (a: RunLabel, b: RunLabel) => a.confidence - b.confidence,
    render: (c: number) => c.toFixed(3),
  },
  {
    title: 'Review',
    dataIndex: 'needs_review',
    render: (n: boolean) => (n ? <Tag color="gold">needs review</Tag> : null),
  },
]

export default function RunDetect() {
  const navigate = useNavigate()
  const { run, busy, error, act } = useRun()
  const { data: datasets } = useFetch(backend.datasets)
  const [dataset, setDataset] = useState<string | null>(null)
  const chosen = dataset ?? run?.dataset ?? null

  const confirmQueue = () =>
    run &&
    act('confirm', () =>
      backend.confirm(
        run.id,
        run.detect_review.map(({ table, column, privacy_role, subtype }) => ({ table, column, privacy_role, subtype })),
      ),
    )

  return (
    <div className="space-y-5">
      <PageHeader
        step="Step 1"
        title="Detect data types (server)"
        description="Detect v3 runs on the server against the whole dataset. Only labels, counts and digests come back; no cell values."
        extra={
          <>
            <Select
              className="w-48"
              placeholder="Dataset"
              value={chosen}
              onChange={setDataset}
              options={(datasets ?? []).map((d) => ({ value: d, label: d }))}
            />
            <Button
              type="primary"
              icon={<ScanOutlined />}
              loading={busy === 'detect'}
              disabled={!chosen || !!busy}
              onClick={() => chosen && act('detect', () => backend.createRun(chosen))}
            >
              Run detect
            </Button>
            {run?.steps.detect && (
              <Button
                icon={<ArrowRightOutlined />}
                iconPlacement="end"
                onClick={() => navigate(`/protect?run=${run.id}`)}
              >
                Select PETs
              </Button>
            )}
          </>
        }
      />
      <RunError error={error} run={run} />
      {run?.manifest ? (
        <>
          <Card size="small" title={<span className="mono">run {run.id}</span>}>
            <Descriptions size="small" column={{ xs: 1, md: 2 }}>
              <Descriptions.Item label="Dataset">{run.manifest.dataset}</Descriptions.Item>
              <Descriptions.Item label="Fingerprint">
                <span className="mono">{run.manifest.dataset_fingerprint.slice(0, 16)}…</span>
              </Descriptions.Item>
              <Descriptions.Item label="Detector">
                <span className="mono">
                  {run.manifest.detector.name} {run.manifest.detector.version}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label="Tables">
                {Object.entries(run.manifest.tables)
                  .map(([t, v]) => `${t} (${v.rows.toLocaleString()} rows, ${v.columns} cols)`)
                  .join(', ')}
              </Descriptions.Item>
            </Descriptions>
          </Card>
          <Card
            size="small"
            title={`Review queue: ${run.detect_review.length} column(s) need a reviewer`}
            extra={
              run.steps.confirm ? (
                <Tag color="green">reviewer-confirmed ({run.confirmation?.count}), no downgrade</Tag>
              ) : (
                <Button
                  size="small"
                  icon={<CheckOutlined />}
                  loading={busy === 'confirm'}
                  disabled={!run.detect_review.length || !!busy}
                  onClick={confirmQueue}
                >
                  Confirm detected labels (no downgrade)
                </Button>
              )
            }
          >
            <Table
              rowKey={(r) => `${r.table}.${r.column}`}
              size="small"
              pagination={false}
              columns={LABEL_COLUMNS}
              dataSource={run.detect_review}
            />
          </Card>
          <Card size="small" title={`All labels (${run.labels.length})`}>
            <Table
              rowKey={(r) => `${r.table}.${r.column}`}
              size="small"
              pagination={{ pageSize: 25 }}
              columns={LABEL_COLUMNS}
              dataSource={run.labels}
            />
          </Card>
        </>
      ) : (
        <EmptyState
          title="Pick a dataset and run detect"
          description="Each run writes a fresh directory on the server."
        />
      )}
    </div>
  )
}
