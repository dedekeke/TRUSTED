import type { Row } from '@/types/pipeline.types'

export interface KAnonymity {
  qis: string[]
  nClasses: number
  minK: number
  shareBelowK: number
  uniqueness: number
}

export function classKeys(rows: Row[], qis: string[]): string[] {
  return rows.map((r) => qis.map((q) => r[q] ?? '').join('␟'))
}

export function kAnonymity(rows: Row[], qis: string[], k = 5): KAnonymity {
  if (!qis.length || !rows.length)
    return { qis, nClasses: rows.length ? 1 : 0, minK: rows.length, shareBelowK: 0, uniqueness: 0 }
  const keys = classKeys(rows, qis)
  const counts = new Map<string, number>()
  for (const key of keys) counts.set(key, (counts.get(key) ?? 0) + 1)
  let below = 0
  let unique = 0
  let minK = Infinity
  for (const key of keys) {
    const c = counts.get(key)!
    if (c < k) below++
    if (c === 1) unique++
    minK = Math.min(minK, c)
  }
  return { qis, nClasses: counts.size, minK, shareBelowK: below / rows.length, uniqueness: unique / rows.length }
}

export function valueCounts(values: string[]): Map<string, number> {
  const m = new Map<string, number>()
  for (const v of values) m.set(v, (m.get(v) ?? 0) + 1)
  return m
}

export function tvd(a: string[], b: string[]): number {
  const ca = valueCounts(a)
  const cb = valueCounts(b)
  const keys = new Set([...ca.keys(), ...cb.keys()])
  let s = 0
  for (const k of keys) s += Math.abs((ca.get(k) ?? 0) / (a.length || 1) - (cb.get(k) ?? 0) / (b.length || 1))
  return s / 2
}

export function toNumber(v: string): number | null {
  if (v == null) return null
  const s = v.trim().replace(/\s/g, '').replace(',', '.')
  if (!s || !/^-?\d+(\.\d+)?$/.test(s)) return null
  return Number(s)
}

export function median(xs: number[]): number {
  if (!xs.length) return NaN
  const s = [...xs].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

export function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN
}

export function relError(orig: number, prot: number): number {
  if (!Number.isFinite(orig) || !Number.isFinite(prot)) return 1
  if (orig === 0) return prot === 0 ? 0 : 1
  return Math.min(1, Math.abs(prot - orig) / Math.abs(orig))
}
