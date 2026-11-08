import { riskColor, scoreColor } from '@/utils/format'

interface Props {
  value: number | null | undefined

  kind?: 'score' | 'risk'
  label?: string
  width?: string
}

export default function ScoreBar({ value, kind = 'score', label, width = 'w-full' }: Props) {
  const v = value == null || Number.isNaN(value) ? null : Math.max(0, Math.min(1, value))
  const color = v == null ? '#bfbfbf' : kind === 'risk' ? riskColor(v) : scoreColor(v)
  return (
    <div className={`flex items-center gap-2 ${width}`}>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-black/5 dark:bg-white/10">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${(v ?? 0) * 100}%`, background: color }}
        />
      </div>
      <span className="mono w-14 text-right text-xs text-[var(--app-muted)] tabular-nums">
        {label ?? (v == null ? 'n/a' : kind === 'risk' ? `${(v * 100).toFixed(1)}%` : v.toFixed(2))}
      </span>
    </div>
  )
}
