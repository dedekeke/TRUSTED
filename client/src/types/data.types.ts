import type { PrivacyRole } from './pipeline.types'

export interface SampleInfo {
  id: string
  dataset: string
  table: string
  label: string
  rows: number
}

export interface CatalogEntry {
  dataset: string
  table: string
  column: string
  privacy_role: PrivacyRole
  subtype: string
  description: string
}

export interface UtilityTask {
  id: string
  table: string
  description: string
  required: boolean | null
  score: number | null
  metric: string
}

export interface Scorecard {
  summary: { privacy: number; utility: number; composite: number }
  risk_components: Record<string, number>
  utility: UtilityTask[]
  tables?: Record<
    string,
    { status?: string; rows_original?: number; rows_protected?: number; columns_dropped?: string[] }
  >
}

/** dataset -> baseline label (B0, B2, B2-k, Quickstart) -> scorecard */
export type Benchmark = Record<string, Record<string, Scorecard>>
