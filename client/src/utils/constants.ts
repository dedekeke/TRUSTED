import type { PetId, PrivacyRole, TrustLevel } from '@/types/pipeline.types'

export const ROLES: PrivacyRole[] = [
  'direct_identifier',
  'quasi_identifier',
  'sensitive_attribute',
  'technical_identifier',
  'free_text',
  'record_key',
  'non_sensitive',
]

export const ROLE_META: Record<PrivacyRole, { label: string; color: string; hint: string }> = {
  direct_identifier: { label: 'Direct identifier', color: 'red', hint: 'Identifies a person on its own' },
  quasi_identifier: { label: 'Quasi-identifier', color: 'orange', hint: 'Identifies in combination with others' },
  sensitive_attribute: {
    label: 'Sensitive attribute',
    color: 'magenta',
    hint: 'The protected fact itself (incl. GDPR Art. 9)',
  },
  technical_identifier: {
    label: 'Technical identifier',
    color: 'volcano',
    hint: 'Device, network or account identifier',
  },
  free_text: { label: 'Free text', color: 'purple', hint: 'Unstructured text that may contain anything' },
  record_key: { label: 'Record key', color: 'blue', hint: 'Row identifier with no meaning outside the table' },
  non_sensitive: { label: 'Non-sensitive', color: 'green', hint: 'Safe to share as is in typical scenarios' },
}

export const SUBTYPES = [
  'PERSON_NAME',
  'NATIONAL_ID',
  'EMAIL',
  'PHONE',
  'STREET_ADDRESS',
  'POSTCODE',
  'MUNICIPALITY',
  'GPS_COORDINATE',
  'LOCATION_NAME',
  'BIRTH_DATE',
  'AGE',
  'SEX',
  'LANGUAGE',
  'NATIONALITY',
  'IBAN',
  'PAYMENT_CARD',
  'CUSTOMER_ID',
  'ACCOUNT_ID',
  'EMPLOYEE_ID',
  'STUDENT_ID',
  'PATIENT_ID',
  'CARD_ID',
  'DEVICE_ID',
  'IP_ADDRESS',
  'MAC_ADDRESS',
  'IMEI',
  'HOSTNAME',
  'USERNAME',
  'URL',
  'USER_AGENT',
  'LICENSE_PLATE',
  'PROPERTY_ID',
  'METER_ID',
  'TIMESTAMP',
  'DATE',
  'DURATION',
  'HEALTH_DATA',
  'DIAGNOSIS_CODE',
  'FINANCIAL_DATA',
  'EDUCATION_DATA',
  'SOCIAL_DATA',
  'OCCUPATION',
  'ORG_NAME',
  'MEASUREMENT',
  'CATEGORY',
  'AGGREGATE',
  'SECRET',
  'FREE_TEXT',
  'RECORD_ID',
  'OTHER',
]

export interface PetMeta {
  label: string
  family: string

  levels: string[]
  description: string
}

export const PET_META: Record<PetId, PetMeta> = {
  keep: { label: 'Keep', family: 'none', levels: [], description: 'Released unchanged' },
  drop: { label: 'Suppress column', family: 'suppression', levels: [], description: 'Column is not released' },
  pseudonymise: {
    label: 'Keyed pseudonym (HMAC-SHA256)',
    family: 'pseudonymisation',
    levels: [],
    description: 'Same input gives the same token, so joins and revisits survive; irreversible without the key',
  },
  mask: {
    label: 'Partial masking',
    family: 'masking',
    levels: ['keep last 2', 'keep last 1', 'full mask'],
    description: 'Hides most characters',
  },
  birth_year: {
    label: 'Birth date → year',
    family: 'generalisation',
    levels: ['year', '5-year band', '10-year band'],
    description: 'Drops day and month',
  },
  age_band: {
    label: 'Age band',
    family: 'binning',
    levels: ['5-year', '10-year (80+ top-coded)', '20-year'],
    description: 'Exact age becomes a band',
  },
  postcode_prefix: {
    label: 'Postcode truncation',
    family: 'generalisation',
    levels: ['3 digits (201**)', '2 digits (20***)', '1 digit (2****)'],
    description: 'Postcode becomes a wider area',
  },
  round_time: {
    label: 'Timestamp rounding',
    family: 'generalisation',
    levels: ['hour', 'day', 'ISO week', 'month'],
    description: 'Time is coarsened',
  },
  round_coords: {
    label: 'Location precision',
    family: 'location precision',
    levels: ['3 dp (~100 m)', '2 dp (~1 km)', '1 dp (~10 km)'],
    description: 'Coordinates rounded',
  },
  round_numeric: {
    label: 'Numeric rounding',
    family: 'binning',
    levels: ['2 significant digits', '1 significant digit'],
    description: 'Values rounded to reduce uniqueness',
  },
  truncate_code: {
    label: 'Code truncation',
    family: 'generalisation',
    levels: ['3 characters', '1 character (chapter)'],
    description: 'e.g. ICD-10 J45.9 → J45',
  },
  rare_merge: {
    label: 'Rare-category merge',
    family: 'aggregation',
    levels: ['< 5 rows → Other', '< 10 rows → Other', '< 25 rows → Other'],
    description: 'Rare categories are pooled',
  },
  redact_text: {
    label: 'Free-text redaction',
    family: 'redaction',
    levels: [],
    description: 'Identifiers in text replaced by typed placeholders',
  },
}

export const TRUST_META: Record<TrustLevel, { label: string; color: string; strictness: number }> = {
  public: { label: 'Public / open data', color: 'red', strictness: 3 },
  contractual: { label: 'Contractual partner', color: 'orange', strictness: 2 },
  internal: { label: 'Internal use', color: 'blue', strictness: 1 },
  controlled_research: { label: 'Controlled research', color: 'green', strictness: 1 },
}

export const DEMO_REQUIREMENTS = [
  { key: 'detect', title: 'Data types identified', path: '/detect' },
  { key: 'select', title: 'PETs selected per data type', path: '/protect' },
  { key: 'transform', title: 'Transformed dataset', path: '/protect' },
  { key: 'utility', title: 'Utility before vs after', path: '/evaluate' },
  { key: 'scenario', title: 'Sharing scenario it is fit for', path: '/scenarios' },
] as const
