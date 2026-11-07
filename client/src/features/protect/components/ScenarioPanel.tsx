import { Card, Descriptions, Select, Tag } from 'antd'
import { SCENARIOS } from '@/data/scenarios'
import { usePipeline } from '@/hooks/usePipeline'
import { TRUST_META } from '@/utils/constants'

export default function ScenarioPanel() {
  const { scenario, setScenarioId, dataset } = usePipeline()
  const datasets = [...new Set(SCENARIOS.map((s) => s.dataset))]
  const options = datasets.map((d) => ({
    label: d,
    options: SCENARIOS.filter((s) => s.dataset === d).map((s) => ({
      value: s.id,
      label: (
        <span>
          <span className="mono font-medium">{s.id}</span> · {s.title}
        </span>
      ),
    })),
  }))
  // matching dataset first
  if (dataset?.dataset) options.sort((a, b) => (a.label === dataset.dataset ? -1 : b.label === dataset.dataset ? 1 : 0))

  return (
    <Card
      size="small"
      title="Sharing scenario"
      extra={
        scenario && <Tag color={TRUST_META[scenario.trust_level]?.color}>{TRUST_META[scenario.trust_level]?.label}</Tag>
      }
    >
      <Select
        showSearch
        allowClear
        placeholder="Who receives the data, and why?"
        className="mb-3 w-full"
        value={scenario?.id}
        onChange={(v) => setScenarioId(v ?? null)}
        options={options}
        optionFilterProp="value"
      />
      {scenario ? (
        <Descriptions
          size="small"
          column={1}
          colon={false}
          styles={{ label: { width: 110 } }}
          items={[
            { key: 'r', label: 'Recipient', children: scenario.recipient },
            { key: 'p', label: 'Purpose', children: scenario.purpose },
            { key: 't', label: 'Threat model', children: scenario.threat_model },
            { key: 'g', label: 'Targets', children: scenario.suggested_privacy_targets },
            {
              key: 'u',
              label: 'Needs tasks',
              children: (
                <div className="flex flex-wrap gap-1">
                  {scenario.utility_requirements.map((u) => (
                    <Tag key={u} className="mono !m-0">
                      {u}
                    </Tag>
                  ))}
                </div>
              ),
            },
          ]}
        />
      ) : (
        <div className="text-sm text-[var(--app-muted)]">
          Without a scenario, contractual-partner defaults are used.
        </div>
      )}
    </Card>
  )
}
