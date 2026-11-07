import { useCallback, useEffect, useState } from 'react'
import { ApiError, jobs } from '@/services/api'
import type { Job } from '@/types/job.types'

const POLL_MS = 1500

/** Poll a job while it runs; stop once it succeeds, fails or waits for a review. refresh() restarts polling. */
export function useJob(id: string | undefined) {
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (!id) return
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const j = await jobs.get(id)
        if (!alive) return
        setJob(j)
        setError(null)
        if (j.state === 'running' || j.state === 'created') timer = setTimeout(poll, POLL_MS)
      } catch (e) {
        if (!alive) return
        setError(e instanceof ApiError ? e : new ApiError('network', String(e)))
        timer = setTimeout(poll, POLL_MS * 4) // the server may be restarting: keep trying, slower
      }
    }
    poll()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [id, tick])

  const refresh = useCallback(() => setTick((t) => t + 1), [])
  return { job, error, refresh, setJob }
}
