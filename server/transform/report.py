"""Manifest, stats, readable summary and refusal diagnostics. Counts and metadata only: no source values,
keys, tokens, row maps or source digests in any of these files."""
from __future__ import annotations

from pathlib import Path

from server.actions import HOUR_ANCHORS, TIME_FORMATS

from .files import FORMAT_VERSION, md_escape, sha256_file, write_json

SEMANTICS = {
    "hmac_sha256": "keyed pseudonym: HMAC-SHA-256, 32 hex characters, scoped to the release and token domain",
    "ipv4_prefix": "IPv4 address generalised to its /24 network (a.b.c.0)",
    "redact_spans": "free text with identifiers replaced by typed placeholders such as [PERSON]",
    "age_band": "age banded by the selected width with an open top band",
    "derive_age_band": "age at the row's original event date, banded; the birth date is not released",
    "postcode_prefix": "first digits of a valid 5-digit postcode; other values blank",
    "suppress_rare": "values seen fewer than min_count times blanked",
    "merge_rare": "values seen fewer than min_count times replaced by 'other'",
    "round_decimals": "rounded to the selected number of decimals",
    "round_numeric": "rounded to the nearest multiple of the selected step",
    "top_bottom_code": "clamped to the selected quantiles",
    "icd_3char": "ICD-10 category (3 characters)",
    "icd_chapter": "ICD-10 chapter letter",
    "diagnosis_group": "diagnosis group from pets_eval.utility.health.diagnosis_group; unmapped codes blank",
    **{m: f"time floored (never rounded), format {f}" for m, f in TIME_FORMATS.items()},
    **{m: f"{d}: only the hour of day and the period are kept; the date shown is an anchor, "
          "not the original event date" for m, d in HOUR_ANCHORS.items()},
}


def describe(c: dict) -> str:
    if c["action"] in ("KEEP", "DROP"):
        return {"KEEP": "released unchanged", "DROP": "not released"}[c["action"]]
    return SEMANTICS.get(c.get("method"), f"{c['action']}/{c.get('method')}")


def manifest(plan, out_root: Path, data_root: Path, checks, validation_status, stats, scorecard_status) -> dict:
    tables = {}
    for t, td in sorted(plan["tables"].items()):
        if td["action"] != "RELEASE":
            continue
        path = data_root / "protected" / f"{t}.csv"
        cols = [{"name": c["column"], "action": c["action"], "method": c.get("method"),
                 "params": c.get("params") or {}, "semantics": describe(c)}
                for c in plan["columns"] if c["table"] == t and c["action"] != "DROP"]
        cols += [{"name": d["column"], "action": "DERIVE", "method": d["method"], "params": d.get("params") or {},
                  "sources_not_released": list(d["sources"]), "semantics": describe({**d, "action": "DERIVE"})}
                 for d in plan.get("derived", []) if d["table"] == t]
        tables[t] = {"file": f"{path.relative_to(out_root)}", "rows": stats["rows"].get(t),
                     "columns": cols, "dropped": [c["column"] for c in plan["columns"]
                                                  if c["table"] == t and c["action"] == "DROP"],
                     "sha256": sha256_file(path) if path.exists() else None,
                     "suppression": (plan.get("suppression") or {}).get(t)}
    return {
        "format_version": FORMAT_VERSION, "policy_version": plan.get("policy_version"),
        "release_id": plan.get("release_id"), "scenario": plan.get("scenario"), "dataset": plan.get("dataset"),
        "trust_level": plan.get("trust_level"), "targets": plan.get("targets"),
        "selection_status": plan.get("status"), "validation_status": validation_status,
        "approved_release": validation_status == "validated",
        "recipient_files": "protected/ only; evaluation/ is owner-private and must never be distributed with it",
        "tables": tables,
        "withheld_tables": sorted(t for t, d in plan["tables"].items() if d["action"] != "RELEASE"),
        "checks": [{"name": c["name"], "status": c["status"], "problems": len(c.get("problems", []))} for c in checks],
        "scorecard": scorecard_status,
    }


