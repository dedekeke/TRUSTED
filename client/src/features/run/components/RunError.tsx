import { Alert } from 'antd'
import type { ApiError } from '@/services/api'
import type { RunState } from '@/types/run.types'

export default function RunError({ error, run }: { error: ApiError | null; run: RunState | null }) {
  return (
    <>
      {error && <Alert showIcon type="error" title={`Request failed: ${error.code}`} description={error.message} />}
      {!!run?.errors.length && (
        <Alert
          showIcon
          type="warning"
          title="Errors recorded on this run"
          description={
            <ul className="mono list-disc pl-4 text-xs">
              {run.errors.map((e, i) => (
                <li key={i}>
                  {e.step}: [{e.code}] {e.message}
                </li>
              ))}
            </ul>
          }
        />
      )}
    </>
  )
}
