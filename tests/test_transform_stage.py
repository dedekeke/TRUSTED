"""Final Transform stage: release gate, staged export, serialized validation. Artificial data only."""
import json
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from server.actions import execute
from server.select.search import _Evaluator, search
from server.select.select import input_digest, select
from server.transform import validate
from server.transform.files import read_csv, write_csv
from server.transform.run import run

KEY = b"test-only-transform-key"


def lab(t, c, role, sub, conf=0.95, ev="test; person table"):
    return {"dataset": "demo", "table": t, "column": c, "privacy_role": role, "subtype": sub, "confidence": conf,
            "evidence": ev}


def demo(n=300):
    """Two joined tables; hour-preserving time, derived age, free text with commas/quotes/newlines."""
    rng = np.random.default_rng(1)
    pids = [f"{i:05d}" for i in rng.integers(0, 120, n)]
    dob = {p: f"{1950 + 20 * (int(p) % 3)}-0{1 + int(p) % 9}-1{int(p) % 9}" for p in set(pids)}
    ts = (pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 365, n), unit="D")
          + pd.to_timedelta(rng.integers(8, 12, n), unit="h") + pd.to_timedelta(rng.integers(0, 59, n), unit="m"))
    visits = pd.DataFrame({"vid": [f"{i:06d}" for i in range(n)], "pid": pids, "dob": [dob[p] for p in pids],
                           "arrival": ts.strftime("%Y-%m-%d %H:%M"), "city": rng.choice(["Turku", "Salo", "Raisio"], n),
                           "note": [f'Anna Virtanen, "kipu"\nsoitti {i}' for i in range(n)]})
    labs = pd.DataFrame({"lab": [f"L{i:05d}" for i in range(n)], "vid": [f"{i:06d}" for i in range(n)],
                         "code": rng.choice(["CRP", "HB"], n)})
    labels = pd.DataFrame([
        lab("visits", "vid", "record_key", "RECORD_ID"), lab("visits", "pid", "direct_identifier", "PATIENT_ID"),
        lab("visits", "dob", "quasi_identifier", "BIRTH_DATE"), lab("visits", "arrival", "quasi_identifier", "TIMESTAMP"),
        lab("visits", "city", "quasi_identifier", "MUNICIPALITY"), lab("visits", "note", "free_text", "FREE_TEXT"),
        lab("labs", "lab", "record_key", "RECORD_ID", ev="test"), lab("labs", "vid", "technical_identifier", "OTHER", ev="test"),
        lab("labs", "code", "non_sensitive", "CATEGORY", ev="test")])
    rel = {"keys": [{"column": "visits.vid"}, {"column": "labs.lab"}],
           "joins": [{"parent": "visits.vid", "child": "labs.vid", "coverage": 1.0, "orphans": 0}],
           "subject_keys": {"visits": "visits.pid", "labs": "visits.pid"}, "subject_key": "visits.pid"}
    req = {"source": "spec", "scenario": None, "dataset": "demo", "trust_level": "controlled_research",
           "targets": {"k": 3}, "precision": {}, "warnings": [],
           "required": {"visits.arrival": ["HOUR"], "visits.city": ["CITY"], "visits.dob": ["AGE"],
                        "visits.note": ["NOTE"], "labs.code": ["CODE"]},
           "joins": [{"columns": ["visits.vid", "labs.vid"], "tasks": ["CODE"], "kind": "same_name"}]}
    return {"visits": visits, "labs": labs}, labels, rel, req


@pytest.fixture(scope="module")
def measured():
    tables, labels, rel, req = demo()
    plan = search(tables, select(tables, labels, rel, req, release_id="demo/recipient-a"), KEY)
    assert plan["status"] == "measured_ok", plan.get("conflict")
    return tables, plan


def write_data(tmp_path, tables, name="demo"):
    data = tmp_path / name
    data.mkdir()
    for t, df in tables.items():
        df.to_csv(data / f"{t}.csv", index=False)
    return data


def write_spans(path, visits, end=13, text=None):
    with open(path, "w", encoding="utf-8") as fh:
        for vid, note in zip(visits.vid, visits.note):
            fh.write(json.dumps({"record_id": vid, "spans": [
                {"start": 0, "end": end, "label": "PERSON", "text": note[:end] if text is None else text,
                 "confidence": .99, "entity_id": "P1"}]}) + "\n")
    return path


