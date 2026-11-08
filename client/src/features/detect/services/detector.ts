import type { ColumnDetection, ColumnStats, PrivacyRole, Row } from '@/types/pipeline.types'
import { VALUE_PATTERNS, matchFull } from '@/utils/patterns'
import { parseDate } from '@/utils/dates'

interface Verdict {
  role: PrivacyRole
  subtype: string
  confidence: number
  reason: string
}

type NameRule = [RegExp, PrivacyRole, string]

const NAME_RULES: NameRule[] = [
  [/(hetu|ssn|national_?id|henkilotunnus|personal_?code|personnummer)/, 'direct_identifier', 'NATIONAL_ID'],
  [/(user_?agent)/, 'technical_identifier', 'USER_AGENT'],
  [/(device_?name|hostname|host_?name|(^|_)host($|_)|workstation)/, 'technical_identifier', 'HOSTNAME'],
  [/(device_?id|imei|serial)/, 'technical_identifier', 'DEVICE_ID'],
  [
    /(school|company|employer|merchant|org|organisation|organization|unit|station|clinic|hospital|ward|team|department|site)_?(name|code)?$/,
    'quasi_identifier',
    'ORG_NAME',
  ],
  [
    /(first_?names?|last_?name|surname|full_?name|(^|_)name$|_name$|nimi|namn|guardian\d?$)/,
    'direct_identifier',
    'PERSON_NAME',
  ],
  [/(e_?mail|sahkoposti|sähköposti)/, 'direct_identifier', 'EMAIL'],
  [/(phone|puhelin|mobile|gsm|(^|_)tel($|_)|msisdn)/, 'direct_identifier', 'PHONE'],
  [/(street|address|osoite|adress)/, 'direct_identifier', 'STREET_ADDRESS'],
  [/(iban|bank_?account|tilinumero)/, 'direct_identifier', 'IBAN'],
  [/(card_?(number|no|pan)|(^|_)pan($|_))/, 'direct_identifier', 'PAYMENT_CARD'],
  [/(plate|rekisteri)/, 'direct_identifier', 'LICENSE_PLATE'],
  [/(^|_)(upn|username|user_?name|login|account_?name|user)($|_)/, 'direct_identifier', 'USERNAME'],
  [/(postcode|postal|zip|postinumero|postnummer)/, 'quasi_identifier', 'POSTCODE'],
  [/(municipality|(^|_)city($|_)|kunta|kommun|(^|_)town($|_)|geo_city)/, 'quasi_identifier', 'MUNICIPALITY'],
  [/(birth|dob|syntym|fodelse)/, 'quasi_identifier', 'BIRTH_DATE'],
  [/((^|_)age($|_)|ika$|ikä)/, 'quasi_identifier', 'AGE'],
  [/(^|_)(sex|gender|sukupuoli|kon)($|_)/, 'quasi_identifier', 'SEX'],
  [/(language|kieli|sprak)/, 'quasi_identifier', 'LANGUAGE'],
  [/(nationality|citizenship|kansalaisuus|country_of_birth)/, 'quasi_identifier', 'NATIONALITY'],
  [/((^|_)(lat|lon|lng|latitude|longitude)($|_))/, 'quasi_identifier', 'GPS_COORDINATE'],
  [/((^|_)ip($|_)|ip_?addr|src_?ip|dst_?ip|client_?ip)/, 'technical_identifier', 'IP_ADDRESS'],
  [/((^|_)mac($|_)|mac_?addr|bssid)/, 'technical_identifier', 'MAC_ADDRESS'],
  [/(url|uri|referer|referrer)/, 'quasi_identifier', 'URL'],
  [/(icd|diagnos)/, 'sensitive_attribute', 'DIAGNOSIS_CODE'],
  [
    /(salary|wage|palkka|income|tulot|union|ay_?maksu|balance|debt|credit_?score|kyc|pep|fraud)/,
    'sensitive_attribute',
    'FINANCIAL_DATA',
  ],
  [
    /(special_?support|disab|religion|uskonto|ethnic|migrant|sick|sairaus|health|medical|triage|disposition|readmit|lab_|test_?result|bp$|heart|resp_rate|temp_c|spo2|pain|priority_?flag|medication)/,
    'sensitive_attribute',
    'HEALTH_DATA',
  ],
  [/(grade|arvosana|gpa|matriculation|absence|poissa)/, 'sensitive_attribute', 'EDUCATION_DATA'],
  [
    /(note|text|description|comment|message|complaint|response|body|summary|kuvaus|viesti|huom)/,
    'free_text',
    'FREE_TEXT',
  ],
  [/(occupation|job|title|ammatti|nimike|profession|role)/, 'quasi_identifier', 'OCCUPATION'],
  [/(_ts$|(^|_)ts($|_)|timestamp|datetime|_time$|(^|_)time($|_)|_at$)/, 'quasi_identifier', 'TIMESTAMP'],
  [/(date|pvm|datum|(^|_)day($|_))/, 'quasi_identifier', 'DATE'],
  [/(meter|metering_?point)/, 'technical_identifier', 'METER_ID'],
  [/(property|kiinteisto)/, 'direct_identifier', 'PROPERTY_ID'],
  [/(student|learner|pupil)_?id/, 'technical_identifier', 'STUDENT_ID'],
  [/(patient)_?id/, 'technical_identifier', 'PATIENT_ID'],
  [/(employee|staff|physician|handler|agent|author)_?id/, 'technical_identifier', 'EMPLOYEE_ID'],
  [/(customer|client|reporter)_?id/, 'technical_identifier', 'CUSTOMER_ID'],
  [/(account)_?id/, 'technical_identifier', 'ACCOUNT_ID'],
  [/(card)_?id/, 'technical_identifier', 'CARD_ID'],
]

