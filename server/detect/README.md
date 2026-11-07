# Detect: local, explainable detection of privacy-relevant data

The Detect step of the TRUSTED PETs pipeline. It finds what needs protecting so that the Select step can choose the right PET.

1. **Columns.** Each column gets a privacy role, a subtype, an Art. 9 flag, a confidence, a one-line reason and a `needs_review` flag.
2. **Free text.** PII spans inside text cells: `start`, `end`, `label`, `confidence`, and an `entity_id` that groups mentions of the same person, which lets Select use consistent pseudonyms.
3. **Linkage facts.** Join keys, identifiers shared across datasets, information hidden inside identifiers, and the share of rows with k<5 on the detected quasi-identifiers.

Everything runs on the local machine. The optional LLM runs in Ollama on `localhost`, so no data leaves the machine.

## Results

All column scores are leave-one-dataset-out over the 9 labelled datasets: the model that labels dataset X never saw X. "Names hidden" means column and table names are removed, as in the obfuscated `unseen` export.

| | macro-F1, names hidden | macro-F1, with names | Free-text PII, F2 |
|---|---|---|---|
| B1 / B2 (organisers' baselines) | 0.401 | 0.646 | 0.184 |
| v1 | 0.757 | 0.858 | – |
| v2 | 0.766 | 0.857 | 0.998 |
| **v3 (main)** | **0.774** | 0.854 | 0.998 |

Recall on PERSON, PHONE, ADDRESS and NATIONAL_ID spans is 0.999. HEALTH-S1 requires at least 0.95.

## Packages

| Package | What it is |
|---|---|
| `pets_detect_v3/` | **Main column detector.** v1 rules, then a per-column router (kNN on names when any name context exists, logistic regression on values when there is none), then the local LLM. The LLM sees each unsure column's value distribution and the table domain. Confidence comes from the statistical model. |
| `pets_detect_v2/` | The v2 column detector. Also the **free-text span detector** (`spans/`), **linkage** (`linkage.py`) and the **HTML report** (`report.py`). |
| `pets_detect/` | v1: the profiler, regex and checksum patterns, and tier-1 rules that v2 and v3 build on. |
| `tests/` | Unit tests for all three packages. |
| `docs/` | Detailed notes: what was kept or dropped, ablations, limitations (Vietnamese). |

## Setup

```bash
cd server/detect
pip install -r requirements.txt
pip install -e ../../../toolkit          # organisers' pets-eval, needed for scoring
# optional LLM tier:
brew install ollama && ollama serve &   # or any Ollama install
ollama pull qwen2.5:7b
```

The organisers' package (`TRUSTED_PETS_PROVING_GROUND_2026`) is found automatically in a parent folder. To point elsewhere, set `PETS_ROOT=/path/to/TRUSTED_PETS_PROVING_GROUND_2026`.

## Commands (run in `server/detect`)

```bash
# column labels (main detector)
python3 -m pets_detect_v3 detect --datasets health            # -> out/v3/field_labels.csv
python3 -m pets_detect_v3 detect --datasets health --no-llm   # without the LLM tier (seconds)
python3 -m pets_detect_v3 unseen                              # organisers' format -> out/v3/unseen_field_labels.csv

# free-text spans: train, score against B2, write the eval-split submission
python3 -m pets_detect_v2 spans --base v3                     # -> out/spans/, out/spans/pets_submission/

# linkage facts for Select
python3 -m pets_detect_v2 linkage                             # -> out/linkage/<dataset>.json

# comparisons and HTML reports
python3 -m pets_detect_v2 compare                             # v1 vs v2 -> out/reports/index.html
python3 -m pets_detect_v3 ablation                            # router choices, no LLM
python3 -m pets_detect_v3 compare                             # v3 vs saved v1/v2 -> out/reports_v3/index.html

python3 -m unittest discover -s tests
```

`pets_detect_v3 compare` reads the saved v1/v2 results in `out/compare/`, so run `pets_detect_v2 compare` once first. `spans --base v3` reads `out/compare_v3/pred_v3_names.csv` when it exists; otherwise it runs v3 without the LLM tier to get the labels.

## Output for the Select step

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

## Limitations

- The tier-1 name rules were written after reading the catalog, so the "with names" scores are optimistic. Names-hidden scores and the organisers' private labels for `unseen` are the honest test.
- Ablation choices were made on the same 9 datasets that are scored. Gains below 0.01 may not carry over to new data.
- The free text is synthetic and template-based. Span scores on real text would be lower.
- v3 over-trusts the `_name` suffix: for example, bus-stop names are labelled `PERSON_NAME`. On `unseen`, v3 misses a trade-union code column that v2 flags.
- `out/`, `.cache/` and `pets_submission/` contain values from the data and are git-ignored. Do not publish them.
