import { useContext } from 'react'
import { PipelineContext } from '@/context/PipelineContext'

export function usePipeline() {
  const ctx = useContext(PipelineContext)
  if (!ctx) throw new Error('usePipeline must be used inside <PipelineProvider>')
  return ctx
}
