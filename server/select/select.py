"""Combine detection, relations, requirements and the rule matrix into one explained plan (decisions.json).

The plan chooses the finest allowed rung per column; the measured search (server.select.search) may coarsen it.
Status is `policy_valid` or `blocked` (with errors). Policy-valid is not measured privacy and never an approval.
The plan never contains key material, raw values, identifier-to-token maps or row maps.
"""
from __future__ import annotations

import hashlib
import json
from itertools import combinations

import pandas as pd

from . import policy
from .detect import CONTEXT_QI, REVIEW_BELOW

POLICY_VERSION = "dynamic-1"
DETECTOR_VERSION = "detect-1"
EVENT_SUBTYPES = ("TIMESTAMP", "DATE")
ROLES = policy.ROLES
ID_ROLES = {"direct_identifier", "technical_identifier", "record_key"}
MIN_JOIN_COVERAGE = 0.95


def fingerprint(tables: dict[str, pd.DataFrame]) -> str:
    """Schema + row counts (no values): transform refuses a plan made for other input."""
    shape = {t: [list(df.columns), len(df)] for t, df in sorted(tables.items())}
    return hashlib.sha256(json.dumps(shape).encode()).hexdigest()[:16]


def _period_end(tables, lab, required) -> str | None:
    """Latest date in the required event columns (e.g. card_transactions.ts), as YYYY-MM-DD."""
    ends = [pd.to_datetime(tables[t][c], errors="coerce").max() for t, c in map(_split, required)
            if lab.get(_ref(t, c), {}).get("subtype") in EVENT_SUBTYPES and t in tables and c in tables[t]]
    ends = [e for e in ends if pd.notna(e)]
    return max(ends).strftime("%Y-%m-%d") if ends else None


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
    direct |= set(relations.get("subject_keys") or {})
    linked, changed = set(direct), True
    while changed:
        changed = False
        for j in relations.get("joins", []):
            a, b = _split(j["parent"])[0], _split(j["child"])[0]
            if (a in linked) != (b in linked):
                linked |= {a, b}
                changed = True
    return linked


def _downgrade(old_role, old_subtype, role, subtype):
    was_id = old_role in ID_ROLES or old_subtype in policy.ID_SUBTYPE_ROLE
    is_id = role in ID_ROLES or subtype in policy.ID_SUBTYPE_ROLE
    was_protected = old_role != "non_sensitive" or old_subtype in policy.SUBTYPE_REROUTE
    is_unprotected = role == "non_sensitive" and subtype not in policy.SUBTYPE_REROUTE
    return (was_id and not is_id) or (was_protected and is_unprotected)


def confirm(labels: pd.DataFrame, confirmed: pd.DataFrame, allow_downgrade: bool = False) -> pd.DataFrame:
    """Apply reviewer-confirmed labels (table,column,privacy_role,subtype): confidence 1.0, the detected label kept.

    Lowering identifier protection or making a protected label non-sensitive requires allow_downgrade."""
    need = {"table", "column", "privacy_role", "subtype"}
    if not need <= set(confirmed.columns):
        raise ValueError(f"confirmation file needs columns {sorted(need)}")
    if confirmed.duplicated(["table", "column"]).any():
        raise ValueError("confirmation file lists a column twice")
    out = labels.copy()
    for col in ("detected_role", "detected_subtype", "detected_confidence", "detected_needs_review"):
        if col not in out:
            out[col] = None
    for r in confirmed.to_dict("records"):
        ref = f"{r['table']}.{r['column']}"
        if r["privacy_role"] not in ROLES or not str(r["subtype"]).strip():
            raise ValueError(f"{ref}: invalid role/subtype {r['privacy_role']}/{r['subtype']}")
        m = (out.table == r["table"]) & (out.column == r["column"])
        if not m.any():
            raise ValueError(f"confirmed label for unknown column {ref}")
        old = out[m].iloc[0]
        if _downgrade(old.privacy_role, old.subtype, r["privacy_role"], r["subtype"]) and not allow_downgrade:
            raise ValueError(f"{ref}: refusing to downgrade {old.privacy_role}/{old.subtype} to {r['privacy_role']} "
                             "without allow_downgrade")
        out.loc[m, ["detected_role", "detected_subtype", "detected_confidence", "detected_needs_review"]] = \
            [old.privacy_role, old.subtype, old.get("detector_confidence", old.confidence),
             bool(old.get("detector_needs_review", False)) or float(old.confidence) < REVIEW_BELOW]
        out.loc[m, ["privacy_role", "subtype", "confidence", "evidence"]] = \
            [r["privacy_role"], r["subtype"], 1.0, f"confirmed by reviewer (detected {old.privacy_role}/{old.subtype})"]
    return out


