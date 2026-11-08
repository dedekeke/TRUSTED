import { appConfig } from '@/config/appConfig'
import { BENCHMARK } from '@/data/benchmark'
import { CATALOG } from '@/data/catalog'
import { SAMPLES } from '@/data/samples'
import { SCENARIOS } from '@/data/scenarios'
import type { Scenario } from '@/types/pipeline.types'
import type { Job, StartOptions, StepName, StepView } from '@/types/job.types'
import type { RunState } from '@/types/run.types'

export class ApiError extends Error {
  readonly code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

const base = appConfig.apiBaseUrl.replace(/\/$/, '')

async function request<T>(path: string, body?: unknown, keepalive = false): Promise<T> {
  const res = await fetch(`${base}/api${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    keepalive,
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

const jobPath = (id: string) => `/jobs/${encodeURIComponent(id)}`

export const jobs = {
  create: (source: { dataset: string } | { upload: string }) => request<Job>('/jobs', source),
  get: (id: string) => request<Job>(jobPath(id)),
  start: (id: string, options: StartOptions) => request<Job>(`${jobPath(id)}/start`, options),
  confirm: (id: string, confirmations: Confirmation[], allowDowngrade = false) =>
    request<Job>(`${jobPath(id)}/confirm`, { confirmations, allow_downgrade: allowDowngrade }),

  cancel: (id: string, keepalive = false) => request<Job>(`${jobPath(id)}/cancel`, {}, keepalive),
  step: (id: string, step: StepName) => request<StepView>(`${jobPath(id)}/steps/${step}`),
  log: (id: string, step: StepName) => request<{ step: StepName; log: string }>(`${jobPath(id)}/steps/${step}/log`),
  downloadUrl: (id: string) => `${base}/api${jobPath(id)}/download`,

  upload: async (id: string, file: File, onProgress?: (share: number) => void) =>
    new Promise<{ file: string; bytes: number; sha256: string }>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('PUT', `${base}/api${jobPath(id)}/files/${encodeURIComponent(file.name)}`)
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
      xhr.onload = () => {
        const data = (() => {
          try {
            return JSON.parse(xhr.responseText)
          } catch {
            return null
          }
        })()
        if (xhr.status >= 200 && xhr.status < 300) resolve(data)
        else reject(new ApiError(data?.error?.code ?? `http_${xhr.status}`, data?.error?.message ?? xhr.statusText))
      }
      xhr.onerror = () => reject(new ApiError('network', 'upload failed'))
      xhr.send(file)
    }),
}

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
