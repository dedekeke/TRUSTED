import { Card, Timeline } from 'antd'
import type { TransformLogEntry } from '@/types/pipeline.types'

export default function TransformLog({ log }: { log: TransformLogEntry[] }) {
  return (
    <Card size="small" title="What the transformer did">
      <Timeline
        className="!mt-2"
        items={log.map((e) => ({
          color: e.step.startsWith('Local suppression')
            ? 'red'
            : e.step.startsWith('Generalise')
              ? 'orange'
              : e.step === 'Result'
                ? 'green'
                : 'blue',
          content: (
            <div>
              <div className="text-sm font-medium">{e.step}</div>
              <div className="text-xs text-[var(--app-muted)]">{e.detail}</div>
            </div>
          ),
        }))}
      />
    </Card>
  )
}
