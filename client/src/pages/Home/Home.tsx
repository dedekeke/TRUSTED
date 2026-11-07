import {
  ArrowRightOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { Button, Card, Steps } from 'antd'
import { useNavigate } from 'react-router-dom'
import StatTile from '@/components/common/StatTile'
import { appConfig } from '@/config/appConfig'
import { usePipeline } from '@/hooks/usePipeline'
import { DEMO_REQUIREMENTS } from '@/utils/constants'

export default function Home() {
  const navigate = useNavigate()
  const { dataset, detections, policies, result, evaluation, scenario } = usePipeline()
  const status: Record<string, boolean> = {
    detect: detections.length > 0,
    select: policies.length > 0,
    transform: !!result,
    utility: !!evaluation,
    scenario: !!scenario,
  }
  const current = !dataset ? 0 : !result ? 1 : !evaluation ? 2 : 3

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-2xl border border-[var(--app-border)] bg-gradient-to-br from-indigo-600 to-blue-500 p-6 text-white sm:p-8">
        <div className="max-w-2xl">
          <div className="text-xs font-semibold tracking-widest text-white/70 uppercase">
            TrustED PETs Transformer · Since AI 2026
          </div>
          <h1 className="mt-2 text-3xl leading-tight font-bold sm:text-4xl">{appConfig.tagline}</h1>
          <p className="mt-3 text-white/85">
            Detect what every column and text field contains, choose a privacy-enhancing technology that fits the
            sharing scenario, transform the data, and show what risk was removed and what value was kept.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button
              size="large"
              className="!border-white !bg-white !text-indigo-700 hover:!bg-indigo-50 hover:!text-indigo-800"
              icon={<ArrowRightOutlined />}
              iconPlacement="end"
              onClick={() => navigate('/detect')}
            >
              Start with a dataset
            </Button>
            <Button
              size="large"
              ghost
              className="!border-white !text-white hover:!border-white hover:!bg-white hover:!text-indigo-700"
              onClick={() => navigate('/benchmark')}
            >
              See the baselines to beat
            </Button>
          </div>
        </div>
      </section>

      <Card>
        <Steps
          current={current}
          onChange={(i) => navigate(['/detect', '/protect', '/protect', '/evaluate'][i])}
          items={[
            { title: 'Detect', icon: <FileSearchOutlined />, content: 'Data types per column' },
            { title: 'Select', icon: <TeamOutlined />, content: 'PET per data type, per scenario' },
            { title: 'Transform', icon: <SafetyCertificateOutlined />, content: 'Protected output' },
            { title: 'Demonstrate', icon: <ExperimentOutlined />, content: 'Risk and utility, before vs after' },
          ]}
        />
      </Card>

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <Card title="What the final demo must show" size="small">
          <ul className="divide-y divide-[var(--app-border)]">
            {DEMO_REQUIREMENTS.map((r, i) => (
              <li key={r.key} className="flex items-center justify-between gap-3 py-2.5">
                <div className="flex items-center gap-3">
                  {status[r.key] ? (
                    <CheckCircleFilled className="text-lg !text-green-500" />
                  ) : (
                    <ClockCircleOutlined className="text-lg text-[var(--app-muted)]" />
                  )}
                  <span>
                    <span className="text-[var(--app-muted)]">{i + 1}.</span> {r.title}
                  </span>
                </div>
                <Button size="small" type="link" onClick={() => navigate(r.path)}>
                  Open
                </Button>
              </li>
            ))}
          </ul>
        </Card>
        <div className="grid grid-cols-2 gap-3">
          <StatTile
            title="Datasets"
            value="9 + 1"
            hint="One synthetic population of 100,000 people; the extra one is the unlabelled 'unseen' export"
          />
          <StatTile title="Sharing scenarios" value="27" hint="Public, contractual, internal, controlled research" />
          <StatTile title="Labelled PII spans" value="354k" hint="For scoring free-text redaction" />
          <StatTile
            title="Composite to beat"
            value="0.49"
            hint="HEALTH-S1: B2 0.49 · B2-k 0.48 · quickstart 0.49"
            accent="#fa8c16"
          />
        </div>
      </div>
    </div>
  )
}
