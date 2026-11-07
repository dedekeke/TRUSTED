"""Deployable Detect v3: training and inference are separate steps.

train  : catalog + labelled datasets + public span labels -> model dir (model.pkl + model.json). Training only.
infer  : model dir + ONE input data dir -> labels.csv, spans.jsonl, linkage.json, manifest.json. Never opens
         metadata/, truth/, gold spans or other datasets.
benchmark: scores saved labels against the catalog. Evaluation only; not part of artifact validation.
"""
from __future__ import annotations

import hashlib
import io
import json
import pickle
import os
import random
import sys
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer

from pets_detect.patterns import ROLES, SUBTYPES
from pets_detect.pipeline import root_paths
from pets_detect.profiler import SAMPLE_ROWS, profile_dataset

from pets_detect_v2.linkage import EMBEDDED
from pets_detect_v2.spans import run as S
from pets_detect_v2.spans.merge import assign_entities
from pets_detect_v2.spans.tagger import Dictionaries, Tagger

from . import __version__
from .compare import FINAL
from .jev import make_llm
from .pipeline import Config, DetectorV3
from .router import Router, _fit_one

_SRC = Path(__file__).resolve().parents[1]
CODE_VERSION = __version__ + "+" + hashlib.sha256(b"".join(
    f.read_bytes() for d in ("pets_detect", "pets_detect_v2", "pets_detect_v3")
    for f in sorted((_SRC / d).rglob("*.py")))).hexdigest()[:12]
SUBJECT_SUBTYPES = {"NATIONAL_ID", "PATIENT_ID", "CUSTOMER_ID", "EMPLOYEE_ID", "STUDENT_ID", "ACCOUNT_ID",
                    "CARD_ID", "EMAIL", "PHONE"}
TRUST_WARNING = ("WARNING: model hash not pinned (--model-sha256 / DETECT_MODEL_SHA256): trusting the model.json next "
                 "to model.pkl. model.pkl is a pickle and runs code when loaded; pin the hash of a model you trained.")
TEXT_BATCH = 2000  # tagger token probabilities are cached per batch; bounded memory on large note tables


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _fresh(out) -> Path:
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"refusing to write into existing {out}")
    return out


class FrozenRouter(Router):
    """Router with pre-fitted value models: one per training dataset (leave-one-dataset-out, so a training dataset
    is still scored without its own labels) and one on all training data (key None) for any other dataset."""

    def _value_model(self, dataset):
        return self._lr.get(dataset, self._lr[None])


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


class HashedTfidf(TfidfVectorizer):
    """A fitted TfidfVectorizer whose vocabulary holds token hashes, not the tokens (training values)."""

    def build_analyzer(self):
        base = super().build_analyzer()
        return lambda doc: [_h(t) for t in base(doc)]


def _hash_vocabulary(v: TfidfVectorizer) -> None:
    v.__class__ = HashedTfidf
    v.vocabulary_ = {_h(t): i for t, i in v.vocabulary_.items()}


def _strip_raw(r: Router) -> None:
    """Drop every training value from the router before it is pickled: kNN needs only the neighbours' labels and the
    precomputed embeddings; the TF-IDF vocabularies (built from sample values) are kept as hashes."""
    kb = r.kb
    kb.docs = [{"privacy_role": d["privacy_role"], "subtype": d["subtype"]} for d in kb.docs]
    for v in (kb.embedder.word, kb.embedder.char):
        _hash_vocabulary(v)
    r.train, r.blind_train, r.blind_t1, r.cache, r._train_hash = [], [], [], None, None


def label_vocabulary(pairs) -> list[list[str]]:
    # rules, recall bias and context adjustment combine roles and subtypes freely, so any role can carry any subtype
    subs = set(SUBTYPES) | {s for _, s in pairs}
    return [[r, s] for r in ROLES for s in sorted(subs)]


