import {
  CheckCircleFilled,
  ClockCircleOutlined,
  CloseCircleFilled,
  ExclamationCircleFilled,
  LoadingOutlined,
  MinusCircleOutlined,
  WarningFilled,
} from '@ant-design/icons'
import type { ReactNode } from 'react'
import type { JobState, StepName, StepStatus } from '@/types/job.types'

export const STEP_TITLES: Record<StepName, { title: string; hint: string }> = {
  input: { title: 'Input', hint: 'Read the CSV files and record their size and sha256' },
  detect: { title: 'Detect', hint: 'Label every column (Detect v3) and find PII spans in free text' },
  review: { title: 'Review', hint: 'A person confirms uncertain labels that the scenario needs' },
  select: { title: 'Select', hint: 'Choose a PET for every column from the scenario and the labels' },
  search: { title: 'Search', hint: 'Coarsen until the privacy targets are met, measuring utility at each step' },
  transform: { title: 'Transform', hint: 'Write the protected files and validate them after writing' },
  evaluate: { title: 'Evaluate', hint: 'pets-eval scorecard compared with the organisers’ baselines' },
}

export const STATUS_META: Record<StepStatus, { label: string; color: string; icon: ReactNode }> = {
  success: { label: 'Passed', color: '#16a34a', icon: <CheckCircleFilled /> },
  failed: { label: 'Failed', color: '#dc2626', icon: <CloseCircleFilled /> },
  needs_review: { label: 'Needs review', color: '#ca8a04', icon: <ExclamationCircleFilled /> },
  warning: { label: 'Not approved', color: '#ea580c', icon: <WarningFilled /> },
  running: { label: 'Running', color: '#2563eb', icon: <LoadingOutlined spin /> },
  queued: { label: 'Queued', color: '#9ca3af', icon: <ClockCircleOutlined /> },
  skipped: { label: 'Skipped', color: '#9ca3af', icon: <MinusCircleOutlined /> },
}

export const JOB_META: Record<JobState, { label: string; color: string }> = {
  created: { label: 'Created', color: 'default' },
  running: { label: 'Running', color: 'processing' },
  needs_review: { label: 'Waiting for review', color: 'gold' },
  succeeded: { label: 'Succeeded', color: 'success' },
  failed: { label: 'Failed', color: 'error' },
  cancelled: { label: 'Cancelled', color: 'default' },
}

export function formatDuration(s?: number | null) {
  if (s == null) return ''
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)}s`
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}
