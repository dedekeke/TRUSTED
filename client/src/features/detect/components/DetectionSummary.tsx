import { Card, Tag } from 'antd'
import StatTile from '@/components/common/StatTile'
import { usePipeline } from '@/hooks/usePipeline'
import type { CatalogEntry } from '@/types/data.types'
import { ROLE_META, ROLES } from '@/utils/constants'
import { pct } from '@/utils/format'

export default function DetectionSummary({ gold }: { gold: Map<string, CatalogEntry> }) {
  const { detections } = usePipeline()
  const graded = detections.filter((d) => gold.has(d.column))
  const correct = graded.filter((d) => gold.get(d.column)!.privacy_role === d.role).length
  const subtypeOk = graded.filter((d) => gold.get(d.column)!.subtype === d.subtype).length
  const uncertain = detections.filter((d) => d.confidence < 0.5).length
  const counts = ROLES.map((r) => [r, detections.filter((d) => d.role === r).length] as const).filter(([, n]) => n > 0)

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <StatTile title="Columns analysed" value={detections.length} hint={`${uncertain} low-confidence (highlighted)`} />
      <StatTile
        title="Role accuracy vs gold"
        value={graded.length ? pct(correct / graded.length, 0) : '—'}
        hint={
          graded.length
            ? `${correct}/${graded.length} columns · subtype ${pct(subtypeOk / graded.length, 0)} · B1 baseline macro-F1 0.65`
            : 'No labels for this table (that is the point of "unseen")'
        }
        accent={graded.length ? (correct / graded.length >= 0.8 ? '#52c41a' : '#faad14') : undefined}
      />
      <Card size="small" className="sm:col-span-2">
        <div className="mb-2 text-xs font-medium tracking-wide text-[var(--app-muted)] uppercase">Data types found</div>
        <div className="flex flex-wrap gap-1.5">
          {counts.map(([r, n]) => (
            <Tag key={r} color={ROLE_META[r].color} className="!m-0">
              {ROLE_META[r].label} · {n}
            </Tag>
          ))}
        </div>
      </Card>
    </div>
  )
}