const PATTERN_KEYS = VALUE_PATTERNS.map((p) => p.key)

export function computeStats(values: string[]): ColumnStats {
  const nonEmptyVals = values.map((v) => (v ?? '').trim()).filter((v) => v !== '')
  const distinctSet = new Set(nonEmptyVals)
  const patternCounts: Record<string, number> = Object.fromEntries(PATTERN_KEYS.map((k) => [k, 0]))
  let lenSum = 0
  let numeric = 0
  for (const v of nonEmptyVals) {
    lenSum += v.length
    const hits = matchFull(v)
    for (const h of hits) patternCounts[h]++
    if (hits.includes('NUMBER')) numeric++
  }
  const n = nonEmptyVals.length || 1
  return {
    nonEmpty: nonEmptyVals.length,
    distinct: distinctSet.size,
    uniqueRatio: distinctSet.size / n,
    avgLength: lenSum / n,
    numericShare: numeric / n,
    examples: [...distinctSet].slice(0, 12),
    patternShares: Object.fromEntries(PATTERN_KEYS.map((k) => [k, patternCounts[k] / n])),
  }
}

function byName(name: string): Verdict | null {
  const n = name.toLowerCase().replace(/[\s-]+/g, '_')
  for (const [rx, role, subtype] of NAME_RULES) {
    if (rx.test(n))
      return {
        role,
        subtype,
        confidence: 0.6,
        reason: `column name "${name}" matches ${subtype.toLowerCase()} keywords`,
      }
  }
  return null
}

const share = (s: ColumnStats, k: string) => s.patternShares[k] ?? 0

