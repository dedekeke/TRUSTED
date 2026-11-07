# TRUSTED PETS

This is the central backend guide: **Detect → Select → Transform**. All three stages exist; the
final transform/export stage follows the plan in [server/transform.md](server/transform.md).
The frontend is in `client/`; its backend API connection remains separate work.

## Layout and setup

```text
server/
  detect/       column detection, text spans and linkage development tools
  select/       selection modules directly in this directory; no privacy_tool layer
  transform/    final stage: release gate, staged export, serialized validation and reports
  actions.py    shared pure protection operations (selection previews and final export run the same code)
  pipeline.py   one command: detect infer -> select -> search -> transform (python -m server.pipeline)
  transform.md  implementation and output-formatting plan for the final stage
```

Use the challenge package's `.venv` Python (the package root is the parent of this Git checkout).
Selection needs `pets_eval`, pandas and numpy; detection has extra dependencies in
`server/detect/requirements.txt`. Run selection commands from this repository root (`src/`):

```bash
../.venv/bin/python -m server.select --help
../.venv/bin/python -m pytest
```

The combined tests include fake localhost LLM servers and need permission to bind a local port.
Latest layout verification: **249 tests passed**, including the flattened CLI and standard-library import checks.
`server.select` is a package name; do not add `server/select` itself to `PYTHONPATH`, because its
`select.py` could shadow Python's standard-library `select` module.

See [combination.md](combination.md) for stage handoffs, expectations, known gaps and validation evidence.

## Detect: local, explainable detection of privacy-relevant data

The Detect step of the TRUSTED PETs pipeline. It finds what needs protecting so that the Select step can choose the right PET.

1. **Columns.** Each column gets a privacy role, a subtype, an Art. 9 flag, a confidence, a one-line reason and a `needs_review` flag.
2. **Free text.** PII spans inside text cells: `start`, `end`, `label`, `confidence`, and an `entity_id` that groups mentions of the same person, which lets Select use consistent pseudonyms.
3. **Linkage facts.** Join keys, identifiers shared across datasets, information hidden inside identifiers, and the share of rows with k<5 on the detected quasi-identifiers.

