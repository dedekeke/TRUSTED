/**
 * Select step: choose a PET for every column from its detected role/subtype and the sharing scenario.
 * Strictness comes from the scenario's trust level (public > contractual > internal / controlled research).
 * Every choice carries a one-sentence rationale for the demo.
 */
import type { ColumnDetection, ColumnPolicy, PetId, Scenario } from '@/types/pipeline.types'
import { TRUST_META } from '@/utils/constants'

const ID_SUBTYPES = new Set([
  'NATIONAL_ID',
  'IBAN',
  'PAYMENT_CARD',
  'LICENSE_PLATE',
  'CUSTOMER_ID',
  'ACCOUNT_ID',
  'EMPLOYEE_ID',
  'STUDENT_ID',
  'PATIENT_ID',
  'CARD_ID',
  'DEVICE_ID',
  'METER_ID',
  'PROPERTY_ID',
  'USERNAME',
  'HOSTNAME',
  'IP_ADDRESS',
  'MAC_ADDRESS',
  'IMEI',
  'RECORD_ID',
  'OTHER',
])

export interface PolicyContext {
  strictness: number
  needsLinkage: boolean
  scenarioLabel: string
}

export function policyContext(scenario: Scenario | null): PolicyContext {
  if (!scenario)
    return { strictness: 2, needsLinkage: true, scenarioLabel: 'no scenario selected (contractual defaults)' }
  const text = `${scenario.notes} ${scenario.suggested_privacy_targets} ${scenario.purpose}`.toLowerCase()
  return {
    strictness: TRUST_META[scenario.trust_level]?.strictness ?? 2,
    needsLinkage: /(pseudonym|join|link|revisit|stable|consistent|per[- ]person|longitudinal|track)/.test(text),
    scenarioLabel: `${scenario.id} (${TRUST_META[scenario.trust_level]?.label ?? scenario.trust_level})`,
  }
}

const P = (column: string, pet: PetId, level: number, rationale: string): ColumnPolicy => ({
  column,
  pet,
  level,
  rationale,
  source: 'policy',
})

export function choosePolicy(d: ColumnDetection, ctx: PolicyContext): ColumnPolicy {
  const { column: c, subtype: st } = d
  const s = ctx.strictness
  const numeric = d.stats.numericShare > 0.8 || (d.stats.patternShares.MONEY ?? 0) > 0.6

  switch (d.role) {
    case 'record_key':
      return s >= 3
        ? P(c, 'pseudonymise', 0, 'Sequential row keys reveal arrival order; re-keyed for an open release')
        : P(c, 'keep', 0, 'Meaningless row key; kept so protected rows can be joined back to other released tables')

    case 'direct_identifier':
      if (ID_SUBTYPES.has(st)) {
        if (ctx.needsLinkage || s <= 2)
          return P(
            c,
            'pseudonymise',
            0,
            st === 'NATIONAL_ID'
              ? 'HETU encodes birth date and sex and is enumerable; a keyed HMAC token keeps one stable key per person without either'
              : `Keyed HMAC token: the scenario needs records of the same ${st.toLowerCase().replace(/_/g, ' ')} to stay linkable, the raw value never leaves`,
          )
        return P(
          c,
          'drop',
          0,
          `Not needed for ${ctx.scenarioLabel}; an open release should not carry person-level keys`,
        )
      }
      return P(
        c,
        'drop',
        0,
        `${st.toLowerCase().replace(/_/g, ' ')} identifies a person on its own and no analysis in the scenario needs it`,
      )

    case 'technical_identifier':
      if (s >= 3 && !ctx.needsLinkage)
        return P(c, 'drop', 0, 'Device/account identifiers single people out and are not needed in open data')
      return P(
        c,
        'pseudonymise',
        0,
        st === 'OTHER' && (d.stats.patternShares.HASH ?? 0) > 0.5
          ? 'Unsalted hashes can be reversed by hashing candidate values; re-tokenised with a secret key'
          : 'Keyed token keeps joins across tables and logs while hiding the real identifier',
      )

    case 'quasi_identifier':
      switch (st) {
        case 'BIRTH_DATE':
          return s >= 3
            ? P(
                c,
                'age_band',
                1,
                'Birth date is the strongest linkage key; 10-year age bands (80+ top-coded) for open data',
              )
            : P(c, 'birth_year', s === 1 ? 0 : 1, 'Day and month removed; year keeps age analyses possible')
        case 'AGE':
          return P(c, 'age_band', s === 1 ? 0 : 1, 'Exact age becomes a band, which is enough for age-group analyses')
        case 'POSTCODE':
          return P(
            c,
            'postcode_prefix',
            s >= 3 ? 1 : 0,
            'Full postcode plus birth year and sex singles out most people; truncated to a wider area',
          )
        case 'TIMESTAMP':
          return P(
            c,
            'round_time',
            s - 1,
            'Exact times enable linkage with sightings and posts; rounded to the coarsest level the analysis tolerates',
          )
        case 'DATE':
          return P(c, 'round_time', Math.min(3, s), 'Dates coarsened to reduce linkage while keeping trends')
        case 'GPS_COORDINATE':
          return P(c, 'round_coords', s >= 3 ? 2 : 1, 'Precise coordinates reveal homes; precision reduced')
        case 'STREET_ADDRESS':
        case 'URL':
          return P(c, 'drop', 0, 'Too specific to keep and not needed for aggregate analysis')
        case 'SEX':
        case 'LANGUAGE':
        case 'MUNICIPALITY':
        case 'NATIONALITY':
        case 'CATEGORY':
          return s >= 3
            ? P(c, 'rare_merge', 0, 'Rare categories pooled so small groups cannot be singled out')
            : P(
                c,
                'keep',
                0,
                'Coarse attribute needed for the analysis; protected through k-anonymity on the full QI set',
              )
        default:
          return P(
            c,
            'rare_merge',
            s >= 3 ? 1 : 0,
            'Rare values pooled into "Other" so that unusual values do not identify people',
          )
      }

    case 'sensitive_attribute':
      if (st === 'DIAGNOSIS_CODE')
        return P(
          c,
          'truncate_code',
          s >= 3 ? 1 : 0,
          'Full ICD-10 sub-codes make rare conditions identifying; 3-character codes keep diagnosis patterns',
        )
      if (numeric)
        return s >= 2
          ? P(
              c,
              'round_numeric',
              0,
              'The value is the analytic target; rounding to 2 significant digits keeps distributions but breaks exact matching',
            )
          : P(
              c,
              'keep',
              0,
              'Analytic target in a controlled environment; protected by de-identifying the QIs around it',
            )
      return s >= 3
        ? P(c, 'rare_merge', 0, 'Rare sensitive categories pooled to avoid disclosure for small groups')
        : P(
            c,
            'keep',
            0,
            'The sensitive fact is what the recipient analyses; identity is protected by the other columns',
          )

    case 'free_text':
      return P(
        c,
        'redact_text',
        0,
        'Free text can contain anything; identifiers are replaced by typed placeholders and names found elsewhere in the table are removed',
      )

    default:
      return P(c, 'keep', 0, 'Not identifying in this scenario')
  }
}

