import type {
  ColumnDetection,
  ColumnPolicy,
  Dataset,
  ProtectedResult,
  Row,
  TransformLogEntry,
} from '@/types/pipeline.types'
import { PET_META } from '@/utils/constants'
import { ageAt, parseDate, roundTime } from '@/utils/dates'
import { TEXT_PATTERNS } from '@/utils/patterns'
import { kAnonymity, toNumber, valueCounts } from '@/utils/stats'

export interface TransformContext {
  tokens: Map<string, string>
  names: RegExp | null
}

export async function newSessionKey(): Promise<CryptoKey> {
  return crypto.subtle.generateKey({ name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
}

async function hmacToken(key: CryptoKey, value: string): Promise<string> {
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(value))
  return (
    'tok_' +
    [...new Uint8Array(sig)]
      .slice(0, 8)
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('')
  )
}

const escapeRx = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

export function buildNameDictionary(dataset: Dataset, dets: ColumnDetection[]): RegExp | null {
  const tokens = new Set<string>()
  for (const d of dets) {
    if (d.subtype !== 'PERSON_NAME') continue
    for (const r of dataset.rows)
      for (const t of (r[d.column] ?? '').split(/[\s,]+/)) if (t.length >= 3 && /^[A-ZÅÄÖ]/.test(t)) tokens.add(t)
  }
  if (!tokens.size) return null
  const list = [...tokens]
    .sort((a, b) => b.length - a.length)
    .slice(0, 8000)
    .map(escapeRx)
  return new RegExp(`(?<![\\p{L}])(${list.join('|')})(?![\\p{L}])`, 'giu')
}

export function redactText(text: string, names: RegExp | null): string {
  let out = text
  for (const { label, rx } of TEXT_PATTERNS) out = out.replace(rx, `[${label}]`)
  if (names) out = out.replace(names, '[PERSON]')
  return out
}

function ageBand(age: number, level: number): string {
  if (!Number.isFinite(age) || age < 0) return ''
  const w = [5, 10, 20][level] ?? 10
  if (age >= 80) return '80+'
  const lo = Math.floor(age / w) * w
  return `${lo}-${lo + w - 1}`
}

function sigDigits(x: number, digits: number): string {
  if (x === 0) return '0'
  return String(Number(x.toPrecision(digits)))
}

export function transformValue(v: string, p: ColumnPolicy, ctx: TransformContext): string {
  const value = (v ?? '').trim()
  if (!value) return ''
  switch (p.pet) {
    case 'keep':
    case 'rare_merge': // handled at column level
      return value
    case 'drop':
      return ''
    case 'pseudonymise':
      return ctx.tokens.get(value) ?? ''
    case 'mask': {
      const keep = [2, 1, 0][p.level] ?? 2
      return '*'.repeat(Math.max(0, value.length - keep)) + (keep ? value.slice(-keep) : '')
    }
    case 'birth_year': {
      const y = parseDate(value)?.getUTCFullYear()
      if (!y) return ''
      if (p.level === 0) return String(y)
      const w = p.level === 1 ? 5 : 10
      const lo = Math.floor(y / w) * w
      return `${lo}-${lo + w - 1}`
    }
    case 'age_band': {
      const n = toNumber(value)
      const d = n == null ? parseDate(value) : null
      return ageBand(n ?? (d ? ageAt(d) : NaN), p.level)
    }
    case 'postcode_prefix': {
      const digits = [3, 2, 1][p.level] ?? 3
      const m = value.match(/\d{5}/)
      return m ? m[0].slice(0, digits) + '*'.repeat(5 - digits) : ''
    }
    case 'round_time': {
      const d = parseDate(value)
      if (!d) return ''
      return roundTimeSafe(d, p.level)
    }
    case 'round_coords': {
      const n = toNumber(value)
      return n == null ? '' : n.toFixed([3, 2, 1][p.level] ?? 2)
    }
    case 'round_numeric': {
      const n = toNumber(value)
      return n == null ? value : sigDigits(n, [2, 1][p.level] ?? 2)
    }
    case 'truncate_code':
      return value.replace('.', '').slice(0, [3, 1][p.level] ?? 3)
    case 'redact_text':
      return redactText(value, ctx.names)
  }
}

const roundTimeSafe = (d: Date, level: number) => roundTime(d, Math.max(0, Math.min(3, level)))

export function transformColumn(values: string[], p: ColumnPolicy, ctx: TransformContext): string[] {
  const out = values.map((v) => transformValue(v, p, ctx))
  if (p.pet === 'rare_merge') {
    const threshold = [5, 10, 25][p.level] ?? 5
    const counts = valueCounts(out)
    return out.map((v) => (v && (counts.get(v) ?? 0) < threshold ? 'Other' : v))
  }
  return out
}

const ESCALATE_FROM_KEEP = 'rare_merge' as const

function nextLevel(p: ColumnPolicy): ColumnPolicy | null {
  const levels = PET_META[p.pet].levels.length
  if (p.pet === 'keep') return { ...p, pet: ESCALATE_FROM_KEEP, level: 0, source: 'k-anonymity' }
  if (levels && p.level < levels - 1) return { ...p, level: p.level + 1, source: 'k-anonymity' }
  return null
}

const levelName = (p: ColumnPolicy) => PET_META[p.pet].levels[p.level] ?? PET_META[p.pet].label

export async function applyPolicies(
  dataset: Dataset,
  dets: ColumnDetection[],
  policies: ColumnPolicy[],
  opts: { key: CryptoKey; k: number | null; qis?: string[] | null },
): Promise<ProtectedResult> {
  const log: TransformLogEntry[] = []
  const byCol = new Map(policies.map((p) => [p.column, { ...p }]))
  const ctx: TransformContext = { tokens: new Map(), names: buildNameDictionary(dataset, dets) }

  for (const p of byCol.values()) {
    if (p.pet !== 'pseudonymise') continue
    for (const r of dataset.rows) {
      const v = (r[p.column] ?? '').trim()
      if (v && !ctx.tokens.has(v)) ctx.tokens.set(v, await hmacToken(opts.key, v))
    }
  }
  if (ctx.names)
    log.push({
      step: 'Redaction dictionary',
      detail: "Names from the table's own name columns are removed from free text",
    })

  const kept = dataset.columns.filter((c) => byCol.get(c)?.pet !== 'drop')
  const colValues = new Map<string, string[]>()
  for (const c of kept)
    colValues.set(
      c,
      transformColumn(
        dataset.rows.map((r) => r[c] ?? ''),
        byCol.get(c)!,
        ctx,
      ),
    )
  const dropped = dataset.columns.filter((c) => !kept.includes(c))
  if (dropped.length) log.push({ step: 'Suppressed columns', detail: dropped.join(', ') })

  const build = (): Row[] => dataset.rows.map((_, i) => Object.fromEntries(kept.map((c) => [c, colValues.get(c)![i]])))

  let rows = build()
  let suppressedCells = 0
  const scenarioQis = opts.qis?.filter((c) => kept.includes(c)) ?? []
  const qis = scenarioQis.length
    ? scenarioQis
    : dets.filter((d) => d.role === 'quasi_identifier' && kept.includes(d.column)).map((d) => d.column)

  if (opts.k && qis.length) {
    const k = opts.k
    let ka = kAnonymity(rows, qis, k)
    log.push({
      step: 'k-anonymity target',
      detail: `k ≥ ${k} on ${qis.join(', ')}${scenarioQis.length ? ' (the QIs named in the scenario target)' : ' (all detected QIs)'}; before: ${(ka.shareBelowK * 100).toFixed(1)} % of rows in classes < ${k}`,
    })
    for (let iter = 0; iter < 40 && ka.shareBelowK > 0; iter++) {
      const candidates = qis
        .map((c) => ({ c, next: nextLevel(byCol.get(c)!), distinct: new Set(colValues.get(c)).size }))
        .filter((x) => x.next && x.distinct > 2)
        .sort((a, b) => b.distinct - a.distinct)
      if (!candidates.length) break
      const { c, next } = candidates[0]
      const before = levelName(byCol.get(c)!)
      byCol.set(c, next!)
      colValues.set(
        c,
        transformColumn(
          dataset.rows.map((r) => r[c] ?? ''),
          next!,
          ctx,
        ),
      )
      rows = build()
      const prev = ka.shareBelowK
      ka = kAnonymity(rows, qis, k)
      log.push({
        step: `Generalise ${c}`,
        detail: `${before} → ${levelName(next!)}: rows in classes < ${k} ${(prev * 100).toFixed(1)} % → ${(ka.shareBelowK * 100).toFixed(1)} %`,
      })
    }
    if (ka.shareBelowK > 0) {
      const order = [...qis].sort((a, b) => new Set(colValues.get(b)).size - new Set(colValues.get(a)).size)
      for (const c of order) {
        const keys = rows.map((r) => qis.map((q) => r[q]).join('␟'))
        const counts = valueCounts(keys)
        let n = 0
        rows.forEach((r, i) => {
          if ((counts.get(keys[i]) ?? 0) < k && r[c] !== '') {
            r[c] = ''
            n++
          }
        })
        suppressedCells += n
        if (n)
          log.push({
            step: `Local suppression ${c}`,
            detail:
              `${n} cells blanked in rows whose class was still smaller than ${k}` +
              (n > 0.3 * rows.length
                ? `. Over 30 % of the column: ${rows.length} rows are too few for k ≥ ${k} on ${qis.length} QIs; use the full table, a lower k or fewer QIs`
                : ''),
          })
        if (kAnonymity(rows, qis, k).shareBelowK === 0) break
      }
    }
    const final = kAnonymity(rows, qis, k)
    log.push({
      step: 'Result',
      detail: `${(final.shareBelowK * 100).toFixed(1)} % of rows in classes < ${k}; min k = ${final.minK}`,
    })
  }

  return {
    columns: kept,
    rows,
    policies: dataset.columns.map((c) => byCol.get(c)!),
    log,
    suppressedCells,
    kTarget: opts.k,
    kQis: opts.k ? qis : [],
  }
}
