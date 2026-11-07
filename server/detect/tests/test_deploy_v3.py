"""Deployable detect v3 on a small synthetic package: train -> infer equals in-process detection, and inference
never opens the catalog, truth, span labels or other datasets."""
import builtins
import hashlib
import io
import json
import random
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

import pets_detect.pipeline as v1_pipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pets_detect_v3 import deploy  # noqa: E402
from pets_detect_v3.compare import FINAL  # noqa: E402
from pets_detect_v3.pipeline import DetectorV3  # noqa: E402

FIRST = ["Aino", "Eemeli", "Katja", "Mikko", "Liisa", "Juha", "Sanna", "Timo"]
LAST = ["Mäkinen", "Repo", "Virtanen", "Korhonen", "Nieminen", "Lahtinen"]
CITIES = ["Turku", "Helsinki", "Tampere", "Espoo"]
DATASETS = ["zz_alpha", "zz_beta", "zz_gamma"]


def _write(root: Path, ds: str, n: int, rnd: random.Random):
    d = root / "data" / ds
    d.mkdir(parents=True)
    pid = f"{ds[3].upper()}ID"
    people = pd.DataFrame({
        f"{pid}": [f"{pid}-{i:05d}" for i in range(n)],
        "full_name": [f"{rnd.choice(FIRST)} {rnd.choice(LAST)}" for _ in range(n)],
        "email": [f"user{i}@mail.example" for i in range(n)],
        "postcode": [f"{rnd.randint(100, 990) * 100:05d}" for _ in range(n)],
        "city": [rnd.choice(CITIES) for _ in range(n)],
        "sex": [rnd.choice("MF") for _ in range(n)],
        "notes": [f"Asiakas {rnd.choice(FIRST)} {rnd.choice(LAST)} soitti numerosta 040 {rnd.randint(1000000, 9999999)} "
                  f"ja kysyi laskusta {rnd.randint(1, 99)}." for _ in range(n)]})
    events = pd.DataFrame({
        "event_id": [f"EV-{i:06d}" for i in range(2 * n)],
        f"{pid.lower()}": [people[pid][rnd.randrange(n)] for _ in range(2 * n)],
        "event_ts": [f"2025-0{rnd.randint(1, 9)}-1{rnd.randint(0, 9)} 1{rnd.randint(0, 9)}:00:00" for _ in range(2 * n)],
        "amount": [f"{rnd.uniform(1, 500):.2f}" for _ in range(2 * n)],
        "category": [rnd.choice(["a", "b", "c"]) for _ in range(2 * n)]})
    people.to_csv(d / "people.csv", index=False)
    events.to_csv(d / "events.csv", index=False)
    roles = {pid: ("record_key", "RECORD_ID"), "full_name": ("direct_identifier", "PERSON_NAME"),
             "email": ("direct_identifier", "EMAIL"), "postcode": ("quasi_identifier", "POSTCODE"),
             "city": ("quasi_identifier", "MUNICIPALITY"), "sex": ("quasi_identifier", "SEX"),
             "notes": ("free_text", "FREE_TEXT"), "event_id": ("record_key", "RECORD_ID"),
             pid.lower(): ("technical_identifier", "CUSTOMER_ID"), "event_ts": ("quasi_identifier", "TIMESTAMP"),
             "amount": ("sensitive_attribute", "FINANCIAL_DATA"), "category": ("non_sensitive", "CATEGORY")}
    cat = [{"dataset": ds, "table": t, "column": c, "privacy_role": roles[c][0], "subtype": roles[c][1],
            "data_kind": "text", "art9_special_category": "False", "description": "", "traps": ""}
           for t, df in (("people", people), ("events", events)) for c in df.columns]
    spans = root / "metadata" / "pii_spans"
    spans.mkdir(parents=True, exist_ok=True)
    with (spans / f"{ds}__people__notes.jsonl").open("w") as fh:
        for rid, text in zip(people[pid], people.notes):
            a = len("Asiakas ")
            b = text.index(" soitti")
            fh.write(json.dumps({"record_id": rid, "spans": [{"start": a, "end": b, "label": "PERSON"}]}) + "\n")
    return cat


