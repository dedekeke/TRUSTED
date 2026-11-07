import { CheckOutlined } from '@ant-design/icons'
import { Alert, AutoComplete, Button, Checkbox, Select, Table, Tag } from 'antd'
import { useState } from 'react'
import { ApiError, jobs } from '@/services/api'
import type { Cell, Job, ViewTable } from '@/types/job.types'
import { ROLE_META } from '@/utils/constants'

const SUBTYPES = `PERSON_NAME NATIONAL_ID EMAIL PHONE STREET_ADDRESS POSTCODE MUNICIPALITY GPS_COORDINATE LOCATION_NAME
BIRTH_DATE AGE SEX LANGUAGE NATIONALITY IBAN PAYMENT_CARD CUSTOMER_ID ACCOUNT_ID EMPLOYEE_ID STUDENT_ID PATIENT_ID
CARD_ID DEVICE_ID IP_ADDRESS MAC_ADDRESS IMEI HOSTNAME USERNAME URL USER_AGENT LICENSE_PLATE PROPERTY_ID METER_ID
TIMESTAMP DATE DURATION HEALTH_DATA DIAGNOSIS_CODE FINANCIAL_DATA EDUCATION_DATA SOCIAL_DATA OCCUPATION ORG_NAME
MEASUREMENT CATEGORY AGGREGATE SECRET FREE_TEXT RECORD_ID OTHER`
  .split(/\s+/)
  .map((value) => ({ value }))

interface Row {
  key: string
  table: string
  column: string
  detected: string
  confidence: Cell
  required_by: Cell
  blocking: boolean
  include: boolean
  privacy_role: string
  subtype: string
}

/** Confirm (or correct) the labels that block selection; the job then continues from Select. */
export default function ReviewForm({ job, table, onDone }: { job: Job; table: ViewTable; onDone: (j: Job) => void }) {
  const [rows, setRows] = useState<Row[]>(() =>
    table.rows.map((r, i) => ({
      key: String(i),
      table: String(r.table),
      column: String(r.column),
      detected: `${r.privacy_role}/${r.subtype}`,
      confidence: r.confidence,
      required_by: r.required_by,
      blocking: Boolean(r.blocking),
      include: Boolean(r.blocking),
      privacy_role: String(r.privacy_role),
      subtype: String(r.subtype),
    })),
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const set = (key: string, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  const chosen = rows.filter((r) => r.include)
  const missing = rows.some((r) => r.blocking && !r.include)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      onDone(
        await jobs.confirm(
          job.id,
          chosen.map(({ table, column, privacy_role, subtype }) => ({ table, column, privacy_role, subtype })),
        ),
      )
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError('network', String(e)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <Alert
        showIcon
        type="warning"
        title="Select stopped: the scenario needs columns whose labels are uncertain"
        description="Check each blocking column, correct its role or subtype if the detector was wrong, then confirm. The run continues from Select and the confirmation is recorded in the plan provenance."
      />
      <Table
        size="small"
        rowKey="key"
        dataSource={rows}
        pagination={false}
        scroll={{ x: 'max-content' }}
        columns={[
          {
            title: 'Confirm',
            dataIndex: 'include',
            render: (v: boolean, r) => (
              <Checkbox checked={v} onChange={(e) => set(r.key, { include: e.target.checked })} />
            ),
          },
          {
            title: 'Column',
            render: (_, r) => (
              <span className="mono text-xs">
                {r.table}.{r.column} {r.blocking && <Tag color="gold">blocking</Tag>}
              </span>
            ),
          },
          {
            title: 'Detected',
            dataIndex: 'detected',
            render: (v: string) => <span className="mono text-xs">{v}</span>,
          },
          {
            title: 'Confidence',
            dataIndex: 'confidence',
            render: (v: Cell) => (typeof v === 'number' ? v.toFixed(3) : '—'),
          },
          {
            title: 'Required by',
            dataIndex: 'required_by',
            render: (v: Cell) => <span className="text-xs">{v || '—'}</span>,
          },
          {
            title: 'Role',
            dataIndex: 'privacy_role',
            render: (v: string, r) => (
              <Select
                size="small"
                className="w-48"
                value={v}
                onChange={(privacy_role) => set(r.key, { privacy_role, include: true })}
                options={Object.entries(ROLE_META).map(([value, m]) => ({ value, label: m.label }))}
              />
            ),
          },
          {
            title: 'Subtype',
            dataIndex: 'subtype',
            render: (v: string, r) => (
              <AutoComplete
                size="small"
                className="!w-44"
                value={v}
                options={SUBTYPES}
                filterOption={(input, o) => !!o?.value.toLowerCase().includes(input.toLowerCase())}
                onChange={(subtype) => set(r.key, { subtype: subtype.toUpperCase(), include: true })}
              />
            ),
          },
        ]}
      />
      {error && (
        <Alert showIcon type="error" title={`Confirmation rejected: ${error.code}`} description={error.message} />
      )}
      <div className="flex items-center justify-end gap-3">
        {missing && <span className="text-xs text-[var(--app-muted)]">All blocking columns must be confirmed.</span>}
        <Button
          type="primary"
          icon={<CheckOutlined />}
          loading={busy}
          disabled={!chosen.length || missing}
          onClick={submit}
        >
          Confirm {chosen.length} label{chosen.length === 1 ? '' : 's'} and continue
        </Button>
      </div>
    </div>
  )
}
