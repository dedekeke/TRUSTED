import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError, backend } from '@/services/api'
import type { RunState } from '@/types/run.types'

const STORE = 'pets.runId'

function remembered(): string | null {
  try {
    return sessionStorage.getItem(STORE)
  } catch {
    return null
  }
}

function remember(id: string) {
  try {
    sessionStorage.setItem(STORE, id)
  } catch {
    // storage blocked: the ?run= URL parameter still carries the run
  }
}

export function useRun() {
  const [params, setParams] = useSearchParams()
  const runId = params.get('run') ?? remembered()
  const [run, setRun] = useState<RunState | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<ApiError | null>(null)

  useEffect(() => {
    if (!runId) return
    let alive = true
    backend
      .run(runId)
      .then((r) => alive && setRun(r))
      .catch((e: unknown) => alive && setError(e instanceof ApiError ? e : new ApiError('network', String(e))))
    return () => {
      alive = false
    }
  }, [runId])

  const act = async (step: string, call: () => Promise<RunState>) => {
    setBusy(step)
    setError(null)
    try {
      const r = await call()
      setRun(r)
      remember(r.id)
      if (params.get('run') !== r.id) setParams({ run: r.id })
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError('network', String(e)))

      if (runId) backend.run(runId).then(setRun, () => undefined)
    } finally {
      setBusy(null)
    }
  }

  return { runId, run, busy, error, act }
}
