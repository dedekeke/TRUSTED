# Detect

The central setup, commands, results and limitations are in [the repository README](../../README.md#detect-local-explainable-detection-of-privacy-relevant-data).
Detailed experiments remain in `docs/`.

## Deployment (train once, infer catalog-free)

From `server/detect` (see `pets_detect_v3/deploy.py`):

```bash
python -m pets_detect_v3 train --root <PKG> --out <new model dir>        # training: reads the catalog and span labels
python -m pets_detect_v3 infer --model <model dir> --data <PKG>/data/health --out <new dir> --no-llm
python -m pets_detect_v3 benchmark --root <PKG> --labels <dir>/labels.csv  # evaluation only (reads the catalog)
```

`infer` reads only the model dir and `--data`, and writes `labels.csv`, `spans.jsonl`, `linkage.json` and
`manifest.json` (contract `pets.detect.manifest/1`). A dataset that was part of training is scored
leave-one-dataset-out, exactly like the in-process detector. `model.pkl` is a pickle: load only models you trained.

**Spans:** span entities are numbered per conversation/record. A text column whose table has exactly one
foreign-key column (e.g. `turns.conversation_id`) is grouped by it, so one person keeps one `entity_id` across
turns; with no or several FK columns each cell is its own group. Group ids are opaque hashes, and the manifest
records the grouping in `artifacts.spans.groups`. Transform turns these ids into `[PERSON_1]`-style pseudonyms.

**Linkage:** `linkage.json` relations are `join`, `subject` and `embedded` (an identifier that encodes other
attributes, e.g. a HETU encodes birth date and sex). Evidence values are numbers only; `embedded` carries fixed
descriptions in `encodes`. Select warns `embedded_qi` when such a column is released in a form that keeps them.