def train_tagger(root, labelled: list[str], catalog: pd.DataFrame, seed: int = 0, max_train: int = 6000,
                 n_dev: int = 1500) -> Tagger | None:
    """Span tagger on the train split of the public span labels; P(O) threshold tuned on the dev split."""
    r, data_dir, _ = root_paths(root)
    rnd = random.Random(seed)
    train, dev = [], []
    for path in sorted((r / "metadata" / "pii_spans").glob("*.jsonl")):
        if path.stem.split("__")[0] not in labelled:
            continue
        parts = defaultdict(list)
        for rec in S.load_file(path, data_dir)["records"]:
            parts[rec["part"]].append(rec)
        for k in sorted(parts):
            rnd.shuffle(parts[k])
        train += [(x["text"], x["gold"]) for x in parts["train"][:max_train]]
        dev += parts["dev"][:n_dev]
    if not train:
        return None
    tagger = Tagger(Dictionaries(last=S.name_dictionary(catalog[catalog.dataset.isin(labelled)], data_dir)))
    tagger.fit(train)
    if dev and S.span_scores is not None:
        tagger.precompute([x["text"] for x in dev])
        tagger.tune_threshold(dev, lambda t: S._score(dev, lambda s: S.detect(s, t))[0]["micro"]["f2"])
    tagger.__dict__.pop("_cache", None)
    tagger.d = None  # the name dictionary (real names) is rebuilt from the input data at inference, never saved
    return tagger


def train(root, out, cfg: Config = FINAL) -> dict:
    out = _fresh(out)
    det = DetectorV3(replace(cfg, tiers=(1, 2)), root)
    r = det.router
    r.cache = None  # never bake cwd-relative cached pickles into the model
    det.prefit(det.labelled)
    lr = {d: r._value_model(d) for d in det.labelled}
    lr[None] = _fit_one(*r._fit_args(None))
    r.__class__ = FrozenRouter
    r._lr = lr
    _strip_raw(r)
    state = {"router": r, "names": det.names, "kind_of": det.kind_of, "art9_of": det.art9_of, "pairs": det.pairs,
             "labelled": det.labelled, "tagger": train_tagger(root, det.labelled, det.catalog)}
    blob = pickle.dumps(state, protocol=4)
    out.mkdir(parents=True)
    (out / "model.pkl").write_bytes(blob)
    meta = {"schema": "pets.detect.model/1", "name": "pets_detect_v3", "version": CODE_VERSION,
            "sklearn": sklearn.__version__, "config": asdict(cfg), "training_datasets": det.labelled,
            "label_vocabulary": label_vocabulary(det.pairs), "model_file": "model.pkl", "model_sha256": sha256(blob),
            "span_tagger": state["tagger"] is not None, "created_at": datetime.now(timezone.utc).isoformat()}
    (out / "model.json").write_text(json.dumps(meta, indent=1))
    return meta


def load_model(model_dir, expected_sha256: str | None = None) -> tuple[dict, dict]:
    """expected_sha256 (or env DETECT_MODEL_SHA256) pins the model; checked before the pickle is loaded."""
    model_dir = Path(model_dir)
    meta = json.loads((model_dir / "model.json").read_text())
    if meta.get("schema") != "pets.detect.model/1":
        raise ValueError(f"unknown model schema {meta.get('schema')!r}")
    blob = (model_dir / meta["model_file"]).read_bytes()
    got = sha256(blob)
    pinned = expected_sha256 or os.environ.get("DETECT_MODEL_SHA256")
    if pinned and got != pinned.lower():
        raise ValueError(f"model.pkl sha256 {got} does not match the pinned model_sha256 {pinned}")
    if not pinned:
        print(TRUST_WARNING, file=sys.stderr, flush=True)
    if got != meta["model_sha256"]:
        raise ValueError("model.pkl does not match model_sha256 in model.json")
    if meta["sklearn"] != sklearn.__version__:
        raise ValueError(f"model trained with scikit-learn {meta['sklearn']}, running {sklearn.__version__}")
    return meta, pickle.loads(blob)


def detector(meta: dict, state: dict, llm: bool) -> DetectorV3:
    c = meta["config"]
    cfg = Config(**{**c, "tiers": tuple(t for t in c["tiers"] if llm or t != 3)})
    det = DetectorV3.__new__(DetectorV3)
    det.__dict__.update({k: v for k, v in state.items() if k != "tagger"})
    det.cfg, det.root, det.data_dir, det.catalog, det.timings = cfg, None, None, None, {}
    det.llm = make_llm(cfg.llm_model) if 3 in cfg.tiers else None
    return det


def group_column(ps, table: str, column: str) -> str | None:
    """The column that groups a text column's rows into one conversation/record (e.g. turns.conversation_id):
    the table's only foreign-key column. None (one group per cell) when there is no FK or several, because
    picking among several (customer_id vs agent_id) would link cells that belong to different conversations."""
    fks = sorted({p["column"] for p in ps if p["table"] == table and p["fk_to"] and p["column"] != column})
    return fks[0] if len(fks) == 1 else None


