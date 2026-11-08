"""Step 7 runner: train, tune and score the span detector; write the eval-split submission.

Protocol (no peeking at test):
- every labelled text column in metadata/pii_spans/ is split by group (conversation for customer_service, record
  otherwise) with a hash: 70% train, 10% dev, 20% test;
- the tagger learns on train, the P(O) threshold is chosen on dev, all numbers in the report come from test;
- customer_service conversations of split=eval have no public labels: they are only predicted, for the
  organisers' hidden check (pets_submission/customer_service_eval_spans.jsonl).
- the name dictionary comes from the data's own person-name columns, as found by the base column detector
  (a company redacting its own transcripts has its customer register). An ablation without it is reported.
"""
from __future__ import annotations

import hashlib
import html
import json
import random
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

from pets_detect.pipeline import root_paths

from . import regex, spoken
from .merge import assign_entities, merge
from .tagger import Dictionaries, Tagger

try:
    from pets_eval.text import span_scores
except ImportError:  # pragma: no cover
    span_scores = None

OUT = Path("out/spans")


def bucket(key: str) -> str:
    b = int(hashlib.md5(key.encode()).hexdigest(), 16) % 10
    return "train" if b < 7 else "dev" if b == 7 else "test"


def choose_base(base: str) -> str:
    if base:
        return base
    f = Path("out/compare/summary.json")
    if f.exists():
        from ..report import pick_winner
        w, _ = pick_winner(json.loads(f.read_text()))
        if w:
            return w
    return "v2"


def column_labels(base: str, root) -> pd.DataFrame:
    for f in (Path(f"out/compare/pred_{base}_names.csv"), Path(f"out/compare_{base}/pred_{base}_names.csv")):
        if f.exists():
            return pd.read_csv(f, dtype=str)
    if base == "v3":
        from pets_detect_v3.compare import FINAL
        from pets_detect_v3.pipeline import DetectorV3
        det = DetectorV3(FINAL.__class__(**{**FINAL.__dict__, "tiers": (1, 2)}), root)
        return pd.concat([det.detect(d) for d in det.labelled])
    from ..pipeline import Config, DetectorV2
    det = DetectorV2(Config(tiers=(1, 2)), root)
    return pd.concat([det.detect(d) for d in det.labelled])


def name_dictionary(labels: pd.DataFrame, data_dir: Path) -> set[str]:
    toks: set[str] = set()
    for (ds, table), g in labels[labels.subtype == "PERSON_NAME"].groupby(["dataset", "table"]):
        f = data_dir / ds / f"{table}.csv"
        if not f.exists():
            continue
        df = pd.read_csv(f, dtype=str, usecols=list(g.column), keep_default_na=False)
        for c in g.column:
            for v in df[c].dropna().unique():
                for t in str(v).replace(",", " ").split():
                    if len(t) > 2 and t[:1].isupper():
                        toks.add(t.lower())
    return toks


def load_file(path: Path, data_dir: Path) -> dict:
    ds, table, col = path.stem.split("__")
    gold = {}
    for line in path.open():
        r = json.loads(line)
        gold[r["record_id"]] = r["spans"]
    df = pd.read_csv(data_dir / ds / f"{table}.csv", dtype=str, keep_default_na=False)
    some = next(iter(gold))
    idcol = next(c for c in df.columns if (df[c] == some).any())
    group = df[idcol]
    split = pd.Series("public", index=df.index)
    if ds == "customer_service":
        conv = pd.read_csv(data_dir / ds / "conversations.csv", dtype=str, usecols=["conversation_id", "split"])
        sp = dict(zip(conv.conversation_id, conv.split))
        group = df["conversation_id"] if "conversation_id" in df else df[idcol]
        split = group.map(sp).fillna("train")
    recs = []
    for rid, text, g, s in zip(df[idcol], df[col], group, split):
        if not text:
            continue
        part = "eval" if s == "eval" else bucket(g)
        recs.append({"id": rid, "text": text, "group": g, "part": part, "gold": gold.get(rid, [])})
    return {"key": path.stem, "dataset": ds, "table": table, "column": col, "records": recs}


