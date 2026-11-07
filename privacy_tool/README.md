# privacy_tool

Dynamic PET selection for tabular releases. Plan: `detailed-select-plan.md` in the challenge package root.
Requires the challenge toolkit (`pets_eval`) installed in the active virtualenv.

## Module contracts

Only `detect` exists on this branch; the other rows are the planned contracts (separate PRs).

Tables are `dict[str, pandas.DataFrame]` read with `dtype=str, keep_default_na=False`. Column references are `"table.column"`.

| Module | Entry point | Returns |
|---|---|---|
| `detect` | `detect_table(df, table, dataset="")` | DataFrame `dataset,table,column,privacy_role,subtype,confidence,evidence` (taxonomy vocabulary); `review_queue(labels)` = rows with confidence < 0.6 |
| `relations` | `discover(tables, labels)` | `{"keys": [...], "joins": [{"parent", "child", "coverage", "orphans", "confidence"}], "subject_key": "t.c" or None}` |
| `requirements` | `from_scenario(scenario_id, tables, root, probe=True, tolerance=0.05)`, `from_spec(path)`, `no_purpose(trust_level, dataset)` | `{"source", "scenario", "dataset", "trust_level", "targets", "targets_text", "tasks": [{"id", "table", "columns", "any_of", "precision", "evidence": {"declared", "parsed", "probed"}}], "required": {"t.c": [task ids]}, "any_of": [[["t.a"], ["t.b", "t.c"]]] (groups of alternatives, each a list of refs all needed), "precision": {"t.c": "hour"}, "joins": [{"columns", "tasks", "kind": "same_name" or "declared"}], "subject_key", "warnings"}`; select must confirm `same_name` joins with `relations.discover` before forcing a shared key domain |
| `policy` | `candidates(label, trust_level, required, in_join=False, precision=None, k=None)`, `targets(trust_level, scenario_targets=None)`, `violations(label, rung, trust_level, k=None)` | `{"rungs": [{"action", "method", "params", "level"}] finest first, "needs_review", "escalate", "notes"}`; targets `{"k", "l"?, "free_text"?, "max_suppression", "notes"}` (notes list any loosening by the scenario); violations = breaches, accepting only DROP or a rung `candidates` offers. `METHODS` = operations `transform` must implement |
| `select` | `select(tables, labels, relations, requirements)` | Plan dict (`decisions.json`), status `ready_for_transform` or `blocked` |
| `transform` | `apply(tables, plan, key, out_dir)` | Protected tables + private row maps in a fresh directory |
| `search` | `search(tables, plan, requirements, key)` | Plan with chosen rungs, measured results and trace |

## Detect

```bash
python -m privacy_tool.detect --data <dataset-or-root-dir> --out labels.csv
pets-eval detect --pred labels.csv   # scoring only; the detector never reads field_catalog.csv or truth/
```

Development score on the 9 shipped datasets (475 fields): macro-F1 0.809, direct-identifier precision/recall 0.922 / 0.934
(B1 rule baseline: 0.646 / 0.895).

## Requirements

```python
from privacy_tool.requirements import from_scenario, from_spec, no_purpose
req = from_scenario("HEALTH-S1", load_tables(root / "data/health"), root)  # parse task needs + probe by dropping columns
req = from_spec("privacy_tool/examples/health_s1_spec.json")               # new dataset without toolkit tasks
```

A column is required when dropping it makes a task not answerable or lowers its score by more than `tolerance`
(0.05). Plan section 5 says "if its score drops"; the tolerance keeps incidental dependencies out (dropping the
duplicate filter `disposition` moves H-U2 to 0.998). Blind spot of drop-one probing: two columns that can stand in
for each other but are not written as `a|b` each look unnecessary; only parsing catches them.

Probing HEALTH-S1 (5 tasks, every column of the tables each task touches, all rows, no sampling) took 33 s on an idle machine and 374 s under heavy load (load average 9.5).
