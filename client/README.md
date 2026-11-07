# PETs Transformer: web UI

React 19 + TypeScript + Vite, styled with Tailwind CSS 4 and Ant Design 6. Built for the TrustED PETs Transformer
challenge (Since AI Hackathon 2026). It walks through the four steps the challenge asks for:

1. **Detect**: every column gets a privacy role and subtype from its name, value patterns and statistics, with the
   reasons shown. On the labelled samples the role matches the gold catalog for 99 of 108 columns. Optional
   **on-device AI** (Chrome's built-in Gemini Nano) can re-check low-confidence columns; the data never leaves the browser.
2. **Select**: a policy engine picks a PET per column (pseudonymise, generalise, round, truncate, redact, suppress…),
   stricter for public data and lighter for controlled research, with a one-sentence rationale for each.
3. **Transform**: applied in the browser. k-anonymity is enforced on the QIs named in the scenario target by climbing
   generalisation ladders first and suppressing single cells only as a last resort. Every step is logged.
4. **Demonstrate**: risk before vs after, utility per column, aggregates before vs after, the scenario the output is fit
   for, and the residual risks. Exports: protected CSV, field labels for `pets-eval detect`, a JSON report, and the
   row map (for scoring only; never publish it).

The scores shown are an in-browser preview computed with the same formulas as `pets-eval`; official numbers come from
`pets-eval scorecard`.

```bash
yarn            # install
yarn dev        # http://localhost:5173
yarn build      # type-check + production build
yarn lint
```

## Data

Everything is hardcoded in `src/data/` for now: synthetic samples from the proving-ground package (300 random rows
per table), the 27 sharing scenarios, the gold field labels and the baseline scorecards. `src/services/api.ts` is
async, so it can be pointed at the FastAPI backend in `../server` later without touching components.

## Structure

Follows [Recommended Folder Structure for React 2025](https://dev.to/pramod_boda/recommended-folder-structure-for-react-2025-48mc).
Imports use the `@/` alias for `src/`.

```
src/
  components/common   RoleTag, ScoreBar, StatTile, PageHeader, EmptyState, MetricBars
  components/layout   AppLayout, AppHeader, Sidebar
  features/           detect · protect · evaluate · benchmark · scenarios (components / hooks / services)
  pages/              Home, Detect, Protect, Evaluate, Benchmark, Scenarios, NotFound
  routes/             AppRoutes
  context/            PipelineContext (pipeline state), ThemeContext (light / dark)
  hooks/              usePipeline, useTheme, useFetch
  services/           api, csvService, onDeviceAI (Gemini Nano)
  utils/              constants, patterns, dates, stats, format, download
  types/  styles/  config/  data/
```
