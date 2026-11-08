"""Final stage: preflight the selected plan, execute it, write a staged release, validate it, then publish.

Result status:
  "validated"          approved measured_ok release published
  "unapproved_export"  --allow-unapproved export of a non-approved plan; checks ran, output marked NOT_APPROVED
  "refused"            preflight failed; only diagnostics are written
  "validation_failed"  exported files stay private under <out>/staging/ with diagnostics
Binding errors (plan or detect artifacts made for other input bytes) raise ArtifactError before any output.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from server.actions import DERIVATIONS, SUPPORTED, execute, resolved_subjects, small_classes
from server.select import artifacts as A
from server.select.select import POLICY_VERSION, render
from server.select.transform import check_plan, release_gate

from . import spans as span_io
from . import validate
from .files import FORMAT_VERSION, read_csv, safe_name, sha256_file, write_csv, write_json
from .report import diagnostics, manifest, summary_md

GATING = ("serialized_round_trip", "row_maps", "actions_applied", "joins", "suppression", "risk", "utility",
          "identifier_scan")
TARGET_CHECKS = ("risk", "utility")
NOT_APPROVED = "NOT_APPROVED.txt"


def read_tables(data: Path) -> dict[str, pd.DataFrame]:
    return {f.stem: read_csv(f) for f in sorted(Path(data).glob("*.csv")) if not f.stem.startswith(("rowmap_", "_"))}


def _refs(plan, table):
    return {f"{table}.{c['column']}" for c in plan["columns"] if c["table"] == table}


def preflight(tables, plan, key, spans=None, text_fallback=False, allow_unapproved=False) -> tuple[list[str], dict]:
    """Every reason this plan must not be exported. `spans` are validated Detect spans per free-text column."""
    errors = []
    if not key:
        errors.append("no HMAC key: set it in the environment")
    if plan.get("policy_version") != POLICY_VERSION:
        errors.append(f"plan policy version {plan.get('policy_version')!r} is not {POLICY_VERSION!r}; regenerate it")
    status = plan.get("status")
    try:
        gate = release_gate(plan, allow_unapproved)
    except ValueError as e:
        gate = None
        hint = {"blocked": "plan is blocked: " + "; ".join(plan.get("errors") or ["see its errors"]),
                "policy_valid": "plan is policy-valid but not measured; run `python -m server.select search` first",
                "target_unmet": "measured selection did not meet its targets (target_unmet); resolve the conflicts "
                                "and reselect, targets are never lowered here",
                "budget_exhausted": "search stopped at its evaluation budget (budget_exhausted); not an approval",
                "measured_ok": "measured_ok but not approved: "
                               + ", ".join((plan.get("outcome") or {}).get("issues") or ["outcome.approved is false"])
                               + " (select with --labels from a detect output dir to bind provenance)"}
        errors.append(hint.get(status, str(e)))
    if plan.get("errors"):
        errors.append(f"plan lists {len(plan['errors'])} unresolved errors")
    if not plan.get("release_id") or not plan.get("release_id_explicit"):
        errors.append("plan needs an explicit recipient-scoped release_id: rerun select with --release-id")
    try:
        check_plan(tables, plan)
    except (ValueError, KeyError) as e:
        errors.append(str(e))
        return errors

    released = {t for t, d in plan["tables"].items() if d["action"] == "RELEASE"}
    cols = {(c["table"], c["column"]): c for c in plan["columns"]}
    for t in sorted(released):
        if not safe_name(t):
            errors.append(f"table name {t!r} is not a safe file name")
        rk = plan["tables"][t].get("record_key")
        if not rk or rk not in tables[t].columns:
            errors.append(f"{t}: needs a source record key for its private row map")
    for c in plan["columns"]:
        if c["table"] in released and (c["action"], c.get("method")) not in SUPPORTED:
            errors.append(f"{c['table']}.{c['column']}: unsupported operation {c['action']}/{c.get('method')}")
    names = {}
    for d in plan.get("derived", []):
        ref = f"{d['table']}.{d['column']}"
        p = d.get("params") or {}
        if d.get("method") not in DERIVATIONS:
            errors.append(f"{ref}: unsupported derivation {d.get('method')}")
        if d["table"] not in released:
            continue
        if any(s not in tables[d["table"]].columns for s in d.get("sources", [])) or len(d.get("sources", [])) != 2:
            errors.append(f"{ref}: derivation sources missing from the source table")
        if d["column"] in tables[d["table"]].columns or ref in names:
            errors.append(f"{ref}: derived column collides with another column")
        names[ref] = True
        for name in ("width", "top"):
            v = p.get(name, 1)
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                errors.append(f"{ref}: {name} must be a positive integer")
    for j in plan.get("joins", []):
        a, b = cols.get(tuple(j["child"].split(".", 1))), cols.get(tuple(j["parent"].split(".", 1)))
        if not a or not b or "DROP" in (a["action"], b["action"]):
            continue
        if {a["action"], b["action"]} & {"HMAC"} and not (
                a["action"] == b["action"] == "HMAC" and a.get("method") == b.get("method") == "hmac_sha256"
                and (a.get("params") or {}).get("domain") == (b.get("params") or {}).get("domain")):
            errors.append(f"{j['child']} -> {j['parent']}: join partners must share one HMAC token domain")
    cap = plan.get("targets", {}).get("max_suppression", .02)
    if not 0 <= cap <= .02:
        errors.append("local suppression allowance must be between 0 and 2%")
    for t, rule in (plan.get("suppression") or {}).items():
        k = rule.get("k")
        if t not in released:
            errors.append(f"suppression selected for unreleased table {t}")
            continue
        if isinstance(k, bool) or not isinstance(k, int) or k < 1:
            errors.append(f"{t}: suppression k must be a positive integer")
        kept = {c for (tt, c), d in cols.items() if tt == t and d["action"] != "DROP"} | \
               {d["column"] for d in plan.get("derived", []) if d["table"] == t}
        if not rule.get("qis") or not set(rule["qis"]) <= kept:
            errors.append(f"{t}: suppression quasi-identifiers are not released columns")
    required = set(plan.get("required") or {})
    sources = {f"{d['table']}.{s}" for d in plan.get("derived", []) for s in d.get("sources", [])}
    for item in plan.get("review_queue") or []:
        ref = item.get("column", "")
        c = cols.get(tuple(ref.split(".", 1)))
        if ref in required or ref in sources or (c and c["action"] != "DROP"):
            errors.append(f"{ref}: unresolved review item on a released or required field; confirm it and reselect")

    spans = spans or {}
    for ref in sorted({f"{c['table']}.{c['column']}" for c in plan["columns"]
                       if c["action"] == "REDACT" and c["table"] in released}):
        if ref not in spans and not text_fallback:
            errors.append(f"{ref}: free text needs Detect spans (--detect <detect output dir> that scanned it) or the "
                          "explicit rule-only redaction fallback (--text-fallback rules)")
    return errors


def _k_flags(frames, tables, plan, ev_dir) -> dict:
    """Rows of an unapproved export whose QI class has fewer than k people: k_flags_<table>.csv (private only,
    a public flag would point an attacker at them) and per-table counts for the UI."""
    k, out = (plan.get("targets") or {}).get("k"), {}
    if not k:
        return out
    for t, df in frames.items():
        qis = [c["column"] for c in plan["columns"] if c["table"] == t and c["privacy_role"] == "quasi_identifier"]
        qis = [c for c in qis + [d["column"] for d in plan.get("derived", []) if d["table"] == t] if c in df]
        small = small_classes(df, qis, resolved_subjects(tables, plan, t), k)
        out[t] = {"rows": len(df), "below_k": int(small.sum()), "qis": qis, "k": k}
        if small.any():
            write_csv(pd.DataFrame({"protected_row": np.flatnonzero(small.values).astype(str)}),
                      ev_dir / f"k_flags_{t}.csv")
    return out


def _stage(out_root, frames, tables, plan, detect, data_dir, gate):
    stage = out_root / "staging"
    for d in ("protected", "evaluation", "reports"):
        (stage / d).mkdir(parents=True)
    for t, df in frames.items():
        write_csv(df, stage / "protected" / f"{t}.csv")
        shutil.copyfile(stage / "protected" / f"{t}.csv", stage / "evaluation" / f"{t}.csv")
        ids = tables[t][plan["tables"][t]["record_key"]].astype(str).values
        write_csv(pd.DataFrame({"protected_row": np.arange(len(df)).astype(str), "original_record_id": ids}),
                  stage / "evaluation" / f"rowmap_{t}.csv")
    if not gate["approved"]:
        write_json(_k_flags(frames, tables, plan, stage / "evaluation"), stage / "evaluation" / "k_flags.json")
        for d in ("protected", "evaluation"):
            (stage / d / NOT_APPROVED).write_text(
                f"NOT AN APPROVED RELEASE: plan status {gate['status']}, exported with --allow-unapproved.\n")
    write_json({"format_version": FORMAT_VERSION, "source_dir": str(Path(data_dir).resolve()),
                "provenance": plan.get("provenance"), "plan_sha256": plan.get("plan_sha256"),
                "tables": {t: {"rows": len(df), "columns": list(df.columns)} for t, df in tables.items()},
                "detect": None if detect is None else {
                    "dir": str(Path(detect["_spans_file"]).parent.resolve()),
                    "dataset_fingerprint": detect.get("dataset_fingerprint"),
                    "spans_sha256": detect["_spans_sha256"],
                    "model_sha256": (detect.get("detector") or {}).get("model_sha256")},
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
               stage / "evaluation" / "input_manifest.json")
    return stage


def run(data_dir, plan: dict, key: bytes, out_dir, detect_dir=None, text_fallback=False, allow_unapproved=False,
        scorecard=True, tasks=None, orig=None, max_adversary=3000, plan_bytes: bytes | None = None) -> dict:
    data_dir, out_root = Path(data_dir), Path(out_dir)
    if out_root.exists():
        raise FileExistsError(f"refusing to write into existing {out_root}")
    src, dst = data_dir.resolve(), out_root.resolve()
    if src == dst or src in dst.parents or dst in src.parents:
        raise ValueError("the output directory must not overlap the source directory")
    tables = read_tables(data_dir)
    if not tables:
        raise ValueError(f"no CSV tables in {data_dir}")
    plan = {**plan, "plan_sha256": A.check_plan(data_dir, plan, plan_bytes or json.dumps(plan).encode())}
    released = {t for t, d in plan["tables"].items() if d["action"] == "RELEASE"}
    redact_refs = {f"{c['table']}.{c['column']}" for c in plan["columns"]
                   if c["action"] == "REDACT" and c["table"] in released}
    detect, spans = None, {}
    if detect_dir is not None:
        detect, by_ref = span_io.load(detect_dir, data_dir, plan)
        spans = span_io.align(detect, by_ref, tables, redact_refs)
    out_root.mkdir(parents=True, exist_ok=False)

    errors = preflight(tables, plan, key, spans, text_fallback, allow_unapproved)
    measured_text = (plan.get("measured") or {}).get("text_redaction")
    used_text = "detect_spans" if spans else "rules_only"
    if redact_refs and measured_text and measured_text != used_text:
        errors.append(f"free text was measured with {measured_text} redaction but would be exported with {used_text}; "
                      "run search and transform with the same --detect dir (or both without it)")
    gate = None
    if not errors:
        gate = release_gate(plan, allow_unapproved)
        try:
            frames, stats = execute(tables, plan, key, spans, text_fallback=text_fallback)
        except (ValueError, KeyError) as e:
            errors.append(f"execution failed: {e}")
    if errors:
        diagnostics(out_root, "refused", errors, plan)
        return {"status": "refused", "errors": errors, "out": str(out_root)}

    stage = _stage(out_root, frames, tables, plan, detect, data_dir, gate)
    check, reloaded = validate.round_trip(tables, plan, frames, stage)
    checks = [check, validate.row_maps(tables, plan, reloaded, stage), validate.actions_applied(plan, reloaded),
              validate.joins(tables, plan, reloaded), validate.suppression(plan, tables, stats)]
    try:
        checks += validate.risk_and_utility(tables, plan, reloaded, key, tasks, orig,
                                            (plan.get("measured") or {}).get("tau", 0.8))
    except Exception as e:  # noqa: BLE001  a metric that cannot be computed is a failed check, not a pass
        checks.append({"name": "risk", "status": "failed", "problems": [f"re-measurement failed: {type(e).__name__}: {e}"],
                       "details": {}})
    scan, scan_report = validate.identifier_scan(plan, stage, reloaded)
    checks.append(scan)
    write_json(scan_report, stage / "reports" / "identifier_check.json")
    write_json({"rows": stats["rows"], "columns": {t: len(c) for t, c in stats["columns"].items()},
                "blanked": stats["blanked"], "suppressed_rows": stats["suppressed_rows"],
                "suppressed_cells": stats["suppressed_cells"], "redaction": stats["redaction"], "release_gate": gate},
               out_root / "transform_stats.json")
    (out_root / "decisions.json").write_text(json.dumps(plan, indent=2, default=str), encoding="utf-8")
    (out_root / "decisions.md").write_text(render(plan), encoding="utf-8")

    gating = [n for n in GATING if gate["approved"] or n not in TARGET_CHECKS]
    failed = [c for c in checks if c["name"] in gating and c["status"] == "failed"]
    if failed:
        scorecard_status = {"status": "not_run", "reason": "validation failed"}
        diagnostics(out_root, "validation_failed", [f"{c['name']} check failed" for c in failed], plan, checks)
        write_json(manifest(plan, out_root, stage, checks, "failed", stats, scorecard_status), out_root / "manifest.json")
        (stage / "reports" / "summary.md").write_text(summary_md(plan, checks, stats, "failed", scorecard_status),
                                                      encoding="utf-8")
        return {"status": "validation_failed", "errors": [p for c in failed for p in c["problems"]],
                "checks": checks, "out": str(out_root)}

    for d in ("protected", "evaluation", "reports"):
        (stage / d).rename(out_root / d)
    stage.rmdir()
    scorecard_status = {"status": "not_run", "reason": "disabled"}
    if scorecard:
        try:
            from pets_eval.scorecard import run_scorecard
            from server.guard import evaluation
            with evaluation():
                rep = run_scorecard(data_dir, out_root / "evaluation", scenario=plan.get("scenario"),
                                    out_dir=out_root / "reports", max_adversary=max_adversary)
            scorecard_status = {"status": "run", "files": ["reports/scorecard.json", "reports/scorecard.html"],
                                "summary": rep.get("summary"),
                                "note": "toolkit assessment for the report only; it never feeds back into selection"}
        except Exception as e:  # noqa: BLE001
            scorecard_status = {"status": "error", "reason": f"{type(e).__name__}: {e}"}
    status = "validated" if gate["approved"] else "unapproved_export"
    (out_root / "reports" / "summary.md").write_text(summary_md(plan, checks, stats, status, scorecard_status),
                                                     encoding="utf-8")
    write_json(manifest(plan, out_root, out_root, checks, status, stats, scorecard_status),
               out_root / "manifest.json")
    return {"status": status, "checks": checks, "out": str(out_root)}
