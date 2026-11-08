import { Alert } from 'antd'
import type { PlanSummary } from '@/types/run.types'

const TEXT = {
  policy_valid: ['info', 'Policy valid — not yet measured', 'Initial plan is within the rule matrix. Not approved.'],
  blocked: ['error', 'Blocked — not approved', 'Named conflicts must be resolved; nothing may be released.'],
  target_unmet: [
    'warning',
    'Target unmet — not approved',
    'The allowed candidate space was searched and no candidate meets the targets.',
  ],
  budget_exhausted: [
    'warning',
    'Budget exhausted — not approved',
    'The evaluation budget ran out with unexplored candidates. This does not show the targets are unreachable.',
  ],
  measured_ok: ['warning', 'Targets met — awaiting approval', 'Measured candidate meets the targets.'],
} as const

export default function StatusBanner({ plan, stage }: { plan: PlanSummary; stage: string }) {
  const approved = plan.outcome.approved
  const [type, title, detail] = approved
    ? ([
        'success',
        'Approved — measured targets met',
        'The measured candidate meets the risk and utility targets.',
      ] as const)
    : (TEXT[plan.status] ?? ['error', `Unknown status ${plan.status} — not approved`, ''])
  const b = plan.outcome.budget
  return (
    <Alert
      showIcon
      type={type}
      title={`${stage}: ${title}`}
      description={
        <div className="text-xs">
          <div>{detail}</div>
          <div className="mono mt-1">
            status={plan.status} · approved={String(approved)}
            {b.limit != null && ` · budget ${b.used}/${b.limit}, ${b.unexplored ?? '?'} unexplored`}
          </div>
        </div>
      }
    />
  )
}