def _group_ids(fp: str, table: str, key: str | None, values) -> list[str]:
    """Opaque per-row group ids: rows sharing a non-blank key value share an id; no value ever appears."""
    if key is None:
        return [f"r{i}" for i in range(len(values))]
    return [sha256(f"{fp}|{table}|{key}|{v}".encode())[:12] if str(v).strip() else f"r{i}"
            for i, v in enumerate(values)]


def _spans(tables, labels, tagger, fp: str, review_below: float, stats: dict, ps=None, groups: dict | None = None):
    """Yields span records; stats gets {"table.column": {"cells", "spans"}} for every column scanned.

    Entities are numbered per group: all cells of one conversation (rows sharing the table's single FK value,
    see group_column) form one group, so a person mentioned in several turns keeps one entity_id. Without such
    a key every cell is its own group. `groups` receives {"table.column": "table.key" or None}."""
    groups = {} if groups is None else groups
    if tagger is not None:
        # as spans.run.name_dictionary, but from the in-memory (fingerprinted) tables
        person = labels[labels.subtype == "PERSON_NAME"]
        tagger.d = Dictionaries(last={w.lower() for t, c in zip(person.table, person.column)
                                      for v in set(tables[t][c]) for w in v.replace(",", " ").split()
                                      if len(w) > 2 and w[:1].isupper()})
    text = labels[(labels.privacy_role == "free_text") | (labels.subtype == "FREE_TEXT")]
    for t, c in zip(text.table, text.column):
        cells = [(i, v) for i, v in enumerate(tables[t][c]) if v.strip()]
        st = stats[f"{t}.{c}"] = {"cells": len(cells), "spans": 0}
        key = group_column(ps or [], t, c)
        groups[f"{t}.{c}"] = f"{t}.{key}" if key else None
        gids = _group_ids(fp, t, key, tables[t][key].tolist() if key else tables[t][c].tolist())
        found = {}
        for k in range(0, len(cells), TEXT_BATCH):  # detection stays batched (bounded tagger cache)
            part = cells[k:k + TEXT_BATCH]
            if tagger is not None:
                tagger.__dict__.pop("_cache", None)
                tagger.precompute([v for _, v in part])
            found.update({i: (v, S.detect(v, tagger)) for i, v in part})
        by_group: dict[str, list] = {}
        for i, (v, sp) in found.items():  # row order within each group
            by_group.setdefault(gids[i], []).append((i, v, sp))
        assign_entities(by_group)  # the same value in one group (conversation or cell) gets one entity id
        for i, (v, sp) in found.items():
            st["spans"] += len(sp)
            for s in sp:
                yield {"span_id": sha256(f"{fp}|{t}|{c}|{i}|{s['start']}|{s['end']}".encode())[:16],
                       "table": t, "column": c, "row_index": i, "start": s["start"], "end": s["end"],
                       "entity_type": s["label"], "entity_id": f"{t}:{c}:{gids[i]}:{s['entity_id']}",
                       "confidence": s["confidence"], "needs_review": bool(s["confidence"] < review_below)}
    if tagger is not None:
        tagger.__dict__.pop("_cache", None)


def _linkage(ps, tables, labels, fp: str) -> dict:
    def rel(kind, left, right, evidence, conf, review):
        key = f"{fp}|{kind}|{left[0]}|{left[1]}|{right[0] if right else ''}|{right[1] if right else ''}"
        return {"relation_id": sha256(key.encode())[:16], "kind": kind,
                "left": {"table": left[0], "column": left[1]},
                "right": {"table": right[0], "column": right[1]} if right else None,
                "evidence": evidence, "confidence": round(float(conf), 3), "needs_review": bool(review)}

    cols = {f"{t}.{c}": (t, c) for t, df in tables.items() for c in df.columns}
    rels = []
    for p in ps:
        for target in p["fk_to"]:
            rt, rc = cols[target]
            lv, rv = set(tables[p["table"]][p["column"]]) - {""}, tables[rt][rc]
            share = len(lv & set(rv)) / len(lv) if lv else 0.0
            rels.append(rel("join", (p["table"], p["column"]), (rt, rc),
                            {"left_distinct": len(lv), "right_distinct": int(rv.nunique()),
                             "left_in_right_share": round(share, 4),
                             "right_unique_ratio": round(rv.nunique() / max(len(rv), 1), 4),
                             "candidate_targets": len(p["fk_to"])},
                            share, share < .95 or len(p["fk_to"]) > 1))
    for row in labels[labels.privacy_role.isin(["direct_identifier", "technical_identifier"])
                      & labels.subtype.isin(SUBJECT_SUBTYPES)].itertuples():
        s = tables[row.table][row.column]
        filled = s[s != ""]
        rels.append(rel("subject", (row.table, row.column), None,
                        {"rows": len(s), "non_blank_share": round(len(filled) / max(len(s), 1), 4),
                         "distinct": int(filled.nunique()),
                         "rows_per_value": round(len(filled) / max(filled.nunique(), 1), 3)},
                        row.confidence, row.needs_review))
    # information hidden inside an identifier (a HETU encodes birth date and sex): fixed descriptions, no values
    for row in labels[labels.subtype.isin(list(EMBEDDED))].itertuples():
        r = rel("embedded", (row.table, row.column), None, {"encoded_attributes": len(EMBEDDED[row.subtype])},
                row.confidence, row.needs_review)  # evidence stays numeric (contract v1)
        r["encodes"] = list(EMBEDDED[row.subtype])  # fixed descriptions from the detector, never data values
        rels.append(r)
    return {"schema": "pets.detect.linkage/1", "relations": rels}


