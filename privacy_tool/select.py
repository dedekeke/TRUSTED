"""Combine detection, relations, requirements and the rule matrix into one explained plan (decisions.json).

The plan chooses the finest allowed rung per column; the measured search (privacy_tool.search) may coarsen it.
Status is `ready_for_transform` or `blocked` (with errors). Ready does not mean privacy-validated.
The plan never contains key material, raw values, identifier-to-token maps or row maps.
"""
from __future__ import annotations

import pandas as pd

from . import policy
from .detect import CONTEXT_QI

POLICY_VERSION = "dynamic-1"
EVENT_SUBTYPES = ("TIMESTAMP", "DATE")


def _ref(t, c):
    return f"{t}.{c}"


def _split(ref):
    t, _, c = ref.partition(".")
    return t, c


class _Domains:
    """Union-find over join pairs: both sides of a required join share one HMAC domain."""

    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = sorted((self.find(a), self.find(b)))
        self.parent[rb] = ra


def _labels_by_ref(labels: pd.DataFrame) -> dict:
    out = {}
    for r in labels.to_dict("records"):
        ref = _ref(r["table"], r["column"])
        if ref in out:
            raise ValueError(f"duplicate label for {ref}")
        out[ref] = r
    return out


def _person_tables(labels: dict, relations: dict) -> set:
    """Tables about people: own person evidence, or joined to such a table (person context crosses joins)."""
    direct = {_split(ref)[0] for ref, lab in labels.items()
              if "person table" in str(lab.get("evidence", "")) or lab["privacy_role"] == "direct_identifier"}
    direct |= set(relations.get("subject_keys") or {})  # subject may be reached through a join
    linked, changed = set(direct), True
    while changed:
        changed = False
        for j in relations.get("joins", []):
            a, b = _split(j["parent"])[0], _split(j["child"])[0]
            if (a in linked) != (b in linked):
                linked |= {a, b}
                changed = True
    return linked


def confirm(labels: pd.DataFrame, confirmed: pd.DataFrame) -> pd.DataFrame:
    """Apply reviewer-confirmed labels (table,column,privacy_role,subtype): confidence 1.0, evidence recorded."""
    out = labels.copy()
    for r in confirmed.to_dict("records"):
        m = (out.table == r["table"]) & (out.column == r["column"])
        if not m.any():
            raise ValueError(f"confirmed label for unknown column {r['table']}.{r['column']}")
        out.loc[m, ["privacy_role", "subtype", "confidence", "evidence"]] = \
            [r["privacy_role"], r["subtype"], 1.0, "confirmed by reviewer"]
    return out


