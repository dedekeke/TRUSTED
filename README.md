# TRUSTED PETS

A local privacy pipeline for the TrustED PETs Transformer challenge (Since AI Hackathon 2026):
**Detect → Select → Search → Transform → Evaluate**. A tabular dataset becomes a protected release with the
reasons for each choice, measured risk and utility, and a validated export. Everything runs on the local machine;
no data leaves it.

- **Detect** labels every column (privacy role, subtype, Art. 9, confidence, `needs_review`), finds PII spans in
  free text and records linkage facts.
- **Select** turns the labels and a sharing scenario (or a requirement spec) into a rule-based plan: one PET per column.
- **Search** coarsens that plan until the k/l/t targets are met while the scenario's utility tasks still work.
- **Transform** writes the protected files, re-validates the written files and publishes only what passes.
- **Evaluate** scores the release with `pets-eval` against the organisers' baselines.

## Layout

The challenge package root is the parent of this folder (`src/`). Code lives here; the package's `data/`,
`truth/`, `holdout/`, `metadata/`, `toolkit/` and `baselines/` are read-only inputs.

```text
start.sh        starts JEV, the API and the UI together
server/
  detect/       column detector (pets_detect, _v2, _v3), text spans, linkage, its own tests
  select/       requirements, relations, policy, select, search, artifacts (import as server.select.*)
  transform/    release gate, staged export, serialized validation, reports
  actions.py    protection operations shared by search previews and the final export
  pipeline.py   whole chain in one command (python -m server.pipeline)
  api.py        local HTTP API for the UI; jobs.py runs pipeline.py in the background,
                api_views.py turns each step's outputs into tables
client/         React UI (Run pipeline, plus in-browser Detect / Protect / Evaluate / Benchmark pages)
tests/          backend tests (pytest)
```

## Setup

Use the package's virtualenv (`../.venv`): it needs `pets_eval`, pandas and numpy, plus Detect's extras.

```bash
../.venv/bin/pip install -r server/detect/requirements.txt
../.venv/bin/pip install -e ../toolkit           # organisers' pets-eval
(cd client && npm install)
../.venv/bin/python -m pytest tests/             # backend tests (bind a local port for fake LLM servers)
```

`server.select` is a package name: do not put `server/select` itself on `PYTHONPATH`, or its `select.py`
shadows the standard-library `select` module.

**Optional LLM tier** (Apple Silicon, about 18 GB memory): AutoTrust-JEV-27B, 4-bit MLX, in its own venv.

```bash
hf download netprojects/AutoTrust-JEV-27B-v1.1-mlx-4bit --local-dir ../models/AutoTrust-JEV-27B-v1.1-mlx-4bit
python3 -m venv .venv-jev
.venv-jev/bin/pip install "git+https://github.com/internet-projects/autotrust-jev27b-mlx@5ef540537b4fc38e6b1586f321d234b465040bc9"
.venv-jev/bin/python -m jev27b_mlx serve ../models/AutoTrust-JEV-27B-v1.1-mlx-4bit --port 8001
```

Serve the local folder, not the repo id, so the server never contacts Hugging Face. Detect finds it at `JEV_HOST`
(default `http://127.0.0.1:8001`) and refuses a server that does not report bidirectional prompt attention; do not
load the model in LM Studio, Ollama or plain `mlx_lm`, which read prompts causally and answer differently. Without a
server the LLM tier is skipped and tiers 1-2 still run. `DETECT_LLM_BACKEND=ollama` uses the older Ollama tier
(`ollama pull qwen2.5:7b`).

**Detect model.** Inference needs a model trained once (training reads the catalog and span labels; inference
never does). From `server/detect`:

```bash
python -m pets_detect_v3 train --root <package-root> --out <new model dir>
```

`model.pkl` is a pickle: load only models you trained, and never commit them.

## Run

Everything at once: JEV on :8001 (reused if already up), the API on :8000, the UI on http://localhost:5174
(`--host`, so reachable on the network). Ctrl-C stops what it started.

```bash
PRIVACY_TOOL_HMAC_KEY=... ./start.sh
# optional: DETECT_MODEL=<dir> (default: newest ../outputs/*/model), RUNS=<new dir>, NO_JEV=1, PETS_ROOT=<package root>
```

By hand:

