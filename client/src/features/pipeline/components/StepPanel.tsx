import { CodeOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Collapse, Empty, Skeleton, Statistic } from 'antd'
import { useEffect, useState } from 'react'
import { ApiError, jobs } from '@/services/api'
import type { Job, JobStep, StepView } from '@/types/job.types'
import ReviewForm from './ReviewForm'
import StepTable from './StepTable'

function RawLog({ jobId, step }: { jobId: string; step: JobStep['name'] }) {
  const [log, setLog] = useState<string | null>(null)
  return (
    <Collapse
      size="small"
      ghost
      onChange={(keys) => {
        if (keys.length && log === null)
          jobs.log(jobId, step).then(
            (r) => setLog(r.log),
            () => setLog('(log unavailable)'),
          )
      }}
      items={[
        {
          key: 'log',
          label: (
            <span className="text-xs text-[var(--app-muted)]">
              <CodeOutlined /> Raw log (for developers; personal-looking values are scrubbed)
            </span>
          ),
          children:
            log === null ? (
              <Skeleton active paragraph={{ rows: 3 }} />
            ) : (
              <pre className="mono max-h-80 overflow-auto rounded bg-black/5 p-3 text-[11px] leading-snug whitespace-pre-wrap dark:bg-white/5">
                {log || '(empty)'}
              </pre>
            ),
        },
      ]}
    />
  )
}

export default function StepPanel({ job, step, onJob }: { job: Job; step: JobStep; onJob: (j: Job) => void }) {
  const [view, setView] = useState<StepView | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const version = `${job.attempt}:${step.status}:${step.finished_at ?? ''}`

  useEffect(() => {
    let alive = true
    if (step.status === 'queued') return
    jobs.step(job.id, step.name).then(
      (v) => alive && (setView(v), setError(null)),
      (e) => alive && setError(e instanceof ApiError ? e : new ApiError('network', String(e))),
    )
    return () => {
      alive = false
    }
  }, [job.id, step.name, step.status, version])

  if (step.status === 'queued') return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Not started yet" />
  if (error)
    return <Alert showIcon type="error" title={`Could not load this step: ${error.code}`} description={error.message} />
  if (!view) return <Skeleton active />

  const review = step.name === 'review' && step.status === 'needs_review' && job.state === 'needs_review'
  const issues = [...view.issues].sort(
    (a, b) => ['error', 'warning', 'info'].indexOf(a.level) - ['error', 'warning', 'info'].indexOf(b.level),
  )
  const nothing = !view.stats.length && !view.tables.some((t) => t.rows.length) && !issues.length

  return (
    <div className="space-y-4">
      {step.error &&
        step.status !== 'needs_review' &&
        (step.status === 'warning' ? (
          <Alert showIcon type="warning" title="Targets not met: continued, not approved" description={step.error} />
        ) : (
          <Alert showIcon type="error" title="Why this step stopped" description={step.error} />
        ))}
      {review && view.tables[0] && <ReviewForm job={job} table={view.tables[0]} onDone={onJob} />}
      {!!issues.length && (
        <Card size="small" title={`Issues (${issues.length})`}>
          <ul className="space-y-1.5">
            {issues.map((i, n) => (
              <li key={n} className="flex gap-2 text-xs">
                <span
                  className={`mono shrink-0 rounded px-1.5 py-0.5 ${
                    i.level === 'error'
                      ? 'bg-red-500/10 text-red-600'
                      : i.level === 'warning'
                        ? 'bg-amber-500/10 text-amber-700'
                        : 'bg-sky-500/10 text-sky-700'
                  }`}
                >
                  {i.code}
                </span>
                <span className="break-words">{i.message}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {!!view.stats.length && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {view.stats.map((s) => (
            <Card key={s.label} size="small">
              <Statistic
                title={<span className="text-xs">{s.label}</span>}
                value={
                  s.value === null || s.value === undefined
                    ? '—'
                    : typeof s.value === 'boolean'
                      ? s.value
                        ? 'yes'
                        : 'no'
                      : s.value
                }
                styles={{ content: { fontSize: 20 } }}
              />
            </Card>
          ))}
        </div>
      )}
      {view.tables
        .filter((t) => !(review && t.id === 'review'))
        .map((t) => (
          <StepTable key={t.id} table={t} highlightFirst={t.id === 'compare'} />
        ))}
      {nothing && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="This step produced no output" />}
      <RawLog jobId={job.id} step={step.name} />
      {step.name === 'transform' && job.download && (
        <Button href={jobs.downloadUrl(job.id)} type="primary">
          Download protected data (.zip)
        </Button>
      )}
    </div>
  )
}
