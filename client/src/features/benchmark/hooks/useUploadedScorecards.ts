import { useEffect, useState } from 'react'
import type { Scorecard } from '@/types/data.types'

const KEY = 'uploaded-scorecards'

export interface UploadedScorecard {
  name: string
  dataset: string
  scorecard: Scorecard
}

/** Scorecards dropped in by the team (pets-eval scorecard.json); remembered in this browser only. */
export function useUploadedScorecards() {
  const [items, setItems] = useState<UploadedScorecard[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(KEY) ?? '[]') as UploadedScorecard[]
    } catch {
      return []
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(items))
    } catch {
      /* storage unavailable */
    }
  }, [items])

  const add = (u: UploadedScorecard) =>
    setItems((xs) => [...xs.filter((x) => !(x.name === u.name && x.dataset === u.dataset)), u])
  const remove = (name: string, dataset: string) =>
    setItems((xs) => xs.filter((x) => !(x.name === name && x.dataset === dataset)))
  return { items, add, remove }
}