export function choosePolicies(dets: ColumnDetection[], scenario: Scenario | null): ColumnPolicy[] {
  const ctx = policyContext(scenario)
  return dets.map((d) => choosePolicy(d, ctx))
}

const GENERIC = new Set(['band', 'area', 'week', 'month', 'year', 'type', 'code', 'group', 'level', 'on', 'of'])

/**
 * Quasi-identifiers named in the scenario's privacy target, e.g. HEALTH-S1 "k>=5 on (age band, sex, municipality,
 * arrival week)", matched to the detected columns. k-anonymity is enforced on exactly these, as the recipient's
 * threat model describes; returns null when the scenario names none.
 */
export function scenarioKQis(
  scenario: Scenario | null,
  dets: ColumnDetection[],
): { terms: string[]; qis: string[] } | null {
  const m = scenario?.suggested_privacy_targets.match(/k\s*(?:>=|≥)\s*\d+\s*on\s*[({]([^)}]+)[)}]/i)
  if (!m) return null
  const terms = m[1]
    .split(',')
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean)
  const qis: string[] = []
  for (const term of terms) {
    const words = term.split(/[\s_]+/)
    const specific = words.filter((w) => !GENERIC.has(w))
    let best: { col: string; score: number } | null = null
    for (const d of dets) {
      if (['direct_identifier', 'record_key', 'free_text'].includes(d.role) || qis.includes(d.column)) continue
      const tokens = d.column.toLowerCase().split(/[_\s]+/)
      let score = specific.filter((w) => tokens.some((t) => t.startsWith(w) || w.startsWith(t))).length * 2
      if (words.some((w) => w === 'age' || w === 'birth') && ['BIRTH_DATE', 'AGE'].includes(d.subtype)) score += 3
      if (words.includes('sex') && d.subtype === 'SEX') score += 3
      if (words.some((w) => w === 'postcode' || w === 'postal') && d.subtype === 'POSTCODE') score += 3
      if (
        !specific.length &&
        words.some((w) => ['month', 'week', 'year'].includes(w)) &&
        ['TIMESTAMP', 'DATE'].includes(d.subtype)
      )
        score += 1
      if (score > 0 && (!best || score > best.score)) best = { col: d.column, score }
    }
    if (best) qis.push(best.col)
  }
  return qis.length ? { terms, qis } : null
}
