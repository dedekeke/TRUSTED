"""Final Transform stage: release gate, staged export, serialized validation. Artificial data only.

Plans are bound exactly as in a real run: data dir -> Detect output dir (contract v1) -> provenance -> search."""
import json
import shutil
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from server.actions import execute
from server.select import artifacts as A
from server.select.search import _Evaluator, search
from server.select.select import select
from server.transform import validate
from server.transform.files import read_csv, write_csv
from server.transform.run import read_tables, run
from tests.contract_fixture import fingerprint, span, write_detect_dir

KEY = b"test-only-transform-key"


def lab(t, c, role, sub, conf=0.95, ev="test; person table"):
    return {"dataset": "demo", "table": t, "column": c, "privacy_role": role, "subtype": sub, "confidence": conf,
            "evidence": ev, "needs_review": "False"}


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


def note_spans(data, text=None):
    """One PERSON span over 'Anna Virtanen' in every note, in Detect contract v1 format."""
    _, fp = fingerprint(data)
    notes = read_tables(data)["visits"]["note"]
    return [span(fp, "visits", "note", i, 0, 13, entity_id=f"visits:note:{i}:P1") for i in range(len(notes))]


def write_data(root, tables, name="demo"):
    data = root / name
    data.mkdir(parents=True)
    for t, df in tables.items():
        df.to_csv(data / f"{t}.csv", index=False)
    return data


def bound_plan(root, tables, labels, rel, req, spans=True, release_id="demo/recipient-a", **search_kw):
    """data + detect dir + select (bound provenance) + search, as the CLI would do."""
    data = write_data(root, tables)
    lab_path = write_detect_dir(root / "detect", data, labels, note_spans(data) if spans else [])
    manifest = A.load_manifest(lab_path, data, "demo")
    read = read_tables(data)
    plan = select(read, labels, rel, req, release_id=release_id)
    plan["provenance"] = A.provenance(data, manifest)
    return data, root / "detect", search(read, plan, KEY, **search_kw)


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    tables, labels, rel, req = demo()
    data, detect, plan = bound_plan(tmp_path_factory.mktemp("bound"), tables, labels, rel, req)
    assert plan["status"] == "measured_ok" and plan["outcome"]["approved"], plan.get("conflict")
    return data, detect, plan


def release(tmp_path, measured, plan=None, **kw):
    data, detect, base = measured
    kw.setdefault("detect_dir", detect)
    kw.setdefault("scorecard", False)
    return run(data, plan or base, KEY, tmp_path / "run", **kw), tmp_path / "run"


def test_validated_release_layout_and_formats(tmp_path, measured):
    data, _, plan = measured
    res, out = release(tmp_path, measured)
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
    assert v.note[0] == '[PERSON], "kipu"\nsoitti 0'  # Detect span applied; quoted multiline text round-trips
    assert set(read_csv(out / "protected" / "labs.csv").vid) == set(v.vid)  # shared token domain
    rm = read_csv(out / "evaluation" / "rowmap_visits.csv")
    assert rm.original_record_id[0] == "000000" and rm.protected_row.tolist()[:3] == ["0", "1", "2"]  # leading zeros
    m = json.loads((out / "manifest.json").read_text())
    assert m["validation_status"] == "validated" and m["approved_release"] and m["selection_status"] == "measured_ok"
    assert m["tables"]["visits"]["file"] == "protected/visits.csv" and len(m["tables"]["visits"]["sha256"]) == 64
    assert "provenance" not in json.dumps(m)  # source digests stay in the private input manifest
    private = json.loads((out / "evaluation" / "input_manifest.json").read_text())
    assert private["provenance"]["dataset_fingerprint"] == fingerprint(data)[1]
    assert private["detect"]["spans_sha256"] == plan["provenance"]["spans_sha256"]
    assert json.loads((out / "transform_stats.json").read_text())["redaction"] == {"visits.note": "detect_spans+rules"}
    scan = json.loads((out / "reports" / "identifier_check.json").read_text())
    assert scan["unexplained"] == {} and "examples" not in scan
    for f in (p for p in out.rglob("*") if p.is_file()):
        assert KEY.decode() not in f.read_text(encoding="utf-8")


def test_no_raw_source_values_in_shareable_or_report_files(tmp_path, measured):
    data, _, _ = measured
    _, out = release(tmp_path, measured)
    src = read_tables(data)["visits"]
    raw = set(src.pid) | set(src.dob) | set(src.vid)
    for f in [*(out / "protected").iterdir(), *(out / "reports").iterdir(), out / "manifest.json"]:
        text = f.read_text(encoding="utf-8")
        assert "Anna Virtanen" not in text, f.name
        assert not any(f",{v}," in text or f"\n{v}," in text or f'"{v}"' in text for v in raw), f.name


@pytest.mark.parametrize("status,outcome,match", [
    ("target_unmet", {"approved": False}, "target_unmet"), ("policy_valid", {}, "not measured"),
    ("budget_exhausted", {"approved": False}, "budget_exhausted"), ("blocked", {}, "blocked"),
    ("measured_ok", {"approved": False, "issues": ["provenance_unbound"]}, "provenance_unbound")])