def release(tmp_path, tables, plan, **kw):
    data = write_data(tmp_path, tables)
    if "spans_files" not in kw:
        kw["spans_files"] = {"visits.note": write_spans(tmp_path / "spans.jsonl", tables["visits"])}
    kw.setdefault("scorecard", False)
    return run(data, plan, KEY, tmp_path / "run", **kw), tmp_path / "run"


def test_validated_release_layout_and_formats(tmp_path, measured):
    tables, plan = measured
    res, out = release(tmp_path, tables, plan)
    assert res["status"] == "validated", res.get("errors")
    assert all(c["status"] in ("passed", "not_run") for c in res["checks"])
    assert {p.name for p in out.iterdir()} == {"decisions.json", "decisions.md", "manifest.json", "transform_stats.json",
                                              "protected", "evaluation", "reports"}
    assert {p.name for p in (out / "protected").iterdir()} == {"visits.csv", "labs.csv"}
    assert {p.name for p in (out / "evaluation").iterdir()} == {"visits.csv", "labs.csv", "rowmap_visits.csv",
                                                               "rowmap_labs.csv", "input_manifest.json"}
    v = read_csv(out / "protected" / "visits.csv")
    assert list(v.columns) == ["vid", "arrival", "city", "note", "age"]  # retained source order, then derived
    assert v.vid.str.fullmatch(r"[0-9a-f]{32}").all() and len(v) == 300
    assert v.arrival.str.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:00").all()
    assert v.note[0] == '[PERSON], "kipu"\nsoitti 0'  # quoted multiline text round-trips
    assert set(read_csv(out / "protected" / "labs.csv").vid) == set(v.vid)  # shared token domain
    rm = read_csv(out / "evaluation" / "rowmap_visits.csv")
    assert rm.original_record_id[0] == "000000" and rm.protected_row.tolist()[:3] == ["0", "1", "2"]  # leading zeros
    m = json.loads((out / "manifest.json").read_text())
    assert m["validation_status"] == "validated" and m["approved_release"] and m["selection_status"] == "measured_ok"
    assert m["tables"]["visits"]["file"] == "protected/visits.csv" and len(m["tables"]["visits"]["sha256"]) == 64
    assert "input_digest" not in json.dumps(m) and "input_digest" not in (out / "decisions.json").read_text()
    assert json.loads((out / "evaluation" / "input_manifest.json").read_text())["input_digest"] == plan["input_digest"]
    scan = json.loads((out / "reports" / "identifier_check.json").read_text())
    assert scan["unexplained"] == {} and "examples" not in scan
    for f in (p for p in out.rglob("*") if p.is_file()):
        assert KEY.decode() not in f.read_text(encoding="utf-8")


def test_no_raw_source_values_in_shareable_or_report_files(tmp_path, measured):
    tables, plan = measured
    _, out = release(tmp_path, tables, plan)
    raw = set(tables["visits"].pid) | set(tables["visits"].dob) | set(tables["visits"].vid)
    for f in [*(out / "protected").iterdir(), *(out / "reports").iterdir(), out / "manifest.json"]:
        text = f.read_text(encoding="utf-8")
        assert "Anna Virtanen" not in text, f.name
        assert not any(f",{v}," in text or f"\n{v}," in text or f'"{v}"' in text for v in raw), f.name


@pytest.mark.parametrize("status,match", [("target_unmet", "target_unmet"), ("ready_for_transform", "not measured"),
                                          ("blocked", "blocked")])
def test_unapproved_plans_are_refused_without_export(tmp_path, measured, status, match):
    tables, plan = measured
    res, out = release(tmp_path, tables, {**plan, "status": status})
    assert res["status"] == "refused" and any(match in e for e in res["errors"])
    assert sorted(p.name for p in out.iterdir()) == ["diagnostics.json", "diagnostics.md"]
    assert json.loads((out / "diagnostics.json").read_text())["approved_release"] is False


def test_changed_source_values_with_same_schema_are_refused(tmp_path, measured):
    tables, plan = measured
    changed = deepcopy(tables)
    changed["visits"].loc[0, "city"] = "Salo" if tables["visits"].city[0] != "Salo" else "Turku"
    res, _ = release(tmp_path, changed, plan)
    assert res["status"] == "refused" and any("digest mismatch" in e for e in res["errors"])
    (tmp_path / "old").mkdir()
    res2, _ = release(tmp_path / "old", tables, {k: v for k, v in plan.items() if k != "input_digest"})
    assert res2["status"] == "refused" and any("no input_digest" in e for e in res2["errors"])


def test_release_id_must_be_explicit(tmp_path, measured):
    tables, plan = measured
    res, _ = release(tmp_path, tables, {**plan, "release_id_explicit": False})
    assert any("explicit recipient-scoped release_id" in e for e in res["errors"])


