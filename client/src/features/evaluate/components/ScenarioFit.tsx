import { CheckCircleOutlined, WarningOutlined } from '@ant-design/icons'
import { Card, Tag } from 'antd'
import type { ColumnDetection, ProtectedResult, Scenario } from '@/types/pipeline.types'
import { TRUST_META } from '@/utils/constants'
import type { Evaluation } from '@/features/evaluate/services/metrics'
import { pct } from '@/utils/format'

interface Props {
  scenario: Scenario | null
  ev: Evaluation
  result: ProtectedResult
  detections: ColumnDetection[]
}

export default function ScenarioFit({ scenario, ev, result, detections }: Props) {
  const residualTotal = Object.values(ev.residual.counts).reduce((a, b) => a + b, 0)
  const pseudonymised = result.policies.filter((p) => p.pet === 'pseudonymise').map((p) => p.column)
  const textCols = result.policies.filter((p) => p.pet === 'redact_text').map((p) => p.column)
  const sensitive = detections
    .filter((d) => d.role === 'sensitive_attribute' && result.columns.includes(d.column))
    .map((d) => d.column)
  const k = result.kTarget ?? 5

  const residual: string[] = []
  const outside = detections
    .filter(
      (d) =>
        d.role === 'quasi_identifier' &&
        result.columns.includes(d.column) &&
        result.kQis.length &&
        !result.kQis.includes(d.column),
    )
    .map((d) => d.column)
  if (outside.length)
    residual.push(
      `k-anonymity is enforced on the QIs named in the scenario target (${result.kQis.join(', ')}); ${outside.join(', ')} were generalised by policy but are outside the k check.`,
    )
  if (pseudonymised.length)
    residual.push(
      `Keyed pseudonyms (${pseudonymised.join(', ')}) keep records linkable: this is pseudonymised, not anonymous, data and remains personal data under GDPR Recital 26.`,
    )
  if (ev.kAfter.shareBelowK > 0)
    residual.push(
      `${pct(ev.kAfter.shareBelowK)} of rows are still in groups smaller than k = ${k} on the quasi-identifiers.`,
    )
  if (textCols.length)
    residual.push(
      `Free-text redaction (${textCols.join(', ')}) is regex + same-table name dictionary: names, places or health details not in those lists can survive.`,
    )
  if (sensitive.length)
    residual.push(
      `Sensitive attributes are released (${sensitive.join(', ')}): k-anonymity does not prevent attribute disclosure in homogeneous groups (l-diversity not enforced).`,
    )
  if (residualTotal)
    residual.push(`The regex scan still finds ${residualTotal} identifier-like strings: review before release.`)
  residual.push(
    'Measured on an in-browser sample against proxy attacks; confirm with `pets-eval scorecard` and the hidden organiser attackers.',
  )

  const fit = ev.privacyAfter >= 0.7 && ev.utility >= 0.6
  return (
    <Card
      size="small"
      title="Fit for scenario"
      extra={
        scenario && (
          <Tag color={TRUST_META[scenario.trust_level]?.color}>
            {scenario.id} · {TRUST_META[scenario.trust_level]?.label}
          </Tag>
        )
      }
    >
      <div className="mb-3 flex items-start gap-2">
        {fit ? (
          <CheckCircleOutlined className="mt-1 text-green-500" />
        ) : (
          <WarningOutlined className="mt-1 text-amber-500" />
        )}
        <div className="text-sm">
          {scenario ? (
            <>
              <span className="font-medium">{fit ? 'Suitable' : 'Needs review'}</span> for{' '}
              <span className="font-medium">{scenario.recipient}</span>: {scenario.purpose.toLowerCase()}.
            </>
          ) : (
            'Pick a sharing scenario on the Protect step to state who this release is for.'
          )}
        </div>
      </div>
      <div className="mb-1 text-xs font-semibold tracking-wide text-[var(--app-muted)] uppercase">
        Residual risks (stated honestly)
      </div>
      <ul className="divide-y divide-[var(--app-border)]">
        {residual.map((r) => (
          <li key={r} className="py-2 text-sm">
            {r}
          </li>
        ))}
      </ul>
    </Card>
  )
}
