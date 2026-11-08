import type { PrivacyRole, Scenario } from '@/types/pipeline.types'

export interface RunLabel {
  table: string
  column: string
  privacy_role: PrivacyRole
  subtype: string
  confidence: number
  needs_review: boolean
  art9?: boolean
  art9_table?: boolean
  data_kind?: string
}

export type PlanStatus = 'policy_valid' | 'blocked' | 'measured_ok' | 'target_unmet' | 'budget_exhausted'

export interface Violation {
  metric: string
  table: string
  target: unknown
  achieved: unknown
  requirements?: string[]
}

export interface Outcome {
  policy_valid: boolean
  targets_met: boolean
  approved: boolean
  budget: { used: number; limit: number | null; exhausted: boolean; unexplored: number | null }
  targets: Record<string, unknown>
  achieved: Record<string, { min_k?: number; share_below_k?: number; unknown_subject_rows?: number }>
  violations: Violation[]
}

export interface PlanColumn {
  table: string
  column: string
  privacy_role: PrivacyRole
  subtype: string
  action: string
  method: string | null
  params: Record<string, unknown>
  required_by: string[]
  needs_review: boolean
  confidence: number
  explanation: string
}

export interface TraceEntry {
  evaluation: number
  phase: string
  accepted?: boolean
  changed_column?: string
  reason?: string
  utility?: unknown
  information_loss?: number
  suppressed_fraction?: number
  share_below_k: Record<string, number | undefined>
}

export interface Conflict {
  reason: string
  violations?: string[]
  limited_by?: Record<string, string>
  remaining_risk?: Record<string, number>
}

export interface PlanSummary {
  status: PlanStatus
  outcome: Outcome
  scenario: string | null
  trust_level: string
  targets: Record<string, unknown>
  columns: PlanColumn[]
  review_queue: { column: string; confidence: number; evidence: string }[]
  reviews: {
    table: string
    column: string
    detected: { role: string; subtype: string; confidence: number; needs_review: boolean }
    confirmed: { role: string; subtype: string }
    downgrade: boolean
  }[]
  errors: string[]
  warnings: string[]
  conflict: Conflict | null
  trace: TraceEntry[]
  measured: { utility: unknown; baseline_utility: unknown; tau: number; evaluations: number } | null
  plan_sha256?: string | null
}

export interface RunState {
  id: string
  dataset: string
  created_at: string
  steps: { detect: boolean; confirm: boolean; select: boolean; search: boolean }
  manifest: {
    dataset: string
    dataset_fingerprint: string
    detector: { name: string; version: string; model_sha256: string }
    tables: Record<string, { rows: number; columns: number }>
    created_at: string
  } | null
  labels: RunLabel[]
  detect_review: RunLabel[]
  confirmation: { reviewer_confirmed: boolean; allow_downgrade: boolean; count: number } | null
  confirmations: { table: string; column: string; privacy_role: string; subtype: string }[]
  select: PlanSummary | null
  search: PlanSummary | null
  errors: { step: string; code: string; message: string }[]
}

export type { Scenario }
