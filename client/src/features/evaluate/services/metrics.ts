/**
 * Demonstrate step (in-browser preview). Uses the same privacy and composite formulas as `pets-eval scorecard`,
 * but with proxy measurements that need no ground truth. The official numbers come from pets-eval.
 */
import type { ColumnDetection, Dataset, ProtectedResult } from '@/types/pipeline.types'
import { scanText } from '@/utils/patterns'
import { kAnonymity, mean, median, relError, toNumber, tvd, type KAnonymity } from '@/utils/stats'
import { transformColumn } from '@/features/protect/services/transforms'

export interface RiskComponent {
  key: string
  label: string
  before: number
  after: number
  explain: string
}

export interface ColumnUtility {
  column: string
  role: string
  treatment: string
  fidelity: number
  granularity: number
  score: number
  note: string
}

export interface AggregateComparison {
  column: string
  kind: 'numeric' | 'categorical'
  before: string
  after: string
  error: number
}

export interface Evaluation {
  risks: RiskComponent[]
  privacyBefore: number
  privacyAfter: number
  utility: number
  composite: number
  kBefore: KAnonymity
  kAfter: KAnonymity
  columns: ColumnUtility[]
  aggregates: AggregateComparison[]
  residual: { counts: Record<string, number>; examples: Record<string, string[]> }
}

export const privacyScore = (risks: number[]) => {
  if (!risks.length) return 1
  const worst = Math.max(...risks)
  const avg = risks.reduce((a, b) => a + b, 0) / risks.length
  return 1 - (0.5 * worst + 0.5 * avg)
}

/** weighted harmonic mean of privacy (30) and utility (25), as in pets-eval */
export const compositeScore = (p: number, u: number) => (p <= 0 || u <= 0 ? 0 : 55 / (30 / p + 25 / u))

const DI_TEXT_SUBTYPES = new Set([
  'PERSON_NAME',
  'EMAIL',
  'PHONE',
  'NATIONAL_ID',
  'IBAN',
  'STREET_ADDRESS',
  'LICENSE_PLATE',
])