def select(tables: dict[str, pd.DataFrame], labels: pd.DataFrame, relations: dict, requirements: dict,
           release_id: str | None = None) -> dict:
    errors, warnings, review = [], list(requirements.get("warnings", [])), []
    trust = requirements["trust_level"]
    tg = policy.targets(trust, requirements.get("targets") or None)
    lab = _labels_by_ref(labels)
    columns = {t: list(df.columns) for t, df in tables.items()}
    exists = {_ref(t, c) for t, cs in columns.items() for c in cs}

    # 1. requirements -> required refs (missing ones block)
    required = {r: list(ts) for r, ts in (requirements.get("required") or {}).items()}
    for r, ts in required.items():
        if r not in exists:
            errors.append(f"{r} is required by {', '.join(ts)} but missing from the input")
    for group in requirements.get("any_of") or []:
        options = [list(alt) if isinstance(alt, (list, tuple)) else alt.split("+") for alt in group]  # nested or "a+b"
        usable = [o for o in options if all(p in exists for p in o)]
        if not usable:
            errors.append(f"none of the alternatives {' | '.join('+'.join(o) for o in options)} is available")
            continue
        for p in usable[0]:  # minimisation: keep only the first usable alternative
            required.setdefault(p, []).append("any_of:" + "|".join("+".join(o) for o in options))
    precision = requirements.get("precision") or {}

    # 2. joins -> shared token domains
    doms, join_refs = _Domains(), set()
    discovered = {frozenset((j["parent"], j["child"])) for j in relations.get("joins", [])}
    for j in requirements.get("joins") or []:
        a, b = j["columns"]
        if frozenset((a, b)) not in discovered:
            warnings.append(f"join {a} = {b} is needed by {', '.join(j.get('tasks', []))} but was not discovered; "
                            "coverage is unverified")
        doms.union(a, b)
        join_refs |= {a, b}

    # 3. person context crosses joins: place/time in a table linked to people is a quasi-identifier
    people = _person_tables(lab, relations)
    for ref, l in lab.items():
        if _split(ref)[0] in people and l["privacy_role"] == "non_sensitive" and l["subtype"] in CONTEXT_QI:
            lab[ref] = {**l, "privacy_role": "quasi_identifier",
                        "evidence": f"{l.get('evidence', '')}; linked to people through a join"}

    # 4. table release scope
    no_purpose = requirements.get("source") == "none"
    used_tables = {_split(r)[0] for r in required} | {_split(r)[0] for r in join_refs}
    plan_tables, plan_cols, derived = {}, [], []
    for t in sorted(tables):
        if no_purpose or t in used_tables:
            keys = [k["column"] for k in relations.get("keys", []) if _split(k["column"])[0] == t]
            keys.sort(key=lambda r: lab.get(r, {}).get("privacy_role") != "record_key")
            rk = _split(keys[0])[1] if keys else None
            if rk is None:
                warnings.append(f"{t}: no record key found; scoring row maps cannot be written")
            plan_tables[t] = {"action": "RELEASE", "record_key": rk,
                              "reason": "used by " + ", ".join(sorted({x for r, ts in required.items()
                                                                       if _split(r)[0] == t for x in ts}) or ["no declared purpose"])}
        else:
            plan_tables[t] = {"action": "WITHHOLD", "record_key": None,
                              "reason": "no declared analysis needs this table"}

    # 5. one decision per source column of each released table
    for t, td in plan_tables.items():
        if td["action"] != "RELEASE":
            continue
        for c in columns[t]:
            ref = _ref(t, c)
            l = lab.get(ref)
            if l is None:
                l = {"privacy_role": "non_sensitive", "subtype": "CATEGORY", "confidence": 0.0, "evidence": "unlabelled"}
                (errors if ref in required else warnings).append(f"{ref} has no label")
            req, in_join = ref in required, ref in join_refs
            try:
                cand = policy.candidates(l, trust, req, in_join, precision.get(ref))
            except ValueError as e:
                errors.append(f"{ref}: {e}")
                continue
            rungs = cand["rungs"]
            if not rungs:
                errors.append(f"{ref}: no allowed operation")
                continue
            if cand["escalate"] and req:
                errors.append(f"{ref} (required by {', '.join(required[ref])}): {cand['escalate']}")
            elif cand["escalate"]:
                warnings.append(f"{ref}: {cand['escalate']}")
            if req and rungs[0]["action"] == "DROP":
                errors.append(f"{ref} is required by {', '.join(required[ref])} but its label is uncertain "
                              f"(confidence {l.get('confidence')}); confirm it (--confirm) before release"
                              if cand["needs_review"] else
                              f"{ref} is required by {', '.join(required[ref])} but policy only allows DROP")
            for r in rungs:
                if r["action"] == "HMAC" and r["method"] == "hmac_sha256":
                    r["params"]["domain"] = doms.find(ref)
            if cand["needs_review"]:
                review.append({"column": ref, "confidence": l.get("confidence"), "evidence": l.get("evidence", "")})
            chosen = rungs[0]
            why = (f"required by {', '.join(required[ref])}" if req else
                   "join key" if in_join else "no declared analysis needs it (minimisation)")
            entry = {"table": t, "column": c, "privacy_role": l["privacy_role"], "subtype": l["subtype"],
                     "confidence": l.get("confidence"), "action": chosen["action"], "method": chosen["method"],
                     "params": dict(chosen["params"]), "level": chosen.get("level", 0), "rungs": rungs,
                     "required_by": required.get(ref, []), "needs_review": cand["needs_review"],
                     "reason": f"{l['privacy_role']}/{l['subtype']}: {why}" + (f"; {'; '.join(cand['notes'])}" if cand["notes"] else "")}
            if chosen["action"] == "DERIVE":
                events = [x for x in columns[t] if lab.get(_ref(t, x), {}).get("subtype") in EVENT_SUBTYPES]
                events.sort(key=lambda x: _ref(t, x) not in required)
                if not events:
                    errors.append(f"{ref}: no event date in {t} to derive age at")
                    continue
                name = "age" if "age" not in columns[t] else f"{c}_age"
                derived.append({"table": t, "column": name, "sources": [c, events[0]], "method": chosen["method"],
                                "params": dict(chosen["params"]), "rungs": rungs, "required_by": required.get(ref, []),
                                "reason": f"age at {events[0]} from {c}, before both are generalised or dropped"})
                entry.update(action="DROP", method=None, params={},
                             reason=entry["reason"] + f"; dropped after deriving {name}")
            plan_cols.append(entry)

    domains = {}
    for c in plan_cols:
        if c["action"] == "HMAC" and c["params"].get("domain"):
            domains.setdefault(c["params"]["domain"], []).append(_ref(c["table"], c["column"]))
    for d, refs in domains.items():  # join partners must share a domain
        for a in refs:
            if a in join_refs and any(doms.find(b) == doms.find(a) and b not in refs for b in join_refs):
                errors.append(f"{a}: join partner not tokenised in the same domain")
    for c in plan_cols:
        bad = policy.violations({"privacy_role": c["privacy_role"], "subtype": c["subtype"],
                                 "confidence": c["confidence"]},
                                {"action": c["action"], "method": c["method"], "params": c["params"]}, trust) \
            if c["action"] != "DROP" else []
        errors += [f"{c['table']}.{c['column']}: {b}" for b in bad]

    scope = requirements.get("scenario") or requirements.get("dataset") or "release"
    return {
        "policy_version": POLICY_VERSION,
        "release_id": release_id or f"{scope}/{trust}",
        "status": "blocked" if errors else "ready_for_transform",
        "source": requirements.get("source"), "scenario": requirements.get("scenario"),
        "dataset": requirements.get("dataset"), "trust_level": trust, "targets": tg,
        "tables": plan_tables, "columns": plan_cols, "derived": derived,
        "domains": domains, "joins": relations.get("joins", []), "subject_keys": relations.get("subject_keys", {}),
        "subject_key": relations.get("subject_key"), "required": required, "precision": precision,
        "review_queue": review, "warnings": warnings, "errors": errors,
    }


