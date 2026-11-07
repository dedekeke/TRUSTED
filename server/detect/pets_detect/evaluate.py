"""Evaluation: leave-one-dataset-out ablation of the tiers, with and without column names, against B1."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .pipeline import Config, Detector, root_paths

try:
    from pets_eval.detect import score_detection
except ImportError:  # pragma: no cover
    score_detection = None


def _summary(name: str, res: dict) -> dict:
    row = {"variant": name, "macro_f1": res["macro_f1"], "accuracy": res["accuracy"],
           "sensitive_recall": res["sensitive_recall"], "subtype_acc": res.get("subtype_accuracy")}
    for r, v in res["per_role"].items():
        row[f"f1_{r}"] = v["f1"]
    return row


def run(root: Path | None = None, out_dir: Path = Path("out/eval"), llm: bool = True, embedder: str = "tfidf",
        llm_model: str | None = None) -> pd.DataFrame:
    if score_detection is None:
        raise SystemExit("pets-eval is not installed: pip install -e <package>/toolkit")
    out_dir.mkdir(parents=True, exist_ok=True)
    r, data_dir, cat_path = root_paths(root)
    catalog = pd.read_csv(cat_path, dtype=str)
    datasets = sorted(d for d in catalog.dataset.unique() if (data_dir / d).is_dir())
    rows = []
    b1 = r / "results" / "b1_field_labels.csv"
    if b1.exists():
        rows.append(_summary("B1 baseline (organisers)", score_detection(pd.read_csv(b1, dtype=str), catalog)))
    variants = []
    for blind in (False, True):
        tag = "name-blind" if blind else "with names"
        variants += [(f"T1 rules [{tag}]", Config(tiers=(1,), blind_names=blind)),
                     (f"T1+T2 rules+retrieval [{tag}]", Config(tiers=(1, 2), blind_names=blind, embedder=embedder))]
        if llm:
            variants.append((f"T1+T2+T3 +local LLM [{tag}]",
                             Config(tiers=(1, 2, 3), blind_names=blind, embedder=embedder, llm_model=llm_model)))
    for name, cfg in variants:
        det = Detector(cfg, root)
        if 3 in cfg.tiers and not det.llm.available():
            continue
        pred = pd.concat([det.detect(ds) for ds in datasets], ignore_index=True)
        slug = name.split(" [")[0].split()[0].replace("+", "_") + ("_blind" if cfg.blind_names else "")
        pred.to_csv(out_dir / f"pred_{slug}.csv", index=False)
        res = score_detection(pred, catalog)
        (out_dir / f"score_{slug}.json").write_text(json.dumps(res, indent=2, default=str))
        rows.append(_summary(name, res))
        print(f"{name:45s} macro-F1 {res['macro_f1']:.3f}  sensitive recall {res['sensitive_recall']:.3f}")
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "ablation.csv", index=False)
    (out_dir / "ablation.md").write_text(_markdown(df))
    return df


def _markdown(df: pd.DataFrame) -> str:
    cols = ["variant", "macro_f1", "accuracy", "sensitive_recall", "subtype_acc",
            "f1_direct_identifier", "f1_quasi_identifier", "f1_sensitive_attribute", "f1_technical_identifier",
            "f1_free_text", "f1_record_key", "f1_non_sensitive"]
    cols = [c for c in cols if c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df[cols].iterrows():
        lines.append("| " + " | ".join(f"{v:.3f}" if isinstance(v, float) else str(v) for v in r) + " |")
    return ("# Detect ablation (leave-one-dataset-out: retrieval never sees the dataset being scored)\n\n"
            + "\n".join(lines) + "\n")
