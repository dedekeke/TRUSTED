export interface ValuePattern {
  key: string

  full: RegExp
}

const HETU = String.raw`\d{6}[-+A-FU-Y]\d{3}[0-9A-Y]`

export const VALUE_PATTERNS: ValuePattern[] = [
  { key: 'NATIONAL_ID', full: new RegExp(`^${HETU}$`) },
  { key: 'EMAIL', full: /^[\w.+-]+@[\w-]+(\.[\w-]+)+$/ },
  { key: 'IBAN', full: /^[A-Z]{2}\d{2}( ?[0-9A-Z]{4}){2,7}( ?[0-9A-Z]{1,3})?$/ },
  { key: 'PAYMENT_CARD', full: /^(\d[ -]?){12,18}\d$/ },
  { key: 'PHONE', full: /^(\+\d{2,3}[\s-]?|0)\d{1,3}[\s-]?\d{3,4}[\s-]?\d{2,4}$/ },
  { key: 'IP_ADDRESS', full: /^\d{1,3}(\.\d{1,3}){3}$/ },
  { key: 'MAC_ADDRESS', full: /^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$/ },
  { key: 'LICENSE_PLATE', full: /^[A-ZÅÄÖ]{2,3}-\d{1,3}$/ },
  { key: 'URL', full: /^https?:\/\/\S+$/ },
  { key: 'HASH', full: /^[0-9A-Fa-f]{32,64}$/ },
  { key: 'UUID', full: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i },
  { key: 'POSTCODE', full: /^\d{5}$/ },
  { key: 'TIMESTAMP', full: /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?/ },
  { key: 'DATE', full: /^(\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4})$/ },
  { key: 'COORDINATE', full: /^-?\d{1,3}\.\d{4,}$/ },
  { key: 'MONEY', full: /^-?\d{1,3}( \d{3})*,\d{2}$/ },
  { key: 'CODE_ID', full: /^[A-Z]{1,6}[-_]?\d{3,}([-_]\d+)*$/ },
  { key: 'ICD10', full: /^[A-TV-Z]\d{2}(\.\d{1,2})?$/ },
  { key: 'ADDRESS', full: /^[A-ZÅÄÖ][a-zåäö-]+\s+\d+(\s?[A-Z])?(\s?\d+)?(,\s*\d{5}\s+\S+)?$/ },
  {
    key: 'PERSON_NAME',
    full: /^(?!.*\b(Oy|Oyj|Ab|Ltd|Ry|Inc|GmbH|School|Koulu|Lukio|Bank|Pankki)\b)[A-ZÅÄÖ][a-zåäöé'-]+(\s+[A-ZÅÄÖ][a-zåäöé'-]+){1,3}$/,
  },
  { key: 'NUMBER', full: /^-?\d+([.,]\d+)?$/ },
  { key: 'BOOLEAN', full: /^(true|false|0|1|yes|no|kyllä|ei)$/i },
]

export const TEXT_PATTERNS: { label: string; rx: RegExp }[] = [
  { label: 'NATIONAL_ID', rx: new RegExp(String.raw`\b${HETU}\b`, 'g') },
  { label: 'EMAIL', rx: /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g },
  { label: 'URL', rx: /https?:\/\/\S+/g },
  { label: 'IBAN', rx: /\b[A-Z]{2}\d{2}(?: ?[0-9A-Z]{4}){2,7}(?: ?[0-9A-Z]{1,3})?\b/g },
  { label: 'PAYMENT_CARD', rx: /\b(?:\d[ -]?){12,18}\d\b/g },
  { label: 'PHONE', rx: /(?:\+\d{2,3}[\s-]?|\b0)\d{1,3}[\s-]?\d{3,4}[\s-]?\d{2,4}\b/g },
  { label: 'IP_ADDRESS', rx: /\b\d{1,3}(?:\.\d{1,3}){3}\b/g },
  { label: 'MAC', rx: /\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b/g },
  { label: 'LICENSE_PLATE', rx: /\b[A-ZÅÄÖ]{2,3}-\d{1,3}\b/g },
  {
    label: 'ADDRESS',
    rx: /\b[A-ZÅÄÖ][a-zåäö]+(?:tie|katu|kuja|polku|rinne|mäki|kaari|tori|väylä|ranta|puisto|gatan|vägen|gränd)\s+\d+(?:\s?[A-Z](?:\s?\d+)?)?\b/g,
  },
]

const HETU_CHECK = '0123456789ABCDEFHJKLMNPRSTUVWXY'

export function isHetu(value: string): boolean {
  const m = value
    .trim()
    .toUpperCase()
    .match(/^(\d{6})[-+A-FU-Y]?(\d{3})([0-9A-Y])$/)
  return !!m && HETU_CHECK[Number(m[1] + m[2]) % 31] === m[3]
}

export function matchFull(value: string): string[] {
  const v = value.trim()
  const hits = VALUE_PATTERNS.filter((p) => p.key !== 'NATIONAL_ID' && p.full.test(v)).map((p) => p.key)
  if (isHetu(v)) hits.unshift('NATIONAL_ID')
  return hits
}

export function scanText(text: string, counts: Record<string, number>, examples: Record<string, string[]>) {
  for (const { label, rx } of TEXT_PATTERNS) {
    if (label === 'ADDRESS') continue
    const m = text.match(rx)
    if (!m) continue
    counts[label] = (counts[label] ?? 0) + m.length
    const ex = (examples[label] ??= [])
    if (ex.length < 3) ex.push(m[0])
  }
}