```bash
PRIVACY_TOOL_HMAC_KEY=... ../.venv/bin/python -m server.api --model <detect model dir> --runs <runs dir> [--port 8000] [--guard]
cd client && VITE_API_BASE_URL=/ npm run dev       # Vite proxies /api to :8000
```

`--guard` refuses any read of the catalog, gold spans, `truth/` or `holdout/` by Detect, Select, Search or
Transform; only the report-only scorecard after export may read them (`server/guard.py`, `evaluation()`). The HMAC key comes only from
`PRIVACY_TOOL_HMAC_KEY`; it is never written to an output. Every run writes into a fresh directory.

The whole chain from the command line (each stage through its own CLI, into `detect/`, `select/`, `search/`,
`transform/` and `pipeline.json`; it stops at a blocked selection or an unapproved public search):

```bash
PRIVACY_TOOL_HMAC_KEY=... python -m server.pipeline --data <package-root>/data/customer_service \
  --scenario CS-S1 --model <detect model dir> --release-id CS-S1/vendor-a --out <fresh dir> [--llm]
```

## UI

The **Run pipeline** page (`/run`) works like a CI run: choose a bundled dataset or a folder of CSV files, choose a
scenario (or write a requirement spec for unknown data) and press Run. Steps Input → Detect → Review → Select →
Search → Transform → Evaluate appear as an accordion (green passed, red failed, yellow waits for a reviewer); each
opens to tables: labels, PET per column, risk targets vs achieved, utility per task, validation checks and the
scorecard against B0/B2/B2-k. A run stopped by `review_required` resumes from Review, exactly like
`select --confirm` on the CLI. **Protected data** downloads `protected/` only. The local LLM tier is on by default.
While a run is in progress, refreshing, closing or leaving the page asks first; leaving anyway cancels the run.

A UI run is the CLI run: `jobs.py` calls `pipeline.run()` with the namespace the CLI builds and the shared
`pipeline.DEFAULTS`, and `server/detect/tests/test_api_parity.py` checks that `protected/` is byte-identical.
Scores come from the stage outputs and `pets-eval`; the UI computes none itself. Responses carry labels, counts,
statuses and digests only, and step logs are scrubbed of personal-looking patterns.

| Endpoint | Purpose |
|---|---|
| `POST /api/jobs` `{dataset}` or `{upload: name}` | new job |
| `PUT /api/jobs/{id}/files/{name}.csv` | upload one CSV, stored byte for byte |
| `POST /api/jobs/{id}/start` `{scenario \| spec, budget, llm, allow_unapproved, no_scorecard, release_id}` | run all steps in the background |
| `GET /api/jobs/{id}` | state and the 7 steps (status, duration, summary, error) |
| `GET /api/jobs/{id}/steps/{step}` / `.../log` | step tables and issues / scrubbed log |
| `POST /api/jobs/{id}/confirm` `{confirmations, allow_downgrade}` | confirm labels; continues from Select (`select-2/`, ...) |
| `POST /api/jobs/{id}/cancel` | stop before the next stage (the running stage finishes); state `cancelled` |
| `GET /api/jobs/{id}/download` | zip of `protected/` (never `evaluation/` or row maps) |
| `GET /api/baselines?dataset=&scenario=` | B0/B2/B2-k and B1 rows from `results/benchmark.json` |

The older step-by-step endpoints under `/api/runs` remain for compatibility.

**Client.** React 19, TypeScript, Vite, Tailwind CSS 4 and Ant Design 6; imports use `@/` for `src/`. Without
`VITE_API_BASE_URL` the other pages run fully in the browser on bundled samples (`src/data/`): in-browser
detection with optional Chrome on-device AI (Gemini Nano) for unsure columns, policy and k-anonymity transforms,
and a risk/utility preview using the `pets-eval` formulas (official numbers come from `pets-eval scorecard`).

```text
client/src/
  pages/        Home, Run, Detect, Protect, Evaluate, Benchmark, Scenarios, NotFound
  features/     pipeline (Run page) · run · detect · protect · evaluate · benchmark · scenarios
  components/   common (RoleTag, ScoreBar, StatTile, ...) and layout (AppLayout, AppHeader, Sidebar)
  services/     api (backend + jobs), csvService, onDeviceAI
  context/ hooks/ routes/ types/ utils/ styles/ config/ data/
```

`npm run dev | build | lint | format` in `client/`.

## Detect

