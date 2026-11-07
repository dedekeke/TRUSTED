import { DownloadOutlined, WarningOutlined } from '@ant-design/icons'
import { Button, Card, Popconfirm, Space } from 'antd'
import type { ColumnDetection, Dataset, ProtectedResult, Scenario } from '@/types/pipeline.types'
import { PET_META } from '@/utils/constants'
import { downloadCsv, downloadJson, downloadText } from '@/utils/download'
import type { Evaluation } from '@/features/evaluate/services/metrics'

interface Props {
  dataset: Dataset
  detections: ColumnDetection[]
  result: ProtectedResult
  ev: Evaluation
  scenario: Scenario | null
}

export default function ExportPanel({ dataset, detections, result, ev, scenario }: Props) {
  const base = dataset.table ?? dataset.name.replace(/\.csv$/i, '')
  const isUnseen = dataset.id.startsWith('unseen__')
  const recordKey = detections.find((d) => d.role === 'record_key')?.column

  const fieldLabels = () => {
    const header = isUnseen ? 'column,privacy_role,subtype' : 'dataset,table,column,privacy_role,subtype'
    const lines = detections.map((d) =>
      (isUnseen
        ? [d.column, d.role, d.subtype]
        : [dataset.dataset ?? 'upload', base, d.column, d.role, d.subtype]
      ).join(','),
    )
    downloadText(
      isUnseen ? 'unseen_field_labels.csv' : `${base}_field_labels.csv`,
      [header, ...lines].join('\n') + '\n',
      'text/csv',
    )
  }

  const report = () =>
    downloadJson(`${base}_protection_report.json`, {
      tool: 'PETs Transformer (web)',
      dataset: dataset.name,
      scenario: scenario ? { id: scenario.id, recipient: scenario.recipient, trust_level: scenario.trust_level } : null,
      k_target: result.kTarget,
      columns: result.policies.map((p) => {
        const d = detections.find((x) => x.column === p.column)
        return {
          column: p.column,
          privacy_role: d?.role,
          subtype: d?.subtype,
          pet: p.pet,
          pet_label: PET_META[p.pet].label,
          level: PET_META[p.pet].levels[p.level] ?? null,
          rationale: p.rationale,
          decided_by: p.source,
        }
      }),
      transform_log: result.log,
      preview_scores: {
        privacy_before: ev.privacyBefore,
        privacy_after: ev.privacyAfter,
        utility: ev.utility,
        composite: ev.composite,
      },
      risks: ev.risks,
      note: 'Pseudonyms use a per-session HMAC-SHA256 key that is never exported.',
    })

  return (
    <Card size="small" title="Export">
      <Space wrap>
        <Button
          type="primary"
          icon={<DownloadOutlined />}
          onClick={() => downloadCsv(`${base}.csv`, result.columns, result.rows)}
        >
          Protected table
        </Button>
        <Button icon={<DownloadOutlined />} onClick={fieldLabels}>
          Field labels (pets-eval detect)
        </Button>
        <Button icon={<DownloadOutlined />} onClick={report}>
          Protection report (JSON)
        </Button>
        {recordKey && (
          <Popconfirm
            icon={<WarningOutlined className="text-red-500" />}
            title="Row map: for scoring only"
            description="It links protected rows back to original records. Never publish or share it."
            okText="Download"
            onConfirm={() =>
              downloadCsv(
                `rowmap_${base}.csv`,
                ['protected_row', 'original_record_id'],
                dataset.rows.map((r, i) => ({ protected_row: String(i), original_record_id: r[recordKey] ?? '' })),
              )
            }
          >
            <Button danger icon={<DownloadOutlined />}>
              Row map
            </Button>
          </Popconfirm>
        )}
      </Space>
      <div className="mt-3 text-xs text-[var(--app-muted)]">
        Official numbers:{' '}
        <span className="mono">
          pets-eval scorecard --original data/{dataset.dataset ?? '<dataset>'} --protected my_out/
          {dataset.dataset ?? '<dataset>'}
          {scenario ? ` --scenario ${scenario.id}` : ''}
        </span>
      </div>
    </Card>
  )
}
