import Papa from 'papaparse'
import type { Row } from '@/types/pipeline.types'

export function downloadText(filename: string, text: string, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadCsv(filename: string, columns: string[], rows: Row[]) {
  downloadText(
    filename,
    Papa.unparse({ fields: columns, data: rows.map((r) => columns.map((c) => r[c] ?? '')) }),
    'text/csv',
  )
}

export function downloadJson(filename: string, obj: unknown) {
  downloadText(filename, JSON.stringify(obj, null, 2), 'application/json')
}
