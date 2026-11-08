import { scoreColor } from '@/utils/format'

export interface MetricSeries {
  name: string
  values: Record<string, number | null>
  highlight?: boolean
}

interface Props {
  metrics: string[]
  series: MetricSeries[]
}

export default function MetricBars({ metrics, series }: Props) {
  return (
    <div className="space-y-4">
      {metrics.map((m) => (
        <div key={m}>
          <div className="mb-1.5 text-xs font-semibold tracking-wide text-[var(--app-muted)] uppercase">{m}</div>
          <div className="space-y-1">
            {series.map((s) => {
              const v = s.values[m]
              return (
                <div key={s.name} className="flex items-center gap-2">
                  <div
                    className={`w-24 shrink-0 truncate text-xs ${s.highlight ? 'font-semibold' : 'text-[var(--app-muted)]'}`}
                  >
                    {s.name}
                  </div>
                  <div className="h-4 flex-1 overflow-hidden rounded bg-black/5 dark:bg-white/10">
                    <div
                      className="h-full rounded transition-all"
                      style={{
                        width: `${Math.max(0, Math.min(1, v ?? 0)) * 100}%`,
                        background: s.highlight ? 'var(--app-accent)' : scoreColor(v),
                        opacity: s.highlight ? 1 : 0.55,
                      }}
                    />
                  </div>
                  <div className="mono w-10 text-right text-xs tabular-nums">{v == null ? '–' : v.toFixed(2)}</div>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
