import { Button, Card, Tag } from 'antd'
import type { Scenario } from '@/types/pipeline.types'
import { TRUST_META } from '@/utils/constants'

interface Props {
  scenario: Scenario
  active: boolean
  onUse: () => void
}

export default function ScenarioCard({ scenario: s, active, onUse }: Props) {
  return (
    <Card
      size="small"
      className={`h-full ${active ? '!border-[var(--app-accent)] !shadow-[0_0_0_1px_var(--app-accent)]' : ''}`}
      title={
        <div className="flex items-center gap-2">
          <span className="mono">{s.id}</span>
          <Tag color={TRUST_META[s.trust_level]?.color} className="!m-0">
            {TRUST_META[s.trust_level]?.label}
          </Tag>
        </div>
      }
      extra={
        <Button size="small" type={active ? 'primary' : 'default'} onClick={onUse}>
          {active ? 'Selected' : 'Use'}
        </Button>
      }
    >
      <div className="mb-2 font-medium">{s.title}</div>
      <dl className="space-y-1.5 text-xs">
        <div>
          <dt className="inline font-semibold">Recipient: </dt>
          <dd className="inline text-[var(--app-muted)]">{s.recipient}</dd>
        </div>
        <div>
          <dt className="inline font-semibold">Purpose: </dt>
          <dd className="inline text-[var(--app-muted)]">{s.purpose}</dd>
        </div>
        <div>
          <dt className="inline font-semibold">Threat: </dt>
          <dd className="inline text-[var(--app-muted)]">{s.threat_model}</dd>
        </div>
        <div>
          <dt className="inline font-semibold">Targets: </dt>
          <dd className="inline text-[var(--app-muted)]">{s.suggested_privacy_targets}</dd>
        </div>
      </dl>
    </Card>
  )
}
