import { BENCHMARK } from '@/data/benchmark'
import { CATALOG } from '@/data/catalog'
import { SAMPLES } from '@/data/samples'
import { SCENARIOS } from '@/data/scenarios'

/**
 * Data access for the UI. For now everything is hardcoded in src/data/.
 * The functions are async so they can later call the FastAPI backend (`${appConfig.apiBaseUrl}/api/...`)
 * without changing any component.
 */
export const api = {
  scenarios: async () => SCENARIOS,
  benchmark: async () => BENCHMARK,
  catalog: async () => CATALOG,
  samples: async () => SAMPLES.map(({ id, dataset, table, label, rows }) => ({ id, dataset, table, label, rows })),
  sampleCsv: async (id: string) => {
    const s = SAMPLES.find((x) => x.id === id)
    if (!s) throw new Error(`unknown sample ${id}`)
    return s.csv
  },
}
