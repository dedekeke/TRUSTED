import EmptyState from '@/components/common/EmptyState'
import PageHeader from '@/components/common/PageHeader'
import { AggregatesTable, ExportPanel, RiskTable, ScenarioFit, ScoreTiles, UtilityTable } from '@/features/evaluate'
import { usePipeline } from '@/hooks/usePipeline'

export default function Evaluate() {
  const { dataset, detections, result, evaluation, scenario } = usePipeline()
  if (!dataset || !result || !evaluation)
    return (
      <EmptyState
        title="Nothing to evaluate yet"
        description="Run the transformer on the Protect step."
        actionLabel="Go to Protect"
        to="/protect"
      />
    )

  return (
    <div className="space-y-5">
      <PageHeader
        step="Step 3"
        title="Demonstrate: risk removed, value kept"
        description="An in-browser preview using the same privacy and composite formulas as pets-eval, with proxy attacks. Confirm the final numbers with pets-eval scorecard."
      />
      <ScoreTiles ev={evaluation} />
      <div className="grid gap-4 xl:grid-cols-2">
        <RiskTable risks={evaluation.risks} />
        <ScenarioFit scenario={scenario} ev={evaluation} result={result} detections={detections} />
      </div>
      <AggregatesTable rows={evaluation.aggregates} />
      <UtilityTable columns={evaluation.columns} />
      <ExportPanel dataset={dataset} detections={detections} result={result} ev={evaluation} scenario={scenario} />
    </div>
  )
}
