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