def select(tables: dict[str, pd.DataFrame], labels: pd.DataFrame, relations: dict, requirements: dict,
           release_id: str | None = None) -> dict:
    errors, warnings, review = [], list(requirements.get("warnings", [])), []
    trust = requirements["trust_level"]
    tg = policy.targets(trust, requirements.get("targets") or None)
    lab = _labels_by_ref(labels)
    for ref, l in lab.items():
        if pd.notna(l.get("detected_role")) and _downgrade(l["detected_role"], l.get("detected_subtype"),
                                                        l["privacy_role"], l["subtype"]):
            warnings.append(f"{ref}: protection downgrade explicitly allowed from "
                            f"{l['detected_role']}/{l.get('detected_subtype')} to {l['privacy_role']}/{l['subtype']}")
    columns = {t: list(df.columns) for t, df in tables.items()}
    exists = {_ref(t, c) for t, cs in columns.items() for c in cs}

    required = {r: list(ts) for r, ts in (requirements.get("required") or {}).items()}
    for r, ts in required.items():
        if r not in exists:
            errors.append(f"{r} is required by {', '.join(ts)} but missing from the input")
    for group in requirements.get("any_of") or []:
        options = [list(alt) if isinstance(alt, (list, tuple)) else alt.split("+") for alt in group]
        usable = [o for o in options if all(p in exists for p in o)]
        if not usable:
            errors.append(f"none of the alternatives {' | '.join('+'.join(o) for o in options)} is available")
            continue
        for p in usable[0]:
            required.setdefault(p, []).append("any_of:" + "|".join("+".join(o) for o in options))
    precision = requirements.get("precision") or {}

    doms, join_refs = _Domains(), set()
    errors += [f"relations: {x}" for x in relations.get("conflicts", [])]
    warnings += [f"relations: {x}" for x in relations.get("notices", [])]
    trusted = [j for j in relations.get("joins", []) if j.get("coverage", 1.0) >= MIN_JOIN_COVERAGE]
    relations = {**relations, "joins": trusted}
    linked = _Domains()
    for j in trusted:
        linked.union(j["parent"], j["child"])
    pairs = [(j, a, b) for j in requirements.get("joins") or [] for a, b in combinations(j["columns"], 2)]
    for j, a, b in pairs:
        if linked.find(a) != linked.find(b):
            ids = all(lab.get(x, {}).get("privacy_role") in ID_ROLES for x in (a, b))
            if j.get("kind", "declared") == "same_name" and ids:
                errors.append(f"{a} = {b} is needed by {', '.join(j.get('tasks', []))} but relations found no join "
                              f"with coverage >= {MIN_JOIN_COVERAGE}")
                continue
            if j.get("kind", "declared") == "same_name":
                warnings.append(f"{a} = {b} share a name in {', '.join(j.get('tasks', []))} but relations found no "
                                "join; not treated as a join")
                continue
            errors.append(f"join {a} = {b} is required but was not found with coverage >= {MIN_JOIN_COVERAGE}")
            continue
        doms.union(a, b)
        join_refs |= {a, b}

    for t, cs in columns.items():
        ids = [_ref(t, c) for c in cs if _ref(t, c) in required and lab.get(_ref(t, c), {}).get("privacy_role") in ID_ROLES]
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if lab[a]["subtype"] == lab[b]["subtype"] and set(required[a]) & set(required[b]):
                    doms.union(a, b)

    people = _person_tables(lab, relations)
    for ref, l in lab.items():
        if _split(ref)[0] in people and l["privacy_role"] == "non_sensitive" and l["subtype"] in CONTEXT_QI | {"URL"}:
            lab[ref] = {**l, "privacy_role": "quasi_identifier",
                        "evidence": f"{l.get('evidence', '')}; linked to people through a join"}

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
                cand = policy.candidates(l, trust, req, in_join, precision.get(ref), k=tg.get("k"))
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
            if cand["unsupported"]:
                if req:
                    errors.append(f"unsupported_label: {ref} (required by {', '.join(required[ref])}): "
                                  f"{l['privacy_role']}/{l['subtype']}: {cand['unsupported']}")
            elif req and cand.get("uncertain") and pd.isna(l.get("detected_role")):
                errors.append(f"review_required: {ref} is required by {', '.join(required[ref])} but its label "
                              f"{l['privacy_role']}/{l['subtype']} is uncertain (confidence {l.get('confidence')}"
                              f"{', detector needs_review' if l.get('detector_needs_review') else ''}); "
                              "confirm it (--confirm) before release")
            elif req and rungs[0]["action"] == "DROP":
                errors.append(f"{ref} is required by {', '.join(required[ref])} but policy only allows DROP")
            for r in rungs:
                if r["action"] == "HMAC" and r["method"] == "hmac_sha256":
                    r["params"]["domain"] = doms.find(ref)
            if cand["needs_review"]:
                review.append({"column": ref, "confidence": l.get("confidence"), "evidence": l.get("evidence", ""),
                               **({"issue": "unsupported_label"} if cand["unsupported"] else {})})
            chosen = rungs[0]
            why = (f"required by {', '.join(required[ref])}" if req else "join key" if in_join else
                   "no declared analysis needs it (minimisation)" if rungs[0]["action"] == "DROP" else
                   "non-sensitive; kept without a declared purpose")
            entry = {"table": t, "column": c, "privacy_role": l["privacy_role"], "subtype": l["subtype"],
                     "detected": {"role": l.get("detected_role"), "subtype": l.get("detected_subtype")}
                     if l.get("detected_role") else None,
                     "confidence": l.get("confidence"), "action": chosen["action"], "method": chosen["method"],
                     "params": dict(chosen["params"]), "level": chosen.get("level", 0), "rungs": rungs,
                     "required_by": required.get(ref, []), "needs_review": cand["needs_review"],
                     "reason": f"{l['privacy_role']}/{l['subtype']}: {why}" + (f"; {'; '.join(cand['notes'])}" if cand["notes"] else "")}
            for field in ('detector_confidence', 'detector_needs_review', 'art9', 'art9_table'):
                if field in l:
                    entry[field] = l[field]
            if chosen["action"] == "DERIVE":
                events = [x for x in columns[t] if lab.get(_ref(t, x), {}).get("subtype") in EVENT_SUBTYPES]
                events.sort(key=lambda x: _ref(t, x) not in required)
                if not events:
                    errors.append(f"{ref}: no event date in {t} to derive age at")
                    continue
                taken = set(columns[t]) | {d["column"] for d in derived if d["table"] == t}
                name = "age" if "age" not in taken else f"{c}_age"
                d = {"table": t, "column": name, "sources": [c, events[0]], "method": chosen["method"],
                     "params": dict(chosen["params"]), "rungs": rungs, "required_by": required.get(ref, []),
                     "reason": f"age at {events[0]} from {c}, before both are generalised or dropped"}
                end = None if _ref(t, events[0]) in required else _period_end(tables, lab, required)
                if end:
                    d.update(ref_date=end,reason=f"age at {end} (end of the analysed period) from {c}")
                derived.append(d)
                entry.update(action="DROP", method=None, params={},
                             reason=entry["reason"] + f"; dropped after deriving {name}")
            plan_cols.append(entry)

    for t, td in plan_tables.items():
        if td["action"] == "RELEASE" and not any(c["table"] == t and c["action"] != "DROP" for c in plan_cols) \
                and not any(d["table"] == t for d in derived):
            plan_tables[t] = {"action": "WITHHOLD", "record_key": None, "reason": "no column is releasable"}
    plan_cols = [c for c in plan_cols if plan_tables[c["table"]]["action"] == "RELEASE"]

    domains = {}
    for c in plan_cols:
        if c["action"] == "HMAC" and c["params"].get("domain"):
            domains.setdefault(c["params"]["domain"], []).append(_ref(c["table"], c["column"]))
    for d, refs in domains.items():
        for a in refs:
            if a in join_refs and any(doms.find(b) == doms.find(a) and b not in refs for b in join_refs):
                errors.append(f"{a}: join partner not tokenised in the same domain")
    for c in plan_cols:
        bad = policy.violations({"privacy_role": c["privacy_role"], "subtype": c["subtype"],
                                 "confidence": c["confidence"]},
                                {"action": c["action"], "method": c["method"], "params": c["params"]}, trust, k=tg.get("k")) \
            if c["action"] != "DROP" else []
        errors += [f"{c['table']}.{c['column']}: {b}" for b in bad]

    scope = requirements.get("scenario") or requirements.get("dataset") or "release"
    if not release_id:
        warnings.append("no release_id given: tokens are scoped to scenario/trust only; pass one per recipient")
    reviews = [{"table": r["table"], "column": r["column"],
                "detected": {"role": r["detected_role"], "subtype": r["detected_subtype"],
                             "confidence": float(r["detected_confidence"]),
                             "needs_review": bool(r["detected_needs_review"])},
                "confirmed": {"role": r["privacy_role"], "subtype": r["subtype"]},
                "downgrade": _downgrade(r["detected_role"], r["detected_subtype"], r["privacy_role"], r["subtype"])}
               for r in labels.to_dict("records") if pd.notna(r.get("detected_role"))]
    plan = {
        "policy_version": POLICY_VERSION, "detector_version": DETECTOR_VERSION,
        "input_fingerprint": fingerprint(tables),
        "release_id": release_id or f"{scope}/{trust}", "release_id_explicit": bool(release_id),
        "status": None,
        "source": requirements.get("source"), "scenario": requirements.get("scenario"),
        "dataset": requirements.get("dataset"), "trust_level": trust, "targets": tg,
        "tables": plan_tables, "columns": plan_cols, "derived": derived,
        "domains": domains, "joins": relations.get("joins", []), "subject_keys": relations.get("subject_keys", {}),
        "subject_key": relations.get("subject_key"), "required": required, "precision": precision,
        "review_queue": review, "reviews": reviews,
        "label_coverage": policy.coverage(zip(labels["privacy_role"], labels["subtype"])),
        "warnings": warnings, "errors": errors,
    }
    return set_status(plan)


