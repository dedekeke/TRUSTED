"""A UI job must produce exactly what `python -m server.pipeline` produces for the same inputs.

Same data, model, HMAC key and release id: the protected files must be byte-identical and every stage must end in
the same status. Uses the real Detect v3 model trained on the small synthetic package of test_deploy_v3.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy_v3 import pkg  # noqa: E402,F401  (module-scoped fixture: package + trained model)

from server import pipeline  # noqa: E402
from server.jobs import Jobs  # noqa: E402

SPEC = {"dataset": "zz_alpha", "trust_level": "internal", "targets": {"k": 1},
        "required": [{"column": "people.notes", "task": "T-NOTES"}, {"column": "events.category", "task": "T-CAT"}]}


def digests(folder: Path) -> dict:
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(folder.iterdir()) if f.is_file()}


def test_defaults_are_shared():
    ap_defaults = {a.dest: a.default for a in pipeline_parser()._actions if a.dest in pipeline.DEFAULTS}
    assert ap_defaults == {k: v for k, v in pipeline.DEFAULTS.items() if k in ap_defaults}
    assert set(ap_defaults) == set(pipeline.DEFAULTS)


def pipeline_parser():
    import argparse
    captured = {}
    real = argparse.ArgumentParser.parse_args

    def grab(self, *a, **k):
        captured["p"] = self
        raise SystemExit(0)
    argparse.ArgumentParser.parse_args = grab
    try:
        with pytest.raises(SystemExit):
            pipeline.main([])
    finally:
        argparse.ArgumentParser.parse_args = real
    return captured["p"]


@pytest.mark.parametrize("required", [SPEC["required"]])
def test_ui_job_equals_cli_run(pkg, tmp_path, monkeypatch, required):  # noqa: F811
    root, model = pkg
    data = root / "data" / "zz_alpha"
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({**SPEC, "required": required}))
    monkeypatch.setenv("PRIVACY_TOOL_HMAC_KEY", "parity-key")
    release = "zz/parity"

    cli_out = tmp_path / "cli"
    code = pipeline.main(["--data", str(data), "--spec", str(spec), "--model", str(model), "--release-id", release,
                          "--out", str(cli_out), "--no-scorecard"])
    cli = json.loads((cli_out / "pipeline.json").read_text())

    jobs = Jobs(root, model, tmp_path / "runs", scenarios=[])
    jid = jobs.create(dataset="zz_alpha")["id"]
    jobs.start(jid, {"spec": {**SPEC, "required": required}, "release_id": release, "no_scorecard": True},
               key_present=True)
    jobs.threads[jid].join(timeout=300)
    st = jobs.state(jid)
    ui_out = tmp_path / "runs" / jid / "pipeline"
    ui = json.loads((ui_out / "pipeline.json").read_text())

    assert code == 0 and st["state"] == "succeeded", (cli, st)
    for stage in ("detect", "select", "search", "transform"):
        assert cli["stages"][stage]["exit"] == ui["stages"][stage]["exit"]
        assert cli["stages"][stage].get("status") == ui["stages"][stage].get("status")
    assert cli["stages"]["detect"]["artifacts"] == ui["stages"]["detect"]["artifacts"]
    assert cli["params"] == ui["params"]
    assert digests(cli_out / "transform" / "protected") == digests(ui_out / "transform" / "protected")
    assert digests(cli_out / "transform" / "protected")


def test_job_status_follows_pipeline_stages(pkg, tmp_path, monkeypatch):  # noqa: F811
    root, model = pkg
    monkeypatch.setenv("PRIVACY_TOOL_HMAC_KEY", "parity-key")
    jobs = Jobs(root, model, tmp_path / "runs", scenarios=[])
    jid = jobs.create(dataset="zz_alpha")["id"]
    bad = {**SPEC, "trust_level": "public", "targets": {"k": 50}, "required": [{"column": "people.city", "task": "T-CITY"},
                                                      {"column": "people.postcode", "task": "T-PC"}]}
    jobs.start(jid, {"spec": bad, "budget": 5, "no_scorecard": True}, key_present=True)
    t = time.time()
    jobs.threads[jid].join(timeout=300)
    st = jobs.state(jid)
    got = {s["name"]: s["status"] for s in st["steps"]}
    assert st["state"] == "failed" and time.time() - t < 300
    assert got["detect"] == got["select"] == "success" and got["search"] == "failed"
    assert got["transform"] == "skipped" and got["evaluate"] == "skipped"
    view = jobs.step_view(jid, "search")
    assert any(t["id"] == "risk" and t["rows"] for t in view["tables"])
