import { DownloadOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Skeleton, Tag, Tooltip } from 'antd'
import { useNavigate } from 'react-router-dom'
import { jobs } from '@/services/api'
import { useJob } from '../hooks/useJob'
import { useLeaveGuard } from '../hooks/useLeaveGuard'
import { JOB_META } from '../stepMeta'
import StatusIcon from './StatusIcon'
import RunTimeline from './RunTimeline'

/** One run: header (dataset, scenario, state, parameters) and the step timeline. */
export default function JobView({ id }: { id: string }) {
  const navigate = useNavigate()
  const { job, error, refresh, setJob } = useJob(id)
  useLeaveGuard(id, job?.state === 'running')

  if (error && !job)
    return <Alert showIcon type="error" title={`Could not load run ${id}: ${error.code}`} description={error.message} />
  if (!job) return <Skeleton active />

  const meta = JOB_META[job.state]
  const p = job.params
  const passed = job.steps.filter((s) => s.status === 'success').length

  return (
    <div className="space-y-4">
      <Card size="small">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <StatusIcon
              size={26}
              status={
                job.state === 'succeeded'
                  ? 'success'
                  : job.state === 'failed'
                    ? 'failed'
                    : job.state === 'needs_review'
                      ? 'needs_review'
                      : job.state === 'cancelled'
                        ? 'skipped'
                        : 'running'
              }
            />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-lg font-semibold">{job.dataset}</span>
                {p?.scenario && <Tag color="blue">{p.scenario}</Tag>}
                {p?.spec && <Tag>custom spec</Tag>}
                <Tag color={meta.color}>{meta.label}</Tag>
                {job.attempt > 1 && <Tag color="gold">reviewed · attempt {job.attempt}</Tag>}
              </div>
              <div className="mono mt-0.5 text-xs text-[var(--app-muted)]">
                run {job.id} ·{' '}
                {job.source === 'upload' ? `${job.uploaded_files.length} uploaded files` : 'bundled dataset'}
                {p &&
                  ` · budget ${p.budget} · τ ${p.tau} · LLM ${p.llm ? 'on' : 'off'}${p.allow_unapproved ? ' · allow-unapproved' : ''}`}
                {` · ${passed}/${job.steps.length} steps passed`}
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            <Tooltip title="Refresh">
              <Button icon={<ReloadOutlined />} onClick={refresh} />
            </Tooltip>
            <Button
              icon={<DownloadOutlined />}
              disabled={!job.download}
              href={job.download ? jobs.downloadUrl(job.id) : undefined}
            >
              Protected data
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/run')}>
              New run
            </Button>
          </div>
        </div>
      </Card>
      {error && (
        <Alert showIcon type="warning" title="Lost contact with the API; retrying" description={error.message} />
      )}
      <RunTimeline job={job} onJob={(j) => (setJob(j), refresh())} />
    </div>
  )
}