1. **Columns:** privacy role, subtype, Art. 9 flag, confidence, one-line reason and `needs_review`.
2. **Free text:** PII spans (`start`, `end`, `label`, `confidence`, `entity_id`). Entities are numbered per
   conversation when the text table has exactly one foreign key (e.g. `turns.conversation_id`), so a person keeps
   one id across turns; otherwise per cell.
3. **Linkage:** `join`, `subject` and `embedded` relations (an identifier that encodes other attributes, such as a
   HETU encoding birth date and sex). Evidence is numbers only.

| Package | What it is |
|---|---|
| `pets_detect_v3/` | **Main detector.** v1 rules, then a per-column router (kNN on names when any name context exists, logistic regression on values when there is none), then the local LLM for unsure columns. Also `train` / `infer` / `benchmark`. |
| `pets_detect_v2/` | v2 column detector; the free-text span detector (`spans/`), linkage (`linkage.py`) and HTML reports. |
| `pets_detect/` | v1: profiler, regex and checksum patterns, tier-1 rules. |

JEV is a decision model: it does not write text, it scores the options offered (table subject, role, subtype,
Art. 9 yes/no) and that probability is the confidence.

**Results** (leave-one-dataset-out over the 9 labelled datasets; "names hidden" removes column and table names, as
in the obfuscated `unseen` export):

