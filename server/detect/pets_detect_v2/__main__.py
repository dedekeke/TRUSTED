"""CLI for detect v2 (run from server/detect).

  python3 -m pets_detect_v2 detect --datasets health [--blind] [--no-llm]
  python3 -m pets_detect_v2 unseen                      # organisers' format -> out/v2/unseen_field_labels.csv
  python3 -m pets_detect_v2 ablation                    # tier-2 model / recall-margin choice, no LLM
  python3 -m pets_detect_v2 compare [--datasets a,b] [--no-llm]   # v1 vs v2 -> out/reports/*.html
  python3 -m pets_detect_v2 report                      # rebuild HTML from saved results
  python3 -m pets_detect_v2 spans [--base v1|v2]        # step 7: PII spans in free text
  python3 -m pets_detect_v2 linkage [--base v1|v2]      # step 7: join keys, embedded QIs, k of QI sets
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from pets_detect.pipeline import root_paths

from .pipeline import Config, DetectorV2


def ablation(root, out: Path) -> pd.DataFrame:
    from pets_eval.detect import score_detection
    rows = []
    for blind in (False, True):
        for model, margin in (("knn", 0.0), ("logreg", 0.0), ("logreg", 0.1), ("logreg", 0.2), ("gbm", 0.1)):
            t0 = time.time()
            d = DetectorV2(Config(tiers=(1, 2), model=model, blind_names=blind, recall_margin=margin), root)
            pred = pd.concat([d.detect(ds) for ds in d.labelled])
            r = score_detection(pred, d.catalog)
            rows.append({"names": "hidden" if blind else "shown", "tier-2 model": model, "recall margin": margin,
                         "macro-F1": r["macro_f1"], "accuracy": r["accuracy"],
                         "sensitive recall": r["sensitive_recall"],
                         "F1 sensitive attr.": r["per_role"]["sensitive_attribute"]["f1"],
                         "subtype acc.": r["subtype_accuracy"], "seconds": round(time.time() - t0, 1)})
            print(rows[-1], flush=True)
    df = pd.DataFrame(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return df


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pets_detect_v2")
    ap.add_argument("--root", help="path to TRUSTED_PETS_PROVING_GROUND_2026")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("detect")
    s.add_argument("--datasets", required=True)
    s.add_argument("--blind", action="store_true")
    s.add_argument("--no-llm", action="store_true")
    s.add_argument("--context", default="")
    s.add_argument("--out", default="out/v2/field_labels.csv")
    s = sub.add_parser("unseen")
    s.add_argument("--no-llm", action="store_true")
    s.add_argument("--out", default="out/v2/unseen_field_labels.csv")
    sub.add_parser("ablation")
    s = sub.add_parser("compare")
    s.add_argument("--datasets", default="")
    s.add_argument("--no-llm", action="store_true")
    sub.add_parser("report")
    s = sub.add_parser("spans")
    s.add_argument("--base", default="", help="column detector whose free_text labels decide what to scan")
    s.add_argument("--max-train", type=int, default=6000, help="training records per text column")
    s = sub.add_parser("linkage")
    s.add_argument("--base", default="")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else None
    r, data_dir, cat_path = root_paths(root)

    if a.cmd in ("detect", "unseen"):
        tiers = (1, 2) if a.no_llm else (1, 2, 3)
        blind = getattr(a, "blind", False) or a.cmd == "unseen"
        det = DetectorV2(Config(tiers=tiers, blind_names=blind, context=getattr(a, "context", "")), root)
        dss = ["unseen"] if a.cmd == "unseen" else [x.strip() for x in a.datasets.split(",")]
        out = pd.concat([det.detect(ds) for ds in dss], ignore_index=True)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        if a.cmd == "unseen":
            out[["dataset", "table", "column", "privacy_role", "subtype"]].to_csv(a.out, index=False)
            out.to_csv(Path(a.out).with_name("unseen_explained.csv"), index=False)
        else:
            out.to_csv(a.out, index=False)
        with pd.option_context("display.width", 200, "display.max_colwidth", 60):
            print(out[["table", "column", "privacy_role", "subtype", "confidence", "source"]].to_string(index=False))
        print(f"\nwrote {len(out)} labels -> {a.out}")
    elif a.cmd == "ablation":
        ablation(root, Path("out/compare/ablation.csv"))
    elif a.cmd in ("compare", "report"):
        from . import compare, report
        if a.cmd == "compare":
            dss = [x.strip() for x in a.datasets.split(",") if x.strip()] or None
            compare.run(dss, llm=not a.no_llm, root=root)
        files = report.build(Path("out/reports"), pd.read_csv(cat_path, dtype=str))
        print(f"wrote {len(files)} HTML files -> out/reports/index.html")
    elif a.cmd == "spans":
        from .spans import run as spans_run
        spans_run.main(root, base=a.base, max_train=a.max_train)
        from . import report
        if Path("out/compare/summary.json").exists():
            report.build(Path("out/reports"), pd.read_csv(cat_path, dtype=str))
    elif a.cmd == "linkage":
        from . import linkage
        linkage.main(root, base=a.base)


if __name__ == "__main__":
    main()
