"""Run v1 and v2 on every dataset, in both modes, score them and write the reports.

Same profiles, same LLM model (qwen2.5:7b, temperature 0), same leave-one-dataset-out protocol for both.
Results are saved as CSV/JSON in out/compare/ so the HTML can be rebuilt without re-running (`report` command).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from pets_detect.pipeline import Config as ConfigV1, Detector as DetectorV1, root_paths

from .pipeline import Config as ConfigV2, DetectorV2

try:
    from pets_eval.detect import score_detection
except ImportError:  # pragma: no cover
    score_detection = None

MODES = {"names": False, "blind": True}


def _run_one(version: str, blind: bool, datasets: list[str], llm: bool, root) -> tuple[pd.DataFrame, dict, dict]:
    if version == "v1":
        det = DetectorV1(ConfigV1(tiers=(1, 2, 3) if llm else (1, 2), blind_names=blind), root)
        llm_obj = det.llm
    else:
        det = DetectorV2(ConfigV2(tiers=(1, 2, 3) if llm else (1, 2), blind_names=blind), root)
        llm_obj = det.llm
    preds, times = [], {}
    for ds in datasets:
        t0 = time.time()
        preds.append(det.detect(ds))
        times[ds] = round(time.time() - t0, 1)
        print(f"  {version} {'blind' if blind else 'names'} {ds:18s} {times[ds]:6.1f}s", flush=True)
    meta = {"llm": bool(llm_obj is not None and llm_obj.available()),
            "llm_model": getattr(llm_obj, "model", None) if llm_obj is not None else None,
            "llm_calls": getattr(llm_obj, "calls", None)}
    return pd.concat(preds, ignore_index=True), times, meta


def run(datasets: list[str] | None = None, llm: bool = True, root: Path | None = None,
        out_dir: Path = Path("out/compare")) -> dict:
    if score_detection is None:
        raise SystemExit("pets-eval is not installed: pip install -e <package>/toolkit")
    out_dir.mkdir(parents=True, exist_ok=True)
    r, data_dir, cat_path = root_paths(root)
    catalog = pd.read_csv(cat_path, dtype=str)
    labelled = sorted(d for d in catalog.dataset.unique() if (data_dir / d).is_dir())
    all_ds = sorted(p.name for p in data_dir.iterdir() if p.is_dir() and any(p.glob("*.csv")))
    datasets = datasets or all_ds
    summary = {"datasets": datasets, "labelled": [d for d in datasets if d in labelled], "runs": {},
               "created": time.strftime("%Y-%m-%d %H:%M")}
    for version in ("v1", "v2"):
        for mode, blind in MODES.items():
            print(f"[compare] {version} / {mode}", flush=True)
            pred, times, meta = _run_one(version, blind, datasets, llm, root)
            pred.to_csv(out_dir / f"pred_{version}_{mode}.csv", index=False)
            scored = [d for d in datasets if d in labelled]
            run_info = {"times": times, **meta, "per_dataset": {}}
            if scored:
                run_info["overall"] = score_detection(pred, catalog, scored)
                for d in scored:
                    run_info["per_dataset"][d] = score_detection(pred, catalog, [d])
            summary["runs"][f"{version}_{mode}"] = run_info
    b1 = r / "results" / "b1_field_labels.csv"
    if b1.exists():
        summary["b1"] = score_detection(pd.read_csv(b1, dtype=str), catalog, summary["labelled"])
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary
