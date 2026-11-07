import { InputNumber, Switch, Tooltip } from 'antd'
import { appConfig } from '@/config/appConfig'
import { usePipeline } from '@/hooks/usePipeline'

export default function KAnonymityControl() {
  const { kTarget, setKTarget } = usePipeline()
  return (
    <div className="flex items-center gap-2">
      <Tooltip title="Climb the generalisation ladders of the quasi-identifiers until every row is in a group of at least k; suppress single cells only as a last resort">
        <span className="text-sm">Enforce k-anonymity</span>
      </Tooltip>
      <Switch size="small" checked={kTarget != null} onChange={(on) => setKTarget(on ? appConfig.defaultK : null)} />
      {kTarget != null && (
        <InputNumber
          size="small"
          min={2}
          max={50}
          value={kTarget}
          onChange={(v) => setKTarget(v ?? appConfig.defaultK)}
          prefix="k ≥"
          className="w-24"
        />
      )}
    </div>
  )
}