def summary_md(plan, checks, stats, validation_status, scorecard_status) -> str:
    e = md_escape
    m = plan.get("measured") or {}
    lines = [f"# Release summary: {e(plan.get('release_id'))}", "",
             f"Validation status: **{validation_status}**. Selection status: {e(plan.get('status'))}. "
             f"Trust level: {e(plan.get('trust_level'))}. Targets: {e(plan.get('targets'))}.", "",
             "Only `protected/` is meant for the recipient. `evaluation/` holds owner-private scoring copies and "
             "row maps. Review this report before sharing it; a successful run is not by itself a privacy guarantee.",
             "", "## Checks", "", "| Check | Status | Problems |", "|---|---|---|"]
    for c in checks:
        lines.append(f"| {e(c['name'])} | {e(c['status'])} | {e('; '.join(c.get('problems', [])[:3])) or '-'} |")
    lines.append(f"| scorecard (report only) | {e(scorecard_status.get('status'))} | "
                 f"{e(scorecard_status.get('reason', '-'))} |")
    lines += ["", "## Chosen actions", "", "| Table | Column | Action | Method | Params |", "|---|---|---|---|---|"]
    for c in plan["columns"]:
        if plan["tables"].get(c["table"], {}).get("action") == "RELEASE":
            lines.append(f"| {e(c['table'])} | {e(c['column'])} | {c['action']} | {e(c.get('method') or '-')} | "
                         f"{e(c.get('params') or '-')} |")
    for d in plan.get("derived", []):
        lines.append(f"| {e(d['table'])} | {e(d['column'])} | DERIVE | {e(d['method'])} | {e(d.get('params'))} |")
    withheld = sorted(t for t, d in plan["tables"].items() if d["action"] != "RELEASE")
    if withheld:
        lines += ["", f"Withheld tables: {', '.join(e(t) for t in withheld)}."]
    risk = next((c for c in checks if c["name"] == "risk"), None)
    if risk and risk.get("details", {}).get("measured"):
        lines += ["", "## Risk on the written tables", "",
                  "| Table | min k | share below k | uniqueness | unresolved subjects | l | t |", "|---|---|---|---|---|---|---|"]
        for t, r in risk["details"]["measured"].items():
            lines.append(f"| {e(t)} | {r['min_k']} | {r['share_below_k']:.4f} | {r['sample_uniqueness']:.4f} | "
                         f"{r['unknown_subject_rows']} | {e(r['l']) if r['l'] else '-'} | {e(r['t']) if r['t'] else '-'} |")
    util = next((c for c in checks if c["name"] == "utility"), None)
    if util and util["status"] != "not_run":
        lines += ["", "## Utility versus baseline", "", "| Task | Score | Baseline | Floor |", "|---|---|---|---|"]
        for task, b in util["details"].get("baseline", {}).items():
            s = util["details"].get("scores", {}).get(task)
            tau = util["details"].get("tau", m.get("tau", 0.8))
            cells = ["-" if v is None else f"{v:.4f}" for v in (s, b, None if b is None else tau * b)]
            lines.append(f"| {e(task)} | {' | '.join(cells)} |")
    elif util:
        lines += ["", f"Utility: not run ({e(util['details'].get('reason'))})."]
    lines += ["", "## Parse losses and suppression", ""]
    if stats.get("blanked"):
        lines += [f"- {e(ref)}: {n} non-blank values became blank (unparseable or unmapped)"
                  for ref, n in sorted(stats["blanked"].items())]
    else:
        lines.append("- no values were blanked by parsing or mapping")
    for t, n in sorted(stats.get("suppressed_rows", {}).items()):
        lines.append(f"- {e(t)}: local suppression blanked quasi-identifiers on {n} rows (rows kept)")
    for ref, how in sorted(stats.get("redaction", {}).items()):
        lines.append(f"- {e(ref)}: free text redacted with {how.replace('_', ' ')}")
    review = plan.get("review_queue") or []
    lines += ["", "## Remaining review items", ""]
    lines += [f"- {e(r['column'])} (not released, informational)" for r in review] or ["- none"]
    return "\n".join(lines) + "\n"


def diagnostics(out_root: Path, status: str, errors: list, plan: dict | None, checks: list | None = None) -> None:
    """Refusal or failed-validation report. Written instead of an approved release."""
    plan = plan or {}
    conflict = plan.get("conflict") or {}
    body = {"format_version": FORMAT_VERSION, "status": status, "approved_release": False,
            "release_id": plan.get("release_id"), "selection_status": plan.get("status"),
            "errors": errors, "conflict": {k: conflict.get(k) for k in ("reason", "violations", "unknown_subjects",
                                                                        "unanswerable_tasks") if k in conflict},
            "checks": checks or []}
    write_json(body, out_root / "diagnostics.json")
    lines = [f"# Transform {status}", "", "No approved release was produced.", "", "## Errors", ""]
    lines += [f"- {md_escape(x)}" for x in errors] or ["- none"]
    if conflict.get("violations"):
        lines += ["", "## Unmet selection targets", ""] + [f"- {md_escape(v)}" for v in conflict["violations"]]
    for c in checks or []:
        if c["status"] == "failed":
            lines += ["", f"## Failed check: {c['name']}", ""] + [f"- {md_escape(p)}" for p in c["problems"]]
    (out_root / "diagnostics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
