"""Background pipeline jobs for the UI: one job = one dataset, one run of server.pipeline with per-step status.

Layout of runs/<job id>/:
  job.json        dataset, source (package | upload), data dir, created_at
  data/<name>/    uploaded CSVs (source=upload only)
  params.json     run parameters (scenario/spec, budget, ...); defaults from server.pipeline.DEFAULTS
  spec.json       requirement spec when the run uses one
  input.json      input file statistics (no values)
  pipeline/       server.pipeline output (detect/, select[-N]/, search[-N]/, transform[-N]/, pipeline.json)
  confirm-N.csv   reviewer-confirmed labels that started attempt N
  status.json     state + the 7 UI steps
  logs/<step>.log captured stdout/stderr of each step

The job calls server.pipeline.run() with the same namespace the CLI builds, so a UI run equals a CLI run
(tests/test_api_parity.py). The only addition is the on_step callback that records status.
"""
from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import re
import secrets
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from server import api_views, pipeline

STEPS = ["input", "detect", "review", "select", "search", "transform", "evaluate"]
JOB_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
RUN_LOCK = threading.Lock()  # one pipeline at a time: stage CLIs print to the process-wide stdout
OK = {"success", "warning"}
# personal-looking patterns removed from logs before they are served (logs are for developers; values never leave)
SCRUB = [re.compile(p) for p in (
    r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+",                          # e-mail
    r"\b\d{6}[-+A-FU-Y]?\d{3}[0-9A-Y]\b",                      # HETU
    r"\b[A-Z]{2}\d{2}(?: ?[0-9A-Z]{4}){3,7}(?: ?[0-9A-Z]{1,4})?\b",  # IBAN
    r"(?:\+358|\b0)\s?\d{1,3}[\s-]?\d{3,4}[\s-]?\d{2,4}\b",     # phone
    r"\b\d{1,3}(?:\.\d{1,3}){3}\b",                            # IPv4
)]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def scrub(text: str) -> str:
    for rx in SCRUB:
        text = rx.sub("[redacted]", text)
    return text


class JobError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


class _StepLog(io.TextIOBase):
    """stdout/stderr sink whose file follows the current step."""

    def __init__(self, logs: Path):
        self.logs, self.step = logs, "input"
        logs.mkdir(parents=True, exist_ok=True)

    def writable(self):
        return True

    def write(self, s):
        with (self.logs / f"{self.step}.log").open("a", encoding="utf-8") as fh:
            fh.write(s)
        return len(s)