def test_unapproved_plans_are_refused_without_export(tmp_path, measured, status, outcome, match):
    _, _, plan = measured
    res, out = release(tmp_path, measured, {**plan, "status": status, "outcome": outcome})
    assert res["status"] == "refused" and any(match in e for e in res["errors"])
    assert sorted(p.name for p in out.iterdir()) == ["diagnostics.json", "diagnostics.md"]
    assert json.loads((out / "diagnostics.json").read_text())["approved_release"] is False


def test_allow_unapproved_exports_marked_and_still_validated(tmp_path, measured):
    _, _, plan = measured
    res, out = release(tmp_path, measured, {**plan, "status": "target_unmet", "outcome": {"approved": False}},
                       allow_unapproved=True)
    assert res["status"] == "unapproved_export", res.get("errors")
    assert "NOT AN APPROVED RELEASE" in (out / "protected" / "NOT_APPROVED.txt").read_text()
    m = json.loads((out / "manifest.json").read_text())
    assert m["approved_release"] is False and m["validation_status"] == "unapproved_export"
    gate = json.loads((out / "transform_stats.json").read_text())["release_gate"]
    assert gate["approved"] is False and gate["allow_unapproved"] is True and len(gate["plan_sha256"]) == 64
    res, out = release(tmp_path / "b", measured, {**plan, "status": "blocked"}, allow_unapproved=True)
    assert res["status"] == "refused"


def test_changed_source_bytes_are_rejected_before_any_output(tmp_path, measured):
    data, detect, plan = measured
    changed = tmp_path / "demo"
    shutil.copytree(data, changed)
    text = (changed / "visits.csv").read_text()
    (changed / "visits.csv").write_text(text.replace("Turku", "Salo", 1))
    with pytest.raises(A.ArtifactError, match="input_mismatch"):
        run(changed, plan, KEY, tmp_path / "run", detect, scorecard=False)
    assert not (tmp_path / "run").exists()
    unbound = {k: v for k, v in plan.items() if k != "provenance"}
    with pytest.raises(A.ArtifactError, match="provenance_missing"):
        run(data, unbound, KEY, tmp_path / "run2", detect, scorecard=False)


def test_release_id_must_be_explicit(tmp_path, measured):
    _, _, plan = measured
    res, _ = release(tmp_path, measured, {**plan, "release_id_explicit": False})
    assert any("explicit recipient-scoped release_id" in e for e in res["errors"])


def test_free_text_needs_detect_spans_or_explicit_rule_fallback(tmp_path, measured):
    res, _ = release(tmp_path, measured, detect_dir=None)
    assert res["status"] == "refused" and any("--text-fallback rules" in e for e in res["errors"])
    res, out = release(tmp_path / "b", measured, detect_dir=None, text_fallback=True)
    assert res["status"] == "validated"
    assert json.loads((out / "transform_stats.json").read_text())["redaction"] == {"visits.note": "rules_only"}


@pytest.mark.parametrize("breakage,code", [("offsets", "stale_span"), ("span_id", "stale_span"),
                                           ("tampered", "artifact_mismatch"), ("other_data", "fingerprint_mismatch")])
