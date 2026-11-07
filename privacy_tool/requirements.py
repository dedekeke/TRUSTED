"""Requirement resolver: what a release must keep for its declared purpose.

Three sources, one output shape (see README "Module contracts"):
- from_scenario: shipped scenario + toolkit utility tasks, parsed from `needs` and confirmed by probing.
- from_spec: a small JSON spec for datasets without toolkit tasks.
- no_purpose: nothing declared; utility is not assessed.

`needs` notation (informal, as written in pets_eval.utility):
  "a|b" or "a or b"  alternatives, at least one needed      -> any_of
  "a+b", "a,b", "a/b" all needed (also inside an alternative: "a|b+c")
  "t.c", "t.a/b/c"    table-qualified (prefix applies to every column in a "/" list)
  "c (time of day)"   precision hint -> precision[c] = "hour"
Unqualified names resolve to the task's table, else to a table the needs name, else (not for alternatives) to the
only table that has them. A name found in several candidate tables is left to probing with a warning.
Tokens that are not columns of the resolved table (e.g. "vitals", "record keys") are ignored with a warning.
any_of is a list of groups; a group is a list of alternatives; an alternative is a list of refs that are all needed:
  [[["t.los"], ["t.arrival", "t.discharge"]]]

Probing drops one column at a time. A column is required when the task becomes not answerable or its score drops by
more than `tolerance` (default 0.05). Plan section 5 says "if its score drops"; the tolerance deviates on purpose so
that incidental dependencies (HEALTH-S1: dropping the duplicate-filter column `disposition` moves H-U2 to 0.998)
do not count as purpose-bound. Blind spot: two columns that can stand in for each other but are not written as
`a|b` each look unnecessary, because each drop alone is compensated by the other; only parsing catches those.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pets_eval.io import get_scenario
from pets_eval.utility import all_tasks

TRUST_LEVELS = ("internal", "contractual", "controlled_research", "public")
PRECISIONS = ("minute", "hour", "date", "week", "month", "year")  # finest first
NO_PURPOSE_WARNING = "no declared purpose: utility not assessed; only non-sensitive fields may be kept"
_HINTS = {"time of day": "hour", "hour": "hour", "minute": "minute", "date": "date", "day": "date",
          "week": "week", "month": "month", "year": "year"}
_REF = re.compile(r"^[A-Za-z_][\w-]*\.[A-Za-z_][\w-]*$")
_TARGET = re.compile(r"\b([kl])\s*(?:>=|≥)\s*(\d+)")


def _empty(source, trust_level, dataset=None, scenario=None):
    if trust_level not in TRUST_LEVELS:
        raise ValueError(f"unknown trust_level {trust_level!r}; expected one of {', '.join(TRUST_LEVELS)}")
    return {"source": source, "scenario": scenario, "dataset": dataset, "trust_level": trust_level, "targets": {},
            "targets_text": None, "tasks": [], "required": {}, "any_of": [], "precision": {}, "joins": [],
            "subject_key": None, "warnings": []}


def no_purpose(trust_level="internal", dataset=None):
    req = _empty("none", trust_level, dataset)
    req["warnings"].append(NO_PURPOSE_WARNING)
    return req


def parse_targets(text):
    """{'k': 5} from free text such as 'k>=5 on (...)' or 'k ≥ 5'; first occurrence of each letter wins."""
    out = {}
    for letter, n in _TARGET.findall(text or ""):
        out.setdefault(letter, int(n))
    return out


# ------------------------------------------------------------------ needs parsing
def _task_tables(task, tables):
    if task.table == "*":
        return list(tables)
    return [t for t in task.table.split("+") if t]


def _resolve(name, prefix, home, named, tables, warnings, need, global_fallback=True):
    """'table.column' for a column token, or None (with a warning) when it is not a column or is ambiguous."""
    name = name.strip()
    if not name:
        return None
    if prefix is not None:
        if prefix in tables and name in tables[prefix].columns:
            return f"{prefix}.{name}"
        if name == "*" and prefix in tables:
            warnings.append(f"{need!r}: '{prefix}.*' is too broad to resolve; left to probing")
            return None
        warnings.append(f"{need!r}: '{prefix}.{name}' is not a column; ignored")
        return None
    hits = [t for t in home if t in tables and name in tables[t].columns]
    if not hits:  # e.g. H-U7 lives on lab_results but needs ed_visits.temp_c: try the other tables the task names
        hits = [t for t in named if t in tables and name in tables[t].columns]
    if not hits and global_fallback:  # e.g. ENERGY-U1 reads customers.postcode without naming the table
        others = [t for t in tables if name in tables[t].columns]
        if len(others) == 1:
            warnings.append(f"{need!r}: '{name}' found only in {others[0]}; resolved there")
            return f"{others[0]}.{name}"
    if len(hits) == 1:
        return f"{hits[0]}.{name}"
    if len(hits) > 1:
        warnings.append(f"{need!r}: '{name}' is ambiguous across {hits}; left to probing")
        return None
    warnings.append(f"{need!r}: '{name}' is not a column of {home + named}; informal token ignored")
    return None


def parse_needs(task, tables):
    """Parsed requirement of one task: {'required', 'any_of', 'precision', 'tables', 'warnings'}."""
    home = _task_tables(task, tables)
    required, any_of, precision, warnings, touched = [], [], {}, [], set(home)
    named = sorted({m for need in task.needs for m in re.findall(r"([A-Za-z_]\w*)\.", need)} - set(home))
    for need in task.needs:
        m = re.search(r"\(([^)]*)\)", need)
        hint = m.group(1).strip().lower() if m else None
        need_body = re.sub(r"\([^)]*\)", "", need).strip()
        alternatives, alts = [], re.split(r"\||\s+or\s+", need_body)
        for alt in alts:
            refs = []
            for part in re.split(r"[+,]", alt):
                prefix, part = None, part.strip()
                if "." in part.split("/", 1)[0]:  # "t.a/b/c": the prefix applies to every name in the list
                    prefix, part = part.split(".", 1)
                    touched.add(prefix)
                for name in part.split("/"):
                    ref = _resolve(name, prefix, home, named, tables, warnings, need, global_fallback=len(alts) == 1)
                    if ref and ref not in refs:
                        refs.append(ref)
                        touched.add(ref.split(".")[0])
            if refs:
                alternatives.append(refs)
        if hint is not None:
            if hint in _HINTS and len(alternatives) == 1 and len(alternatives[0]) == 1:
                precision[alternatives[0][0]] = _HINTS[hint]
            else:
                warnings.append(f"{need!r}: hint '({hint})' is not a precision; ignored")
        if len(alternatives) == 1:
            required += [r for r in alternatives[0] if r not in required]
        elif len(alternatives) > 1:
            any_of.append(alternatives)
    return {"required": required, "any_of": any_of, "precision": precision,
            "tables": sorted(t for t in touched if t in tables), "warnings": warnings}


# ------------------------------------------------------------------ probing
def probe_task(task, tables, touched, tolerance=0.05):
    """Drop one column at a time from the touched tables and rerun the task on (original, reduced).

    Returns {'baseline', 'required': [refs], 'affected': {ref: score}, 'warnings'}. A column is required when
    the task becomes not answerable (score None) or its score drops by more than `tolerance`.
    """
    out = {"baseline": None, "required": [], "affected": {}, "warnings": []}
    try:
        base = task.fn(tables, tables)["score"]
    except Exception as e:  # task code is outside our control; report and skip probing
        out["warnings"].append(f"{task.id}: baseline run failed ({type(e).__name__}: {e}); not probed")
        return out
    if base is None:
        out["warnings"].append(f"{task.id}: not answerable on the original tables; not probed")
        return out
    out["baseline"] = round(base, 4)
    for t in touched:
        for col in tables[t].columns:
            ref = f"{t}.{col}"
            reduced = {**tables, t: tables[t].drop(columns=[col])}
            try:
                score = task.fn(tables, reduced)["score"]
            except Exception as e:
                out["warnings"].append(f"{task.id}: run without {ref} failed ({type(e).__name__}: {e}); treated as required")
                score = None
            if score is None or abs(base - score) > 1e-9:
                out["affected"][ref] = None if score is None else round(score, 4)
            if score is None or base - score > tolerance:
                out["required"].append(ref)
    return out


def _joins(refs):
    """Same column name required in two tables -> those columns must stay joinable (consistent transform).

    Not filtered by uniqueness: a shared timestamp (CYBER-U5 email_gateway/proxy_logs ts_utc) also needs one
    consistent transform; relations.py decides whether a join is a key join.
    """
    by_col = {}
    for r in refs:
        by_col.setdefault(r.split(".", 1)[1], []).append(r)
    return [sorted(v) for v in by_col.values() if len({x.split(".")[0] for x in v}) > 1]


def _add_join(req, columns, task_id, kind):
    """kind 'same_name' (heuristic: select must confirm it with relations.discover) or 'declared' (spec)."""
    for j in req["joins"]:
        if j["columns"] == columns and j["kind"] == kind:
            if task_id not in j["tasks"]:
                j["tasks"].append(task_id)
            return
    req["joins"].append({"columns": columns, "tasks": [task_id], "kind": kind})


def _merge_precision(req, ref, level):
    old = req["precision"].get(ref)
    if old is None or PRECISIONS.index(level) < PRECISIONS.index(old):
        req["precision"][ref] = level


def from_scenario(scenario_id, tables, root, probe=True, tolerance=0.05):
    scenario = get_scenario(scenario_id, root)
    if scenario is None:
        raise ValueError(f"unknown scenario {scenario_id!r}")
    req = _empty("scenario", scenario["trust_level"], scenario["dataset"], scenario_id)
    req["targets_text"] = scenario.get("suggested_privacy_targets")
    req["targets"] = parse_targets(req["targets_text"])
    wanted = scenario.get("utility_requirements", [])
    tasks = [t for t in all_tasks([scenario["dataset"]]) if t.id in wanted]
    missing = set(wanted) - {t.id for t in tasks}
    if missing:
        req["warnings"].append(f"tasks not found in the toolkit: {sorted(missing)}")
    for task in tasks:
        parsed = parse_needs(task, tables)
        req["warnings"] += parsed["warnings"]
        alternatives = {r for g in parsed["any_of"] for alt in g for r in alt}
        evidence = {"declared": False, "parsed": {k: parsed[k] for k in ("required", "any_of", "precision")},
                    "probed": None}
        columns = list(parsed["required"])
        if probe:
            p = probe_task(task, tables, parsed["tables"], tolerance)
            req["warnings"] += p["warnings"]
            evidence["probed"] = {k: p[k] for k in ("baseline", "required", "affected")}
            for r in p["required"]:
                if r in columns:
                    continue
                if r not in alternatives:
                    columns.append(r)
                elif p["affected"].get(r, 0) is None:  # the other alternatives cannot stand in for it
                    columns.append(r)
                    req["warnings"].append(f"{task.id}: {r} is listed as an alternative, but the task is not "
                                           "answerable without it; marked required")
            if p["baseline"] is not None:
                req["warnings"] += [f"{task.id}: {r} is in the needs but dropping it has no measurable effect; "
                                    "kept as parsed" for r in parsed["required"] if r not in p["affected"]]
        req["tasks"].append({"id": task.id, "table": task.table, "columns": columns, "any_of": parsed["any_of"],
                             "precision": parsed["precision"], "evidence": evidence})
        for ref in columns:
            req["required"].setdefault(ref, []).append(task.id)
        for g in parsed["any_of"]:
            if g not in req["any_of"]:
                req["any_of"].append(g)
        for ref, level in parsed["precision"].items():
            _merge_precision(req, ref, level)
        for cols in _joins(columns):
            _add_join(req, cols, task.id, "same_name")
    return req


# ------------------------------------------------------------------ spec files
_SPEC_KEYS = {"dataset", "trust_level", "targets", "required", "any_of", "joins", "subject_key"}
_ITEM_KEYS = {"column", "precision", "task"}
_TARGET_KEYS = {"k", "l", "t", "max_suppression"}


def _ref(value, where):
    if not isinstance(value, str) or not _REF.match(value):
        raise ValueError(f"{where}: {value!r} is not a 'table.column' reference")
    return value


def from_spec(path):
    """Load and strictly validate a JSON requirement spec (see examples/health_s1_spec.json)."""
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: not valid JSON ({e})") from e
    if not isinstance(spec, dict):
        raise ValueError(f"{path}: spec must be a JSON object")
    unknown = set(spec) - _SPEC_KEYS
    if unknown:
        raise ValueError(f"{path}: unknown keys {sorted(unknown)}; allowed: {sorted(_SPEC_KEYS)}")
    for k in ("dataset", "trust_level", "required"):
        if k not in spec:
            raise ValueError(f"{path}: missing required key {k!r}")
    if not isinstance(spec["dataset"], str) or not spec["dataset"]:
        raise ValueError(f"{path}: 'dataset' must be a non-empty string")
    req = _empty("spec", spec["trust_level"], spec["dataset"])
    targets = spec.get("targets", {})
    if not isinstance(targets, dict):
        raise ValueError(f"{path}: 'targets' must be an object")
    bad = set(targets) - _TARGET_KEYS
    if bad:
        raise ValueError(f"{path}: unknown targets keys {sorted(bad)}; allowed: {sorted(_TARGET_KEYS)}")
    for k in ("k", "l"):
        if k in targets and (not isinstance(targets[k], int) or isinstance(targets[k], bool) or targets[k] < 1):
            raise ValueError(f"{path}: targets.{k} must be a positive integer")
    for k in ("t", "max_suppression"):
        v = targets.get(k, 0)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
            raise ValueError(f"{path}: targets.{k} must be a number between 0 and 1")
    req["targets"] = dict(targets)
    if not isinstance(spec["required"], list):
        raise ValueError(f"{path}: 'required' must be a list")
    tasks = {}
    for i, item in enumerate(spec["required"]):
        where = f"{path}: required[{i}]"
        if not isinstance(item, dict):
            raise ValueError(f"{where}: must be an object with 'column'")
        bad = set(item) - _ITEM_KEYS
        if bad:
            raise ValueError(f"{where}: unknown keys {sorted(bad)}; allowed: {sorted(_ITEM_KEYS)}")
        ref = _ref(item.get("column"), f"{where}.column")
        task_id = item.get("task", "spec")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError(f"{where}.task must be a non-empty string")
        task = tasks.setdefault(task_id, {"id": task_id, "table": ref.split(".")[0], "columns": [], "any_of": [],
                                          "precision": {}, "evidence": {"declared": True, "parsed": None, "probed": None}})
        if ref not in task["columns"]:
            task["columns"].append(ref)
        if task_id not in req["required"].setdefault(ref, []):
            req["required"][ref].append(task_id)
        if "precision" in item:
            if item["precision"] not in PRECISIONS:
                raise ValueError(f"{where}.precision {item['precision']!r} not in {PRECISIONS}")
            task["precision"][ref] = item["precision"]
            _merge_precision(req, ref, item["precision"])
    req["tasks"] = list(tasks.values())
    any_of = spec.get("any_of", [])
    if not isinstance(any_of, list) or not all(isinstance(g, list) and len(g) >= 2 for g in any_of):
        raise ValueError(f"{path}: 'any_of' must be a list of groups, each with at least two alternatives")
    for gi, g in enumerate(any_of):
        for alt in g:
            if not isinstance(alt, list) or not alt:
                raise ValueError(f"{path}: any_of[{gi}]: alternative {alt!r} must be a non-empty list of refs")
            for r in alt:
                _ref(r, f"{path}: any_of[{gi}]")
    req["any_of"] = [[list(alt) for alt in g] for g in any_of]
    joins = spec.get("joins", [])
    if not isinstance(joins, list):
        raise ValueError(f"{path}: 'joins' must be a list of [ref, ref] pairs")
    for ji, j in enumerate(joins):
        if not isinstance(j, list) or len(j) != 2:
            raise ValueError(f"{path}: joins[{ji}] must be a [ref, ref] pair")
        a, b = (_ref(r, f"{path}: joins[{ji}]") for r in j)
        if a.split(".")[0] == b.split(".")[0]:
            raise ValueError(f"{path}: joins[{ji}] must connect two different tables")
        _add_join(req, sorted([a, b]), "spec", "declared")
    if spec.get("subject_key") is not None:
        req["subject_key"] = _ref(spec["subject_key"], f"{path}: subject_key")
    return req
