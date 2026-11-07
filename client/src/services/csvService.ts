import Papa from 'papaparse'
import { appConfig } from '@/config/appConfig'
import type { Row } from '@/types/pipeline.types'

export interface ParsedCsv {
  columns: string[]
  rows: Row[]
  truncated: boolean
}

/** Parse CSV text with every value kept as a string (phone numbers, postcodes and IDs break as numbers). */
export function parseCsvText(text: string, maxRows = appConfig.maxUploadRows): ParsedCsv {
  const res = Papa.parse<Row>(text, { header: true, skipEmptyLines: true, dynamicTyping: false })
  const columns = (res.meta.fields ?? []).filter(Boolean)
  return { columns, rows: res.data.slice(0, maxRows), truncated: res.data.length > maxRows }
}

export function parseCsvFile(file: File, maxRows = appConfig.maxUploadRows): Promise<ParsedCsv> {
  return file.text().then((t) => parseCsvText(t, maxRows))
}
