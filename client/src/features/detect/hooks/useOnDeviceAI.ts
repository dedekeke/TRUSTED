import { useCallback, useEffect, useState } from 'react'
import { nanoClassify, nanoStatus, type NanoStatus } from '@/services/onDeviceAI'
import { usePipeline } from '@/hooks/usePipeline'
import type { ColumnDetection } from '@/types/pipeline.types'

export function useOnDeviceAI() {
  const { updateDetection } = usePipeline()
  const [status, setStatus] = useState<NanoStatus>('unsupported')
  const [busy, setBusy] = useState<string | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    nanoStatus().then(setStatus)
  }, [])

  const refine = useCallback(
    async (targets: ColumnDetection[]) => {
      setError(null)
      for (const d of targets) {
        setBusy(d.column)
        try {
          const a = await nanoClassify(d.column, d.stats, setProgress)
          updateDetection(d.column, {
            role: a.role,
            subtype: a.subtype,
            confidence: Math.max(d.confidence, 0.7),
            reasons: [`Gemini Nano (on-device): ${a.reason}`, ...d.reasons.map((r) => `rules: ${r}`)],
            source: 'on-device AI',
          })
          setStatus('available')
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e))
          break
        }
      }
      setBusy(null)
      setProgress(null)
    },
    [updateDetection],
  )

  return { status, busy, progress, error, refine }
}
