"""UI pipeline jobs over the real HTTP server: background run, per-step status, review/resume, upload, download."""
import io
import json
import time
import urllib.request
import zipfile

import pandas as pd
import pytest

from server import api as server_api
from tests.test_api import KEY, NOTE, call, fake_detect, root  # noqa: F401  (root is a fixture)

pytestmark = pytest.mark.usefixtures("hmac_key")


@pytest.fixture
def hmac_key(monkeypatch):
    monkeypatch.setenv("PRIVACY_TOOL_HMAC_KEY", KEY)


@pytest.fixture
def server(root):  # noqa: F811
    httpd = server_api.serve(server_api.Api(root, root / "model", root / "runs", detect=fake_detect), 0)
    import threading
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def wait(base, jid, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        st = call(base, f"/api/jobs/{jid}")[1]
        if st["state"] not in ("created", "running"):
            return st
        time.sleep(0.1)
    raise AssertionError(f"job still running: {st}")


def steps(st):
    return {s["name"]: s["status"] for s in st["steps"]}


SPEC_OK = {"dataset": "demo", "trust_level": "internal", "targets": {"k": 1},
           "required": [{"column": "people.note", "task": "T-NOTE"}]}


def test_bundled_dataset_runs_all_steps_green_and_serves_tables_without_values(server):
    jid = call(server, "/api/jobs", {"dataset": "demo"})[1]["id"]
    st = call(server, f"/api/jobs/{jid}/start", {"spec": SPEC_OK, "no_scorecard": True})[1]
    assert st["state"] == "running" and st["params"]["budget"] == 50 and st["params"]["tau"] == 0.8
    st = wait(server, jid)
    assert st["state"] == "succeeded", st
    assert steps(st) == {"input": "success", "detect": "success", "review": "success", "select": "success",
                         "search": "success", "transform": "success", "evaluate": "skipped"}
    assert all(s["duration_s"] is not None for s in st["steps"] if s["status"] == "success" and s["name"] != "review")
    assert next(s for s in st["steps"] if s["name"] == "review")["duration_s"] is None
    texts = [call(server, f"/api/jobs/{jid}")[2]]
    for name in ("input", "detect", "review", "select", "search", "transform", "evaluate"):
        status, view, text, _ = call(server, f"/api/jobs/{jid}/steps/{name}")
        assert status == 200 and {"stats", "tables", "issues"} <= set(view)
        texts += [text, call(server, f"/api/jobs/{jid}/steps/{name}/log")[2]]
    det = call(server, f"/api/jobs/{jid}/steps/detect")[1]
    assert {t["id"] for t in det["tables"]} >= {"labels", "spans", "quality"}
    blob = " ".join(texts)
    assert "Anna" not in blob and "Virtanen" not in blob and KEY not in blob and '"p1"' not in blob
    assert call(server, f"/api/jobs/{jid}/start", {"spec": SPEC_OK})[1]["error"]["code"] == "already_started"


def test_review_pauses_then_confirm_resumes_into_new_dirs(server, root):  # noqa: F811
    spec = {**SPEC_OK, "required": [{"column": "people.score", "task": "T-SCORE"}]}
    jid = call(server, "/api/jobs", {"dataset": "demo"})[1]["id"]
    call(server, f"/api/jobs/{jid}/start", {"spec": spec, "no_scorecard": True})
    st = wait(server, jid)
    assert st["state"] == "needs_review"
    assert steps(st)["review"] == "needs_review" and steps(st)["select"] == "failed"
    assert steps(st)["search"] == "skipped"
    rev = call(server, f"/api/jobs/{jid}/steps/review")[1]["tables"][0]["rows"]
    assert [(r["column"], r["blocking"]) for r in rev if r["blocking"]] == [("score", True)]
    body = {"confirmations": [{"table": "people", "column": "score", "privacy_role": "non_sensitive",
                               "subtype": "MEASUREMENT"}], "allow_downgrade": False}
    st = call(server, f"/api/jobs/{jid}/confirm", body)[1]
    assert st["attempt"] == 2 and steps(st)["review"] == "success"
    st = wait(server, jid)
    assert steps(st)["select"] == "success", st
    out = root / "runs" / "jobs" / jid / "pipeline"
    assert (out / "select").is_dir() and (out / "select-2").is_dir()
    plan = json.loads((out / "select-2" / "decisions.json").read_text())
    assert plan["provenance"]["confirm_sha256"]
    assert call(server, f"/api/jobs/{jid}/confirm", body)[1]["error"]["code"] == "not_waiting"


def test_upload_keeps_bytes_and_runs_with_a_spec(server, root):  # noqa: F811
    jid = call(server, "/api/jobs", {"upload": "demo"})[1]["id"]
    src = root / "data" / "demo"
    for f in sorted(src.glob("*.csv")):
        req = urllib.request.Request(f"{server}/api/jobs/{jid}/files/{f.name}", data=f.read_bytes(), method="PUT")
        with urllib.request.urlopen(req) as r:
            assert json.loads(r.read())["bytes"] == f.stat().st_size
    stored = root / "runs" / "jobs" / jid / "data" / "demo"
    assert all((stored / f.name).read_bytes() == f.read_bytes() for f in src.glob("*.csv"))
    assert call(server, f"/api/jobs/{jid}")[1]["uploaded_files"] == ["people.csv", "visits.csv"]
    bad = urllib.request.Request(f"{server}/api/jobs/{jid}/files/..%2Fx.csv", data=b"a", method="PUT")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(bad)
    assert e.value.code in (400, 404)
    call(server, f"/api/jobs/{jid}/start", {"spec": SPEC_OK, "no_scorecard": True})
    assert wait(server, jid)["state"] == "succeeded"


def test_download_holds_protected_files_only(server):
    jid = call(server, "/api/jobs", {"dataset": "demo"})[1]["id"]
    call(server, f"/api/jobs/{jid}/start", {"spec": SPEC_OK, "no_scorecard": True})
    assert wait(server, jid)["download"] is True
    with urllib.request.urlopen(f"{server}/api/jobs/{jid}/download") as r:
        names = zipfile.ZipFile(io.BytesIO(r.read())).namelist()
    assert names and all(n.startswith("protected/") and "rowmap" not in n for n in names)
    notes = pd.read_csv(zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(
        f"{server}/api/jobs/{jid}/download").read())).open("protected/people.csv"), dtype=str).note
    assert not notes.fillna("").str.contains("Virtanen").any()