def test_free_text_needs_spans_or_explicit_rule_fallback(tmp_path, measured):
    tables, plan = measured
    res, _ = release(tmp_path, tables, plan, spans_files={})
    assert res["status"] == "refused" and any("--text-fallback rules" in e for e in res["errors"])
    (tmp_path / "b").mkdir()
    res, out = release(tmp_path / "b", tables, plan, spans_files={}, text_fallback=True)
    assert res["status"] == "validated"
    assert json.loads((out / "transform_stats.json").read_text())["redaction"] == {"visits.note": "rules_only"}


@pytest.mark.parametrize("kind", ["stale", "offsets", "unknown", "missing"])
def test_invalid_spans_are_rejected(tmp_path, measured, kind):
    tables, plan = measured
    path = tmp_path / "spans.jsonl"
    if kind == "stale":
        write_spans(path, tables["visits"], text="Someone Else!")
    elif kind == "offsets":
        write_spans(path, tables["visits"], end=10_000)
    else:
        write_spans(path, tables["visits"])
        lines = path.read_text().splitlines()
        lines = lines[1:] if kind == "missing" else lines + [json.dumps({"record_id": "nope", "spans": []})]
        path.write_text("\n".join(lines) + "\n")
    res, _ = release(tmp_path, tables, plan, spans_files={"visits.note": path})
    assert res["status"] == "refused" and any("invalid Detect spans" in e for e in res["errors"])
    assert "Someone" not in json.dumps(res["errors"]) and "Anna" not in json.dumps(res["errors"])


def test_review_items_block_only_released_or_required_fields(tmp_path, measured):
    tables, plan = measured
    res, _ = release(tmp_path, tables, {**plan, "review_queue": [{"column": "visits.city", "confidence": .5, "evidence": "test"}]})
    assert res["status"] == "refused" and any("unresolved review item" in e for e in res["errors"])
    (tmp_path / "b").mkdir()
    res, _ = release(tmp_path / "b", tables, {**plan, "review_queue": [{"column": "labs.lab", "confidence": .5, "evidence": "test"}]})
    assert res["status"] == "validated"  # dropped, unrequired: informational only


def test_output_directory_rules(tmp_path, measured):
    tables, plan = measured
    data = write_data(tmp_path, tables)
    (tmp_path / "exists").mkdir()
    with pytest.raises(FileExistsError):
        run(data, plan, KEY, tmp_path / "exists", scorecard=False)
    with pytest.raises(ValueError, match="overlap"):
        run(data, plan, KEY, data / "inside", scorecard=False)
    assert not (data / "inside").exists()


def test_identifier_hit_fails_validation_and_keeps_staging_private(tmp_path, measured):
    tables, plan = measured
    leaky = deepcopy(tables)
    leaky["labs"].loc[0, "code"] = "maija.m@example.com"  # a KEEP column carrying an identifier
    plan = {**plan, "input_digest": input_digest(leaky)}
    res, out = release(tmp_path, leaky, plan)
    assert res["status"] == "validation_failed"
    assert not (out / "protected").exists() and (out / "staging" / "protected" / "labs.csv").exists()
    m = json.loads((out / "manifest.json").read_text())
    assert m["validation_status"] == "failed" and not m["approved_release"]
    scan = json.loads((out / "staging" / "reports" / "identifier_check.json").read_text())
    assert scan["unexplained_by_column"] == {"labs.code": {"EMAIL": 1}}
    assert "maija" not in (out / "diagnostics.md").read_text()


def test_hmac_token_scanner_hits_are_classified_not_ignored(tmp_path):
    token = "0401234567" + "ab" * 11  # 32 hex chars that start like a Finnish mobile number
    (tmp_path / "protected").mkdir()
    df = pd.DataFrame({"id": [token], "other": [token]})
    write_csv(df, tmp_path / "protected" / "t.csv")
    plan = {"columns": [{"table": "t", "column": "id", "action": "HMAC", "method": "hmac_sha256"},
                        {"table": "t", "column": "other", "action": "KEEP", "method": None}]}
    check, report = validate.identifier_scan(plan, tmp_path, {"t": df})
    assert report["raw_totals"]["PHONE"] == 2
    assert report["classified_false_positives"]["PHONE"]["count"] == 1
    assert report["unexplained_by_column"] == {"t.other": {"PHONE": 1}} and check["status"] == "failed"


