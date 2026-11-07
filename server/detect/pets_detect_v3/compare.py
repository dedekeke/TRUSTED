"""Run ONLY v3 and compare it with the saved v1/v2 results of the earlier comparison (out/compare/).

v1 and v2 are not re-run: their saved predictions are re-scored with the same scorer and catalog, so all three
versions are directly comparable, and the v1/v2 baseline stays fixed even if their code changes later.
"""
from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

from pets_detect.pipeline import root_paths

from .pipeline import Config, DetectorV3

SAVED = Path("out/compare")
OUT = Path("out/compare_v3")
REPORTS = Path("out/reports_v3")

# final configuration, set from the ablation (see notes); LLM steps B1-B4 switched on
# ablation (out/compare_v3/ablation*.csv): B1 and B2 kept; B3 and B4 dropped because they lowered macro-F1 with names
FINAL = Config(router="A1", margin_names=.10, margin_values=.10, margin_art9=0.0, b2_honest_conf=True,
               b3_art9_llm=False)
STEP4 = Config(router="A1", margin_names=.10, margin_values=.10)          # + B1 only (new prompt)


def _score(pred, catalog, datasets):
    from pets_eval.detect import score_detection
    return score_detection(pred, catalog, datasets)


def load_saved() -> dict:
    need = [SAVED / f"pred_{v}_{m}.csv" for v in ("v1", "v2") for m in ("names", "blind")] + [SAVED / "summary.json"]
    missing = [str(p) for p in need if not p.exists()]
    if missing:
        raise SystemExit("saved v1/v2 results missing: " + ", ".join(missing) +
                         "\nrun `python3 -m pets_detect_v2 compare` once first (v3 does not re-run v1/v2)")
    summary = json.loads((SAVED / "summary.json").read_text())
    return summary


def run(root=None, llm: bool = True, cfg: Config = FINAL, tag: str = "v3") -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    saved = load_saved()
    _, data_dir, cat_path = root_paths(root)
    catalog = pd.read_csv(cat_path, dtype=str)
    datasets, labelled = saved["datasets"], saved["labelled"]
    res = {"baseline_created": saved["created"], "created": time.strftime("%Y-%m-%d %H:%M"),
           "datasets": datasets, "labelled": labelled, "config": cfg.__dict__ | {"tiers": list(cfg.tiers)},
           "runs": {k: v for k, v in saved["runs"].items()}, "b1": saved.get("b1")}
    for view in ("names", "blind"):
        c = replace(cfg, view=view, tiers=(1, 2, 3) if llm else (1, 2))
        det = DetectorV3(c, root)
        preds, times = [], {}
        for ds in datasets:
            t0 = time.time()
            preds.append(det.detect(ds))
            times[ds] = round(time.time() - t0, 1)
            print(f"  {tag} {view:5s} {ds:18s} {times[ds]:6.1f}s", flush=True)
        pred = pd.concat(preds, ignore_index=True)
        pred.to_csv(OUT / f"pred_{tag}_{view}.csv", index=False)
        info = {"times": times, "llm": bool(det.llm is not None and det.llm.available()),
                "llm_model": det.llm.model if det.llm else None, "llm_calls": det.llm.calls if det.llm else 0,
                "overall": _score(pred, catalog, labelled),
                "per_dataset": {d: _score(pred, catalog, [d]) for d in labelled}}
        res["runs"][f"{tag}_{view}"] = info
        o = info["overall"]
        print(f"[{tag} {view}] macro-F1 {o['macro_f1']:.3f}  sensitive recall {o['sensitive_recall']:.3f}  "
              f"LLM calls {info['llm_calls']}", flush=True)
    # mixed view: router check only (no LLM), against the two single-source routers
    res["mixed"] = {}
    for name, router in (("always kNN (names)", "knn"), ("always LogReg (values)", "logreg"),
                         (f"v3 router ({cfg.router})", cfg.router)):
        pred = pd.concat([DetectorV3(replace(cfg, view="mixed", tiers=(1, 2), router=router), root).detect(d)
                          for d in labelled], ignore_index=True)
        res["mixed"][name] = _score(pred, catalog, labelled)
        print(f"[mixed] {name:24s} macro-F1 {res['mixed'][name]['macro_f1']:.3f}", flush=True)
    (OUT / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def build_reports(root=None):
    from .report_v3 import build
    files = build(root)
    print(f"wrote {len(files)} HTML files -> {REPORTS / 'index.html'}")