def test_bad_requests_are_named(server):
    assert call(server, "/api/jobs", {"dataset": "../data"})[1]["error"]["code"] == "unknown_dataset"
    assert call(server, "/api/jobs", {})[1]["error"]["code"] == "bad_request"
    jid = call(server, "/api/jobs", {"dataset": "demo"})[1]["id"]
    assert call(server, f"/api/jobs/{jid}/start", {"scenario": "H-S1"})[1]["error"]["code"] == "unknown_scenario"
    assert call(server, f"/api/jobs/{jid}/start", {"spec": SPEC_OK, "budget": 0})[1]["error"]["code"] == "bad_request"
    assert call(server, f"/api/jobs/{jid}/steps/nope")[1]["error"]["code"] in ("unknown_step", "not_found")
    assert call(server, "/api/jobs/x")[1]["error"]["code"] == "bad_job_id"
    assert call(server, f"/api/jobs/{jid}/download")[1]["error"]["code"] == "no_release"


def test_missing_hmac_key_is_named(server, monkeypatch):
    monkeypatch.delenv("PRIVACY_TOOL_HMAC_KEY")
    jid = call(server, "/api/jobs", {"dataset": "demo"})[1]["id"]
    assert call(server, f"/api/jobs/{jid}/start", {"spec": SPEC_OK})[1]["error"]["code"] == "hmac_key_missing"


def test_baselines_endpoint(server, root):  # noqa: F811
    body = call(server, "/api/baselines?dataset=demo&scenario=DEMO-S1")[1]
    assert body["dataset"] == "demo" and body["baselines"] == []


def upload_demo(base, root, name="demo"):  # noqa: F811
    jid = call(base, "/api/jobs", {"upload": name})[1]["id"]
    for f in sorted((root / "data" / "demo").glob("*.csv")):
        urllib.request.urlopen(urllib.request.Request(f"{base}/api/jobs/{jid}/files/{f.name}", data=f.read_bytes(),
                                                      method="PUT")).read()
    return jid


@pytest.fixture
def outside_server(root, tmp_path_factory):  # noqa: F811
    """Runs folder outside the package, as in real use: uploaded files cannot find the package by walking up."""
    import threading
    runs = tmp_path_factory.mktemp("elsewhere") / "runs"
    httpd = server_api.serve(server_api.Api(root, root / "model", runs, detect=fake_detect), 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_uploaded_data_with_a_bundled_scenario_finds_the_package(outside_server, root, monkeypatch):  # noqa: F811
    monkeypatch.delenv("PETS_ROOT", raising=False)
    jid = upload_demo(outside_server, root)
    call(outside_server, f"/api/jobs/{jid}/start", {"scenario": "DEMO-S1", "no_scorecard": True})
    st = wait(outside_server, jid)
    assert steps(st)["select"] == "success", st
    assert "PETS_ROOT" not in __import__("os").environ


def test_select_rejection_is_reported_with_its_reason(outside_server, root, monkeypatch):  # noqa: F811
    import server.jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "_package_root", lambda r: __import__("contextlib").nullcontext())
    monkeypatch.delenv("PETS_ROOT", raising=False)
    jid = upload_demo(outside_server, root)
    call(outside_server, f"/api/jobs/{jid}/start", {"scenario": "DEMO-S1", "no_scorecard": True})
    sel = next(s for s in wait(outside_server, jid)["steps"] if s["name"] == "select")
    assert sel["status"] == "failed" and "TypeError" not in (sel["error"] or "")
    assert "cannot find the challenge package root" in sel["error"]


def test_cancel_stops_before_the_next_stage(root):  # noqa: F811
    import threading
    started, release = threading.Event(), threading.Event()

    def slow_detect(model, data, out):
        started.set()
        release.wait(10)
        fake_detect(model, data, out)
    httpd = server_api.serve(server_api.Api(root, root / "model", root / "runs", detect=slow_detect), 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_port}"
    try:
        jid = call(base, "/api/jobs", {"dataset": "demo"})[1]["id"]
        call(base, f"/api/jobs/{jid}/start", {"spec": SPEC_OK, "no_scorecard": True})
        assert started.wait(10)
        assert call(base, f"/api/jobs/{jid}/cancel", {})[1]["state"] == "running"
        release.set()
        st = wait(base, jid)
        assert st["state"] == "cancelled", st
        assert steps(st)["detect"] == "success" and steps(st)["select"] == "skipped"
        assert call(base, f"/api/jobs/{jid}/cancel", {})[1]["state"] == "cancelled"
    finally:
        release.set()
        httpd.shutdown()
