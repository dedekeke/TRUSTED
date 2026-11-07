"""CLI.

  python -m pets_detect detect --datasets health,unseen --out out/field_labels.csv
  python -m pets_detect unseen --out out/unseen_submission.csv
  python -m pets_detect evaluate [--no-llm]
  python -m pets_detect explain health ed_visits patient_hetu
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import evaluate
from .pipeline import Config, Detector, load_profiles


def _cfg(a) -> Config:
    tiers = tuple(int(t) for t in a.tiers.split(","))
    return Config(tiers=tiers, embedder=a.embed, llm_model=a.llm_model, blind_names=a.blind,
                  exclude_self=not a.include_self, context=a.context)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pets_detect", description="Local, explainable field detector (rules + RAG)")
    ap.add_argument("--root", help="path to TRUSTED_PETS_PROVING_GROUND_2026 (default: env PETS_ROOT or sibling)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(s):
        s.add_argument("--tiers", default="1,2,3", help="which tiers to run, e.g. 1 / 1,2 / 1,2,3")
        s.add_argument("--embed", default="tfidf", help="tfidf | ollama:<model> (e.g. ollama:bge-m3)")
        s.add_argument("--llm-model", default=None, help="Ollama model for tier 3 (default qwen2.5:7b)")
        s.add_argument("--blind", action="store_true", help="ignore column names")
        s.add_argument("--context", default="", help="one sentence describing the dataset (helps tier 3)")
        s.add_argument("--include-self", action="store_true",
                       help="allow retrieval from the dataset being detected (do NOT use when scoring)")

    s = sub.add_parser("detect", help="label the columns of one or more datasets")
    s.add_argument("--datasets", required=True, help="comma-separated dataset folder names")
    s.add_argument("--out", default="out/field_labels.csv")
    common(s)

    s = sub.add_parser("unseen", help="label the obfuscated 'unseen' export in the organisers' format")
    s.add_argument("--out", default="out/unseen_submission.csv")
    common(s)

    s = sub.add_parser("evaluate", help="leave-one-dataset-out ablation vs B1")
    s.add_argument("--out", default="out/eval")
    s.add_argument("--no-llm", action="store_true")
    s.add_argument("--embed", default="tfidf")
    s.add_argument("--llm-model", default=None)

    s = sub.add_parser("explain", help="show the full reasoning for one column")
    s.add_argument("dataset")
    s.add_argument("table")
    s.add_argument("column")
    common(s)

    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else None

    if a.cmd == "evaluate":
        df = evaluate.run(root, Path(a.out), llm=not a.no_llm, embedder=a.embed, llm_model=a.llm_model)
        print((Path(a.out) / "ablation.md").read_text())
        return

    det = Detector(_cfg(a), root)
    if a.cmd == "detect":
        out = pd.concat([det.detect(ds.strip()) for ds in a.datasets.split(",")], ignore_index=True)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(a.out, index=False)
        print(out[["dataset", "table", "column", "privacy_role", "subtype", "confidence", "source"]]
              .to_string(index=False))
        print(f"\nwrote {len(out)} labels -> {a.out}")
    elif a.cmd == "unseen":
        out = det.detect("unseen")
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        out[["column", "privacy_role", "subtype"]].to_csv(a.out, index=False)
        out.to_csv(Path(a.out).with_name("unseen_explained.csv"), index=False)
        print(out[["column", "privacy_role", "subtype", "confidence", "source", "reason"]].to_string(index=False))
        print(f"\nwrote submission -> {a.out} (explanations in unseen_explained.csv)")
    elif a.cmd == "explain":
        ps = [p for p in load_profiles(a.dataset, det.data_dir) if p["table"] == a.table and p["column"] == a.column]
        if not ps:
            raise SystemExit("column not found")
        p = ps[0]
        rec = det.classify(p)
        show = {k: v for k, v in p.items() if not (k.startswith("m_") and isinstance(v, float) and v < .2)}
        print(json.dumps({"profile": show, "decision": rec}, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
