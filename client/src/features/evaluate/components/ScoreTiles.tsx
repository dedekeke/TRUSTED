import { ArrowRightOutlined } from '@ant-design/icons'
import StatTile from '@/components/common/StatTile'
import type { Evaluation } from '@/features/evaluate/services/metrics'
import { scoreColor } from '@/utils/format'

export default function ScoreTiles({ ev }: { ev: Evaluation }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <StatTile
        title="Privacy (1 − risk)"
        value={
          <span className="flex items-center gap-2">
            <span className="text-base text-[var(--app-muted)]">{ev.privacyBefore.toFixed(2)}</span>
            <ArrowRightOutlined className="text-sm text-[var(--app-muted)]" />
            <span style={{ color: scoreColor(ev.privacyAfter) }}>{ev.privacyAfter.toFixed(2)}</span>
          </span>
        }
        hint="1 − (0.5 × worst + 0.5 × mean risk)"
      />
      <StatTile
        title="Utility retained"
        value={ev.utility.toFixed(2)}
        accent={scoreColor(ev.utility)}
        hint="Mean over analytical columns"
      />
      <StatTile
        title="Composite"
        value={ev.composite.toFixed(2)}
        accent={scoreColor(ev.composite)}
        hint="Harmonic mean, privacy 30 · utility 25"
      />
      <StatTile
        title="k-anonymity"
        value={
          <span>
            {ev.kBefore.minK} <ArrowRightOutlined className="text-sm text-[var(--app-muted)]" /> {ev.kAfter.minK}
          </span>
        }
        hint={`min class size on ${ev.kAfter.qis.length} quasi-identifier(s)`}
      />
    </div>
  )
}
