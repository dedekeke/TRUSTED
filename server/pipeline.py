"""One command for the whole chain: Detect infer -> Select -> Search -> Transform.

  python -m server.pipeline --data <dataset dir> (--scenario ID | --spec FILE) --model <detect model dir>
                            --release-id ID --out <new dir> [--confirm FILE] [--budget N] [--llm]
                            [--model-sha256 SHA] [--text-fallback rules] [--allow-unapproved] [--no-scorecard]

Each stage writes its own subdirectory (detect/, select/, search/, transform/) through the stage's own CLI, so
every gate, binding check and issue code applies exactly as when the stages are run by hand. The chain stops at
the first stage that does not hand over (blocked selection, unapproved search without --allow-unapproved).
pipeline.json records each stage's exit code, status and artifact digests. The HMAC key comes from
PRIVACY_TOOL_HMAC_KEY and is never written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DETECT_SRC = Path(__file__).resolve().parent / "detect"
KEY_ENV = "PRIVACY_TOOL_HMAC_KEY"


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _status(path: Path) -> dict:
    if not path.is_file():
        return {}
    plan = json.loads(path.read_text())
    return {"status": plan.get("status"), "approved": (plan.get("outcome") or {}).get("approved"),
            "plan_sha256": _sha(path)}


def _detect(a, out: Path) -> dict:
    if str(DETECT_SRC) not in sys.path:  # detect packages live in server/detect (not an importable package path)
        sys.path.insert(0, str(DETECT_SRC))
    from pets_detect_v3 import deploy
    m = deploy.infer(a.model, a.data, out, llm=a.llm, model_sha256=a.model_sha256)
    return {"exit": 0, "status": "ok", "model_sha256": m["detector"]["model_sha256"],
            "dataset_fingerprint": m["dataset_fingerprint"],
            "artifacts": {k: v["sha256"] for k, v in m["artifacts"].items()}}


def run(a) -> int:
    from server.select.__main__ import main as select_main
    from server.transform.__main__ import main as transform_main
    out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to write into existing {out}")
    if not os.environ.get(KEY_ENV):
        sys.exit(f"set {KEY_ENV} (the HMAC key) in the environment")
    out.mkdir(parents=True)
    record = {"schema": "pets.pipeline/1", "data": str(Path(a.data).resolve()), "release_id": a.release_id,
              "scenario": a.scenario, "spec": a.spec, "started_at": datetime.now(timezone.utc).isoformat(),
              "stages": {}}

    def save(code: int) -> int:
        record["exit"] = code
        (out / "pipeline.json").write_text(json.dumps(record, indent=2))
        return code

    try:
        record["stages"]["detect"] = _detect(a, out / "detect")
    except Exception as e:  # noqa: BLE001  any detect failure stops the chain with a named reason
        record["stages"]["detect"] = {"exit": 1, "status": "failed", "error": f"{type(e).__name__}: {e}"}
        print(f"detect failed: {e}", file=sys.stderr)
        return save(1)

    argv = ["select", "--data", a.data, "--labels", str(out / "detect" / "labels.csv"),
            "--release-id", a.release_id, "--out", str(out / "select")]
    argv += ["--scenario", a.scenario] if a.scenario else ["--spec", a.spec]
    if a.confirm:
        argv += ["--confirm", a.confirm]
    code = _call(select_main, argv)
    record["stages"]["select"] = {"exit": code, **_status(out / "select" / "decisions.json")}
    if code != 0:
        return save(code)

    code = _call(select_main, ["search", "--data", a.data, "--plan", str(out / "select" / "decisions.json"),
                               "--out", str(out / "search"), "--budget", str(a.budget), "--detect", str(out / "detect")])
    st = _status(out / "search" / "decisions.json")
    record["stages"]["search"] = {"exit": code, **st}
    if not st.get("approved") and not a.allow_unapproved:
        record["stages"]["transform"] = {"exit": None, "status": "not_run",
                                         "reason": f"search status {st.get('status')}, approved={st.get('approved')}; "
                                                   "pass --allow-unapproved for a marked, non-release export"}
        return save(code or 3)

    argv = ["--data", a.data, "--plan", str(out / "search" / "decisions.json"), "--out", str(out / "transform"),
            "--detect", str(out / "detect")]
    argv += ["--text-fallback", a.text_fallback] if a.text_fallback else []
    argv += ["--allow-unapproved"] if a.allow_unapproved else []
    argv += ["--no-scorecard"] if a.no_scorecard else []
    code = _call(transform_main, argv)
    man = out / "transform" / "manifest.json"
    record["stages"]["transform"] = {"exit": code,
                                     "status": json.loads(man.read_text()).get("validation_status") if man.is_file()
                                     else "refused" if (out / "transform" / "diagnostics.json").is_file() else None,
                                     "manifest_sha256": _sha(man)}
    return save(code)


def _call(fn, argv) -> int:
    try:
        return int(fn(argv) or 0)
    except SystemExit as e:  # stage CLIs exit with a message on argument/environment errors
        if e.code not in (None, 0) and not isinstance(e.code, int):
            print(e.code, file=sys.stderr)
        return e.code if isinstance(e.code, int) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m server.pipeline", description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--scenario")
    g.add_argument("--spec")
    ap.add_argument("--model", required=True, help="trained detect model dir (python -m pets_detect_v3 train)")
    ap.add_argument("--model-sha256", help="pinned sha256 of model.pkl, checked before loading it")
    ap.add_argument("--release-id", required=True, help="recipient-scoped release id (scopes HMAC tokens)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--confirm", help="reviewer-confirmed labels CSV for select")
    ap.add_argument("--budget", type=int, default=50)
    ap.add_argument("--llm", action="store_true", help="use the local LLM tier in detect (Ollama)")
    ap.add_argument("--text-fallback", choices=["rules"])
    ap.add_argument("--allow-unapproved", action="store_true")
    ap.add_argument("--no-scorecard", action="store_true")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
