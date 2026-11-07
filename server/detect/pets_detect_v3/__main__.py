"""CLI for detect v3 (run from server/detect).

  python3 -m pets_detect_v3 detect --datasets health [--view names|blind|mixed] [--no-llm]
  python3 -m pets_detect_v3 unseen                 # organisers' format -> out/v3/unseen_field_labels.csv
  python3 -m pets_detect_v3 ablation               # router / margin steps, no LLM, 3 views -> out/compare_v3/ablation.csv
  python3 -m pets_detect_v3 compare                # runs ONLY v3; v1/v2 come from out/compare/ -> out/reports_v3/
  python3 -m pets_detect_v3 report                 # rebuild out/reports_v3/ from saved results
"""
from __future__ import annotations

import argparse
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

from pets_detect.pipeline import root_paths

from .pipeline import Config, DetectorV3

OUT = Path("out/compare_v3")


def score(pred, catalog, datasets=None):
    from pets_eval.detect import score_detection
    return score_detection(pred, catalog, datasets)


def run_variant(cfg: Config, root, datasets=None):
    d = DetectorV3(cfg, root)
    dss = datasets or d.labelled
    d.prefit(dss)
    return pd.concat([d.detect(x) for x in dss], ignore_index=True), d


def ablation(root) -> pd.DataFrame:
    """Steps 0-3 of the plan, without the LLM. Step 0 rows are the v2 numbers (v2 code, tiers 1-2)."""
    from pets_detect_v2.pipeline import Config as C2, DetectorV2
    _, _, cat_path = root_paths(root)
    catalog = pd.read_csv(cat_path, dtype=str)
    rows = []

    def add(step, name, view, pred, t0):
        r = score(pred, catalog)
        rows.append({"step": step, "variant": name, "view": view, "macro-F1": r["macro_f1"],
                     "accuracy": r["accuracy"], "sensitive recall": r["sensitive_recall"],
                     "F1 sensitive attr.": r["per_role"]["sensitive_attribute"]["f1"],
                     "subtype acc.": r["subtype_accuracy"], "seconds": round(time.time() - t0, 1)})
        print(rows[-1], flush=True)

    for view in ("names", "blind"):
        t0 = time.time()
        d2 = DetectorV2(C2(tiers=(1, 2), blind_names=view == "blind"), root)
        add(0, "v2 (LogReg, margin 0.10)", view, pd.concat([d2.detect(x) for x in d2.labelled]), t0)
    base = Config(tiers=(1, 2), margin_names=.10, margin_values=.10)
    for view in ("names", "blind", "mixed"):
        for router in ("knn", "logreg", "A1", "A2"):
            t0 = time.time()
            pred, _ = run_variant(replace(base, view=view, router=router), root)
            add(1, f"router {router}, margin 0.10", view, pred, t0)
        for router in ("A1", "A2"):
            t0 = time.time()
            pred, _ = run_variant(replace(base, view=view, router=router, margin_names=.03), root)
            add(2, f"router {router}, margin by name_info (0.03-0.10)", view, pred, t0)
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "ablation.csv", index=False)
    return df


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pets_detect_v3")
    ap.add_argument("--root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("detect")
    s.add_argument("--datasets", required=True)
    s.add_argument("--view", default="names")
    s.add_argument("--no-llm", action="store_true")
    s.add_argument("--out", default="out/v3/field_labels.csv")
    s = sub.add_parser("unseen")
    s.add_argument("--no-llm", action="store_true")
    sub.add_parser("ablation")
    s = sub.add_parser("compare")
    s.add_argument("--no-llm", action="store_true")
    sub.add_parser("report")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else None
    from . import compare
    if a.cmd in ("detect", "unseen"):
        cfg = replace(compare.FINAL, tiers=(1, 2) if a.no_llm else (1, 2, 3),
                      view="blind" if a.cmd == "unseen" else a.view)
        dss = ["unseen"] if a.cmd == "unseen" else [x.strip() for x in a.datasets.split(",")]
        out, _ = run_variant(cfg, root, dss)
        path = Path("out/v3/unseen_field_labels.csv" if a.cmd == "unseen" else a.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        if a.cmd == "unseen":
            out[["dataset", "table", "column", "privacy_role", "subtype"]].to_csv(path, index=False)
            out.to_csv(path.with_name("unseen_explained.csv"), index=False)
        else:
            out.to_csv(path, index=False)
        with pd.option_context("display.width", 220, "display.max_colwidth", 50):
            print(out[["table", "column", "privacy_role", "subtype", "confidence", "tier2_used",
                       "needs_review"]].to_string(index=False))
        print(f"\nwrote {len(out)} labels -> {path}")
    elif a.cmd == "ablation":
        ablation(root)
    elif a.cmd == "compare":
        compare.run(root, llm=not a.no_llm)
        compare.build_reports(root)
    elif a.cmd == "report":
        compare.build_reports(root)


if __name__ == "__main__":
    main()
