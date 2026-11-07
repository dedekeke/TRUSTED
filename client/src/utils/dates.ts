/** Lenient date parsing for the mixed formats found in real exports (ISO, d.m.yyyy, dd/mm/yy, Finnish HETU). */

export function parseDate(value: string): Date | null {
  const v = value.trim()
  if (!v) return null
  let m = v.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/)
  if (m) return mk(+m[1], +m[2], +m[3], +(m[4] ?? 0), +(m[5] ?? 0))
  m = v.match(/^(\d{1,2})[./](\d{1,2})[./](\d{2,4})$/)
  if (m) {
    let y = +m[3]
    if (m[3].length === 2) y += y > 30 ? 1900 : 2000
    return mk(y, +m[2], +m[1])
  }
  return null
}

/** Birth date encoded in a Finnish personal identity code (HETU). */
export function birthDateFromHetu(hetu: string): Date | null {
  const m = hetu.trim().match(/^(\d{2})(\d{2})(\d{2})([-+A-FU-Y])/)
  if (!m) return null
  const sign = m[4]
  const century = sign === '+' ? 1800 : 'ABCDEF'.includes(sign) ? 2000 : 1900
  return mk(century + +m[3], +m[2], +m[1])
}

function mk(y: number, mo: number, d: number, h = 0, mi = 0): Date | null {
  const dt = new Date(Date.UTC(y, mo - 1, d, h, mi))
  return Number.isNaN(dt.getTime()) || mo < 1 || mo > 12 || d < 1 || d > 31 ? null : dt
}

const pad = (n: number) => String(n).padStart(2, '0')

export function isoWeek(d: Date): string {
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()))
  const day = t.getUTCDay() || 7
  t.setUTCDate(t.getUTCDate() + 4 - day)
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1))
  const week = Math.ceil(((t.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
  return `${t.getUTCFullYear()}-W${pad(week)}`
}

/** level 0 hour, 1 day, 2 ISO week, 3 month — formats understood by pets-eval */
export function roundTime(d: Date, level: number): string {
  const y = d.getUTCFullYear()
  const mo = pad(d.getUTCMonth() + 1)
  const day = pad(d.getUTCDate())
  switch (level) {
    case 0:
      return `${y}-${mo}-${day} ${pad(d.getUTCHours())}:00`
    case 1:
      return `${y}-${mo}-${day}`
    case 2:
      return isoWeek(d)
    default:
      return `${y}-${mo}`
  }
}

export function ageAt(birth: Date, ref = new Date(Date.UTC(2025, 6, 1))): number {
  let a = ref.getUTCFullYear() - birth.getUTCFullYear()
  const before =
    ref.getUTCMonth() < birth.getUTCMonth() ||
    (ref.getUTCMonth() === birth.getUTCMonth() && ref.getUTCDate() < birth.getUTCDate())
  if (before) a -= 1
  return a
}
