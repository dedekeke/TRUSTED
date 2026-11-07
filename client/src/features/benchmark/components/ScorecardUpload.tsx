import { UploadOutlined } from '@ant-design/icons'
import { App, Button, Upload } from 'antd'
import type { Scorecard } from '@/types/data.types'
import type { UploadedScorecard } from '@/features/benchmark/hooks/useUploadedScorecards'

export default function ScorecardUpload({ onAdd }: { onAdd: (u: UploadedScorecard) => void }) {
  const { message } = App.useApp()
  return (
    <Upload
      accept=".json,application/json"
      showUploadList={false}
      beforeUpload={async (file) => {
        try {
          const raw = JSON.parse(await file.text()) as Scorecard & { dataset?: string; scenario?: string | null }
          if (!raw.summary || !raw.risk_components) throw new Error('not a pets-eval scorecard.json')
          const name = raw.scenario ? `Ours · ${raw.scenario}` : `Ours · ${file.name.replace(/\.json$/, '')}`
          onAdd({
            name,
            dataset: raw.dataset ?? 'health',
            scorecard: { summary: raw.summary, risk_components: raw.risk_components, utility: raw.utility ?? [] },
          })
          message.success(`Added ${name} to ${raw.dataset ?? 'health'}`)
        } catch (e) {
          message.error(`${file.name}: ${e instanceof Error ? e.message : e}`)
        }
        return false
      }}
    >
      <Button icon={<UploadOutlined />}>Add our scorecard.json</Button>
    </Upload>
  )
}