function byValues(s: ColumnStats, values: string[], index: number): Verdict | null {
  const v = (role: PrivacyRole, subtype: string, sh: number, what: string): Verdict => ({
    role,
    subtype,
    confidence: Math.min(0.97, 0.5 + sh / 2),
    reason: `${(sh * 100).toFixed(0)} % of values look like ${what}`,
  })
  const strong = 0.6
  if (share(s, 'NATIONAL_ID') >= strong)
    return v('direct_identifier', 'NATIONAL_ID', share(s, 'NATIONAL_ID'), 'Finnish personal identity codes (HETU)')
  if (share(s, 'EMAIL') >= strong) return v('direct_identifier', 'EMAIL', share(s, 'EMAIL'), 'e-mail addresses')
  if (share(s, 'IBAN') >= strong) return v('direct_identifier', 'IBAN', share(s, 'IBAN'), 'IBANs')
  if (share(s, 'MAC_ADDRESS') >= strong)
    return v('technical_identifier', 'MAC_ADDRESS', share(s, 'MAC_ADDRESS'), 'MAC addresses')
  if (share(s, 'IP_ADDRESS') >= strong)
    return v('technical_identifier', 'IP_ADDRESS', share(s, 'IP_ADDRESS'), 'IPv4 addresses')
  if (share(s, 'LICENSE_PLATE') >= strong)
    return v('direct_identifier', 'LICENSE_PLATE', share(s, 'LICENSE_PLATE'), 'licence plates')
  if (share(s, 'URL') >= strong) return v('quasi_identifier', 'URL', share(s, 'URL'), 'URLs')
  if (share(s, 'PHONE') >= strong && s.uniqueRatio > 0.3)
    return v('direct_identifier', 'PHONE', share(s, 'PHONE'), 'phone numbers')
  if (share(s, 'PAYMENT_CARD') >= strong && s.avgLength >= 13)
    return v('direct_identifier', 'PAYMENT_CARD', share(s, 'PAYMENT_CARD'), 'payment card numbers')
  if (share(s, 'UUID') >= strong)
    return v('technical_identifier', 'RECORD_ID', share(s, 'UUID'), 'UUIDs (correlation / session ids)')
  if (share(s, 'HASH') >= strong)
    return v(
      'technical_identifier',
      'OTHER',
      share(s, 'HASH'),
      'hex digests: hashed identifiers can be reversed by dictionary attack',
    )
  if (share(s, 'TIMESTAMP') >= strong) return v('quasi_identifier', 'TIMESTAMP', share(s, 'TIMESTAMP'), 'timestamps')
  if (share(s, 'DATE') >= strong) {
    const years = values.map((x) => parseDate(x)?.getUTCFullYear()).filter((y): y is number => y != null)
    const sorted = [...years].sort((a, b) => a - b)
    const med = sorted[Math.floor(sorted.length / 2)]
    const spread = sorted.length ? sorted[sorted.length - 1] - sorted[0] : 0
    if (med && med < 2010 && spread > 15)
      return {
        ...v('quasi_identifier', 'BIRTH_DATE', share(s, 'DATE'), 'dates'),
        reason: `dates spanning ${spread} years with median year ${med}: looks like birth dates`,
      }
    return v('quasi_identifier', 'DATE', share(s, 'DATE'), 'dates')
  }
  if (share(s, 'COORDINATE') >= strong)
    return v('quasi_identifier', 'GPS_COORDINATE', share(s, 'COORDINATE'), 'high-precision coordinates')
  if (
    share(s, 'ICD10') >= strong &&
    s.distinct >= 10 &&
    values.filter((x) => x.includes('.')).length > 0.2 * s.nonEmpty
  )
    return v('sensitive_attribute', 'DIAGNOSIS_CODE', share(s, 'ICD10'), 'ICD-10 diagnosis codes')
  if (share(s, 'MONEY') >= strong)
    return v('sensitive_attribute', 'FINANCIAL_DATA', share(s, 'MONEY'), 'money amounts (Finnish format)')
  if (share(s, 'ADDRESS') >= 0.5)
    return v('direct_identifier', 'STREET_ADDRESS', share(s, 'ADDRESS'), 'street addresses')
  if (share(s, 'POSTCODE') >= strong && s.distinct > 5)
    return v('quasi_identifier', 'POSTCODE', share(s, 'POSTCODE'), '5-digit postcodes')
  if (share(s, 'PERSON_NAME') >= 0.7 && s.uniqueRatio > 0.3 && s.avgLength < 40)
    return {
      ...v('direct_identifier', 'PERSON_NAME', share(s, 'PERSON_NAME'), 'person names (2–4 capitalised words)'),
      confidence: 0.8,
    }

  if (share(s, 'CODE_ID') >= strong && s.uniqueRatio > 0.95 && index === 0)
    return {
      role: 'record_key',
      subtype: 'RECORD_ID',
      confidence: 0.8,
      reason: 'first column, unique code per row: row key',
    }
  if (share(s, 'CODE_ID') >= strong && s.uniqueRatio > 0.2)
    return v('technical_identifier', 'OTHER', share(s, 'CODE_ID'), 'system codes that single out a person or account')

  const words = s.examples.reduce((a, e) => a + e.split(/\s+/).length, 0) / Math.max(1, s.examples.length)
  if (s.avgLength > 30 && words > 4 && s.uniqueRatio > 0.5)
    return {
      role: 'free_text',
      subtype: 'FREE_TEXT',
      confidence: 0.75,
      reason: `long varied text (avg ${s.avgLength.toFixed(0)} chars, ~${words.toFixed(0)} words)`,
    }
  return null
}