def render(plan: dict) -> str:
    """Readable Markdown table of the same decisions (no values)."""
    lines = [f"# Release plan: {plan['scenario'] or plan['dataset']} ({plan['trust_level']})", "",
             f"Status: **{plan['status']}**. Targets: {plan['targets']}", ""]
    for kind in ("errors", "warnings"):
        if plan[kind]:
            lines += [f"## {kind.title()}", ""] + [f"- {x}" for x in plan[kind]] + [""]
    lines += ["## Tables", "", "| Table | Action | Reason |", "|---|---|---|"]
    lines += [f"| {t} | {d['action']} | {d['reason']} |" for t, d in plan["tables"].items()]
    lines += ["", "## Columns", "", "| Table | Column | Action | Parameters | Required by | Explanation |",
              "|---|---|---|---|---|---|"]
    for c in plan["columns"]:
        p = ", ".join(f"{k}={v}" for k, v in c["params"].items())
        m = f"{c['method']} {p}".strip() if c["method"] else p
        lines.append(f"| {c['table']} | {c['column']} | {c['action']} | {m} | {', '.join(c['required_by'])} | {c['reason']} |")
    for d in plan["derived"]:
        lines.append(f"| {d['table']} | {d['column']} (derived) | DERIVE | {d['method']} width={d['params'].get('width')} "
                     f"| {', '.join(d['required_by'])} | {d['reason']} |")
    if plan["review_queue"]:
        lines += ["", "## Needs review", ""] + [f"- {r['column']} (confidence {r['confidence']}): {r['evidence']}"
                                               for r in plan["review_queue"]]
    return "\n".join(lines) + "\n"