def detect(text: str, tagger: Tagger | None) -> list[dict]:
    sp = regex.find(text) + spoken.find(text)
    if tagger is not None:
        sp += tagger.predict(text)
    return merge(sp)


def _score(recs, pred_fn):
    gold = {r["id"]: r["gold"] for r in recs}
    pred = {r["id"]: pred_fn(r["text"]) for r in recs}
    return span_scores(gold, pred, mode="overlap"), pred


def example_html(text: str, pred: list[dict], gold: list[dict]) -> str:
    """Text with detected spans shown as [LABEL] and missed gold spans as [MISSED LABEL]: no raw PII remains."""
    marks = [(s["start"], s["end"], f"[{s['label']}]", False) for s in pred]
    for g in gold:
        if not any(g["start"] < p["end"] and p["start"] < g["end"] for p in pred):
            marks.append((g["start"], g["end"], f"[MISSED {g['label']}]", True))
    marks.sort()
    out, pos = [], 0
    for a, b, lab, miss in marks:
        if a < pos:
            continue
        out.append(html.escape(text[pos:a]))
        style = ' style="color:var(--bad)"' if miss else ""
        out.append(f"<mark{style}>{html.escape(lab)}</mark>")
        pos = b
    out.append(html.escape(text[pos:]))
    s = "".join(out)
    return s if len(s) < 900 else s[:900] + "…"


