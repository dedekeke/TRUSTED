"""Key, foreign-key and subject-key discovery across the tables of one dataset.

Evidence is values only (exact string equality after trimming whitespace); column names are never used.
Equal-looking strings are evidence, not proof: every join carries its measured coverage and orphan count,
and nothing below COVERAGE is reported unless it was declared.
"""
from __future__ import annotations

import re

import pandas as pd

from privacy_tool.detect import R

KEY_UNIQUE = 0.99  # non-blank values distinct at least this share
KEY_MAX_BLANK = 0.01
COVERAGE = 0.95  # child distinct values found in the parent key
MIN_CHILD_DISTINCT = 20  # fewer distinct values looks like a category, not a reference
SHAPE_AGREE = 0.9
SUBJECT_MAX_DISTINCT = 0.95
SAMPLE = 200
KEY_ROLES = {"record_key", "technical_identifier", "direct_identifier"}
NOT_KEY_SUBTYPES = {"DATE", "TIMESTAMP", "BIRTH_DATE", "MEASUREMENT", "FINANCIAL_DATA", "GPS_COORDINATE", "AGE"}
PERSON_IDS = {"CUSTOMER_ID", "PATIENT_ID", "STUDENT_ID", "EMPLOYEE_ID", "CARD_ID", "ACCOUNT_ID"}
ID_LIKE = re.compile(r"^(?=.*\d)\S{3,40}$")
DECIMAL = re.compile(r"^[-+]?\d+[.,]\d+$")


def _shape(v: str) -> str:
    """Character-class shape: letter runs -> A, digit runs -> 9, other characters kept."""
    return re.sub(r"\d+", "9", re.sub(r"[^\W\d_]+", "A", v))


