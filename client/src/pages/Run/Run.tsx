import { Alert } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import PageHeader from '@/components/common/PageHeader'
import { JobView, NewRunForm } from '@/features/pipeline'
import { backend } from '@/services/api'

export default function Run() {
  const { id } = useParams()
  const navigate = useNavigate()

  return (
    <div className="space-y-5">
      <PageHeader
        step="Pipeline"
        title={id ? 'Pipeline run' : 'Run the pipeline'}
        description="Input → Detect → Review → Select → Search → Transform → Evaluate. Green steps passed, red steps failed; open a step to see its results as tables."
      />
      {!backend.enabled ? (
        <Alert
          showIcon
          type="info"
          title="The pipeline runs on the local API"
          description={
            <span className="text-xs">
              Start{' '}
              <span className="mono">
                PRIVACY_TOOL_HMAC_KEY=… python -m server.api --model &lt;detect model&gt; --runs &lt;dir&gt;
              </span>{' '}
              and run the client with <span className="mono">VITE_API_BASE_URL=/</span>.
            </span>
          }
        />
      ) : id ? (
        <JobView id={id} />
      ) : (
        <NewRunForm onStarted={(job) => navigate(`/run/${job.id}`)} />
      )}
    </div>
  )
}
