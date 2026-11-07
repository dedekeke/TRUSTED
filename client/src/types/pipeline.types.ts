export type Row = Record<string, string>

export type PrivacyRole =
  | 'direct_identifier'
  | 'quasi_identifier'
  | 'sensitive_attribute'
  | 'technical_identifier'
  | 'free_text'
  | 'record_key'
  | 'non_sensitive'

export interface Dataset {
  id: string
  name: string
  /** proving-ground dataset / table, when the data comes from the package */
  dataset?: string
  table?: string
  columns: string[]
  rows: Row[]
  source: 'sample' | 'upload'
}

export interface ColumnStats {
  nonEmpty: number
  distinct: number
  uniqueRatio: number
  avgLength: number
  numericShare: number
  examples: string[]
  /** share of non-empty values matching each value pattern */
  patternShares: Record<string, number>
}

export type DetectionSource = 'rules' | 'on-device AI' | 'manual'

export interface ColumnDetection {
  column: string
  role: PrivacyRole
  subtype: string
  confidence: number
  reasons: string[]
  source: DetectionSource
  stats: ColumnStats
}

export type PetId =
  | 'keep'
  | 'drop'
  | 'pseudonymise'
  | 'mask'
  | 'birth_year'
  | 'age_band'
  | 'postcode_prefix'
  | 'round_time'
  | 'round_coords'
  | 'round_numeric'
  | 'truncate_code'
  | 'rare_merge'
  | 'redact_text'

export interface ColumnPolicy {
  column: string
  pet: PetId
  /** generalisation level on the PET's ladder (0 = finest) */
  level: number
  rationale: string
  source: 'policy' | 'manual' | 'k-anonymity'
}

export type TrustLevel = 'public' | 'contractual' | 'internal' | 'controlled_research'

export interface Scenario {
  id: string
  dataset: string
  title: string
  recipient: string
  purpose: string
  trust_level: TrustLevel
  threat_model: string
  legal_context: string
  utility_requirements: string[]
  suggested_privacy_targets: string
  notes: string
}

export interface TransformLogEntry {
  step: string
  detail: string
}

export interface ProtectedResult {
  columns: string[]
  rows: Row[]
  policies: ColumnPolicy[]
  log: TransformLogEntry[]
  suppressedCells: number
  kTarget: number | null
  /** quasi-identifiers k-anonymity was enforced on */
  kQis: string[]
}