def test_invalid_detect_spans_are_rejected(tmp_path, measured, breakage, code):
    data, detect, plan = measured
    bad = tmp_path / "detect"
    shutil.copytree(detect, bad)
    lines = [json.loads(x) for x in (bad / "spans.jsonl").read_text().splitlines()]
    if breakage == "offsets":
        lines[0]["end"] = 10_000
    elif breakage == "span_id":
        lines[0]["span_id"] = "0" * 16
    if breakage in ("offsets", "span_id", "tampered"):
        (bad / "spans.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines) + ("\n" if breakage == "tampered" else ""))
        if breakage != "tampered":  # keep the manifest consistent so the span check itself must catch it
            man = json.loads((bad / "manifest.json").read_text())
            man["artifacts"]["spans"]["sha256"] = A.sha256_file(bad / "spans.jsonl")
            (bad / "manifest.json").write_text(json.dumps(man))
            plan = {**plan, "provenance": {**plan["provenance"], "spans_sha256": man["artifacts"]["spans"]["sha256"]}}
    else:
        man = json.loads((bad / "manifest.json").read_text())
        man["dataset_fingerprint"] = "f" * 64
        (bad / "manifest.json").write_text(json.dumps(man))
    with pytest.raises(A.ArtifactError, match=code):
        run(data, plan, KEY, tmp_path / "run", bad, scorecard=False)
    assert not (tmp_path / "run").exists()


def test_review_items_block_only_released_or_required_fields(tmp_path, measured):
    _, _, plan = measured
    item = {"confidence": .5, "evidence": "test"}
    res, _ = release(tmp_path, measured, {**plan, "review_queue": [{"column": "visits.city", **item}]})
    assert res["status"] == "refused" and any("unresolved review item" in e for e in res["errors"])
    res, _ = release(tmp_path / "b", measured, {**plan, "review_queue": [{"column": "labs.lab", **item}]})
    assert res["status"] == "validated"  # dropped, unrequired: informational only


def test_output_directory_rules(tmp_path, measured):
    data, detect, plan = measured
    (tmp_path / "exists").mkdir()
    with pytest.raises(FileExistsError):
        run(data, plan, KEY, tmp_path / "exists", detect, scorecard=False)
    with pytest.raises(ValueError, match="overlap"):
        run(data, plan, KEY, data / "inside", detect, scorecard=False)
    assert not (data / "inside").exists()


def test_identifier_hit_fails_validation_and_keeps_staging_private(tmp_path):
    tables, labels, rel, req = demo()
    tables["labs"].loc[0, "code"] = "maija.m@example.com"  # a KEEP column carrying an identifier
    data, detect, plan = bound_plan(tmp_path / "in", tables, labels, rel, req)
    assert plan["outcome"]["approved"]
    res = run(data, plan, KEY, tmp_path / "run", detect, scorecard=False)
    out = tmp_path / "run"
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


def test_local_suppression_matches_the_measured_preview(tmp_path):
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
    data = write_data(tmp_path, tables)
    lab_path = write_detect_dir(tmp_path / "detect", data, labels)
    read = read_tables(data)
    plan = select(read, labels, rel, req, release_id="demo/recipient-b")
    plan["provenance"] = A.provenance(data, A.load_manifest(lab_path, data, "demo"))
    city = next(c for c in plan["columns"] if c["column"] == "city")
    city["rungs"] = city["rungs"][:1]
    plan = search(read, plan, KEY)
    assert plan["status"] == "measured_ok" and plan["suppression"] and plan["outcome"]["approved"]
    frames, stats = execute(read, plan, KEY)
    levels = next(e["levels"] for e in plan["search_trace"] if e["evaluation"] == plan["measured"]["chosen_evaluation"])
    preview = _Evaluator(read, plan, KEY, [], read).build(levels, plan["suppression"])
    assert frames["visits"]["city"].tolist() == preview["visits"]["city"].astype(str).tolist()
    assert stats["suppressed_rows"] == {"visits": 2} and len(frames["visits"]) == 100  # rows kept, QIs blanked
    res = run(data, plan, KEY, tmp_path / "run", scorecard=False)
    assert res["status"] == "validated", res.get("errors")
    tampered = {**plan, "search_trace": [{**e, "suppressed_fraction": 0.5} for e in plan["search_trace"]]}
    res = run(data, tampered, KEY, tmp_path / "run2", scorecard=False)
    assert res["status"] == "validation_failed" and any("differs from the measured" in e for e in res["errors"])


def test_scorecard_is_report_only(tmp_path, measured):
    res, out = release(tmp_path, measured, scorecard=True)
    assert res["status"] == "validated"
    assert json.loads((out / "manifest.json").read_text())["scorecard"]["status"] in ("run", "error")


def test_csv_writer_refuses_missing_values(tmp_path):
    with pytest.raises(ValueError):
        write_csv(pd.DataFrame({"a": [np.nan]}), tmp_path / "x.csv")
    with pytest.raises(ValueError):
        write_csv(pd.DataFrame({"a": [1]}), tmp_path / "y.csv")


def test_cli_exit_codes_and_legacy_delegation(tmp_path, measured, monkeypatch, capsys):
    from server.select.__main__ import main as select_main
    from server.transform.__main__ import main
    data, detect, plan = measured
    good, unmet = tmp_path / "good.json", tmp_path / "unmet.json"
    good.write_text(json.dumps(plan))
    unmet.write_text(json.dumps({**plan, "status": "target_unmet", "outcome": {"approved": False}}))
    monkeypatch.setenv("PRIVACY_TOOL_HMAC_KEY", KEY.decode())
    assert main(["--data", str(data), "--plan", str(good), "--out", str(tmp_path / "a"),
                 "--detect", str(detect), "--no-scorecard"]) == 0
    assert main(["--data", str(data), "--plan", str(unmet), "--out", str(tmp_path / "b"), "--no-scorecard"]) == 2
    assert select_main(["transform", "--data", str(data), "--plan", str(unmet), "--out", str(tmp_path / "c"),
                        "--detect", str(detect), "--no-scorecard"]) == 2
    assert not (tmp_path / "c" / "protected").exists()
    assert select_main(["transform", "--data", str(data), "--plan", str(unmet), "--out", str(tmp_path / "d"),
                        "--detect", str(detect), "--no-scorecard", "--allow-unapproved"]) == 0
    assert (tmp_path / "d" / "protected" / "NOT_APPROVED.txt").exists()
    monkeypatch.delenv("PRIVACY_TOOL_HMAC_KEY")
    with pytest.raises(SystemExit, match="HMAC key"):
        main(["--data", str(data), "--plan", str(good), "--out", str(tmp_path / "e")])
    assert not (tmp_path / "e").exists()