def infer(model_dir, data, out, llm: bool = False, model_sha256: str | None = None) -> dict:
    out, data = _fresh(out), Path(data)
    meta, state = load_model(model_dir, model_sha256)
    files = sorted(f for f in data.glob("*.csv") if not f.stem.startswith(("rowmap_", "_")))
    if not files:
        raise FileNotFoundError(f"no CSV tables in {data}")
    raw = {f.stem: f.read_bytes() for f in files}
    tables = {t: pd.read_csv(io.BytesIO(b), dtype=str, keep_default_na=False) for t, b in raw.items()}
    shas = {t: sha256(b) for t, b in raw.items()}
    fp = sha256("\n".join(f"{t}:{shas[t]}" for t in sorted(shas)).encode())

    det = detector(meta, state, llm)
    # profile exactly the fingerprinted bytes, read as profiler.load_dataset() does
    sample = {t: pd.read_csv(io.BytesIO(b), dtype=str, nrows=SAMPLE_ROWS, keep_default_na=False, na_values=[""])
              for t, b in raw.items()}
    ps = profile_dataset(data.name, data, tables=sample)
    labels = det.detect(data.name, ps)
    vocab = {tuple(x) for x in meta["label_vocabulary"]}
    off = set(zip(labels.privacy_role, labels.subtype)) - vocab
    if off:
        raise ValueError(f"labels outside the model's label_vocabulary: {sorted(off)}")

    out.mkdir(parents=True)
    labels.to_csv(out / "labels.csv", index=False)
    span_stats: dict = {}
    span_groups: dict = {}
    with (out / "spans.jsonl").open("w") as fh:
        for s in _spans(tables, labels, state["tagger"], fp, det.cfg.review_below, span_stats, ps, span_groups):
            fh.write(json.dumps(s) + "\n")
    (out / "linkage.json").write_text(json.dumps(_linkage(ps, tables, labels, fp), indent=1))
    art = lambda f, **kw: {"file": f, "sha256": sha256((out / f).read_bytes()), **kw}  # noqa: E731
    manifest = {
        "schema": "pets.detect.manifest/1", "dataset": data.name, "dataset_fingerprint": fp,
        "inputs": {t: {"file": f"{t}.csv", "sha256": shas[t], "rows": len(df), "columns": list(df.columns)}
                   for t, df in tables.items()},
        "detector": {"name": "pets_detect_v3", "version": meta["version"], "model_sha256": meta["model_sha256"],
                     "config": asdict(det.cfg)},
        "label_vocabulary": meta["label_vocabulary"],
        "artifacts": {"labels": art("labels.csv"), "spans": art("spans.jsonl", schema="pets.detect.spans/1",
                                                                 columns=span_stats, groups=span_groups),
                      "linkage": art("linkage.json")},
        "created_at": datetime.now(timezone.utc).isoformat()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def benchmark(root, labels, datasets=None) -> dict:
    """Prediction quality vs the catalog (evaluation only: reads metadata/field_catalog.csv)."""
    from pets_eval.detect import score_detection
    pred = pd.read_csv(labels, dtype=str)
    catalog = pd.read_csv(root_paths(root)[2], dtype=str)
    return score_detection(pred, catalog, datasets or sorted(pred.dataset.unique()))