def main(root=None, base: str = "", max_train: int = 6000, n_dev: int = 1500, n_test: int = 4000, seed: int = 0):
    if span_scores is None:
        raise SystemExit("pets-eval is not installed")
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(seed)
    r, data_dir, _ = root_paths(root)
    base = choose_base(base)
    labels = column_labels(base, root)
    free = labels[labels.privacy_role == "free_text"]
    free_keys = {f"{a}__{b}__{c}" for a, b, c in zip(free.dataset, free.table, free.column)}
    names = name_dictionary(labels, data_dir)
    print(f"[spans] base column detector: {base}; {len(names)} name tokens from person-name columns", flush=True)

    files = [load_file(p, data_dir) for p in sorted((r / "metadata" / "pii_spans").glob("*.jsonl"))]
    train, dev, test = [], {}, {}
    for f in files:
        parts = defaultdict(list)
        for rec in f["records"]:
            parts[rec["part"]].append(rec)
        for k in parts:
            rnd.shuffle(parts[k])
        train += [(x["text"], x["gold"]) for x in parts["train"][:max_train]]
        dev[f["key"]] = parts["dev"][:n_dev]
        test[f["key"]] = parts["test"][:n_test]
        f["n_train"] = min(len(parts["train"]), max_train)
        f["eval"] = parts["eval"]
        print(f"  {f['key']:55s} train {f['n_train']:5d}  dev {len(dev[f['key']]):5d}  test {len(test[f['key']]):5d}"
              f"  eval {len(parts['eval'])}", flush=True)

    test_texts = [x["text"] for v in test.values() for x in v]

    def fit(dicts):
        tg = Tagger(dicts).fit(train)
        dev_all = [x for v in dev.values() for x in v]
        tg.precompute([x["text"] for x in dev_all] + test_texts)
        best = tg.tune_threshold(dev_all, lambda t: _score(dev_all, lambda s: detect(s, t))[0]["micro"]["f2"])
        return tg, best

    tagger, best = fit(Dictionaries(last=names))
    print(f"[spans] tagger trained on {len(train)} records; dev F2 {best[0]:.3f} at P(O) threshold {best[1]}",
          flush=True)
    tagger_nodict, best_nd = fit(Dictionaries())

    summary = {"base": base, "protocol": (
        f"Hash split by conversation/record: 70% train / 10% dev / 20% test. Tagger (logistic regression, hashed "
        f"token features) trained on {len(train)} records, P(O) threshold {tagger.o_threshold} chosen on dev, scores "
        f"on test only. Overlap matching with the same label (pets_eval.text.span_scores). Column detector for the "
        f"name dictionary and free_text coverage: {base}."),
        "files": {}, "datasets": {}, "ablation": {}}
    all_gold, all_pred = {}, {"b2": {}, "regex+spoken": {}, "v2 (no data names)": {}, "v2": {}}
    for f in files:
        recs = test[f["key"]]
        if not recs:
            continue
        sb, pb = _score(recs, regex.b2_spans)
        sv, pv = _score(recs, lambda s: detect(s, tagger))
        _, pr = _score(recs, lambda s: detect(s, None))
        _, pn = _score(recs, lambda s: detect(s, tagger_nodict))
        for rec in recs:
            all_gold[f"{f['key']}|{rec['id']}"] = rec["gold"]
        for name, p in (("b2", pb), ("regex+spoken", pr), ("v2 (no data names)", pn), ("v2", pv)):
            all_pred[name].update({f"{f['key']}|{k}": v for k, v in p.items()})
        ex = [example_html(x["text"], pv[x["id"]], x["gold"]) for x in recs if x["gold"]][:4]
        summary["files"][f["key"]] = {"n_test": len(recs), "n_train": f["n_train"], "b2": sb, "v2": sv,
                                      "v2_exact": span_scores({x["id"]: x["gold"] for x in recs}, pv, mode="exact")["micro"],
                                      "detected_as_free_text": f["key"] in free_keys, "examples": ex}
        summary["datasets"].setdefault(f["dataset"], []).append(f["key"])
        print(f"  {f['key']:55s} F2 B2 {sb['micro']['f2']:.3f} -> v2 {sv['micro']['f2']:.3f}  "
              f"recall {sb['micro']['recall']:.3f} -> {sv['micro']['recall']:.3f}", flush=True)
        with (OUT / f"pred_test_{f['key']}.jsonl").open("w") as fh:
            for x in recs:
                fh.write(json.dumps({"record_id": x["id"], "spans": [
                    {**s, "text": x["text"][s["start"]:s["end"]]} for s in pv[x["id"]]]}, ensure_ascii=False) + "\n")
    for name, p in all_pred.items():
        summary["ablation"][name] = span_scores(all_gold, p, mode="overlap")["micro"]
    focus = ["PERSON", "PHONE", "ADDRESS", "NATIONAL_ID"]
    summary["focus_recall"] = {name: span_scores(all_gold, p, labels=focus)["micro"]["recall"]
                               for name, p in all_pred.items()}
    summary["thresholds"] = {"with_dict": tagger.o_threshold, "no_dict": tagger_nodict.o_threshold}

    sub = OUT / "pets_submission"
    sub.mkdir(exist_ok=True)
    for f in files:
        if f["key"] != "customer_service__turns__text" or not f["eval"]:
            continue
        groups = defaultdict(list)
        tagger.precompute([x["text"] for x in f["eval"]])
        for x in f["eval"]:
            groups[x["group"]].append((x["id"], x["text"], detect(x["text"], tagger)))
        assign_entities(groups)
        with (sub / "customer_service_eval_spans.jsonl").open("w") as fh:
            for g in groups.values():
                for rid, text, sp in g:
                    fh.write(json.dumps({"record_id": rid, "spans": [
                        {"start": s["start"], "end": s["end"], "label": s["label"], "text": text[s["start"]:s["end"]],
                         "confidence": s["confidence"], "entity_id": s["entity_id"]} for s in sp]},
                        ensure_ascii=False) + "\n")
        summary["eval_submission"] = {"file": str(sub / "customer_service_eval_spans.jsonl"),
                                      "records": len(f["eval"])}
    summary["seconds"] = round(time.time() - t0, 1)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({"ablation_micro_f2": {k: v["f2"] for k, v in summary["ablation"].items()},
                      "focus_recall": summary["focus_recall"]}, indent=1))
    return summary
