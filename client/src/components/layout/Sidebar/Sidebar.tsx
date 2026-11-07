import {
  BarChartOutlined,
  CheckCircleFilled,
  DashboardOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { Menu } from 'antd'
import { useLocation, useNavigate } from 'react-router-dom'
import { appConfig } from '@/config/appConfig'
import { usePipeline } from '@/hooks/usePipeline'

export default function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { detections, result, evaluation } = usePipeline()
  const done = (ok: boolean) => (ok ? <CheckCircleFilled className="!text-green-500" /> : null)

  const items = [
    { key: '/', icon: <DashboardOutlined />, label: 'Overview' },
    {
      type: 'group' as const,
      label: 'Pipeline',
      children: [
        {
          key: '/detect',
          icon: <FileSearchOutlined />,
          label: <span className="flex items-center justify-between">1 · Detect {done(detections.length > 0)}</span>,
        },
        {
          key: '/protect',
          icon: <SafetyCertificateOutlined />,
          label: <span className="flex items-center justify-between">2 · Select & transform {done(!!result)}</span>,
        },
        {
          key: '/evaluate',
          icon: <ExperimentOutlined />,
          label: <span className="flex items-center justify-between">3 · Demonstrate {done(!!evaluation)}</span>,
        },
      ],
    },
    {
      type: 'group' as const,
      label: 'Reference',
      children: [
        { key: '/scenarios', icon: <TeamOutlined />, label: 'Sharing scenarios' },
        { key: '/benchmark', icon: <BarChartOutlined />, label: 'Baseline benchmark' },
      ],
    },
  ]

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-5 py-4">
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--app-accent)] text-white">
          <SafetyCertificateOutlined className="text-lg" />
        </div>
        <div className="leading-tight">
          <div className="font-semibold">{appConfig.name}</div>
          <div className="text-[11px] text-[var(--app-muted)]">{appConfig.tagline}</div>
        </div>
      </div>
      <Menu
        mode="inline"
        selectedKeys={[pathname]}
        items={items}
        onClick={({ key }) => {
          navigate(key)
          onNavigate?.()
        }}
        className="!border-e-0"
      />
      <div className="mt-auto px-5 py-4 text-[11px] leading-relaxed text-[var(--app-muted)]">
        Synthetic data only · TrustED PETs Transformer
        <br />
        Since AI Hackathon 2026
      </div>
    </div>
  )
}
