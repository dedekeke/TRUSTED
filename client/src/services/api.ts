import { appConfig } from '@/config/appConfig'
import { BENCHMARK } from '@/data/benchmark'
import { CATALOG } from '@/data/catalog'
import { SAMPLES } from '@/data/samples'
import { SCENARIOS } from '@/data/scenarios'
import type { Scenario } from '@/types/pipeline.types'
import type { RunState } from '@/types/run.types'

/** Error with the backend's named code (e.g. input_mismatch, step_done, blocked). */
export class ApiError extends Error {
  readonly code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

const base = appConfig.apiBaseUrl.replace(/\/$/, '')

async function request<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${base}/api${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(data?.error?.code ?? `http_${res.status}`, data?.error?.message ?? res.statusText)
  return data as T
}

export interface Confirmation {
  table: string
  column: string
  privacy_role: string
  subtype: string
}

/** The server/api.py pipeline (Detect → confirm → Select → Search). Used when VITE_API_BASE_URL is set. */
export const backend = {
  enabled: appConfig.apiBaseUrl !== '',
  datasets: () => request<{ datasets: string[] }>('/datasets').then((r) => r.datasets),
  createRun: (dataset: string) => request<RunState>('/runs', { dataset }),
  run: (id: string) => request<RunState>(`/runs/${encodeURIComponent(id)}`),
  confirm: (id: string, confirmations: Confirmation[]) =>
    request<RunState>(`/runs/${encodeURIComponent(id)}/confirm`, { confirmations, allow_downgrade: false }),
  select: (id: string, scenario: string) => request<RunState>(`/runs/${encodeURIComponent(id)}/select`, { scenario }),
  search: (id: string, budget: number) => request<RunState>(`/runs/${encodeURIComponent(id)}/search`, { budget }),
}

/** Static data for the in-browser mode; scenarios come from the backend when it is configured. */
export const api = {
  scenarios: async (): Promise<Scenario[]> =>
    backend.enabled ? (await request<{ scenarios: Scenario[] }>('/scenarios')).scenarios : SCENARIOS,
  benchmark: async () => BENCHMARK,
  catalog: async () => CATALOG,
  samples: async () => SAMPLES.map(({ id, dataset, table, label, rows }) => ({ id, dataset, table, label, rows })),
  sampleCsv: async (id: string) => {
    const s = SAMPLES.find((x) => x.id === id)
    if (!s) throw new Error(`unknown sample ${id}`)
    return s.csv
  },
}
