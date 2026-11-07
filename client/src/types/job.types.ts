/** Shapes returned by server/api.py /api/jobs (labels, counts, statuses and digests only; never cell values). */

export type StepName = 'input' | 'detect' | 'review' | 'select' | 'search' | 'transform' | 'evaluate'

export type StepStatus = 'queued' | 'running' | 'success' | 'failed' | 'needs_review' | 'warning' | 'skipped'

export type JobState = 'created' | 'running' | 'needs_review' | 'succeeded' | 'failed'

export interface JobStep {
  name: StepName
  status: StepStatus
  started_at?: string | null
  finished_at?: string | null
  duration_s?: number | null
  summary?: string
  error?: string | null
}

export interface JobParams {
  scenario: string | null
  spec: boolean
  release_id: string
  budget: number
  tau: number
  llm: boolean
  text_fallback: string | null
  allow_unapproved: boolean
  no_scorecard: boolean
}

export interface Job {
  id: string
  dataset: string
  source: 'package' | 'upload'
  created_at: string
  uploaded_files: string[]
  params: JobParams | null
  state: JobState
  attempt: number
  updated_at: string
  steps: JobStep[]
  download: boolean
}

export type Cell = string | number | boolean | null

export interface ViewTable {
  id: string
  title: string
  note?: string
  columns: { key: string; title: string }[]
  rows: Record<string, Cell>[]
}

export interface ViewIssue {
  level: 'error' | 'warning' | 'info'
  code: string
  message: string
}

export interface StepView {
  step: StepName
  status: StepStatus
  stats: { label: string; value: Cell; hint?: string }[]
  tables: ViewTable[]
  issues: ViewIssue[]
}

export interface StartOptions {
  scenario?: string
  spec?: Record<string, unknown>
  budget?: number
  llm?: boolean
  allow_unapproved?: boolean
  no_scorecard?: boolean
}

export interface Confirmation {
  table: string
  column: string
  privacy_role: string
  subtype: string
}
