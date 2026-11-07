import { ArrowRightOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { Button, Card } from 'antd'
import { useNavigate } from 'react-router-dom'
import EmptyState from '@/components/common/EmptyState'
import PageHeader from '@/components/common/PageHeader'
import { BeforeAfterPreview, KAnonymityControl, PolicyTable, ScenarioPanel, TransformLog } from '@/features/protect'
import { usePipeline } from '@/hooks/usePipeline'

export default function Protect() {
  const navigate = useNavigate()
  const { dataset, result, running, runProtection, resetPolicies } = usePipeline()
  if (!dataset)
    return (
      <EmptyState
        title="No dataset yet"
        description="Detect the data types first."
        actionLabel="Go to Detect"
        to="/detect"
      />
    )

  return (
    <div className="space-y-5">
      <PageHeader
        step="Step 2"
        title="Select PETs and transform"
        description="The policy engine proposes a PET for each data type, stricter for open data and lighter for controlled research. Change any choice, then run the transformer."
        extra={
          <>
            <Button icon={<ReloadOutlined />} onClick={resetPolicies}>
              Reset to policy
            </Button>
            <Button type="primary" icon={<ThunderboltOutlined />} loading={running} onClick={runProtection}>
              Run transformer
            </Button>
            {result && (
              <Button icon={<ArrowRightOutlined />} iconPlacement="end" onClick={() => navigate('/evaluate')}>
                Demonstrate
              </Button>
            )}
          </>
        }
      />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card size="small" title="PET per column" extra={<KAnonymityControl />}>
          <PolicyTable />
        </Card>
        <div className="space-y-4">
          <ScenarioPanel />
          {result && <TransformLog log={result.log} />}
        </div>
      </div>
      {result && (
        <Card size="small" title="Protected output">
          <BeforeAfterPreview dataset={dataset} result={result} />
        </Card>
      )}
    </div>
  )
}
