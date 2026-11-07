import { ArrowRightOutlined } from '@ant-design/icons'
import { Button, Card } from 'antd'
import { useNavigate } from 'react-router-dom'
import EmptyState from '@/components/common/EmptyState'
import PageHeader from '@/components/common/PageHeader'
import { CATALOG } from '@/data/catalog'
import { DatasetPicker, DetectionSummary, DetectionTable, OnDeviceAIPanel, useOnDeviceAI } from '@/features/detect'
import { usePipeline } from '@/hooks/usePipeline'

export default function Detect() {
  const navigate = useNavigate()
  const { dataset, detections } = usePipeline()
  const ai = useOnDeviceAI()
  const gold = new Map(
    CATALOG.filter((c) => c.dataset === dataset?.dataset && c.table === dataset?.table).map((c) => [c.column, c]),
  )
  const uncertain = detections.filter((d) => d.confidence < 0.5)
  const aiUsable = ai.status !== 'unsupported' && ai.status !== 'unavailable'

  return (
    <div className="space-y-5">
      <PageHeader
        step="Step 1"
        title="Detect data types"
        description="Every column gets a privacy role and subtype from its name, its value patterns and its statistics. Each label shows why it was chosen. Click a role to correct it."
        extra={
          detections.length > 0 && (
            <Button
              type="primary"
              icon={<ArrowRightOutlined />}
              iconPlacement="end"
              onClick={() => navigate('/protect')}
            >
              Select PETs
            </Button>
          )
        }
      />
      <DatasetPicker />
      {dataset ? (
        <>
          <DetectionSummary gold={gold} />
          <OnDeviceAIPanel
            status={ai.status}
            busy={ai.busy}
            progress={ai.progress}
            error={ai.error}
            uncertain={uncertain.length}
            onRefine={() => ai.refine(uncertain)}
          />
          <Card size="small" title={<span className="mono">{dataset.name}</span>}>
            <DetectionTable gold={gold} aiAvailable={aiUsable} aiBusy={ai.busy} onAskAI={(d) => ai.refine([d])} />
          </Card>
        </>
      ) : (
        <EmptyState
          title="Pick a sample table or drop a CSV"
          description="Try unseen/export_2025_q4: 26 columns named c01…c26, no labels."
        />
      )}
    </div>
  )
}