Everything runs on the local machine. The optional LLM tier is [AutoTrust-JEV-27B](https://huggingface.co/netprojects/AutoTrust-JEV-27B-v1.1-mlx-4bit) (4-bit MLX), served on `localhost`, so no data leaves the machine. JEV is a decision model: it does not write text, it gives a probability for each label we offer (role, subtype, Art. 9 yes/no), and that probability is the confidence.

### Results

All column scores are leave-one-dataset-out over the 9 labelled datasets: the model that labels dataset X never saw X. "Names hidden" means column and table names are removed, as in the obfuscated `unseen` export.

| | macro-F1, names hidden | macro-F1, with names | Free-text PII, F2 |
|---|---|---|---|
| B1 / B2 (organisers' baselines) | 0.401 | 0.646 | 0.184 |
| v1 | 0.757 | 0.858 | – |
| v2 | 0.766 | 0.857 | 0.998 |
| **v3 (main)** | **0.774** | 0.854 | 0.998 |

Recall on PERSON, PHONE, ADDRESS and NATIONAL_ID spans is 0.999. HEALTH-S1 requires at least 0.95.

### Packages

| Package | What it is |
|---|---|
| `pets_detect_v3/` | **Main column detector.** v1 rules, then a per-column router (kNN on names when any name context exists, logistic regression on values when there is none), then the local LLM. The LLM sees each unsure column's value distribution and the table domain. Confidence comes from the statistical model. |
| `pets_detect_v2/` | The v2 column detector. Also the **free-text span detector** (`spans/`), **linkage** (`linkage.py`) and the **HTML report** (`report.py`). |
| `pets_detect/` | v1: the profiler, regex and checksum patterns, and tier-1 rules that v2 and v3 build on. |
| `tests/` | Unit tests for all three packages. |
| `docs/` | Detailed notes: what was kept or dropped, ablations, limitations (Vietnamese). |

### Setup

```bash
cd server/detect
pip install -r requirements.txt
pip install -e ../../../toolkit          # organisers' pets-eval, needed for scoring
```

Optional LLM tier (Apple Silicon, ~18 GB memory; run from the folder that holds `TRUSTED_PETS_PROVING_GROUND_2026`'s `.venv`):

```bash
hf download netprojects/AutoTrust-JEV-27B-v1.1-mlx-4bit --local-dir models/AutoTrust-JEV-27B-v1.1-mlx-4bit
python3 -m venv .venv-jev     # separate venv: mlx, mlx-vlm and transformers stay out of the detector's
.venv-jev/bin/pip install "git+https://github.com/internet-projects/autotrust-jev27b-mlx@5ef540537b4fc38e6b1586f321d234b465040bc9"
.venv-jev/bin/python -m jev27b_mlx serve models/AutoTrust-JEV-27B-v1.1-mlx-4bit --port 8000
```

Use the local folder, not the repo id: the server then never contacts Hugging Face. The detector finds the server at `JEV_HOST` (default `http://127.0.0.1:8000`) and refuses it unless it reports bidirectional prompt attention. Do not load the model in LM Studio, Ollama or plain `mlx_lm`: they read the prompt causally and give different answers. If the server is not running, tier 3 is skipped and tiers 1-2 still run. `DETECT_LLM_BACKEND=ollama` switches back to the previous Ollama tier (`ollama pull qwen2.5:7b`).

The organisers' package (`TRUSTED_PETS_PROVING_GROUND_2026`) is found automatically in a parent folder. To point elsewhere, set `PETS_ROOT=/path/to/TRUSTED_PETS_PROVING_GROUND_2026`.

### Commands (run in `server/detect`)

```bash
## column labels (main detector)
python3 -m pets_detect_v3 detect --datasets health            # -> out/v3/field_labels.csv
python3 -m pets_detect_v3 detect --datasets health --no-llm   # without the LLM tier (seconds)
python3 -m pets_detect_v3 unseen                              # organisers' format -> out/v3/unseen_field_labels.csv

## free-text spans: train, score against B2, write the eval-split submission
python3 -m pets_detect_v2 spans --base v3                     # -> out/spans/, out/spans/pets_submission/

## linkage facts for Select
python3 -m pets_detect_v2 linkage                             # -> out/linkage/<dataset>.json

## comparisons and HTML reports
python3 -m pets_detect_v2 compare                             # v1 vs v2 -> out/reports/index.html
python3 -m pets_detect_v3 ablation                            # router choices, no LLM
python3 -m pets_detect_v3 compare                             # v3 vs saved v1/v2 -> out/reports_v3/index.html

python3 -m unittest discover -s tests
```

`pets_detect_v3 compare` reads the saved v1/v2 results in `out/compare/`, so run `pets_detect_v2 compare` once first. `spans --base v3` reads `out/compare_v3/pred_v3_names.csv` when it exists; otherwise it runs v3 without the LLM tier to get the labels.

### Output for the Select step

The column labels CSV (`out/v3/field_labels.csv`, or `out/compare_v3/pred_v3_names.csv`) has these columns:

```
dataset, table, column, privacy_role, subtype, confidence, source, reason, data_kind, art9,
needs_review, table_domain, art9_table, name_info, tier2_used, t1_role, t1_conf, p_top3
```

Span files are JSONL, one record per line, in the same format as `metadata/pii_spans/`:

```json
{"record_id": "T0000001", "spans": [{"start": 0, "end": 11, "label": "PERSON",
  "text": "...", "confidence": 0.97, "entity_id": "P1"}]}
```

### Limitations

- The tier-1 name rules were written after reading the catalog, so the "with names" scores are optimistic. Names-hidden scores and the organisers' private labels for `unseen` are the honest test.
- Ablation choices were made on the same 9 datasets that are scored. Gains below 0.01 may not carry over to new data.
- The free text is synthetic and template-based. Span scores on real text would be lower.
- v3 over-trusts the `_name` suffix: for example, bus-stop names are labelled `PERSON_NAME`. On `unseen`, v3 misses a trade-union code column that v2 flags.
- `out/`, `.cache/` and `pets_submission/` contain values from the data and are git-ignored. Do not publish them.

## Select: policy plan and measured search

Selection modules live directly under `server/select/` and import as `server.select.*`.
For example, `from server.select.requirements import from_spec`.

From this repository root, using an explained Detect label artifact:

```bash
python -m server.select select --data <package-root>/data/health --scenario HEALTH-S1 \
  --labels <detect-out>/labels.csv --out <fresh-plan-dir>   # needs <detect-out>/manifest.json
PRIVACY_TOOL_HMAC_KEY=... python -m server.select search --data <package-root>/data/health \
  --plan <fresh-plan-dir>/decisions.json --budget 50 --out <fresh-search-dir>
```

`--labels` consumes the saved artifact; it never trains or instantiates Detect v3. The label schema must
cover the input dataset and all its columns, with finite confidence in [0,1]. High-confidence
`needs_review` flags still trigger conservative treatment. Original confidence and Art. 9 flags are
retained; free-text detector reasons and samples are excluded from selection outputs.
Without `--labels`, `server.select.detect` remains a legacy lightweight fallback.

Use `--confirm` only with reviewed labels (`table,column,privacy_role,subtype`). Explicit protection
reductions require `--allow-downgrade` and appear as warnings. Uncertain required fields otherwise
produce a protective plan or actionable block. A new dataset can use `--spec` with a local requirement JSON.
The CSV/JSON examples under `server/select/examples` are local inputs and are not tracked.
No declared purpose is supported by `--no-purpose`.

`select` writes field labels plus `decisions.json` and `decisions.md`; `search` writes the chosen
plan and deterministic trace. Neither exports protected tables or row maps. Every output directory
must be fresh. The key is supplied by `PRIVACY_TOOL_HMAC_KEY`, never stored in decisions.

| Status | Meaning | CLI exit |
|---|---|---|
| `policy_valid` | Initial plan within the rule matrix; privacy targets unmeasured; **not** an approved release | 0 from select |
| `blocked` | Named input, policy, review, span or linkage conflicts (or a rejected artifact, nothing written) | 2 |
| `measured_ok` | Measured candidate meets risk and utility targets; the only status with `outcome.approved: true` | 0 from search |
| `target_unmet` | Search covered its allowed candidate space and no candidate meets the targets | 3 |
| `budget_exhausted` | Budget ran out with unexplored candidates; never a claim of infeasibility | 4 |

Every plan carries `outcome` = `{policy_valid, targets_met, approved, budget: {used, limit, exhausted, unexplored},
targets, achieved, violations: [{metric, table, target, achieved, requirements}]}`.

Named issue codes. Rejections (exit 2, no output): `manifest_missing`, `manifest_schema`, `dataset_mismatch`,
`table_set_mismatch`, `input_mismatch` (names the table; one changed cell is enough), `fingerprint_mismatch`,
`labels_mismatch`, `labels_schema` (bound labels need `needs_review`), `artifact_mismatch`, `artifact_missing`,
`provenance_missing` (search/transform). Plan errors/warnings: `unsupported_label`, `review_required`, `stale_span`,
`missing_span_evidence` (a needed free-text column absent from `artifacts.spans.columns`, or without spans when an
older manifest has no such map), `missing_linkage_evidence` (an error when a released column is a join/subject
key), `ambiguous_join`, `ambiguous_subject` (warning; selection keeps its own subject resolution) and
`provenance_unbound` (search on a built-in-detector plan: `outcome.approved` stays false). Only 16-hex ids from
artifacts are echoed; anything else is reported as `line N` / `relation N`.

`transform` exports only an approved `measured_ok` plan and first re-checks the plan's input digests. Any other
non-blocked status (`policy_valid`, `target_unmet`, `budget_exhausted`, unapproved `measured_ok`) needs
`--allow-unapproved`; the gate is recorded in `transform_stats.json` (`release_gate`) and as
`NOT_APPROVED.txt` in both output directories. `blocked` never exports.

`select --labels <detect out>/labels.csv` requires the contract-v1 `manifest.json` next to it (or `--manifest`):
raw-byte sha256 of every input CSV, the labels/spans/linkage digests and the label vocabulary. `decisions.json`
gets `provenance` (input digests, dataset fingerprint, detector name/version/model digest, artifact digests,
`confirm_sha256`) and `evidence` (span/linkage counts and relation ids only). `search` recomputes the input
digests, rejects a plan made for other bytes and records `plan_sha256`. Without `--labels` the legacy detector
plan is marked `provenance.bound: false`. `--confirm` rows are recorded as `reviews` (detected vs confirmed,
`downgrade`); a required column whose label is uncertain and unconfirmed blocks with `review_required`.

Search probes requirement floors at τ=0.8, then greedily coarsens one rung at a time, with deterministic
ties and local suppression allowance ≤2%. At most 50 search evaluations are counted, including the utility
reference; initial requirement-discovery probes are separate. Owner-data k/l/t and uniqueness use distinct
subject contributions. Unknown subjects remain unresolved. With a t target, each candidate checks t;
without one, t is measured on the chosen plan. A budget stop does not prove every possible plan fails.

### Selection module contracts


Selection through measured search is implemented. The built-in detector is a legacy fallback. All protection
operations, including hour-preserving rungs and local suppression, live in `server/actions.py`; the final
export is `server.transform`.

Tables are `dict[str, pandas.DataFrame]` read with `dtype=str, keep_default_na=False`. Column references are `"table.column"`.

| Module | Entry point | Returns |
|---|---|---|
| `detect` | `detect_table(df, table, dataset="")` | DataFrame `dataset,table,column,privacy_role,subtype,confidence,evidence` (taxonomy vocabulary); `review_queue(labels)` = rows with confidence < 0.6 |
| `relations` | `discover(tables, labels=None, declared=None)` | `{"keys": [{"column", "unique_ratio", "null_rate"}], "joins": [{"parent", "child", "coverage", "orphans", "confidence"[, "declared"]}], "subject_keys": {table: "t.c"}, "subject_paths": {table: ["t.c", ...]}, "subject_key": "t.c" or None, "conflicts": [str], "notices": [str]}`. `subject_keys[t]` is the person column, possibly in a joined table (`subject_paths[t]` = child, parent, ..., subject). A table whose own key is a person id (one row per person) uses that key. Subject keys need labels: without them `subject_keys` is empty and `notices` says so. `declared = {"joins": [[parent, child]], "subject_key": "t.c"}` overrides discovery; problems go to `conflicts` |
| `requirements` | `from_scenario(scenario_id, tables, root, probe=True, tolerance=0.05)`, `from_spec(path)`, `no_purpose(trust_level, dataset)` | `{"source", "scenario", "dataset", "trust_level", "targets", "targets_text", "tasks": [{"id", "table", "columns", "any_of", "precision", "evidence": {"declared", "parsed", "probed"}}], "required": {"t.c": [task ids]}, "any_of": [[["t.a"], ["t.b", "t.c"]]] (groups of alternatives, each a list of refs all needed), "precision": {"t.c": "hour"}, "joins": [{"columns", "tasks", "kind": "same_name" or "declared"}], "subject_key", "warnings"}`; select must confirm `same_name` joins with `relations.discover` before forcing a shared key domain |
| `policy` | `candidates(label, trust_level, required, in_join=False, precision=None, k=None)`, `targets(trust_level, scenario_targets=None)`, `violations(label, rung, trust_level, k=None)` | `{"rungs": [{"action", "method", "params", "level"}] finest first, "needs_review", "escalate", "notes"}`; targets `{"k", "l"?, "free_text"?, "max_suppression", "notes"}` (notes list any loosening by the scenario); violations = breaches, accepting only DROP or a rung `candidates` offers. `METHODS` = operations `transform` must implement |
| `select` | `select(tables, labels, relations, requirements, release_id=None)`, `confirm(labels, confirmed)`, `render(plan)` | Plan dict (`decisions.json`): `tables` (RELEASE/WITHHOLD + record_key), one `columns` entry per released source column (chosen rung + all `rungs`), `derived`, `domains`, `review_queue`, `warnings`, `errors`; `reviews`, `label_coverage`, `outcome`; status `policy_valid` or `blocked` |
| `transform` | `check_plan(tables, plan)`, `release_gate(plan, allow_unapproved=False)`, `apply(tables, plan, key, out_dir=None, eval_dir=None, allow_unapproved=False)` | Rule-matrix re-validation; the shared approval rule; `apply` is the legacy in-memory API over `server.actions.execute`. Use `python -m server.transform` for releases |
| `search` | `search(tables, plan, key, tasks=None, orig=None, budget=50, tau=0.8)` | Plan with chosen rungs, measured results and trace |


### Requirement resolver limits

Drop-one probing uses tolerance 0.05 so incidental dependencies do not bind the purpose. Two interchangeable
columns can each look unnecessary when tested alone; parsed alternatives are needed to catch that case.
Scenario resolution is followed by precision probes during search. Selection does not read the training
catalog, truth or gold spans.

## Transform: validated release export

`server.transform` executes a **measured** plan and publishes a release only after the written files pass
validation. Design and contracts: [server/transform.md](server/transform.md).

```bash
PRIVACY_TOOL_HMAC_KEY=... python -m server.transform --data <package-root>/data/health \
  --plan <fresh-search-dir>/decisions.json --out <fresh-run-dir> \
  [--detect <detect-out-dir>] [--text-fallback rules] [--allow-unapproved] [--no-scorecard]
```

`python -m server.select transform` takes the same options and calls the same executor. The whole chain runs
with one command (each stage through its own CLI, into `detect/`, `select/`, `search/`, `transform/`):

```bash
PRIVACY_TOOL_HMAC_KEY=... python -m server.pipeline --data <package-root>/data/customer_service \
  --scenario CS-S1 --model <detect model dir> --release-id CS-S1/vendor-a --out <fresh dir>
```

Free text uses the Detect spans: at internal/contractual trust the `entity_pseudonyms` profile writes
`[PERSON_1]`, `[PHONE_2]`, ... numbered per conversation (a person keeps one number across turns; numbers
restart in the next conversation, so they do not link records); otherwise `[PERSON]`. Run `search` with the same
`--detect` dir (the pipeline does): previews then redact exactly as the export, and Transform refuses a plan
measured with different text redaction.

| Exit | Status | Result |
|---|---|---|
| 0 | `validated` | `protected/` (recipient), `evaluation/` (owner-private copies, row maps, input manifest), `reports/`, `manifest.json` with `approved_release: true` |
| 0 | `unapproved_export` | Only with `--allow-unapproved` for a non-blocked plan: same layout and checks (k/l/t and utility are recorded, not gating), `NOT_APPROVED.txt` in `protected/` and `evaluation/`, `approved_release: false` |
| 2 | `refused` | Preflight failed; only `diagnostics.json`/`.md` are written, no data. Input-binding rejections (`[input_mismatch]`, `[stale_span]`, ...) print the code and write nothing |
| 3 | `validation_failed` | Files stay private under `staging/`; `diagnostics.*` and a `failed` manifest name the failed checks |

Before writing anything, Transform checks the plan's `provenance` against the input bytes (the same contract-v1
binding as `search`), and, with `--detect`, the Detect manifest, the `spans.jsonl` sha256 and every
`span_id`/offset. Preflight then refuses a plan that is not an approved `measured_ok` (`outcome.approved`
needs provenance bound to a Detect manifest), has unresolved review items on released or required fields,
or lacks an explicit `--release-id`. Free-text columns need Detect spans for that column; without them the
rule-only redactor must be chosen explicitly with `--text-fallback rules`. After writing, Transform reloads
every file and checks:
- round trip and row maps
- action output formats
- join/orphan status
- suppression against the measured candidate
- k/l/t, uniqueness and utility re-measured on the written tables
- `pets-eval check` on all lines of `protected/`

Each scanner hit is attributed to a cell. The only accepted false positive is a pattern match inside a
validated HMAC token. The toolkit scorecard runs on the evaluation copy and is report-only.

Full-data HEALTH-S1 is still `target_unmet` (12.98% below k=5, l failures, 921 visits and 2,205 linked lab
rows with missing subject IDs). Transform therefore refuses it with diagnostics; it lowers no targets and
drops no rows. A full-data release needs the owner to resolve those conflicts and reselect.

Never commit raw data, protected/evaluation outputs, row maps or keys. Detector outputs/caches and selection
outputs may contain sensitive material; use fresh ignored directories and keep them private.