def suppression_inputs():
    rng = np.random.default_rng(0)
    n = 100
    tables = {"visits": pd.DataFrame({"vid": [f"V{i:05d}" for i in range(n)], "pid": [f"p{i}" for i in range(n)],
                                      "city": ["common"] * 98 + ["x", "y"],
                                      "score": rng.integers(0, 100, n).astype(str)})}
    labels = pd.DataFrame([lab("visits", "vid", "record_key", "RECORD_ID"),
                           lab("visits", "pid", "direct_identifier", "PATIENT_ID"),
                           lab("visits", "city", "quasi_identifier", "MUNICIPALITY"),
                           lab("visits", "score", "non_sensitive", "MEASUREMENT")])
    rel = {"keys": [{"column": "visits.vid"}], "joins": [], "subject_keys": {"visits": "visits.pid"}}
    req = {"source": "spec", "scenario": "T", "dataset": "demo", "trust_level": "controlled_research",
           "targets": {"k": 2}, "required": {"visits.city": ["CITY"]}, "precision": {}, "joins": [], "warnings": []}
    plan = select(tables, labels, rel, req, release_id="demo/recipient-b")
    city = next(c for c in plan["columns"] if c["column"] == "city")
    city["rungs"] = city["rungs"][:1]
    return tables, search(tables, plan, KEY)


def test_local_suppression_matches_the_measured_preview(tmp_path):
    tables, plan = suppression_inputs()
    assert plan["status"] == "measured_ok" and plan["suppression"]
    frames, stats = execute(tables, plan, KEY)
    levels = next(e["levels"] for e in plan["search_trace"] if e["evaluation"] == plan["measured"]["chosen_evaluation"])
    preview = _Evaluator(tables, plan, KEY, [], tables).build(levels, plan["suppression"])
    assert frames["visits"]["city"].tolist() == preview["visits"]["city"].astype(str).tolist()
    assert stats["suppressed_rows"] == {"visits": 2} and len(frames["visits"]) == 100  # rows kept, QIs blanked
    data = write_data(tmp_path, tables)
    res = run(data, plan, KEY, tmp_path / "run", scorecard=False)
    assert res["status"] == "validated", res.get("errors")
    tampered = {**plan, "search_trace": [{**e, "suppressed_fraction": 0.5} for e in plan["search_trace"]]}
    res = run(data, tampered, KEY, tmp_path / "run2", scorecard=False)
    assert res["status"] == "validation_failed" and any("differs from the measured" in e for e in res["errors"])


def test_scorecard_is_report_only(tmp_path, measured):
    tables, plan = measured
    res, out = release(tmp_path, tables, plan, scorecard=True)
    assert res["status"] == "validated"
    status = json.loads((out / "manifest.json").read_text())["scorecard"]["status"]
    assert status in ("run", "error")


def test_csv_writer_refuses_missing_values(tmp_path):
    with pytest.raises(ValueError):
        write_csv(pd.DataFrame({"a": [np.nan]}), tmp_path / "x.csv")
    with pytest.raises(ValueError):
        write_csv(pd.DataFrame({"a": [1]}), tmp_path / "y.csv")


def test_cli_exit_codes_and_legacy_delegation(tmp_path, measured, monkeypatch):
    from server.select.__main__ import main as select_main
    from server.transform.__main__ import main
    tables, plan = measured
    data = write_data(tmp_path, tables)
    spans = write_spans(tmp_path / "spans.jsonl", tables["visits"])
    good, unmet = tmp_path / "good.json", tmp_path / "unmet.json"
    good.write_text(json.dumps(plan))
    unmet.write_text(json.dumps({**plan, "status": "target_unmet"}))
    monkeypatch.setenv("PRIVACY_TOOL_HMAC_KEY", KEY.decode())
    assert main(["--data", str(data), "--plan", str(good), "--out", str(tmp_path / "a"),
                 "--spans", f"visits.note={spans}", "--no-scorecard"]) == 0
    assert main(["--data", str(data), "--plan", str(unmet), "--out", str(tmp_path / "b"), "--no-scorecard"]) == 2
    assert select_main(["transform", "--data", str(data), "--plan", str(unmet), "--out", str(tmp_path / "c"),
                        "--no-scorecard"]) == 2
    assert not (tmp_path / "c" / "protected").exists()
    monkeypatch.delenv("PRIVACY_TOOL_HMAC_KEY")
    with pytest.raises(SystemExit, match="HMAC key"):
        main(["--data", str(data), "--plan", str(good), "--out", str(tmp_path / "d")])
    assert not (tmp_path / "d").exists()
