import { ArrowLeftOutlined, SearchOutlined, SolutionOutlined } from '@ant-design/icons'
import { Alert, Button, Card, InputNumber, Select, Table, Tag } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import EmptyState from '@/components/common/EmptyState'
import PageHeader from '@/components/common/PageHeader'
import RoleTag from '@/components/common/RoleTag'
import RiskTable from '@/features/evaluate/components/RiskTable'
import TransformLog from '@/features/protect/components/TransformLog'
import { useFetch } from '@/hooks/useFetch'
import { api, backend } from '@/services/api'
import type { PlanColumn, PlanSummary } from '@/types/run.types'
import RunError from './RunError'
import StatusBanner from './StatusBanner'
import { useRun } from '../hooks/useRun'

function List({ title, items, type }: { title: string; items: string[]; type: 'error' | 'warning' | 'info' }) {
  if (!items.length) return null
  return (
    <Alert
      type={type}
      title={`${title} (${items.length})`}
      description={
        <ul className="list-disc pl-4 text-xs">
          {items.map((x, i) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
      }
    />
  )
}

function Conflicts({ plan }: { plan: PlanSummary }) {
  const c = plan.conflict
  const v = plan.outcome.violations
  if (!c && !v.length) return null
  return (
    <Card size="small" title="Conflicts and violations">
      {c && <div className="mb-2 text-sm font-medium">{c.reason}</div>}
      <List title="Unmet" items={c?.violations ?? []} type="warning" />
      {c?.limited_by && (
        <List
          title="Limited by requirements"
          items={Object.entries(c.limited_by).map(([col, why]) => `${col}: ${why}`)}
          type="info"
        />
      )}
      {!!v.length && (
        <Table
          className="mt-2"
          rowKey={(r) => `${r.metric}:${r.table}`}
          size="small"
          pagination={false}
          dataSource={v}
          columns={[
            { title: 'Metric', dataIndex: 'metric' },
            { title: 'Table', dataIndex: 'table' },
            { title: 'Target', dataIndex: 'target', render: (x) => JSON.stringify(x) },
            { title: 'Achieved', dataIndex: 'achieved', render: (x) => JSON.stringify(x) },
            { title: 'Tasks', dataIndex: 'requirements', render: (r?: string[]) => r?.join(', ') },
          ]}
        />
      )}
    </Card>
  )
}

const PLAN_COLUMNS = [
  {
    title: 'Column',
    key: 'ref',
    render: (_: unknown, c: PlanColumn) => <span className="mono font-medium">{`${c.table}.${c.column}`}</span>,
  },
  {
    title: 'Data type',
    key: 'role',
    render: (_: unknown, c: PlanColumn) => (
      <div className="flex flex-col items-start gap-0.5">
        <RoleTag role={c.privacy_role} />
        <span className="mono text-[11px] text-[var(--app-muted)]">{c.subtype}</span>
      </div>
    ),
  },
  {
    title: 'PET',
    key: 'pet',
    render: (_: unknown, c: PlanColumn) => (
      <span className="mono text-xs">
        {c.action} {c.method ?? ''} {Object.keys(c.params).length ? JSON.stringify(c.params) : ''}
      </span>
    ),
  },
  { title: 'Required by', dataIndex: 'required_by', render: (r: string[]) => r.join(', ') },
  { title: 'Why', dataIndex: 'explanation', render: (e: string) => <span className="text-xs">{e}</span> },
]

export default function RunPlan() {
  const navigate = useNavigate()
  const { runId, run, busy, error, act } = useRun()
  const { data: scenarios } = useFetch(api.scenarios)
  const [scenario, setScenario] = useState<string | null>(null)
  const [budget, setBudget] = useState(50)
  if (!runId)
    return <EmptyState title="No run yet" description="Run detect first." actionLabel="Go to Detect" to="/detect" />

  const options = (scenarios ?? []).filter((s) => s.dataset === run?.dataset)
  const chosen = scenario ?? run?.select?.scenario ?? options[0]?.id ?? null
  const plan = run?.search ?? run?.select ?? null
  const baseline = run?.search?.trace.find((e) => e.phase === 'baseline')

  return (
    <div className="space-y-5">
      <PageHeader
        step="Step 2"
        title="Select PETs and search (server)"
        description="Select builds the rule-based plan for the scenario; Search measures it on the data and coarsens it within the evaluation budget."
        extra={
          <>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(`/detect?run=${runId}`)}>
              Review
            </Button>
            <Select
              className="w-56"
              placeholder="Scenario"
              value={chosen}
              onChange={setScenario}
              options={options.map((s) => ({ value: s.id, label: `${s.id} · ${s.title}` }))}
            />
            <Button
              type="primary"
              icon={<SolutionOutlined />}
              loading={busy === 'select'}
              disabled={!run?.steps.detect || run.steps.select || !chosen || !!busy}
              onClick={() => chosen && act('select', () => backend.select(runId, chosen))}
            >
              Select
            </Button>
            <InputNumber min={1} max={500} value={budget} onChange={(v) => setBudget(v ?? 50)} addonBefore="Budget" />
            <Button
              type="primary"
              icon={<SearchOutlined />}
              loading={busy === 'search'}
              disabled={!run?.steps.select || run.steps.search || !!busy}
              onClick={() => act('search', () => backend.search(runId, budget))}
            >
              Search
            </Button>
          </>
        }
      />
      <RunError error={error} run={run} />
      {busy === 'search' && <Alert type="info" showIcon title="Searching… this can take a minute or two." />}
      {run?.select && <StatusBanner plan={run.select} stage="Select" />}
      {run?.search && <StatusBanner plan={run.search} stage="Search" />}
      {plan ? (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            <Card size="small" title={`Review queue (${plan.review_queue.length})`}>
              {plan.review_queue.length ? (
                <ul className="list-disc pl-4 text-xs">
                  {plan.review_queue.map((r) => (
                    <li key={r.column}>
                      <span className="mono">{r.column}</span> (confidence {r.confidence}): {r.evidence}
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-xs">Nothing left to review.</span>
              )}
              {!!plan.reviews.length && (
                <div className="mt-3 text-xs">
                  <div className="font-medium">Reviewer-confirmed</div>
                  {plan.reviews.map((r) => (
                    <div key={`${r.table}.${r.column}`} className="mono">
                      {r.table}.{r.column}: {r.detected.role}/{r.detected.subtype} → {r.confirmed.role}/
                      {r.confirmed.subtype} {r.downgrade && <Tag color="red">downgrade</Tag>}
                    </div>
                  ))}
                </div>
              )}
            </Card>
            <Conflicts plan={plan} />
          </div>
          <List title="Errors" items={plan.errors} type="error" />
          <List title="Warnings" items={plan.warnings} type="warning" />
          {run?.search && (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
              <RiskTable
                risks={Object.entries(run.search.outcome.achieved)
                  .filter(([, a]) => a.share_below_k != null)
                  .map(([t, a]) => ({
                    key: t,
                    label: `${t}: share below k`,
                    explain: 'Share of known subject/class entries in classes smaller than the k target',
                    before: baseline?.share_below_k[t] ?? 0,
                    after: a.share_below_k ?? 0,
                  }))}
              />
              <TransformLog
                log={run.search.trace.map((e) => ({
                  step: `#${e.evaluation} ${e.phase}${e.changed_column ? ` · ${e.changed_column}` : ''}${e.accepted === false ? ' (rejected)' : ''}`,
                  detail: [
                    e.reason,
                    Object.entries(e.share_below_k)
                      .map(([t, s]) => `${t} k-share ${s?.toFixed(4)}`)
                      .join(', '),
                  ]
                    .filter(Boolean)
                    .join(' · '),
                }))}
              />
            </div>
          )}
          <Card size="small" title={`Chosen plan (${run?.search ? 'after search' : 'select'})`}>
            <Table
              rowKey={(c) => `${c.table}.${c.column}`}
              size="small"
              pagination={{ pageSize: 25 }}
              columns={PLAN_COLUMNS}
              dataSource={plan.columns}
              scroll={{ x: 900 }}
            />
          </Card>
        </>
      ) : (
        <EmptyState title="No plan yet" description="Choose a scenario and run Select." />
      )}
    </div>
  )
}