@pytest.fixture(scope="module")
def pkg(tmp_path_factory):
    root = tmp_path_factory.mktemp("pkg")
    rnd = random.Random(0)
    cat = sum((_write(root, ds, 120, rnd) for ds in DATASETS), [])
    pd.DataFrame(cat).to_csv(root / "metadata" / "field_catalog.csv", index=False)
    (root / "truth").mkdir()
    mp = pytest.MonkeyPatch()
    mp.setenv("DETECT_V3_NO_MODEL_CACHE", "1")
    model = root / "out" / "model"
    deploy.train(root, model)
    yield root, model
    mp.undo()


def _guarded(root: Path, allowed_data: Path):
    """Fail on any open() under metadata/, truth/ (of the test package and of the real package) or a data dir other
    than the input."""
    real_root = Path(v1_pipeline.DEFAULT_ROOT)
    banned = [root / "metadata", root / "truth", real_root / "metadata", real_root / "truth"] + \
        [p for p in (root / "data").iterdir() if p != allowed_data]
    real = builtins.open

    def guard(file, *a, **kw):
        if isinstance(file, (str, Path)):
            p = Path(file).resolve()
            if any(p.is_relative_to(b.resolve()) for b in banned):
                raise AssertionError(f"inference opened {p}")
        return real(file, *a, **kw)
    return guard


def test_infer_reads_only_model_and_input_and_matches_in_process(pkg, tmp_path, monkeypatch):
    root, model = pkg
    data = root / "data" / "zz_alpha"
    guard = _guarded(root, data)
    monkeypatch.setattr(builtins, "open", guard)
    monkeypatch.setattr(io, "open", guard)
    monkeypatch.setattr(v1_pipeline, "DEFAULT_ROOT", tmp_path / "no-such-package")
    man = deploy.infer(model, data, tmp_path / "detect")
    monkeypatch.undo()

    out = tmp_path / "detect"
    got = pd.read_csv(out / "labels.csv", dtype=str, keep_default_na=False)
    want = DetectorV3(replace(FINAL, tiers=(1, 2)), root).detect("zz_alpha").astype(str)
    pd.testing.assert_frame_equal(got, want)

    # manifest binds every artifact and input file by sha256
    for t, inp in man["inputs"].items():
        assert inp["sha256"] == hashlib.sha256((data / inp["file"]).read_bytes()).hexdigest()
    for a in man["artifacts"].values():
        assert a["sha256"] == hashlib.sha256((out / a["file"]).read_bytes()).hexdigest()
    shas = {t: v["sha256"] for t, v in man["inputs"].items()}
    fp = hashlib.sha256("\n".join(f"{t}:{shas[t]}" for t in sorted(shas)).encode()).hexdigest()
    assert man["dataset_fingerprint"] == fp
    assert set(zip(got.privacy_role, got.subtype)) <= {tuple(x) for x in man["label_vocabulary"]}
    assert man["detector"]["model_sha256"] == json.loads((model / "model.json").read_text())["model_sha256"]

    # spans: offsets inside the cell, recomputable ids, no raw text
    notes = pd.read_csv(data / "people.csv", dtype=str, keep_default_na=False).notes
    spans = [json.loads(x) for x in (out / "spans.jsonl").read_text().splitlines()]
    assert spans and all(s["column"] == "notes" for s in spans)
    for s in spans:
        assert 0 <= s["start"] < s["end"] <= len(notes[s["row_index"]])
        key = f"{fp}|{s['table']}|{s['column']}|{s['row_index']}|{s['start']}|{s['end']}"
        assert s["span_id"] == hashlib.sha256(key.encode()).hexdigest()[:16]
        assert set(s) == {"span_id", "table", "column", "row_index", "start", "end", "entity_type", "entity_id",
                          "confidence", "needs_review"}
    assert man["artifacts"]["spans"]["columns"] == {"people.notes": {"cells": 120, "spans": len(spans)}}
    raw = (out / "spans.jsonl").read_text() + (out / "linkage.json").read_text()
    assert notes[0][8:20] not in raw

    link = json.loads((out / "linkage.json").read_text())
    joins = [r for r in link["relations"] if r["kind"] == "join"]
    assert {"table": "people", "column": "AID"} in [r["right"] for r in joins]
    assert all(isinstance(v, (int, float)) for r in link["relations"] for v in r["evidence"].values())


