import { Collapse, Tooltip } from 'antd'
import { useState } from 'react'
import type { Job, JobStep, StepName } from '@/types/job.types'
import { formatDuration, STATUS_META, STEP_TITLES } from '../stepMeta'
import StatusIcon from './StatusIcon'
import StepPanel from './StepPanel'

/** A step opens by itself when it fails, waits for a review, or is the finished evaluation. */
const openByDefault = (s: JobStep) =>
  s.status === 'failed' || s.status === 'needs_review' || (s.name === 'evaluate' && s.status === 'success')

/** GitHub-Actions-like list of steps: green = passed, red = failed; expand a step to see its tables. */
export default function RunTimeline({ job, onJob }: { job: Job; onJob: (j: Job) => void }) {
  // the user's open/close choice, kept until that step's status (or the attempt) changes
  const [choice, setChoice] = useState<Record<string, boolean>>({})
  const stateKey = (s: JobStep) => `${job.attempt}:${s.name}:${s.status}`
  const open = job.steps.filter((s) => choice[stateKey(s)] ?? openByDefault(s)).map((s) => s.name)

  return (
    <Collapse
      activeKey={open}
      onChange={(keys) => {
        const next = new Set(keys as string[])
        setChoice((c) => ({ ...c, ...Object.fromEntries(job.steps.map((s) => [stateKey(s), next.has(s.name)])) }))
      }}
      className="overflow-hidden"
      items={job.steps.map((s, i) => {
        const meta = STATUS_META[s.status]
        return {
          key: s.name,
          collapsible: s.status === 'queued' ? ('disabled' as const) : undefined,
          label: (
            <div className="flex min-w-0 items-start gap-3">
              <StatusIcon status={s.status} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <Tooltip title={STEP_TITLES[s.name as StepName].hint}>
                    <span className="font-medium">
                      {i + 1}. {STEP_TITLES[s.name as StepName].title}
                    </span>
                  </Tooltip>
                  <span className="text-xs font-medium" style={{ color: meta.color }}>
                    {meta.label}
                  </span>
                  {s.summary && <span className="truncate text-xs text-[var(--app-muted)]">{s.summary}</span>}
                </div>
                {s.error && (s.status === 'failed' || s.status === 'needs_review') && (
                  <div className="mt-0.5 line-clamp-2 text-xs" style={{ color: meta.color }}>
                    {s.error}
                  </div>
                )}
              </div>
            </div>
          ),
          extra: <span className="mono text-xs text-[var(--app-muted)]">{formatDuration(s.duration_s)}</span>,
          children: <StepPanel job={job} step={s} onJob={onJob} />,
        }
      })}
    />
  )
}