class Jobs:
    def __init__(self, root: Path, model: Path, runs: Path, model_sha256: str | None = None, detect_fn=None,
                 benchmark: dict | None = None, scenarios: list[dict] | None = None):
        self.root, self.model, self.runs = Path(root), Path(model), Path(runs)
        self.model_sha256, self.detect_fn = model_sha256, detect_fn
        self.benchmark = benchmark or {}
        self.scenarios = scenarios or []
        self.threads: dict[str, threading.Thread] = {}

    # ---------------------------------------------------------------- files
    def dir(self, job_id: str) -> Path:
        if not JOB_ID.match(job_id or ""):
            raise JobError(400, "bad_job_id", "job id must look like 20261107T130507Z-0123abcd")
        d = self.runs / job_id
        if not (d / "job.json").is_file():
            raise JobError(404, "job_not_found", f"no job {job_id}")
        return d

    @staticmethod
    def _read(d: Path, name: str, default=None):
        p = d / name
        return json.loads(p.read_text()) if p.is_file() else default

    @staticmethod
    def _write(d: Path, name: str, obj) -> None:
        tmp = d / f".{name}.tmp"
        tmp.write_text(json.dumps(obj, indent=1, default=str))
        tmp.replace(d / name)

    def _status(self, d: Path) -> dict:
        return self._read(d, "status.json")

    def _set(self, d: Path, step: str | None = None, **fields) -> dict:
        st = self._status(d)
        if step is None:
            st.update(fields)
        else:
            s = st["steps"][step]
            if fields.get("status") == "running" and s["status"] != "running":
                s["started_at"], s["finished_at"], s["duration_s"] = now(), None, None
            if fields.get("status") not in (None, "running", "queued") and s.get("started_at") and not s.get("finished_at"):
                s["finished_at"] = now()
                s["duration_s"] = round((datetime.fromisoformat(s["finished_at"]) -
                                         datetime.fromisoformat(s["started_at"])).total_seconds(), 1)
            s.update(fields)
        st["updated_at"] = now()
        self._write(d, "status.json", st)
        return st

    # ---------------------------------------------------------------- create / upload
    def create(self, dataset: str | None = None, upload: str | None = None) -> dict:
        if bool(dataset) == bool(upload):
            raise JobError(400, "bad_request", "give either dataset (bundled) or upload (new dataset name)")
        if dataset:
            data = self.root / "data" / dataset
            if not NAME.match(dataset) or not data.is_dir():
                raise JobError(400, "unknown_dataset", f"no bundled dataset {dataset!r}")
            source, name = "package", dataset
        else:
            if not NAME.match(upload):
                raise JobError(400, "bad_name", "dataset name: letters, digits, _ and - only")
            source, name = "upload", upload
        job_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
        d = self.runs / job_id
        d.mkdir(parents=True)
        if source == "upload":
            data = d / "data" / name
            data.mkdir(parents=True)
        self._write(d, "job.json", {"id": job_id, "dataset": name, "source": source, "data": str(data),
                                    "created_at": now()})
        self._write(d, "status.json", {"state": "created", "attempt": 0, "created_at": now(), "updated_at": now(),
                                       "steps": {s: {"status": "queued"} for s in STEPS}})
        return self.state(job_id)

    def upload(self, job_id: str, filename: str, stream, length: int, limit: int = 512 * 2 ** 20) -> dict:
        d = self.dir(job_id)
        job = self._read(d, "job.json")
        if job["source"] != "upload":
            raise JobError(409, "not_upload", "this job uses a bundled dataset")
        if self._status(d)["state"] != "created":
            raise JobError(409, "already_started", "files can only be added before the job starts")
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.csv$", filename or ""):
            raise JobError(400, "bad_filename", "file name: letters, digits, _ and - with a .csv extension")
        if length <= 0 or length > limit:
            raise JobError(413, "too_large", f"file must be 1 byte .. {limit // 2 ** 20} MB")
        target = Path(job["data"]) / filename
        h, left = hashlib.sha256(), length
        with target.open("wb") as fh:  # bytes are stored exactly as sent (provenance hashes the raw bytes)
            while left:
                chunk = stream.read(min(1 << 20, left))
                if not chunk:
                    break
                fh.write(chunk)
                h.update(chunk)
                left -= len(chunk)
        if left:
            target.unlink(missing_ok=True)
            raise JobError(400, "incomplete_upload", "connection closed before the whole file arrived")
        return {"file": filename, "bytes": length, "sha256": h.hexdigest()}

    # ---------------------------------------------------------------- start / confirm
    def start(self, job_id: str, body: dict, key_present: bool) -> dict:
        d = self.dir(job_id)
        job = self._read(d, "job.json")
        if self._status(d)["state"] != "created":
            raise JobError(409, "already_started", "this job already ran; create a new job to run again")
        if not key_present:
            raise JobError(503, "hmac_key_missing", f"start the server with {pipeline.KEY_ENV} set")
        scenario, spec = body.get("scenario"), body.get("spec")
        if bool(scenario) == bool(spec):
            raise JobError(400, "bad_request", "give either scenario (id) or spec (requirement JSON object)")
        if scenario:
            known = {s["id"]: s["dataset"] for s in self.scenarios}
            if known.get(scenario) != job["dataset"]:
                raise JobError(400, "unknown_scenario", "scenario must be one of " + str(
                    sorted(k for k, v in known.items() if v == job["dataset"])) +
                    " (scenarios belong to a dataset name; other data needs a spec)")
        elif not isinstance(spec, dict):
            raise JobError(400, "bad_spec", "spec must be a JSON object")
        params = {k: body.get(k, v) for k, v in pipeline.DEFAULTS.items()}
        if not isinstance(params["budget"], int) or isinstance(params["budget"], bool) or not 1 <= params["budget"] <= 500:
            raise JobError(400, "bad_request", "budget must be an integer 1..500")
        if not isinstance(params["tau"], (int, float)) or not 0 < params["tau"] <= 1:
            raise JobError(400, "bad_request", "tau must be in (0, 1]")
        for k in ("llm", "allow_unapproved", "no_scorecard"):
            if not isinstance(params[k], bool):
                raise JobError(400, "bad_request", f"{k} must be true or false")
        if params["text_fallback"] not in (None, "rules"):
            raise JobError(400, "bad_request", "text_fallback must be null or 'rules'")
        release_id = body.get("release_id") or f"{scenario or job['dataset']}/{job_id}"
        if not isinstance(release_id, str) or not re.match(r"^[\w./:-]{1,128}$", release_id):
            raise JobError(400, "bad_request", "release_id: up to 128 of letters, digits and _ . / : -")
        if spec:
            self._write(d, "spec.json", spec)
        if not any(Path(job["data"]).glob("*.csv")):
            raise JobError(400, "no_input", "the dataset has no CSV files")
        self._write(d, "params.json", {"scenario": scenario, "spec": bool(spec), "release_id": release_id, **params})
        self._set(d, state="running", attempt=1, started_at=now())
        self._spawn(job_id, d, "detect", 1, None)
        return self.state(job_id)

    def confirm(self, job_id: str, rows: list, allow_downgrade: bool, validate) -> dict:
        d = self.dir(job_id)
        st = self._status(d)
        if st["state"] != "needs_review":
            raise JobError(409, "not_waiting", "the job is not waiting for a review")
        keys = ("table", "column", "privacy_role", "subtype")
        if not isinstance(rows, list) or not rows or not isinstance(allow_downgrade, bool) or \
                not all(isinstance(r, dict) and all(isinstance(r.get(k), str) and r[k] for k in keys) for r in rows):
            raise JobError(400, "bad_request", "need confirmations: [{table,column,privacy_role,subtype}], "
                                               "allow_downgrade: bool")
        import pandas as pd
        confirmed = pd.DataFrame([{k: r[k] for k in keys} for r in rows])
        validate(Path(self._read(d, "job.json")["data"]), d / "pipeline" / "detect", confirmed, allow_downgrade)
        attempt = st["attempt"] + 1
        path = d / f"confirm-{attempt}.csv"
        confirmed.to_csv(path, index=False)
        self._write(d, f"confirm-{attempt}.json", {"reviewer_confirmed": True, "allow_downgrade": allow_downgrade,
                                                   "count": len(confirmed), "at": now()})
        for s in ("select", "search", "transform", "evaluate"):
            self._set(d, s, status="queued", summary="", error=None, started_at=None, finished_at=None,
                      duration_s=None)
        self._set(d, "review", status="success", error=None,
                  summary=f"{len(confirmed)} nhãn đã được người duyệt xác nhận")
        self._set(d, state="running", attempt=attempt)
        self._spawn(job_id, d, "select", attempt, str(path))
        return self.state(job_id)

    # ---------------------------------------------------------------- worker
    def _spawn(self, job_id, d, start, attempt, confirm):
        t = threading.Thread(target=self._work, args=(d, start, attempt, confirm), daemon=True, name=f"job-{job_id}")
        self.threads[job_id] = t
        t.start()

    def _namespace(self, d: Path, confirm: str | None) -> SimpleNamespace:
        """Exactly the argparse namespace `python -m server.pipeline` builds for the same options."""
        job, p = self._read(d, "job.json"), self._read(d, "params.json")
        return SimpleNamespace(data=job["data"], scenario=p["scenario"],
                               spec=str(d / "spec.json") if p["spec"] else None, model=str(self.model),
                               model_sha256=self.model_sha256, release_id=p["release_id"],
                               out=str(d / "pipeline"), confirm=confirm,
                               **{k: p[k] for k in pipeline.DEFAULTS})

    def _work(self, d: Path, start: str, attempt: int, confirm: str | None):
        log = _StepLog(d / "logs")
        with RUN_LOCK, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                if start == "detect":
                    self._input(d, log)
                    if self._status(d)["steps"]["input"]["status"] != "success":
                        return

                def on_step(stage, entry):
                    log.step = stage
                    self._on_step(d, stage, entry, attempt)
                pipeline.run(self._namespace(d, confirm), on_step=on_step, detect_fn=self.detect_fn,
                             start=start, attempt=attempt)
            except SystemExit as e:  # pipeline refuses (missing key, existing dir)
                print(f"pipeline refused: {e.code}", file=sys.stderr)
                self._fail_running(d, f"pipeline refused: {e.code}")
            except Exception as e:  # noqa: BLE001 - reported on the job, never swallowed
                print(f"internal error: {type(e).__name__}: {e}", file=sys.stderr)
                self._fail_running(d, f"{type(e).__name__}: {e}")
            finally:
                self._finish(d, attempt)

    def _input(self, d: Path, log: _StepLog):
        log.step = "input"
        self._set(d, "input", status="running")
        data = Path(self._read(d, "job.json")["data"])
        rows, issues = [], []
        csv.field_size_limit(sys.maxsize)
        for f in sorted(data.glob("*.csv")):
            try:
                with f.open(newline="", encoding="utf-8") as fh:
                    r = csv.reader(fh)
                    header = next(r, [])
                    n = sum(1 for _ in r)
                rows.append({"file": f.name, "rows": n, "columns": len(header),
                             "size_mb": round(f.stat().st_size / 2 ** 20, 2),
                             "sha256": hashlib.sha256(f.read_bytes()).hexdigest()[:12]})
            except (UnicodeDecodeError, csv.Error) as e:
                issues.append({"level": "error", "code": "unreadable_csv", "message": f"{f.name}: {e}"})
        if not rows:
            issues.append({"level": "error", "code": "no_input", "message": "no readable CSV file"})
        self._write(d, "input.json", {"tables": rows, "issues": issues})
        ok = rows and not issues
        self._set(d, "input", status="success" if ok else "failed",
                  summary=api_views.summary("input", d, self.ctx(d)),
                  error=None if ok else issues[0]["message"])

    def _on_step(self, d: Path, stage: str, entry: dict, attempt: int):
        if entry.get("status") == "running":
            self._set(d, stage, status="running", error=None)
            if stage == "select" and attempt == 1:
                self._set(d, "review", status="running", summary="đang kiểm tra cột bắt buộc")
            return
        ctx = self.ctx(d)
        if stage == "detect":
            ok = entry.get("status") == "ok"
            self._set(d, "detect", status="success" if ok else "failed", error=entry.get("error"),
                      summary=api_views.summary("detect", d, ctx) if ok else "")
        elif stage == "select":
            plan = ctx["select"] / "decisions.json"
            errors = json.loads(plan.read_text()).get("errors", []) if plan.is_file() else []
            only_review = bool(errors) and all(str(e).startswith("review_required") for e in errors)
            if entry.get("exit") == 0:
                self._set(d, "select", status="success", summary=api_views.summary("select", d, ctx))
                if attempt == 1:
                    n = sum(r["confidence"] is not None for r in api_views.review_items(ctx))
                    self._set(d, "review", status="success",
                              summary=f"{n} cột được cờ, không cột bắt buộc nào cần duyệt" if n
                              else "không có cột cần duyệt")
            else:
                msg = (f"{len(errors)} lỗi: " + str(errors[0])[:300]) if errors else "select từ chối input (xem log)"
                self._set(d, "select", status="failed", error=msg,
                          summary=api_views.summary("select", d, ctx) if plan.is_file() else "blocked")
                if only_review:
                    self._set(d, "review", status="needs_review", summary=api_views.summary("review", d, ctx),
                              error="Cần xác nhận nhãn các cột đang chặn rồi chạy tiếp")
                elif attempt == 1:
                    self._set(d, "review", status="success", summary="không phải lỗi duyệt nhãn")
        elif stage == "search":
            ok = bool(entry.get("approved"))
            self._set(d, "search", status="success" if ok else "failed",
                      summary=api_views.summary("search", d, ctx),
                      error=None if ok else f"search: {entry.get('status')} (chưa đạt mục tiêu, không được duyệt)")
        elif stage == "transform":
            s = entry.get("status")
            if s == "not_run":
                self._set(d, "transform", status="skipped", summary="không chạy", error=entry.get("reason"))
            else:
                status = "success" if s == "validated" else "warning" if s == "unapproved_export" else "failed"
                self._set(d, "transform", status=status, summary=api_views.summary("transform", d, ctx),
                          error=None if status in OK else f"transform: {s}")

    def _fail_running(self, d: Path, msg: str):
        for s, v in self._status(d)["steps"].items():
            if v["status"] == "running":
                self._set(d, s, status="failed", error=msg)

    def _finish(self, d: Path, attempt: int):
        st = self._status(d)
        ctx = self.ctx(d)
        steps = st["steps"]
        no_scorecard = (self._read(d, "params.json") or {}).get("no_scorecard")
        if steps["transform"]["status"] in OK and ctx.get("transform") and \
                (ctx["transform"] / "reports" / "scorecard.json").is_file():
            self._set(d, "evaluate", status="running")
            self._set(d, "evaluate", status="success", summary=api_views.summary("evaluate", d, ctx))
        elif steps["transform"]["status"] in OK and no_scorecard:
            self._set(d, "evaluate", status="skipped", summary="scorecard đã tắt (no_scorecard)")
        steps = self._status(d)["steps"]
        for s in STEPS:  # whatever never ran after a stop is skipped
            if steps[s]["status"] in ("queued", "running"):
                self._set(d, s, status="skipped")
        steps = self._status(d)["steps"]
        if steps["review"]["status"] == "needs_review":
            state = "needs_review"
        elif all(steps[s]["status"] in OK or (s == "evaluate" and no_scorecard and steps[s]["status"] == "skipped")
                 for s in STEPS):
            state = "succeeded"
        else:
            state = "failed"
        self._set(d, state=state, finished_at=now())

    # ---------------------------------------------------------------- read
    def ctx(self, d: Path) -> dict:
        job = self._read(d, "job.json")
        params = self._read(d, "params.json") or {}
        st = self._status(d) or {}
        attempt = max(st.get("attempt") or 1, 1)
        out = d / "pipeline"
        bench = self.benchmark
        ds = job["dataset"]

        def latest(stage):
            for n in range(attempt, 0, -1):
                p = pipeline.stage_dir(out, stage, n)
                if p.exists():
                    return p
            return None
        confirm = d / f"confirm-{attempt}.csv"
        return {"pipeline": out, "select": latest("select"), "search": latest("search"),
                "transform": latest("transform"),
                "select_dirs": [p for n in range(1, attempt + 1) if (p := pipeline.stage_dir(out, "select", n)).exists()],
                "confirm": str(confirm) if confirm.is_file() else None, "dataset": ds,
                "scenario": params.get("scenario"), "benchmark": bench,
                "baseline_tasks": {k: (bench.get(f"{k}_{ds}") or {}).get("utility_tasks", {}) for k in ("B2", "B2K")}}

    def state(self, job_id: str) -> dict:
        d = self.dir(job_id)
        job, st = self._read(d, "job.json"), self._status(d)
        params = self._read(d, "params.json")
        files = sorted(p.name for p in Path(job["data"]).glob("*.csv")) if job["source"] == "upload" else []
        return {"id": job_id, "dataset": job["dataset"], "source": job["source"], "created_at": job["created_at"],
                "uploaded_files": files, "params": params, "state": st["state"], "attempt": st["attempt"],
                "updated_at": st["updated_at"],
                "steps": [{"name": s, **st["steps"][s]} for s in STEPS],
                "download": st["steps"]["transform"]["status"] in OK}

    def step_view(self, job_id: str, step: str) -> dict:
        d = self.dir(job_id)
        if step not in STEPS:
            raise JobError(404, "unknown_step", f"step must be one of {STEPS}")
        ctx = self.ctx(d)
        v = api_views.VIEWS[step](d, ctx)
        s = self._status(d)["steps"][step]
        if s.get("status") == "failed" and s.get("error") and not v["issues"]:
            v["issues"] = [{"level": "error", "code": "failed", "message": s["error"]}]
        return {"step": step, "status": s.get("status"), **v}

    def step_log(self, job_id: str, step: str) -> dict:
        d = self.dir(job_id)
        if step not in STEPS:
            raise JobError(404, "unknown_step", f"step must be one of {STEPS}")
        p = d / "logs" / f"{step}.log"
        text = p.read_text(encoding="utf-8", errors="replace")[-200_000:] if p.is_file() else ""
        return {"step": step, "log": scrub(text)}

    def protected_zip(self, job_id: str) -> tuple[str, bytes]:
        import zipfile
        d = self.dir(job_id)
        ctx = self.ctx(d)
        if self._status(d)["steps"]["transform"]["status"] not in OK or ctx.get("transform") is None:
            raise JobError(409, "no_release", "transform has not produced a release")
        prot = ctx["transform"] / "protected"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:  # protected/ only: never evaluation/ or row maps
            for f in sorted(prot.iterdir()):
                if f.is_file() and not f.name.startswith("rowmap_"):
                    z.write(f, f"protected/{f.name}")
        name = f"{self._read(d, 'job.json')['dataset']}_{job_id}_protected.zip"
        return name, buf.getvalue()