def test_infer_refuses_existing_out_and_tampered_model(pkg, tmp_path):
    root, model = pkg
    with pytest.raises(FileExistsError):
        deploy.infer(model, root / "data" / "zz_beta", tmp_path)
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "model.pkl").write_bytes((model / "model.pkl").read_bytes() + b"x")
    (bad / "model.json").write_text((model / "model.json").read_text())
    with pytest.raises(ValueError, match="model_sha256"):
        deploy.infer(bad, root / "data" / "zz_beta", tmp_path / "o")


def test_model_files_hold_no_training_values(pkg):
    root, model = pkg
    blob = b"".join(f.read_bytes() for f in model.iterdir())
    values = set()
    for f in (root / "data").glob("*/*.csv"):
        df = pd.read_csv(f, dtype=str, keep_default_na=False)
        for c in df.columns:
            for v in df[c].unique():
                values |= {v} | {w.lower().strip(".,") for w in v.split()}
    leaked = sorted(v for v in values if len(v) >= 6 and v.encode() in blob)
    assert not leaked, leaked[:10]


def test_pinned_hash_is_checked_before_unpickling(pkg, tmp_path, monkeypatch, capsys):
    root, model = pkg
    monkeypatch.setattr(deploy.pickle, "loads", lambda b: pytest.fail("unpickled an unverified model"))
    with pytest.raises(ValueError, match="pinned"):
        deploy.load_model(model, "0" * 64)
    monkeypatch.setenv("DETECT_MODEL_SHA256", "f" * 64)
    with pytest.raises(ValueError, match="pinned"):
        deploy.load_model(model)
    monkeypatch.undo()
    deploy.load_model(model)
    assert "not pinned" in capsys.readouterr().err
    sha = json.loads((model / "model.json").read_text())["model_sha256"]
    deploy.load_model(model, sha)
    assert "not pinned" not in capsys.readouterr().err


def test_benchmark_scores_against_catalog(pkg, tmp_path):
    root, model = pkg
    deploy.infer(model, root / "data" / "zz_gamma", tmp_path / "d")
    r = deploy.benchmark(root, tmp_path / "d" / "labels.csv")
    assert r["n_fields"] == 12 and 0 <= r["macro_f1"] <= 1


def _conversation_inputs():
    turns = pd.DataFrame({"turn_id": ["t1", "t2", "t3", "t4"], "conversation_id": ["c1", "c1", "c2", "c1"],
                          "text": ["call me at 040 1234567", "yes 040 1234567 again", "040 1234567 here",
                                   "or 050 7654321"]})
    labels = pd.DataFrame([{"table": "turns", "column": "text", "privacy_role": "free_text", "subtype": "FREE_TEXT"},
                           {"table": "turns", "column": "conversation_id", "privacy_role": "technical_identifier",
                            "subtype": "OTHER"}])
    ps = [{"table": "turns", "column": "turn_id", "fk_to": []},
          {"table": "turns", "column": "conversation_id", "fk_to": ["conversations.conversation_id"]},
          {"table": "turns", "column": "text", "fk_to": []}]
    return {"turns": turns}, labels, ps


def test_entities_are_numbered_per_conversation_not_per_cell():
    tables, labels, ps = _conversation_inputs()
    stats, groups = {}, {}
    spans = list(deploy._spans(tables, labels, None, "f" * 64, 0.6, stats, ps, groups))
    ids = {s["row_index"]: s["entity_id"] for s in spans if s["entity_type"] == "PHONE"}
    assert ids[0] == ids[1]                      # same number, two turns of conversation c1: one entity
    assert ids[0] != ids[2]                      # same number in conversation c2: not linkable
    assert ids[3] != ids[0] and ids[3].split(":")[2] == ids[0].split(":")[2]  # other number, same group
    assert groups == {"turns.text": "turns.conversation_id"}
    assert all("c1" not in s["entity_id"] and "040" not in s["entity_id"] for s in spans)  # opaque ids


def test_no_or_ambiguous_group_key_keeps_one_group_per_cell():
    tables, labels, ps = _conversation_inputs()
    ps[0]["fk_to"] = ["other.turn_id"]           # two FK columns: customer vs conversation is ambiguous
    groups = {}
    spans = list(deploy._spans(tables, labels, None, "f" * 64, 0.6, {}, ps, groups))
    ids = {s["row_index"]: s["entity_id"] for s in spans if s["entity_type"] == "PHONE"}
    assert ids[0] != ids[1] and groups == {"turns.text": None}
