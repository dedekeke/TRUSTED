import PageHeader from '@/components/common/PageHeader'
import { BenchmarkView } from '@/features/benchmark'

export default function Benchmark() {
  return (
    <div>
      <PageHeader
        title="Baseline benchmark"
        description="pets-eval scorecards of the reference solutions shipped with the package. Add your own scorecard.json to compare."
      />
      <BenchmarkView />
    </div>
  )
}