| | macro-F1, names hidden | macro-F1, with names | Free-text PII, F2 |
|---|---|---|---|
| B1 / B2 (organisers' baselines) | 0.401 | 0.646 | 0.184 |
| v1 | 0.757 | 0.858 | – |
| v2 | 0.766 | 0.857 | 0.998 |
| **v3** | **0.774** | 0.854 | 0.998 |

Recall on PERSON, PHONE, ADDRESS and NATIONAL_ID spans is 0.999 (HEALTH-S1 requires 0.95).

**Commands** (in `server/detect`):

```bash
python -m pets_detect_v3 infer --model <model dir> --data <package-root>/data/health --out <new dir> [--no-llm]
python -m pets_detect_v3 benchmark --root <package-root> --labels <dir>/labels.csv   # evaluation only (reads the catalog)
python -m pets_detect_v3 detect --datasets health [--no-llm]   # development path (reads the catalog)
python -m pets_detect_v3 unseen                                  # organisers' format
python -m pets_detect_v2 spans --base v3                         # span training, scoring, submission
python -m pets_detect_v2 linkage
python -m pets_detect_v3 ablation | compare                      # router ablation; v3 vs saved v1/v2 reports
python -m unittest discover -s tests
```

`infer` reads only the model dir and `--data` and writes `labels.csv`, `spans.jsonl`, `linkage.json` and
`manifest.json` (contract `pets.detect.manifest/1`: raw-byte sha256 of every input CSV, artifact digests and the
label vocabulary). A dataset that was part of training is scored leave-one-dataset-out.

**Limitations.** Tier-1 name rules were written after reading the catalog, so "with names" scores are optimistic;
names-hidden scores and the private `unseen` labels are the honest test. Ablation choices were made on the scored
datasets, so gains below 0.01 may not carry over. The free text is synthetic and template-based. v3 over-trusts the
`_name` suffix (bus-stop names become `PERSON_NAME`) and on `unseen` misses a trade-union code column that v2 flags.
`out/`, `.cache/` and `pets_submission/` hold values from the data: keep them private.

## Select and Search

```bash
python -m server.select select --data <package-root>/data/health --scenario HEALTH-S1 \
  --labels <detect-out>/labels.csv --release-id <id> --out <fresh-plan-dir>   # needs <detect-out>/manifest.json
PRIVACY_TOOL_HMAC_KEY=... python -m server.select search --data <package-root>/data/health \
  --plan <fresh-plan-dir>/decisions.json --budget 50 --out <fresh-search-dir> [--detect <detect-out>]
```

- `--labels` reads the saved Detect artifact (never trains or runs Detect). Labels must cover exactly the input
  columns with confidence in [0,1]. `needs_review` triggers conservative treatment even at high confidence; detector
  free-text reasons and samples never reach selection outputs. Without `--labels` a legacy built-in detector is
  used and the plan is marked `provenance.bound: false`.
- `--confirm <csv>` takes reviewed labels (`table,column,privacy_role,subtype`); weaker protection also needs
  `--allow-downgrade` and is reported as a warning. An uncertain, unconfirmed required column blocks with
  `review_required`. `--spec <json>` states requirements for a dataset without a scenario; `--no-purpose` declares none.
- `decisions.json` records `provenance` (input digests, dataset fingerprint, detector and artifact digests,
  `confirm_sha256`), `evidence` (span/linkage counts and ids only) and `reviews`. `search` re-checks the input
  digests and records `plan_sha256`. Neither command writes protected tables or row maps.
- Search probes requirement floors at τ=0.8, then coarsens one rung at a time (deterministic ties, local
  suppression ≤2%), with at most 50 evaluations. k/l/t and uniqueness count distinct subjects; unknown subjects stay
  unresolved. Pass the same `--detect` dir as Transform so previews redact text exactly as the export.

| Status | Meaning | Exit |
|---|---|---|
| `policy_valid` | plan within the rule matrix; targets not yet measured; **not** an approval | 0 (select) |
| `blocked` | named input, policy, review, span or linkage conflict, or a rejected artifact | 2 |
| `measured_ok` | targets and utility met; the only status with `outcome.approved: true` | 0 (search) |
| `target_unmet` | allowed candidate space covered, no candidate meets the targets | 3 |
| `budget_exhausted` | budget ran out with candidates left; not a proof of infeasibility | 4 |

On a non-public release, `target_unmet` / `budget_exhausted` is a warning in the pipeline and the run continues to a
NOT_APPROVED export; public releases stop. Every plan carries `outcome` = `{policy_valid, targets_met, approved,
budget, targets, achieved, violations}`.

Issue codes. Rejections (exit 2, nothing written): `manifest_missing`, `manifest_schema`, `dataset_mismatch`,
`table_set_mismatch`, `input_mismatch`, `fingerprint_mismatch`, `labels_mismatch`, `labels_schema`,
`artifact_mismatch`, `artifact_missing`, `provenance_missing`. Plan errors/warnings: `unsupported_label`,
`review_required`, `stale_span`, `missing_span_evidence`, `missing_linkage_evidence`, `ambiguous_join`,
`ambiguous_subject`, `embedded_qi`, `provenance_unbound`. Only 16-hex artifact ids are echoed; anything else is
reported as `line N` / `relation N`.

### Select module contracts

Tables are `dict[str, pandas.DataFrame]` read with `dtype=str, keep_default_na=False`; column references are
`"table.column"`.

| Module | Entry point | Returns |
|---|---|---|
| `detect` | `detect_table(df, table, dataset="")`, `review_queue(labels)` | legacy labels `dataset,table,column,privacy_role,subtype,confidence,evidence`; rows with confidence < 0.6 |
| `relations` | `discover(tables, labels=None, declared=None)` | `keys`, `joins` (`parent`, `child`, `coverage`, `orphans`, `confidence`), `subject_keys` / `subject_paths` per table, `subject_key`, `conflicts`, `notices`. Subject keys need labels. `declared = {"joins": [[parent, child]], "subject_key": "t.c"}` overrides discovery |
| `requirements` | `from_scenario(scenario_id, tables, root, probe=True, tolerance=0.05)`, `from_spec(path)`, `no_purpose(trust_level, dataset)` | `source`, `scenario`, `dataset`, `trust_level`, `targets`, `tasks` (`id`, `table`, `columns`, `any_of`, `precision`, `evidence`), `required`, `any_of`, `precision`, `joins` (`same_name` joins must be confirmed by `relations`), `subject_key`, `warnings` |
| `policy` | `candidates(label, trust_level, required, in_join=False, precision=None, k=None)`, `targets(trust_level, scenario_targets=None)`, `violations(label, rung, trust_level, k=None)` | rungs finest first (`action`, `method`, `params`, `level`) with `needs_review`, `escalate`, `notes`; targets `k`, `l`, `free_text`, `max_suppression`; breaches (only DROP or an offered rung passes) |
| `select` | `select(tables, labels, relations, requirements, release_id=None)`, `confirm(labels, confirmed)`, `render(plan)` | plan (`decisions.json`): `tables`, `columns` (chosen rung + all rungs), `derived`, `domains`, `review_queue`, `warnings`, `errors`, `reviews`, `label_coverage`, `outcome`, status |
| `search` | `search(tables, plan, key, tasks=None, orig=None, budget=50, tau=0.8)` | plan with chosen rungs, measured results and trace |
| `transform` | `check_plan(tables, plan)`, `release_gate(plan, allow_unapproved=False)`, `apply(...)` | rule-matrix re-check; the shared approval rule; legacy in-memory export (use `python -m server.transform` for releases) |

Drop-one probing uses tolerance 0.05, so two interchangeable columns can each look unnecessary alone; parsed
alternatives (`any_of`) catch that. Selection never reads the catalog, `truth/` or gold spans.

## Transform

```bash
PRIVACY_TOOL_HMAC_KEY=... python -m server.transform --data <package-root>/data/health \
  --plan <fresh-search-dir>/decisions.json --out <fresh-run-dir> \
  [--detect <detect-out-dir>] [--text-fallback rules] [--allow-unapproved] [--no-scorecard]
```

`python -m server.select transform` calls the same executor. Before writing anything, Transform re-checks the plan's
`provenance` against the input bytes and, with `--detect`, the Detect manifest, `spans.jsonl` digest and every
`span_id`/offset. It refuses a plan that is not an approved `measured_ok`, has unresolved review items on released
or required fields, or was selected without an explicit `select --release-id`. Free-text columns need Detect spans; the rule-only redactor
must be chosen explicitly with `--text-fallback rules`. It runs exactly the selected rung for every column and never
lowers a target, invents a subject or drops rows.

Free text: at internal/contractual trust, `[PERSON_1]`, `[PHONE_2]`, ... numbered per conversation (numbers restart
in the next one, so they do not link records); otherwise `[PERSON]`.

| Exit | Status | Result |
|---|---|---|
| 0 | `validated` | `protected/`, `evaluation/`, `reports/`, `manifest.json` with `approved_release: true` |
| 0 | `unapproved_export` | only with `--allow-unapproved`: same layout and checks, k/l/t and utility recorded but not gating, `NOT_APPROVED.txt` in `protected/` and `evaluation/`, rows below k listed in `evaluation/k_flags_<table>.csv` |
| 2 | `refused` | preflight failed: only `diagnostics.json` / `.md`; input-binding rejections print the code and write nothing |
| 3 | `validation_failed` | files stay private under `staging/`; diagnostics and a `failed` manifest name the checks |

```text
<fresh-run>/
  decisions.json, decisions.md, manifest.json, transform_stats.json
  protected/<table>.csv             recipient data only
  evaluation/<table>.csv            owner-private copy for scoring, rowmap_<table>.csv, input_manifest.json
  reports/                          summary.md, identifier_check.json, scorecard.json / .html
```

After writing, Transform reloads every file and checks the round trip and row maps, action output formats,
join/orphan status, suppression against the measured candidate, k/l/t, uniqueness and utility on the written tables,
and `pets-eval check` on all lines of `protected/`. Each scanner hit is attributed to a cell; the only accepted false
positive is a pattern inside a validated HMAC token. The scorecard runs on the evaluation copy and is report-only.
CSV is UTF-8 with a header and no index; missing values are empty fields (never `nan`/`None`); IDs and tokens stay
strings; JSON has no NaN/Infinity and no keys or raw values.

## Status

- **CS-S1, full data:** detect → `policy_valid` → `measured_ok` (2 evaluations) → **validated**. Utility CS-U1
  0.9995, CS-U3 1.0, CS-U4 1.0, CS-U5 0.0 (baseline also 0.0). Residual text PII: NATIONAL_ID, PAYMENT_CARD, IBAN,
  PHONE, EMAIL 0%; SECRET 1.07%; PERSON 0.2%; HEALTH 0.57%; ORG 17.8%, LOCATION 12.0%, DATE 6.6%.
- **HEALTH-S1, full data:** blocks at select with `review_required` on `ed_visits.visit_id` and
  `lab_results.test_code` (needed by H-U7) until a reviewer confirms them. The measured plan has stayed
  `target_unmet` (12.98% below k=5, l failures, 921 visits and 2,205 lab rows without a subject id); more search does
  not repair missing identities, so a full release needs the owner to resolve them and reselect.
- Cross-dataset shared identifiers and Detect's k<5 row estimate are not part of single-dataset inference.

## Data safety

Never commit raw data, Detect outputs or caches, trained models, selection/protected/evaluation outputs, row maps,
keys or `.env` files. Run folders hold data: keep them private and write every run to a fresh directory.
