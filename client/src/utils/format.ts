export const pct = (v: number | null | undefined, digits = 1) =>
  v == null || Number.isNaN(v) ? '–' : `${(v * 100).toFixed(digits)} %`

export const score = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? 'n/a' : v.toFixed(2))

export const num = (v: number) => v.toLocaleString('en-US')

export const humanize = (s: string) => s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

export const scoreColor = (v: number | null | undefined) =>
  v == null ? '#bfbfbf' : v >= 0.75 ? '#52c41a' : v >= 0.5 ? '#faad14' : '#ff4d4f'

export const riskColor = (v: number) => (v <= 0.05 ? '#52c41a' : v <= 0.25 ? '#faad14' : '#ff4d4f')
