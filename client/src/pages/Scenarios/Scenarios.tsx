import { Segmented, Select } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageHeader from '@/components/common/PageHeader'
import { SCENARIOS } from '@/data/scenarios'
import { ScenarioCard } from '@/features/scenarios'
import { usePipeline } from '@/hooks/usePipeline'
import { TRUST_META } from '@/utils/constants'
import type { TrustLevel } from '@/types/pipeline.types'

export default function Scenarios() {
  const navigate = useNavigate()
  const { scenario, setScenarioId, dataset } = usePipeline()
  const [ds, setDs] = useState<string>(dataset?.dataset ?? 'all')
  const [trust, setTrust] = useState<'all' | TrustLevel>('all')
  const datasets = [...new Set(SCENARIOS.map((s) => s.dataset))]
  const shown = SCENARIOS.filter(
    (s) => (ds === 'all' || s.dataset === ds) && (trust === 'all' || s.trust_level === trust),
  )

  return (
    <div>
      <PageHeader
        title="Sharing scenarios"
        description="Who receives the data and why. The scenario decides how strict each PET is and which analyses must still work."
        extra={
          <>
            <Select
              className="w-44"
              value={ds}
              onChange={setDs}
              options={[{ value: 'all', label: 'All datasets' }, ...datasets.map((d) => ({ value: d, label: d }))]}
            />
            <Segmented
              value={trust}
              onChange={(v) => setTrust(v as 'all' | TrustLevel)}
              options={[
                { value: 'all', label: 'All' },
                ...(Object.keys(TRUST_META) as TrustLevel[]).map((t) => ({
                  value: t,
                  label: TRUST_META[t].label.split(' ')[0],
                })),
              ]}
            />
          </>
        }
      />
      <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
        {shown.map((s) => (
          <ScenarioCard
            key={s.id}
            scenario={s}
            active={scenario?.id === s.id}
            onUse={() => {
              setScenarioId(s.id)
              if (dataset) navigate('/protect')
            }}
          />
        ))}
      </div>
    </div>
  )
}
