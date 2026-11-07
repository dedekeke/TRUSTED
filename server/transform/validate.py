"""Validate the serialized release: reload the written files and check them against the source snapshot, the
plan and the measured selection. Every check returns {"name", "status": passed|failed|not_run, "details"}.

Nothing here feeds back into selection: a failed check stops the release, it never changes a rung.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
from pets_eval import check as scanner

from server.actions import blank, normaliser
from server.select.search import _Evaluator, risk_violations

from .files import MISSING_TOKENS, read_csv, sha256_file

HEX32 = re.compile(r"[0-9a-f]{32}")
AGE_BAND = r"\d+-\d+|\d+\+"
FORMAT_RX = {  # allowed non-blank output per method
    "hmac_sha256": r"[0-9a-f]{32}",
    "floor_hour": r"\d{4}-\d{2}-\d{2} \d{2}:00", "date": r"\d{4}-\d{2}-\d{2}", "iso_week": r"\d{4}-W\d{2}",
    "month": r"\d{4}-\d{2}", "year": r"\d{4}",
    "week_hour": r"\d{4}-\d{2}-\d{2} \d{2}:00", "month_hour": r"\d{4}-\d{2}-01 \d{2}:00", "year_hour": r"\d{4}-01-01 \d{2}:00",
    "age_band": AGE_BAND, "derive_age_band": AGE_BAND, "ipv4_prefix": r"(?:\d{1,3}\.){3}0",
    "icd_3char": r"[A-Z]\d{2}", "icd_chapter": r"[A-Z]",
}
TOL = 1e-9


def _result(name, problems, details=None):
    return {"name": name, "status": "failed" if problems else "passed", "problems": problems[:50],
            "details": details or {}}


def _decisions(plan, table):
    return {c["column"]: c for c in plan["columns"] if c["table"] == table}


def round_trip(source, plan, frames, root: Path) -> tuple[dict, dict]:
    """Reload protected/ and evaluation/; compare with the executed frames and the source snapshot."""
    problems, reloaded = [], {}
    released = sorted(t for t, d in plan["tables"].items() if d["action"] == "RELEASE")
    files = {p.name for p in (root / "protected").iterdir()}
    expected = {f"{t}.csv" for t in released}
    if files != expected:
        problems.append(f"protected/ holds {sorted(files - expected)} unexpected, {sorted(expected - files)} missing")
    for t in released:
        p, e = root / "protected" / f"{t}.csv", root / "evaluation" / f"{t}.csv"
        if not p.exists() or not e.exists():
            continue
        df = read_csv(p)
        reloaded[t] = df
        if sha256_file(p) != sha256_file(e):
            problems.append(f"{t}: evaluation copy differs from the protected file")
        mem = frames[t]
        if list(df.columns) != list(mem.columns):
            problems.append(f"{t}: header differs from the executed columns")
        elif df.shape != mem.shape or not (df.values == mem.astype(str).values).all():
            problems.append(f"{t}: reloaded values differ from the executed values")
        if len(df) != len(source[t]):
            problems.append(f"{t}: {len(df)} rows written for {len(source[t])} source rows")
        dec = _decisions(plan, t)
        dropped = [c for c, d in dec.items() if d["action"] == "DROP" and c in df.columns]
        if dropped:
            problems.append(f"{t}: dropped columns present: {dropped}")
        derived = [d["column"] for d in plan.get("derived", []) if d["table"] == t]
        expected_cols = [c for c in source[t].columns if dec.get(c, {}).get("action") != "DROP"] + derived
        if list(df.columns) != expected_cols:
            problems.append(f"{t}: columns are not the retained source columns in order followed by derived ones")
        for c in df.columns:
            d = dec.get(c)
            tokens = df[c].isin(MISSING_TOKENS)
            if d is not None and d["action"] == "KEEP":
                tokens &= source[t][c].astype(str).reset_index(drop=True).ne(df[c])
            if tokens.any():
                problems.append(f"{t}.{c}: {int(tokens.sum())} cells hold a missing-value token instead of a blank")
    withheld = [t for t, d in plan["tables"].items() if d["action"] != "RELEASE" and (root / "protected" / f"{t}.csv").exists()]
    if withheld:
        problems.append(f"withheld tables written: {withheld}")
    return _result("serialized_round_trip", problems, {"tables": len(reloaded)}), reloaded


def row_maps(source, plan, reloaded, root: Path) -> dict:
    problems = []
    for t, df in reloaded.items():
        path = root / "evaluation" / f"rowmap_{t}.csv"
        if not path.exists():
            problems.append(f"{t}: row map missing")
            continue
        rm = read_csv(path)
        if list(rm.columns) != ["protected_row", "original_record_id"]:
            problems.append(f"{t}: row map header must be protected_row,original_record_id")
            continue
        if rm["protected_row"].tolist() != [str(i) for i in range(len(df))]:
            problems.append(f"{t}: protected_row is not 0..n-1 in protected order")
        rk = plan["tables"][t]["record_key"]
        if rm["original_record_id"].tolist() != source[t][rk].astype(str).tolist():
            problems.append(f"{t}: row map ids are not aligned with the source record key")
    for p in (root / "protected").glob("rowmap_*"):
        problems.append(f"row map {p.name} inside protected/")
    for t, d in plan["tables"].items():
        if d["action"] != "RELEASE" and (root / "evaluation" / f"rowmap_{t}.csv").exists():
            problems.append(f"row map written for withheld table {t}")
    return _result("row_maps", problems)


def actions_applied(plan, reloaded) -> dict:
    """Every written column has the shape its selected action produces; no raw value passes a generaliser."""
    problems = []
    for t, df in reloaded.items():
        items = [c for c in plan["columns"] if c["table"] == t and c["action"] not in ("DROP", "KEEP")]
        items += [{**d, "action": "DERIVE"} for d in plan.get("derived", []) if d["table"] == t]
        for c in items:
            col = df.get(c["column"])
            if col is None:
                problems.append(f"{t}.{c['column']}: selected {c['action']} column missing")
                continue
            rx = FORMAT_RX.get(c.get("method"))
            values = col[~blank(col)]
            if rx is not None:
                bad = ~values.str.fullmatch(rx)
                if bad.any():
                    problems.append(f"{t}.{c['column']}: {int(bad.sum())} values do not match {c['method']} output")
            if c.get("method") == "week_hour" and len(values):
                monday = pd.to_datetime(values, errors="coerce").dt.day_of_week.eq(0)
                if not monday.all():
                    problems.append(f"{t}.{c['column']}: week_hour anchor is not a Monday")
            if c.get("method") == "postcode_prefix":
                bad = ~values.str.fullmatch(rf"\d{{{c['params']['digits']}}}")
                if bad.any():
                    problems.append(f"{t}.{c['column']}: {int(bad.sum())} postcodes longer than the selected prefix")
    return _result("actions_applied", problems)


def joins(source, plan, reloaded) -> dict:
    """Shared HMAC domains keep join matches, and original orphans stay orphans."""
    problems, checked = [], 0
    cols = {(c["table"], c["column"]): c for c in plan["columns"]}
    for j in plan.get("joins", []):
        (ct, cc), (pt, pc) = j["child"].split(".", 1), j["parent"].split(".", 1)
        a, b = cols.get((ct, cc)), cols.get((pt, pc))
        if not a or not b or ct not in reloaded or pt not in reloaded or "DROP" in (a["action"], b["action"]):
            continue
        if a["action"] != "HMAC" or b["action"] != "HMAC":
            continue
        checked += 1
        na, nb = normaliser(a.get("subtype", "")), normaliser(b.get("subtype", ""))
        child = source[ct][cc].astype(str)
        parents = set(source[pt][pc].astype(str)[~blank(source[pt][pc])].map(nb))
        orig_match = child.map(na).isin(parents) & ~blank(source[ct][cc])
        tokens = set(reloaded[pt][pc][~blank(reloaded[pt][pc])])
        prot_match = reloaded[ct][cc].isin(tokens) & ~blank(reloaded[ct][cc])
        if orig_match.reset_index(drop=True).tolist() != prot_match.tolist():
            problems.append(f"{j['child']} -> {j['parent']}: {int((orig_match.values != prot_match.values).sum())} "
                            "rows changed join/orphan status")
    return _result("joins", problems, {"joins_checked": checked})


def suppression(plan, source, stats) -> dict:
    problems = []
    rules = plan.get("suppression") or {}
    cap = plan.get("targets", {}).get("max_suppression", .02)
    total_rows = sum(len(source[t]) for t, d in plan["tables"].items() if d["action"] == "RELEASE")
    executed = stats.get("suppressed_rows", {})
    for t, rule in rules.items():
        n = executed.get(t, 0)
        if len(source[t]) and n / len(source[t]) > cap + TOL:
            problems.append(f"{t}: {n} suppressed rows exceed the {cap:.0%} allowance")
    overall = sum(executed.values()) / max(1, total_rows)
    if overall > cap + TOL:
        problems.append(f"overall suppression {overall:.2%} exceeds the {cap:.0%} allowance")
    chosen = (plan.get("measured") or {}).get("chosen_evaluation")
    entry = next((e for e in plan.get("search_trace", []) if e.get("evaluation") == chosen), None)
    if rules:
        if entry is None:
            problems.append("selected suppression has no measured search candidate to compare with")
        elif abs(entry.get("suppressed_fraction", 0.) - overall) > TOL:
            problems.append(f"executed suppression {overall:.6f} differs from the measured {entry['suppressed_fraction']:.6f}")
    return _result("suppression", problems, {"rows": executed, "overall_fraction": overall, "allowance": cap})


def _close(a, b):
    if a is None or b is None:
        return a is b
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=TOL)


def risk_and_utility(source, plan, reloaded, key, tasks, orig, tau) -> list[dict]:
    """Re-measure owner-data k/l/t, uniqueness and required utility on the serialized tables."""
    ev = _Evaluator(source, plan, key, tasks, orig if orig is not None else source)
    prot = {t: df.set_axis(source[t].index) for t, df in reloaded.items()}
    risk = ev.risk(prot, measure_t=True)
    targets = plan["targets"]
    problems = risk_violations(risk, targets)
    measured = (plan.get("measured") or {}).get("risk", {})
    for t, r in risk.items():
        m = measured.get(t)
        if m is None:
            problems.append(f"{t}: no measured risk in the plan to compare with")
            continue
        pairs = [("share_below_k", r["share_below_k"], m.get("share_below_k")),
                 ("min_k", r["k_anonymity"].get("min_k"), m.get("k_anonymity", {}).get("min_k")),
                 ("sample_uniqueness", r["sample_uniqueness"], m.get("sample_uniqueness"))]
        for s, v in r["sensitive"].items():
            ms = m.get("sensitive", {}).get(s, {})
            pairs.append((f"{s} l", v["l_diversity"].get("min_distinct_l"), ms.get("l_diversity", {}).get("min_distinct_l")))
            if v["t_closeness"].get("evaluated", True) and "max_t" in v["t_closeness"]:
                pairs.append((f"{s} t", v["t_closeness"].get("max_t"), ms.get("t_closeness", {}).get("max_t")))
        for name, now, then in pairs:
            if not _close(now, then):
                problems.append(f"{t}: serialized {name}={now} differs from the measured {then}")
    summary = {t: {"min_k": r["k_anonymity"].get("min_k"), "share_below_k": r["share_below_k"],
                   "sample_uniqueness": r["sample_uniqueness"], "unknown_subject_rows": r["unknown_subject_rows"],
                   "l": {s: v["l_diversity"].get("min_distinct_l") for s, v in r["sensitive"].items()},
                   "t": {s: v["t_closeness"].get("max_t") for s, v in r["sensitive"].items()}}
               for t, r in risk.items()}
    out = [_result("risk", problems, {"targets": targets, "measured": summary})]

    base = (plan.get("measured") or {}).get("baseline_utility") or {}
    if not base:
        out.append({"name": "utility", "status": "not_run", "problems": [],
                    "details": {"reason": "the plan declares no required utility task"}})
        return out
    if not tasks:
        out.append(_result("utility", ["required utility tasks could not be loaded for re-measurement"]))
        return out
    scores = ev.utility(prot)
    problems = []
    chosen = (plan.get("measured") or {}).get("utility", {})
    for task, b in base.items():
        s = scores.get(task)
        if b is None or s is None or s < tau * b:
            problems.append(f"{task}: unanswerable or below tau={tau} of its baseline")
        elif not _close(s, chosen.get(task)):
            problems.append(f"{task}: serialized score {s} differs from the measured {chosen.get(task)}")
    out.append(_result("utility", problems, {"scores": scores, "baseline": base, "tau": tau}))
    return out


def identifier_scan(plan, root: Path, reloaded) -> tuple[dict, dict]:
    """pets-eval check on all lines of protected/ only; attribute every hit to a cell and classify it.

    The only accepted false positive: a pattern match inside a validated 32-hex token of an HMAC column.
    Anything else, including scanner totals not explained cell by cell, fails the check."""
    raw = scanner.scan_path(root / "protected", max_lines=None)
    hmac_cols = {(c["table"], c["column"]) for c in plan["columns"]
                 if c["action"] == "HMAC" and c.get("method") == "hmac_sha256"}
    classified, unexplained = defaultdict(int), defaultdict(int)
    by_column = defaultdict(lambda: defaultdict(int))
    for t, df in reloaded.items():
        header = scanner.scan_text(",".join(df.columns))
        for label, n in header.items():
            unexplained[label] += n
            by_column[f"{t} (header)"][label] += n
        for c in df.columns:
            for v in df[c][~blank(df[c])].tolist():
                hits = scanner.scan_text(v)
                for label, n in hits.items():
                    if (t, c) in hmac_cols and HEX32.fullmatch(v):
                        classified[label] += n
                    else:
                        unexplained[label] += n
                        by_column[f"{t}.{c}"][label] += n
    for label, n in raw["totals"].items():
        gap = n - classified[label] - unexplained[label]
        if gap > 0:
            unexplained[label] += gap
            by_column["(scan lines not attributable to one cell)"][label] += gap
    report = {
        "scanner": "pets_eval.check.scan_path", "scope": "all lines of protected/*.csv",
        "files_scanned": raw["n_files_scanned"], "raw_totals": dict(raw["totals"]),
        "classified_false_positives": {label: {"count": n, "reason": "pattern inside a validated 32-hex HMAC token "
                                                                     "of an HMAC column"} for label, n in classified.items()},
        "unexplained": dict(unexplained), "unexplained_by_column": {k: dict(v) for k, v in by_column.items()},
        "note": "Counts only; no matched values are recorded. The scanner exits successfully even with hits, "
                "so these totals are the evidence.",
    }
    problems = [f"{label}: {n} unexplained scanner hits" for label, n in unexplained.items() if n]
    return _result("identifier_scan", problems, {"raw_totals": dict(raw["totals"]),
                                                 "classified_false_positives": dict(classified)}), report
