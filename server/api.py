"""Minimal local HTTP API over Detect v3 inference and server.select (stdlib only).

  python -m server.api --model <detect model dir> --runs <runs dir> [--model-sha256 HEX] [--port 8000] [--root PKG]
                       [--guard]

Each run is runs/<id>/ with one fresh sub-dir per step: detect/, confirm.csv, select/, search/. A step that already
ran answers 409 `step_done`; start a new run to redo it. Responses carry labels, statuses, counts and digests only:
never cell values, span text, the HMAC key (env PRIVACY_TOOL_HMAC_KEY, server side) or row maps.
--guard installs an audit hook that refuses to open metadata/field_catalog.csv, metadata/pii_spans/, truth/ and holdout/.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import secrets
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "detect"))  # pets_detect* packages

from pets_eval.io import find_package_root, load_scenarios  # noqa: E402

from server.select import __main__ as cli  # noqa: E402
from server.select import artifacts, select  # noqa: E402
from server.select import labels as detection_labels  # noqa: E402

DEV_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}
RUN_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
LABEL_FIELDS = ["table", "column", "privacy_role", "subtype", "confidence", "needs_review", "art9", "art9_table",
                "data_kind"]  # `reason` and similar free text are excluded: they may quote cell values
TRACE_DROP = {"risk"}  # per-evaluation risk dumps are large; share below k is kept per table
STEP_LOCK = threading.Lock()  # one pipeline step at a time: the CLI steps print to the process-wide stdout


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


def guard(root: Path) -> list[str]:
    """Audit hook: refuse opening evaluation-only files under root. Returns the list it appends refusals to."""
    root = root.resolve()
    banned = [root / "metadata" / "field_catalog.csv", root / "metadata" / "pii_spans", root / "truth",
              root / "holdout"]
    refused: list[str] = []

    def hook(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            p = Path(os.fsdecode(args[0]))
            if not p.is_absolute():
                p = Path.cwd() / p
            p = Path(os.path.normpath(p))
            if any(p == b or b in p.parents for b in banned):
                refused.append(str(p))
                raise PermissionError(f"guard: evaluation-only file opened at runtime: {p}")

    sys.addaudithook(hook)
    return refused


def _bool(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


class Api:
    def __init__(self, root, model, runs, detect=None, model_sha256=None):
        self.root, self.model, self.runs = Path(root).resolve(), Path(model), Path(runs)
        self.model_sha256 = model_sha256  # None: load_model falls back to env DETECT_MODEL_SHA256
        self.runs.mkdir(parents=True, exist_ok=True)
        self.detect = detect or self._infer

    def _infer(self, model, data, out):
        from pets_detect_v3 import deploy
        return deploy.infer(model, data, out, llm=False, model_sha256=self.model_sha256)

    # ------------------------------------------------------------------ helpers
    def datasets(self) -> list[str]:
        return sorted(p.name for p in (self.root / "data").iterdir() if p.is_dir() and artifacts.input_files(p))

    def scenarios(self) -> list[dict]:
        keep = ("id", "dataset", "title", "recipient", "purpose", "trust_level", "threat_model", "legal_context",
                "utility_requirements", "suggested_privacy_targets", "notes")
        return [{k: s.get(k) for k in keep} for s in load_scenarios(self.root)]

    def run_dir(self, run_id: str) -> Path:
        if not RUN_ID.match(run_id or ""):
            raise ApiError(400, "bad_run_id", "run id must look like 20261107T130507Z-0123abcd")
        d = self.runs / run_id
        if not d.is_dir():
            raise ApiError(404, "run_not_found", f"no run {run_id}")
        return d

    def data_dir(self, d: Path) -> Path:
        return self.root / "data" / json.loads((d / "run.json").read_text())["dataset"]

    @staticmethod
    def fresh(path: Path, step: str) -> Path:
        if path.exists():
            raise ApiError(409, "step_done", f"{step} already ran for this run; start a new run to redo it")
        return path

    def labels(self, d: Path) -> pd.DataFrame:
        if not (d / "detect" / "manifest.json").is_file():
            raise ApiError(409, "detect_missing", "run detect first")
        return pd.read_csv(d / "detect" / "labels.csv", dtype=str, keep_default_na=False)

    @staticmethod
    def log_error(d: Path, step: str, code: str, message: str) -> None:
        path = d / "errors.json"
        errs = json.loads(path.read_text()) if path.exists() else []
        errs.append({"step": step, "code": code, "message": message, "at": datetime.now(timezone.utc).isoformat()})
        path.write_text(json.dumps(errs, indent=1))

    def step(self, d: Path, name: str, fn):
        """Run a CLI step with its prints captured; named artifact/provenance rejections become 409."""
        out, err = io.StringIO(), io.StringIO()
        with STEP_LOCK, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = fn()
            except artifacts.ArtifactError as e:
                self.log_error(d, name, e.code, str(e))
                raise ApiError(409, e.code, str(e)) from None
            except (ValueError, SystemExit) as e:
                self.log_error(d, name, "rejected", str(e))
                raise ApiError(400, "rejected", str(e)) from None
        if not (d / name).exists():  # the CLI returned without output: blocked before writing (message on stderr)
            msg = err.getvalue().strip() or out.getvalue().strip() or f"{name} produced no output"
            self.log_error(d, name, "blocked", msg)
            raise ApiError(409, "blocked", msg)
        return code

    # ------------------------------------------------------------------ steps
    def create_run(self, body: dict) -> dict:
        dataset = body.get("dataset")
        if dataset not in self.datasets():
            raise ApiError(400, "unknown_dataset", f"dataset must be one of {self.datasets()}")
        run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
        d = self.runs / run_id
        d.mkdir()
        (d / "run.json").write_text(json.dumps({"dataset": dataset, "model": str(self.model),
                                                "created_at": datetime.now(timezone.utc).isoformat()}))
        try:
            with STEP_LOCK:
                self.detect(self.model, self.root / "data" / dataset, d / "detect")
        except Exception as e:  # noqa: BLE001 - reported on the run, never swallowed
            self.log_error(d, "detect", type(e).__name__, str(e))
            raise ApiError(500, "detect_failed", str(e)) from None
        return self.state(run_id)

    def confirm(self, run_id: str, body: dict) -> dict:
        d = self.run_dir(run_id)
        rows = body.get("confirmations")
        allow = body.get("allow_downgrade", False)
        if not isinstance(rows, list) or not rows or not isinstance(allow, bool):
            raise ApiError(400, "bad_request", "need confirmations: [{table,column,privacy_role,subtype}], "
                                               "allow_downgrade: bool")
        keys = ("table", "column", "privacy_role", "subtype")
        if not all(isinstance(r, dict) and all(isinstance(r.get(k), str) and r[k] for k in keys) for r in rows):
            raise ApiError(400, "bad_request", f"each confirmation needs string {', '.join(keys)}")
        confirmed = pd.DataFrame([{k: r[k] for k in keys} for r in rows])
        data = self.data_dir(d)
        labels = detection_labels.from_detection(self.labels(d), cli.read_tables(data), data.name)
        try:
            select.confirm(labels, confirmed, allow)  # same validation select applies (unknown column, downgrade)
        except ValueError as e:
            raise ApiError(400, "invalid_confirmation", str(e)) from None
        confirmed.to_csv(self.fresh(d / "confirm.csv", "confirm"), index=False)
        (d / "confirm.json").write_text(json.dumps({"reviewer_confirmed": True, "allow_downgrade": allow,
                                                    "count": len(confirmed),
                                                    "at": datetime.now(timezone.utc).isoformat()}))
        return self.state(run_id)

    def select(self, run_id: str, body: dict) -> dict:
        d = self.run_dir(run_id)
        data = self.data_dir(d)
        scenario = body.get("scenario")
        known = {s["id"]: s["dataset"] for s in self.scenarios()}
        if known.get(scenario) != data.name:
            raise ApiError(400, "unknown_scenario", f"scenario must be one of "
                                                    f"{sorted(k for k, v in known.items() if v == data.name)}")
        self.labels(d)
        self.fresh(d / "select", "select")
        confirm = json.loads((d / "confirm.json").read_text()) if (d / "confirm.json").exists() else None
        a = SimpleNamespace(data=str(data), out=str(d / "select"), labels=str(d / "detect" / "labels.csv"),
                            manifest=None, confirm=str(d / "confirm.csv") if confirm else None,
                            allow_downgrade=bool(confirm and confirm["allow_downgrade"]), scenario=scenario,
                            spec=None, no_purpose=None, no_probe=False, declare_joins=False, release_id=None,
                            rows=20000)
        self.step(d, "select", lambda: cli.cmd_select(a))
        return self.state(run_id)

    def search(self, run_id: str, body: dict) -> dict:
        d = self.run_dir(run_id)
        budget = body.get("budget", 50)
        if not isinstance(budget, int) or isinstance(budget, bool) or not 1 <= budget <= 500:
            raise ApiError(400, "bad_request", "budget must be an integer 1..500")
        if not os.environ.get(cli.KEY_ENV):
            raise ApiError(503, "hmac_key_missing", f"start the server with {cli.KEY_ENV} set")
        if not (d / "select" / "decisions.json").is_file():
            raise ApiError(409, "select_missing", "run select first")
        self.fresh(d / "search", "search")
        a = SimpleNamespace(data=str(self.data_dir(d)), plan=str(d / "select" / "decisions.json"),
                            out=str(d / "search"), budget=budget, tau=0.8)
        self.step(d, "search", lambda: cli.cmd_search(a))
        return self.state(run_id)

    # ------------------------------------------------------------------ state
    def state(self, run_id: str) -> dict:
        d = self.run_dir(run_id)
        run = json.loads((d / "run.json").read_text())
        res = {"id": run_id, "dataset": run["dataset"], "created_at": run["created_at"],
               "steps": {s: (d / p).exists() for s, p in
                         (("detect", "detect/manifest.json"), ("confirm", "confirm.csv"),
                          ("select", "select/decisions.json"), ("search", "search/decisions.json"))},
               "manifest": None, "labels": [], "detect_review": [], "confirmation": None, "confirmations": [],
               "select": None, "search": None,
               "errors": json.loads((d / "errors.json").read_text()) if (d / "errors.json").exists() else []}
        if res["steps"]["detect"]:
            m = json.loads((d / "detect" / "manifest.json").read_text())
            res["manifest"] = {"dataset": m["dataset"], "dataset_fingerprint": m["dataset_fingerprint"],
                               "detector": {k: m["detector"].get(k) for k in ("name", "version", "model_sha256")},
                               "tables": {t: {"rows": v["rows"], "columns": len(v["columns"])}
                                          for t, v in m["inputs"].items()},
                               "created_at": m["created_at"]}
            lab = self.labels(d)
            res["labels"] = [{k: (float(r[k]) if k == "confidence" else _bool(r[k]) if k in
                                  ("needs_review", "art9", "art9_table") else r[k]) for k in LABEL_FIELDS if k in r}
                             for r in lab.to_dict("records")]
            res["detect_review"] = [x for x in res["labels"] if x["needs_review"]]
        if res["steps"]["confirm"]:
            res["confirmation"] = json.loads((d / "confirm.json").read_text())
            res["confirmations"] = pd.read_csv(d / "confirm.csv", dtype=str).to_dict("records")
        for s in ("select", "search"):
            if res["steps"][s]:
                res[s] = plan_summary(json.loads((d / s / "decisions.json").read_text()))
        return res


def plan_summary(p: dict) -> dict:
    """The fields the UI shows; decisions.json itself holds no values (contract v1)."""
    cols = [{k: c.get(k) for k in ("table", "column", "privacy_role", "subtype", "action", "method", "params",
                                   "required_by", "needs_review", "confidence")}
            | {"explanation": c.get("selection_explanation", c.get("reason"))} for c in p["columns"]]
    trace = [{k: v for k, v in e.items() if k not in TRACE_DROP}
             | {"share_below_k": {t: r.get("share_below_k") for t, r in (e.get("risk") or {}).items()}}
             for e in p.get("search_trace", [])]
    measured = p.get("measured")
    return {"status": p["status"], "outcome": p["outcome"], "scenario": p.get("scenario"),
            "trust_level": p.get("trust_level"), "targets": p.get("targets"), "tables": p["tables"],
            "columns": cols, "derived": p.get("derived", []), "review_queue": p["review_queue"],
            "reviews": p["reviews"], "errors": p["errors"], "warnings": p["warnings"],
            "evidence": p.get("evidence"), "conflict": p.get("conflict"), "trace": trace,
            "measured": measured and {k: measured.get(k) for k in ("utility", "baseline_utility", "tau", "evaluations",
                                                                   "information_loss")},
            "provenance": p.get("provenance"), "plan_sha256": p.get("plan_sha256")}


def handler(api: Api):
    routes = [("GET", re.compile(r"^/api/datasets$"), lambda m, b: {"datasets": api.datasets()}),
              ("GET", re.compile(r"^/api/scenarios$"), lambda m, b: {"scenarios": api.scenarios()}),
              ("POST", re.compile(r"^/api/runs$"), lambda m, b: api.create_run(b)),
              ("GET", re.compile(r"^/api/runs/([^/]+)$"), lambda m, b: api.state(m[1])),
              ("POST", re.compile(r"^/api/runs/([^/]+)/confirm$"), lambda m, b: api.confirm(m[1], b)),
              ("POST", re.compile(r"^/api/runs/([^/]+)/select$"), lambda m, b: api.select(m[1], b)),
              ("POST", re.compile(r"^/api/runs/([^/]+)/search$"), lambda m, b: api.search(m[1], b))]

    class Handler(BaseHTTPRequestHandler):
        def send(self, status: int, body: dict | None = None):
            data = json.dumps(body, default=str).encode() if body is not None else b""
            self.send_response(status)
            origin = self.headers.get("Origin")
            if origin in DEV_ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send(204)

        def dispatch(self, method):
            try:
                path = self.path.split("?", 1)[0]
                body = {}
                if method == "POST":
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 1_000_000:
                        raise ApiError(413, "too_large", "request body over 1 MB")
                    try:
                        body = json.loads(self.rfile.read(n) or b"{}")
                    except ValueError:
                        raise ApiError(400, "bad_json", "body must be JSON") from None
                    if not isinstance(body, dict):
                        raise ApiError(400, "bad_json", "body must be a JSON object")
                for verb, pattern, fn in routes:
                    m = pattern.match(path)
                    if m and verb == method:
                        return self.send(200, fn(m, body))
                raise ApiError(404, "not_found", f"no route {method} {path}")
            except ApiError as e:
                self.send(e.status, {"error": {"code": e.code, "message": str(e)}})
            except Exception as e:  # noqa: BLE001
                self.log_error("unhandled: %r", e)
                self.send(500, {"error": {"code": "internal", "message": type(e).__name__}})

        def do_GET(self):
            self.dispatch("GET")

        def do_POST(self):
            self.dispatch("POST")

    return Handler


def serve(api: Api, port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), handler(api))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m server.api")
    ap.add_argument("--model", required=True, help="detect v3 model dir (from `pets_detect_v3 train`)")
    ap.add_argument("--runs", required=True, help="directory for run outputs (one fresh sub-dir per run)")
    ap.add_argument("--model-sha256", help="pinned sha256 of model.pkl (or env DETECT_MODEL_SHA256)")
    ap.add_argument("--root", help="challenge package root (default: found upwards from the cwd)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--guard", action="store_true", help="refuse opening catalog, gold spans, truth/, holdout/")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else find_package_root()
    if root is None:
        sys.exit("cannot find the challenge package root; pass --root")
    if a.guard:
        guard(root)
    httpd = serve(Api(root, a.model, a.runs, model_sha256=a.model_sha256), a.port)
    print(f"serving on http://127.0.0.1:{a.port} (root {root}, runs {a.runs}, guard {'on' if a.guard else 'off'})",
          flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