def _profile(s: pd.Series) -> dict:
    # Count raw values first, then trim the (far fewer) distinct ones: cheap on 1.6M-row columns.
    vc = s.value_counts(sort=False)  # first-occurrence order: deterministic
    counts = pd.Series(vc.to_numpy(), index=vc.index.astype(str).str.strip()).groupby(level=0, sort=False).sum()
    blank = int(counts.pop("")) if "" in counts.index else 0
    vals = counts.index
    n = int(counts.sum())
    lens = vals.str.len()
    sample = list(vals[:: max(1, len(vals) // SAMPLE)][:SAMPLE])
    return {"rows": len(s), "nonblank": n, "distinct": len(vals), "blank_rate": blank / len(s) if len(s) else 1.0,
            "counts": counts, "values": vals, "len": (int(lens.min()), int(lens.max())) if len(vals) else (0, 0),
            "sample": sample, "shapes": {_shape(v) for v in sample},
            "date_or_measure": bool(sample) and sum(bool(R["DATE_SHAPE"].match(v) or DECIMAL.match(v))
                                                    for v in sample) / len(sample) >= 0.5}


def _excluded(p: dict, label) -> bool:
    return p["date_or_measure"] or (label is not None and label[1] in NOT_KEY_SUBTYPES)


def _identifier_like(p: dict, label) -> bool:
    if label is not None:
        return label[0] in KEY_ROLES
    return bool(p["sample"]) and sum(bool(ID_LIKE.match(v)) for v in p["sample"]) / len(p["sample"]) >= 0.9


def _measure_join(parent: dict, child: dict) -> dict:
    found = child["values"].isin(parent["values"])
    cov = float(found.mean()) if len(found) else 0.0
    return {"coverage": round(cov, 4), "orphans": int((~found).sum())}


def _format_agree(parent: dict, child: dict) -> float:
    """Share of the child's sampled shapes seen in the parent sample; 0 if the length ranges differ."""
    (pmin, pmax), (cmin, cmax) = parent["len"], child["len"]
    if not child["sample"] or cmin < pmin or cmax > pmax:
        return 0.0
    return sum(_shape(v) in parent["shapes"] for v in child["sample"]) / len(child["sample"])


def _confidence(coverage: float, agree: float, distinct: int) -> float:
    # coverage dominates; agreeing shapes over many distinct values add the rest
    return round(coverage * (0.7 + 0.3 * agree * min(1.0, distinct / 100)), 3)


def discover(tables: dict[str, pd.DataFrame], labels: pd.DataFrame | None = None, declared: dict | None = None) -> dict:
    """Candidate keys, joins (parent key -> child column) and per-table subject keys; see privacy_tool/README.md."""
    lab = {} if labels is None else {(r.table, r.column): (r.privacy_role, r.subtype) for r in labels.itertuples()}
    prof = {f"{t}.{c}": _profile(df[c]) for t, df in sorted(tables.items()) for c in df.columns}
    ref_label = {ref: lab.get(tuple(ref.split(".", 1))) for ref in prof}

    keys = []
    for ref, p in prof.items():
        unique = p["distinct"] / p["nonblank"] if p["nonblank"] else 0.0
        if (p["nonblank"] and unique >= KEY_UNIQUE and p["blank_rate"] <= KEY_MAX_BLANK
                and _identifier_like(p, ref_label[ref]) and not _excluded(p, ref_label[ref])):
            keys.append({"column": ref, "unique_ratio": round(unique, 4), "null_rate": round(p["blank_rate"], 4)})

    joins = {}
    for k in keys:
        parent, ptable = prof[k["column"]], k["column"].split(".", 1)[0]
        pset = set(parent["values"])
        for ref, child in prof.items():
            if (ref.split(".", 1)[0] == ptable or child["distinct"] < MIN_CHILD_DISTINCT
                    or _excluded(child, ref_label[ref])):
                continue
            agree = _format_agree(parent, child)
            if agree < SHAPE_AGREE:
                continue
            # cheap sample containment before the full set test
            if sum(v in pset for v in child["sample"]) / len(child["sample"]) < COVERAGE - .1:
                continue
            m = _measure_join(parent, child)
            if m["coverage"] >= COVERAGE:
                joins[(k["column"], ref)] = {"parent": k["column"], "child": ref, **m,
                                             "confidence": _confidence(m["coverage"], agree, child["distinct"])}
    for (p, c) in list(joins):  # two keys covering each other: keep the larger side as parent
        if (c, p) in joins and (prof[p]["distinct"], c) < (prof[c]["distinct"], p):
            del joins[(p, c)]

    subject_keys = {}
    for t, df in sorted(tables.items()):
        ranked = []
        for i, c in enumerate(df.columns):
            role, sub = ref_label[f"{t}.{c}"] or (None, None)
            tier = 0 if role == "direct_identifier" and sub == "NATIONAL_ID" else \
                1 if role == "technical_identifier" and sub in PERSON_IDS else None
            p = prof[f"{t}.{c}"]
            if tier is not None and p["nonblank"] and p["distinct"] / p["nonblank"] < SUBJECT_MAX_DISTINCT \
                    and (p["counts"] >= 2).any():
                ranked.append((tier, i, f"{t}.{c}"))
        if ranked:
            subject_keys[t] = min(ranked)[2]

    conflicts = []
    declared = declared or {}
    for pref, cref in declared.get("joins", []):
        missing = [r for r in (pref, cref) if r not in prof]
        if missing:
            conflicts.append(f"declared join {pref} -> {cref}: column {', '.join(missing)} not found")
            m = {"coverage": 0.0, "orphans": None, "confidence": 0.0}
        else:
            m = _measure_join(prof[pref], prof[cref])
            m["confidence"] = _confidence(m["coverage"], _format_agree(prof[pref], prof[cref]), prof[cref]["distinct"])
            if m["coverage"] < COVERAGE:
                conflicts.append(f"declared join {pref} -> {cref}: measured coverage {m['coverage']:.2%} < {COVERAGE:.0%}")
        for other in [j for j in joins if j[1] == cref and j[0] != pref]:
            conflicts.append(f"discovered join {other[0]} -> {cref} contradicts declared parent {pref}; dropped")
            del joins[other]
        joins[(pref, cref)] = {"parent": pref, "child": cref, **m, "declared": True}

    by_size = sorted(subject_keys, key=lambda t: (-len(tables[t]), t))
    subject_key = subject_keys[by_size[0]] if by_size else None
    if declared.get("subject_key"):
        subject_key = declared["subject_key"]
        if subject_key not in prof:
            conflicts.append(f"declared subject key {subject_key}: column not found")
        else:
            subject_keys[subject_key.split(".", 1)[0]] = subject_key

    return {"keys": sorted(keys, key=lambda k: k["column"]),
            "joins": [joins[j] for j in sorted(joins)],
            "subject_keys": dict(sorted(subject_keys.items())),
            "subject_key": subject_key,
            "conflicts": sorted(conflicts)}
