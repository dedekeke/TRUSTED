import { RobotOutlined } from '@ant-design/icons'
import { Alert, Button, Progress } from 'antd'
import type { NanoStatus } from '@/services/onDeviceAI'

interface Props {
  status: NanoStatus
  busy: string | null
  progress: number | null
  error: string | null
  uncertain: number
  onRefine: () => void
}

const TEXT: Record<NanoStatus, string> = {
  available: 'Gemini Nano is ready on this device.',
  downloadable: 'Gemini Nano can be downloaded by Chrome on first use.',
  downloading: 'Chrome is downloading Gemini Nano…',
  unavailable: 'Chrome reports Gemini Nano is unavailable on this device.',
  unsupported: 'This browser has no built-in AI (Chrome Prompt API). The rule-based detector still works.',
}

export default function OnDeviceAIPanel({ status, busy, progress, error, uncertain, onRefine }: Props) {
  const usable = status === 'available' || status === 'downloadable' || status === 'downloading'
  return (
    <Alert
      type={usable ? 'info' : 'warning'}
      showIcon
      icon={<RobotOutlined />}
      title={<span className="font-medium">On-device AI (Google Web AI · Gemini Nano)</span>}
      description={
        <div className="space-y-2">
          <div>
            {TEXT[status]} Column samples stay in the browser: nothing is sent to a server.
            {usable && ` ${uncertain} column(s) have low rule confidence.`}
          </div>
          {progress != null && progress < 1 && <Progress percent={Math.round(progress * 100)} size="small" />}
          {error && <div className="text-red-500">{error}</div>}
        </div>
      }
      action={
        usable && (
          <Button size="small" type="primary" ghost loading={!!busy} disabled={!uncertain} onClick={onRefine}>
            {busy ? `Asking about ${busy}` : 'Refine uncertain columns'}
          </Button>
        )
      }
    />
  )
}
