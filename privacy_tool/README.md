# privacy_tool

Dynamic PET selection for tabular releases. Plan: `detailed-select-plan.md` in the challenge package root.
Requires the challenge toolkit (`pets_eval`) installed in the active virtualenv.

## Module contracts

Tables are `dict[str, pandas.DataFrame]` read with `dtype=str, keep_default_na=False`. Column references are `"table.column"`.

| Module | Entry point | Returns |
|---|---|---|
| `detect` | `detect_table(df, table, dataset="")` | DataFrame `dataset,table,column,privacy_role,subtype,confidence,evidence` (taxonomy vocabulary); `review_queue(labels)` = rows with confidence < 0.6 |
| `relations` | `discover(tables, labels)` | `{"keys": [...], "joins": [{"parent", "child", "coverage", "orphans", "confidence"}], "subject_key": "t.c" or None}` |
| `requirements` | `from_scenario(scenario_id, tables, root)`, `from_spec(path)`, `no_purpose()` | `{"source", "scenario", "trust_level", "targets", "tasks": [{"id", "columns", "evidence"}], "required": {"t.c": [task ids]}, "joins": [...], "subject_key"}` |
| `policy` | `candidates(label, trust_level, required, in_join)`, `targets(trust_level)` | Ordered rungs (finest first) `{"action", "method", "params"}`; hard-constraint checks |
| `select` | `select(tables, labels, relations, requirements)` | Plan dict (`decisions.json`), status `ready_for_transform` or `blocked` |
| `transform` | `apply(tables, plan, key, out_dir)` | Protected tables + private row maps in a fresh directory |
| `search` | `search(tables, plan, requirements, key)` | Plan with chosen rungs, measured results and trace |

## Detect

```bash
python -m privacy_tool.detect --data <dataset-or-root-dir> --out labels.csv
pets-eval detect --pred labels.csv   # scoring only; the detector never reads field_catalog.csv or truth/
```

Development score on the 9 shipped datasets (475 fields): macro-F1 0.789, direct-identifier recall 0.934
(B1 rule baseline: 0.646 / 0.895).