export function evaluate(ds: Dataset, dets: ColumnDetection[], res: ProtectedResult, k = 5): Evaluation {
  const n = ds.rows.length || 1
  const det = new Map(dets.map((d) => [d.column, d]))
  const pol = new Map(res.policies.map((p) => [p.column, p]))
  const released = new Set(res.columns)

  // 1. direct identifiers retained verbatim (same row, same column)
  const diCols = dets.filter((d) => d.role === 'direct_identifier').map((d) => d.column)
  let diTotal = 0
  let diKept = 0
  for (const c of diCols) {
    ds.rows.forEach((r, i) => {
      const v = (r[c] ?? '').trim()
      if (!v) return
      diTotal++
      if (released.has(c) && res.rows[i][c] === v) diKept++
    })
  }
  const diBefore = diTotal ? 1 : 0
  const diAfter = diTotal ? diKept / diTotal : 0

  // 2. free-text leakage: identifier values of the same row that occur in the original text and survive redaction
  const textCols = dets.filter((d) => d.role === 'free_text').map((d) => d.column)
  const idCols = dets.filter((d) => DI_TEXT_SUBTYPES.has(d.subtype)).map((d) => d.column)
  let occ = 0
  let leaked = 0
  for (const tc of textCols) {
    ds.rows.forEach((r, i) => {
      const orig = r[tc] ?? ''
      if (!orig) return
      const prot = released.has(tc) ? (res.rows[i][tc] ?? '') : ''
      for (const ic of idCols) {
        for (const part of (r[ic] ?? '').split(/\s+/).filter((t) => t.length >= 3)) {
          if (orig.includes(part)) {
            occ++
            if (prot.includes(part)) leaked++
          }
        }
      }
    })
  }

  // 3. residual identifiers anywhere in the output (regex scan, like pets-eval check)
  const counts: Record<string, number> = {}
  const examples: Record<string, string[]> = {}
  let rowsWithResidual = 0
  for (const r of res.rows) {
    const before = Object.values(counts).reduce((a, b) => a + b, 0)
    for (const c of res.columns) {
      const v = r[c]
      if (v && !v.startsWith('tok_')) scanText(v, counts, examples)
    }
    if (Object.values(counts).reduce((a, b) => a + b, 0) > before) rowsWithResidual++
  }
  const countsBefore: Record<string, number> = {}
  let rowsResidualBefore = 0
  for (const r of ds.rows) {
    const b = Object.values(countsBefore).reduce((a, x) => a + x, 0)
    for (const c of ds.columns) if (r[c]) scanText(r[c], countsBefore, {})
    if (Object.values(countsBefore).reduce((a, x) => a + x, 0) > b) rowsResidualBefore++
  }

  // 4. k-anonymity / uniqueness on the detected quasi-identifiers
  // measure on the QI set k-anonymity was enforced on (the scenario's), else on every detected QI
  const qisOrig = res.kQis.length ? res.kQis : dets.filter((d) => d.role === 'quasi_identifier').map((d) => d.column)
  const qisProt = qisOrig.filter((c) => released.has(c))
  const kBefore = kAnonymity(ds.rows, qisOrig, k)
  const kAfter = kAnonymity(res.rows, qisProt, k)

  const risks: RiskComponent[] = [
    {
      key: 'di',
      label: 'Direct identifiers retained',
      before: diBefore,
      after: diAfter,
      explain: 'Share of direct-identifier values still present verbatim',
    },
    {
      key: 'text',
      label: 'Free-text identifier leakage',
      before: occ ? 1 : 0,
      after: occ ? leaked / occ : 0,
      explain: `Identifiers of the same person found in text (${occ} occurrences) that survive redaction`,
    },
    {
      key: 'residual',
      label: 'Rows with residual identifiers',
      before: rowsResidualBefore / n,
      after: rowsWithResidual / n,
      explain: 'Regex scan for HETU, e-mail, IBAN, cards, phones, IPs, MACs, plates',
    },
    {
      key: 'k',
      label: `Records with k < ${k}`,
      before: kBefore.shareBelowK,
      after: kAfter.shareBelowK,
      explain: `Rows in equivalence classes smaller than ${k} on the quasi-identifiers`,
    },
    {
      key: 'unique',
      label: 'Unique on quasi-identifiers',
      before: kBefore.uniqueness,
      after: kAfter.uniqueness,
      explain: 'Proxy for linkage re-identification: rows that an attacker knowing the QIs could single out',
    },
  ]

  // 5. utility per analytical column
  const columns: ColumnUtility[] = []
  for (const c of ds.columns) {
    const d = det.get(c)!
    const p = pol.get(c)!
    if (['direct_identifier', 'record_key'].includes(d.role) && p.pet !== 'pseudonymise') continue
    if (d.role === 'technical_identifier' && p.pet === 'drop') continue
    const origVals = ds.rows.map((r) => r[c] ?? '')
    if (!released.has(c)) {
      columns.push({
        column: c,
        role: d.role,
        treatment: 'suppressed',
        fidelity: 0,
        granularity: 0,
        score: 0,
        note: 'Column not released: analyses that need it are impossible',
      })
      continue
    }
    const protVals = res.rows.map((r) => r[c] ?? '')
    if (p.pet === 'pseudonymise') {
      columns.push({
        column: c,
        role: d.role,
        treatment: 'join key',
        fidelity: 1,
        granularity: 1,
        score: 1,
        note: 'Keyed tokens keep equality, so joins and counts per person survive',
      })
      continue
    }
    if (p.pet === 'redact_text') {
      const changed = origVals.filter((v, i) => v !== protVals[i]).length
      const kept = 1 - (changed / Math.max(1, origVals.filter(Boolean).length)) * 0.2
      columns.push({
        column: c,
        role: d.role,
        treatment: 'redacted',
        fidelity: kept,
        granularity: 1,
        score: kept,
        note: `${changed} texts changed; the rest of each text is kept for topic and sentiment analysis`,
      })
      continue
    }
    // the same transform applied to the original without suppression: differences = information lost to suppression
    const mapped = transformColumn(origVals, { ...p }, { tokens: new Map(), names: null })
    const fidelity = 1 - tvd(mapped, protVals)
    const dBefore = new Set(origVals.filter(Boolean)).size || 1
    const dAfter = new Set(protVals.filter(Boolean)).size
    const granularity = Math.min(1, dAfter / dBefore)
    const generalised = p.pet !== 'keep'
    const score = generalised ? fidelity * (0.6 + 0.4 * Math.sqrt(granularity)) : fidelity
    columns.push({
      column: c,
      role: d.role,
      treatment: p.pet,
      fidelity,
      granularity,
      score,
      note: generalised
        ? `${dBefore} → ${dAfter} distinct values`
        : fidelity < 1
          ? 'Some cells suppressed for k-anonymity'
          : 'Unchanged',
    })
  }
  const utility = columns.length ? columns.reduce((a, b) => a + b.score, 0) / columns.length : 0

  // 6. before/after aggregates the recipient would compute
  const aggregates: AggregateComparison[] = []
  for (const c of res.columns) {
    const d = det.get(c)!
    if (!['sensitive_attribute', 'non_sensitive', 'quasi_identifier'].includes(d.role)) continue
    const o = ds.rows.map((r) => r[c] ?? '')
    const pr = res.rows.map((r) => r[c] ?? '')
    const on = o.map(toNumber).filter((x): x is number => x != null)
    const pn = pr.map(toNumber).filter((x): x is number => x != null)
    if (on.length > 0.8 * o.filter(Boolean).length && on.length > 10 && pn.length > 0) {
      aggregates.push({
        column: c,
        kind: 'numeric',
        before: `mean ${mean(on).toFixed(2)} · median ${median(on).toFixed(2)}`,
        after: `mean ${mean(pn).toFixed(2)} · median ${median(pn).toFixed(2)}`,
        error: (relError(mean(on), mean(pn)) + relError(median(on), median(pn))) / 2,
      })
    } else if (new Set(o).size <= 20) {
      const top = (vals: string[]) => {
        const m = new Map<string, number>()
        vals.forEach((v) => m.set(v || '∅', (m.get(v || '∅') ?? 0) + 1))
        return [...m.entries()]
          .sort((a, b) => b[1] - a[1])
          .slice(0, 3)
          .map(([k2, v]) => `${k2} ${((v / vals.length) * 100).toFixed(0)}%`)
          .join(' · ')
      }
      aggregates.push({ column: c, kind: 'categorical', before: top(o), after: top(pr), error: tvd(o, pr) })
    }
  }

  const privacyBefore = privacyScore(risks.map((r) => r.before))
  const privacyAfter = privacyScore(risks.map((r) => r.after))
  return {
    risks,
    privacyBefore,
    privacyAfter,
    utility,
    composite: compositeScore(privacyAfter, utility),
    kBefore,
    kAfter,
    columns,
    aggregates: aggregates.slice(0, 12),
    residual: { counts, examples },
  }
}