def set_status(plan: dict) -> dict:
    """Select outcome: policy_valid or blocked. Never approved: privacy targets are measured by search."""
    plan["status"] = "blocked" if plan["errors"] else "policy_valid"
    plan["outcome"] = {"policy_valid": not plan["errors"], "targets_met": False, "approved": False,
                       "budget": {"used": 0, "limit": None, "exhausted": False, "unexplored": None},
                       "targets": {k: v for k, v in plan["targets"].items() if k != "notes"},
                       "achieved": {}, "violations": []}
    return plan


STATUS_TEXT = {
    "policy_valid": "initial plan within the rule matrix; privacy targets not measured; not an approved release",
    "blocked": "named conflicts must be resolved; nothing may be released",
    "measured_ok": "the measured candidate meets the risk and utility targets",
    "target_unmet": "the allowed candidate space was searched and no candidate meets the targets; not approved",
    "budget_exhausted": "the evaluation budget ran out with unexplored candidates; this is not proof that the "
                        "targets are infeasible; not approved",
}


def render(plan: dict) -> str:
    """Readable Markdown table of the same decisions (no values)."""
    lines = [f"# Release plan: {plan['scenario'] or plan['dataset']} ({plan['trust_level']})", "",
             f"Status: **{plan['status']}**: {STATUS_TEXT.get(plan['status'], 'unknown status')}. "
             f"Targets: {plan['targets']}", "",
             f"Approved release: **{'yes' if (plan.get('outcome') or {}).get('approved') else 'no'}**"
             + ("; provenance_unbound: the plan is not bound to a detect manifest (built-in detector), so it cannot "
                "be approved" if "provenance_unbound" in (plan.get("outcome") or {}).get("issues", []) else ""), ""]
    prov = plan.get("provenance")
    if prov:
        lines += [f"Provenance: {'bound to detect manifest' if prov.get('bound') else 'UNBOUND (legacy built-in detector)'}"
                  f", dataset fingerprint {prov.get('dataset_fingerprint', '')[:16]}"
                  + (f", plan sha256 {plan['plan_sha256'][:16]}" if plan.get("plan_sha256") else ""), ""]
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
        explanation = c.get('selection_explanation', c['reason'])
        lines.append(f"| {c['table']} | {c['column']} | {c['action']} | {m} | {', '.join(c['required_by'])} | {explanation} |")
    for d in plan["derived"]:
        lines.append(f"| {d['table']} | {d['column']} (derived) | DERIVE | {d['method']} width={d['params'].get('width')} "
                     f"| {', '.join(d['required_by'])} | {d.get('selection_explanation', d['reason'])} |")
    if plan.get('measured'):
        measured = plan['measured']
        lines += ['', '## Measured (own data)', '', f"- Risk: {measured['risk']}",
                  f"- Utility: {measured['utility']} (baseline {measured['baseline_utility']}, tau={measured['tau']})",
                  f"- Evaluations: {measured['evaluations']}"]
        if plan.get('suppression'):
            lines.append(f"- Local suppression: {plan['suppression']}")
        budget = (plan.get('outcome') or {}).get('budget') or {}
        lines.append(f"- Budget: {budget.get('used')}/{budget.get('limit')} evaluations, "
                     f"{budget.get('unexplored')} unexplored candidates")
        if plan.get('conflict'):
            lines.append(f"- **{plan['status']}**: {plan['conflict']}")
    if plan["review_queue"]:
        lines += ["", "## Needs review", ""] + [f"- {r['column']} (confidence {r['confidence']}): {r['evidence']}"
                                               for r in plan["review_queue"]]
    return "\n".join(lines) + "\n"
