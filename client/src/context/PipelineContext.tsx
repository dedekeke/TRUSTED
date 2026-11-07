import { createContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { appConfig } from '@/config/appConfig'
import { detectDataset } from '@/features/detect/services/detector'
import { evaluate, type Evaluation } from '@/features/evaluate/services/metrics'
import { choosePolicies, scenarioKQis } from '@/features/protect/services/policyEngine'
import { applyPolicies, newSessionKey } from '@/features/protect/services/transforms'
import { SCENARIOS } from '@/data/scenarios'
import type { ColumnDetection, ColumnPolicy, Dataset, ProtectedResult, Scenario } from '@/types/pipeline.types'

export interface PipelineState {
  dataset: Dataset | null
  detections: ColumnDetection[]
  scenario: Scenario | null
  policies: ColumnPolicy[]
  kTarget: number | null
  result: ProtectedResult | null
  evaluation: Evaluation | null
  running: boolean
  loadDataset: (ds: Dataset) => void
  updateDetection: (column: string, patch: Partial<ColumnDetection>) => void
  setScenarioId: (id: string | null) => void
  updatePolicy: (column: string, patch: Partial<ColumnPolicy>) => void
  resetPolicies: () => void
  setKTarget: (k: number | null) => void
  runProtection: () => Promise<void>
  reset: () => void
}

// eslint-disable-next-line react-refresh/only-export-components
export const PipelineContext = createContext<PipelineState | null>(null)

/**
 * Pipeline state. Policies are *derived* from detections + scenario, with the analyst's manual overrides on top.
 * Any change to an input clears the protected result, so stale output is never shown.
 */
export function PipelineProvider({ children }: { children: ReactNode }) {
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [detections, setDetections] = useState<ColumnDetection[]>([])
  const [scenario, setScenario] = useState<Scenario | null>(null)
  const [overrides, setOverrides] = useState<Record<string, ColumnPolicy>>({})
  const [kTarget, setKTargetState] = useState<number | null>(appConfig.defaultK)
  const [result, setResult] = useState<ProtectedResult | null>(null)
  const [running, setRunning] = useState(false)
  const [key, setKey] = useState<CryptoKey | null>(null)

  // one secret HMAC key per browser session; it is never shown, stored or exported
  useEffect(() => {
    newSessionKey().then(setKey)
  }, [])

  const policies = useMemo(
    () => choosePolicies(detections, scenario).map((p) => overrides[p.column] ?? p),
    [detections, scenario, overrides],
  )

  const evaluation = useMemo(
    () => (dataset && result ? evaluate(dataset, detections, result, kTarget ?? appConfig.defaultK) : null),
    [dataset, detections, result, kTarget],
  )

  const loadDataset = (ds: Dataset) => {
    setDataset(ds)
    setDetections(detectDataset(ds.columns, ds.rows))
    setOverrides({})
    setResult(null)
    // suggest the first scenario of the matching proving-ground dataset
    if (ds.dataset && scenario?.dataset !== ds.dataset)
      setScenario(SCENARIOS.find((s) => s.dataset === ds.dataset) ?? null)
  }

  const updateDetection = (column: string, patch: Partial<ColumnDetection>) => {
    setDetections((ds) =>
      ds.map((d) => (d.column === column ? { ...d, ...patch, source: patch.source ?? 'manual' } : d)),
    )
    setResult(null)
  }

  const setScenarioId = (id: string | null) => {
    setScenario(SCENARIOS.find((s) => s.id === id) ?? null)
    setResult(null)
  }

  const updatePolicy = (column: string, patch: Partial<ColumnPolicy>) => {
    const base = policies.find((p) => p.column === column)
    if (!base) return
    setOverrides((o) => ({
      ...o,
      [column]: { ...base, ...patch, source: 'manual', rationale: patch.rationale ?? 'Set manually by the analyst' },
    }))
    setResult(null)
  }

  const resetPolicies = () => {
    setOverrides({})
    setResult(null)
  }

  const setKTarget = (k: number | null) => {
    setKTargetState(k)
    setResult(null)
  }

  const runProtection = async () => {
    if (!dataset || !key) return
    setRunning(true)
    try {
      setResult(
        await applyPolicies(dataset, detections, policies, {
          key,
          k: kTarget,
          qis: scenarioKQis(scenario, detections)?.qis,
        }),
      )
    } finally {
      setRunning(false)
    }
  }

  const reset = () => {
    setDataset(null)
    setDetections([])
    setOverrides({})
    setResult(null)
  }

  const value: PipelineState = {
    dataset,
    detections,
    scenario,
    policies,
    kTarget,
    result,
    evaluation,
    running,
    loadDataset,
    updateDetection,
    setScenarioId,
    updatePolicy,
    resetPolicies,
    setKTarget,
    runProtection,
    reset,
  }
  return <PipelineContext.Provider value={value}>{children}</PipelineContext.Provider>
}