function fallback(s: ColumnStats): Verdict {
  if (s.nonEmpty === 0) return { role: 'non_sensitive', subtype: 'OTHER', confidence: 0.3, reason: 'column is empty' }
  if (s.numericShare > 0.9)
    return {
      role: 'non_sensitive',
      subtype: 'MEASUREMENT',
      confidence: 0.4,
      reason: 'numeric measurement with no identifying pattern',
    }
  if (s.distinct <= 30)
    return {
      role: 'non_sensitive',
      subtype: 'CATEGORY',
      confidence: 0.45,
      reason: `low-cardinality category (${s.distinct} values)`,
    }
  return {
    role: 'quasi_identifier',
    subtype: 'OTHER',
    confidence: 0.35,
    reason: `high-cardinality values (${s.distinct} distinct): may help single people out`,
  }
}

export function detectColumn(column: string, values: string[], index: number): ColumnDetection {
  const stats = computeStats(values)
  const name = byName(column)
  const val = byValues(stats, values, index)
  const reasons: string[] = []
  let pick: Verdict

  if (name && val) {
    if (name.role === val.role) {
      pick = { ...name, subtype: name.subtype, confidence: Math.min(0.99, val.confidence + 0.15) }
      reasons.push(name.reason, val.reason)
    } else if (val.confidence >= 0.85 && name.role !== 'free_text') {
      pick = val
      reasons.push(val.reason, `overrides the name hint (${name.subtype.toLowerCase()})`)
    } else {
      pick = name
      reasons.push(name.reason, `values also resemble ${val.subtype.toLowerCase()}`)
    }
  } else if (val) {
    pick = val
    reasons.push(val.reason)
  } else if (name) {
    pick = name
    reasons.push(name.reason)
  } else {
    pick = fallback(stats)
    reasons.push(pick.reason)
  }

  if (
    index === 0 &&
    stats.uniqueRatio > 0.98 &&
    ['technical_identifier', 'quasi_identifier', 'non_sensitive'].includes(pick.role)
  ) {
    pick = { role: 'record_key', subtype: 'RECORD_ID', confidence: 0.75, reason: '' }
    reasons.push('first column with a unique value per row: treated as the row key')
  }
  if (stats.uniqueRatio > 0.9 && stats.nonEmpty > 50 && pick.role === 'non_sensitive') {
    pick = { ...pick, role: 'quasi_identifier', confidence: 0.4 }
    reasons.push('almost every value is unique, so it can single people out')
  }

  return {
    column,
    role: pick.role,
    subtype: pick.subtype,
    confidence: pick.confidence,
    reasons,
    source: 'rules',
    stats,
  }
}

export function detectDataset(columns: string[], rows: Row[]): ColumnDetection[] {
  return columns.map((c, i) =>
    detectColumn(
      c,
      rows.map((r) => r[c] ?? ''),
      i,
    ),
  )
}
