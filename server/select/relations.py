"""Key, foreign-key and subject-key discovery across the tables of one dataset.

Evidence is values only (exact string equality after trimming whitespace); column names are never used.
Equal-looking strings are evidence, not proof: every join carries its measured coverage and orphan count,
and nothing below COVERAGE is reported unless it was declared.
"""
from __future__ import annotations

import re

import pandas as pd

KEY_UNIQUE = 0.99
KEY_MAX_BLANK = 0.01
COVERAGE = 0.95
MIN_CHILD_DISTINCT = 20
SHAPE_AGREE = 0.85
SUBJECT_MAX_DISTINCT = 0.95
SAMPLE = 200
PARENT_SAMPLE = 2000
KEY_ROLES = {"record_key", "technical_identifier", "direct_identifier"}
NOT_ID_SUBTYPES = {"DATE", "TIMESTAMP", "BIRTH_DATE", "MEASUREMENT", "FINANCIAL_DATA", "GPS_COORDINATE", "AGE",
                   "PERSON_NAME", "STREET_ADDRESS", "FREE_TEXT"}
OWNED_IDS = {"PAYMENT_CARD", "IBAN", "LICENSE_PLATE"}
PERSON_IDS = {"CUSTOMER_ID", "PATIENT_ID", "STUDENT_ID", "EMPLOYEE_ID", "CARD_ID", "ACCOUNT_ID"} | OWNED_IDS
ACCOUNT_NAMES = {"EMAIL", "USERNAME"}
HOLDINGS = {"CARD_ID", "ACCOUNT_ID"} | OWNED_IDS
PERSON_ROW_IDS = {"NATIONAL_ID", "EMAIL", "PHONE"}
PERSON_ROW_UNIQUE = 0.95
PERSON_ROW_PRESENT = 0.5
STAFF_IDS = {"EMPLOYEE_ID"}
ID_LIKE = re.compile(r"^(?=.*\d)\S{3,40}$")
DECIMAL = re.compile(r"^[-+]?\d+[.,]\d+$")
DATE_SHAPE = re.compile(r"^\d{1,4}[-./]\d{1,2}([-./]\d{1,4})?([ T]|$)|^\d{4}-?W\d{1,2}$")
NO_LABELS = "no labels: subject keys not discovered (they need detector subtypes)"


def _shape(v: str) -> str:
    """Character-class shape: letter runs -> A, digit runs -> 9, other characters kept."""
    return re.sub(r"\d+", "9", re.sub(r"[^\W\d_]+", "A", v))


def _spread(vals: pd.Index, n: int) -> list[str]:
    return list(vals[:: max(1, len(vals) // n)][:n])


def _share(vals: list[str], test) -> float:
    return sum(map(test, vals)) / len(vals) if vals else 0.0


def _profile(s: pd.Series) -> dict:
    vc = s.value_counts(sort=False)
    counts = pd.Series(vc.to_numpy(), index=vc.index.astype(str).str.strip()).groupby(level=0).sum()
    blank = int(counts.pop("")) if "" in counts.index else 0
    vals = counts.index
    lens = vals.str.len()
    sample = _spread(vals, SAMPLE)
    return {"rows": len(s), "nonblank": int(counts.sum()), "distinct": len(vals),
            "blank_rate": blank / len(s) if len(s) else 1.0, "counts": counts, "values": vals,
            "len": (int(lens.min()), int(lens.max())) if len(vals) else (0, 0), "sample": sample,
            "shapes": {_shape(v) for v in _spread(vals, PARENT_SAMPLE)},
            "id_values": _share(sample, lambda v: bool(ID_LIKE.match(v))) >= 0.9,
            "spaces": _share(sample, lambda v: any(ch.isspace() for ch in v)) >= 0.05,
            "date_or_measure": _share(sample, lambda v: bool(DATE_SHAPE.match(v) or DECIMAL.match(v))) >= 0.5}


def _identifier_like(p: dict, label) -> bool:
    """Same test for keys and join children: labelled ID role (or ID-looking values), never text/dates/measures."""
    if p["spaces"] or p["date_or_measure"] or not p["sample"]:
        return False
    if label is not None:
        return label[0] in KEY_ROLES and label[1] not in NOT_ID_SUBTYPES
    return p["id_values"]


def _dense_integers(p: dict) -> bool:
    """Values are exactly 0..N or 1..N: a row counter, which any small integer column would 'join'."""
    if not all(v.isdigit() for v in p["sample"]):
        return False
    nums = pd.to_numeric(pd.Series(p["values"]), errors="coerce")
    return nums.notna().all() and nums.min() <= 1 and nums.max() - nums.min() + 1 == p["distinct"]


def _measure_join(parent: dict, child: dict) -> dict:
    found = child["values"].isin(parent["values"])
    cov = float(found.mean()) if len(found) else 0.0
    return {"coverage": round(cov, 4), "orphans": int((~found).sum())}


def _format_agree(parent: dict, child: dict) -> float:
    """Share of sampled child values inside the parent's length range with a shape seen in the parent.

    A share, not min/max: a few odd orphans must not hide a join (coverage decides those)."""
    lo, hi = parent["len"]
    return _share(child["sample"], lambda v: lo <= len(v) <= hi and _shape(v) in parent["shapes"])


def _confidence(coverage: float, agree: float, distinct: int) -> float:
    return round(coverage * (0.7 + 0.3 * agree * min(1.0, distinct / 100)), 3)


def _repeats(p: dict) -> bool:
    return bool(p["nonblank"]) and p["distinct"] / p["nonblank"] < SUBJECT_MAX_DISTINCT and bool((p["counts"] >= 2).any())


def _tier(label) -> int | None:
    """Person-identifier strength from the detector label: national id, then person ids, then account names."""
    role, sub = label or (None, None)
    if role not in KEY_ROLES:
        return None
    return 0 if sub == "NATIONAL_ID" else 1 if sub in PERSON_IDS else 2 if sub in ACCOUNT_NAMES else None


def _person_row_key(t, df, prof, ref_label, key_refs) -> str | None:
    """S1: a table whose rows are people (a national id, e-mail or phone almost unique per row, even when it is
    sometimes blank) has its own record key as subject: one row = one person, no row left without a subject."""
    people = any(ref_label[f"{t}.{c}"] and ref_label[f"{t}.{c}"][0] == "direct_identifier"
                 and ref_label[f"{t}.{c}"][1] in PERSON_ROW_IDS
                 and prof[f"{t}.{c}"]["nonblank"] >= PERSON_ROW_PRESENT * prof[f"{t}.{c}"]["rows"]
                 and prof[f"{t}.{c}"]["distinct"] >= PERSON_ROW_UNIQUE * prof[f"{t}.{c}"]["nonblank"]
                 for c in df.columns)
    if not people:
        return None
    keys = [f"{t}.{c}" for c in df.columns if f"{t}.{c}" in key_refs]
    keys.sort(key=lambda r: (ref_label[r] is None or ref_label[r][0] != "record_key", list(df.columns).index(r.split(".", 1)[1])))
    return keys[0] if keys else None


def adopt_detect_subjects(rel: dict, suggestions: list[dict]) -> dict:
    """S3: for a table selection resolved no subject for, adopt Detect's subject suggestion when it is confident
    (>= 0.9, not under review) and present on nearly every row (>= 95%, so it leaves no rows without a subject).
    Tables selection resolved itself are never changed. Returns rel with the adopted keys and a notice each."""
    paths = dict(rel.get("subject_paths") or {})
    notices = list(rel.get("notices") or [])
    best = {}
    for s in suggestions:
        t, ref = s["table"], f"{s['table']}.{s['column']}"
        if t in paths or s.get("needs_review") or (s.get("confidence") or 0) < 0.9 or \
                (s.get("non_blank_share") or 0) < 0.95:
            continue
        if t not in best or s["confidence"] > best[t][0]:
            best[t] = (s["confidence"], ref)
    for t, (conf, ref) in sorted(best.items()):
        paths[t] = [ref]
        notices.append(f"subject_adopted: {ref} from the detect linkage artifact (confidence {conf:.2f}); "
                       "selection found no subject for this table")
    if not best:
        return rel
    keys = {t: p[-1] for t, p in sorted(paths.items())}
    return {**rel, "subject_paths": dict(sorted(paths.items())), "subject_keys": keys, "notices": notices,
            "subject_key": rel.get("subject_key") or next(iter(keys.values()), None)}


def _subjects(tables, prof, ref_label, joins, key_refs) -> dict[str, list[str]]:
    """Per table, the path from the table to its subject column: [local ref] or [child, parent, ..., subject].

    A table's own person key (one row per person) beats repeating columns, except a card/account key next to a
    repeating owner (rows are the person's holdings). Staff ids and account names that are not themselves a join
    child give way to a subject inherited through joins."""
    children = {j["child"] for j in joins.values()}
    local, weak = {}, {}
    for t, df in sorted(tables.items()):
        own, ranked = [], []
        for i, c in enumerate(df.columns):
            ref = f"{t}.{c}"
            tier = _tier(ref_label[ref])
            if tier is None:
                continue
            sub, p = ref_label[ref][1], prof[ref]
            cand = (sub in STAFF_IDS, tier, i, ref, sub)
            if ref in key_refs:
                own.append(cand)
            elif p["distinct"] >= MIN_CHILD_DISTINCT and _repeats(p) and \
                    (tier == 0 or (tier == 1 and p["id_values"]) or (tier == 2 and not p["spaces"])):
                ranked.append(cand)
        if own and not (min(own)[4] in HOLDINGS and ranked):
            local[t] = [min(own)[3]]
        elif ranked:
            best = min(ranked)
            (weak if best[0] or (best[1] == 2 and best[3] not in children) else local)[t] = [best[3]]
        elif (row_key := _person_row_key(t, df, prof, ref_label, key_refs)):
            local[t] = [row_key]
    paths = dict(local)
    for _ in tables:
        changed = False
        for j in sorted(joins.values(), key=lambda j: (j["child"], j["parent"])):
            ct, pt = j["child"].split(".", 1)[0], j["parent"].split(".", 1)[0]
            if pt in paths and ct not in local:
                up = paths[pt]
                cand = [j["child"], *up] if up[0] == j["parent"] else [j["child"], j["parent"], *up]
                if ct in {r.split(".", 1)[0] for r in up}:
                    continue
                if ct not in paths or len(cand) < len(paths[ct]):
                    paths[ct], changed = cand, True
        if not changed:
            break
    for t, p in weak.items():
        paths.setdefault(t, p)
    return paths


def discover(tables: dict[str, pd.DataFrame], labels: pd.DataFrame | None = None, declared: dict | None = None) -> dict:
    """Candidate keys, joins (parent key -> child column) and per-table subject keys; see the central README."""
    lab = {} if labels is None else {(r.table, r.column): (r.privacy_role, r.subtype) for r in labels.itertuples()}
    prof = {f"{t}.{c}": _profile(df[c]) for t, df in sorted(tables.items()) for c in df.columns}
    ref_label = {ref: lab.get(tuple(ref.split(".", 1))) for ref in prof}

    keys = []
    for ref, p in prof.items():
        unique = p["distinct"] / p["nonblank"] if p["nonblank"] else 0.0
        if p["nonblank"] and unique >= KEY_UNIQUE and p["blank_rate"] <= KEY_MAX_BLANK \
                and _identifier_like(p, ref_label[ref]):
            keys.append({"column": ref, "unique_ratio": round(unique, 4), "null_rate": round(p["blank_rate"], 4)})

    joins = {}
    for k in keys:
        parent, ptable = prof[k["column"]], k["column"].split(".", 1)[0]
        if _dense_integers(parent):
            continue
        pset = set(parent["values"])
        for ref, child in prof.items():
            if ref.split(".", 1)[0] == ptable or child["distinct"] < MIN_CHILD_DISTINCT \
                    or not _identifier_like(child, ref_label[ref]):
                continue
            agree = _format_agree(parent, child)
            if agree < SHAPE_AGREE:
                continue
            if _share(child["sample"], pset.__contains__) < COVERAGE - .1:
                continue
            m = _measure_join(parent, child)
            if m["coverage"] >= COVERAGE:
                joins[(k["column"], ref)] = {"parent": k["column"], "child": ref, **m,
                                             "confidence": _confidence(m["coverage"], agree, child["distinct"])}
    for (p, c) in list(joins):
        if (c, p) in joins and (prof[p]["distinct"], c) < (prof[c]["distinct"], p):
            del joins[(p, c)]

    conflicts, notices = [], []
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

    if labels is None:
        paths = {}
        notices.append(NO_LABELS)
    else:
        paths = _subjects(tables, prof, ref_label, {j: v for j, v in joins.items() if v["coverage"] >= COVERAGE},
                         {k["column"] for k in keys})
    by_size = sorted(paths, key=lambda t: (-len(tables[t]), t))
    subject_key = paths[by_size[0]][-1] if by_size else None
    want = declared.get("subject_key")
    if want:
        if want not in prof:
            conflicts.append(f"declared subject key {want}: column not found")
        else:
            own_person_key = want in {k["column"] for k in keys} and _tier(ref_label[want]) is not None
            if not _repeats(prof[want]) and not own_person_key:
                conflicts.append(f"declared subject key {want}: values do not repeat across rows")
            paths[want.split(".", 1)[0]] = [want]
        if subject_key is not None and subject_key != want:
            conflicts.append(f"declared subject key {want} contradicts discovered {subject_key}")
        subject_key = want

    return {"keys": sorted(keys, key=lambda k: k["column"]),
            "joins": [joins[j] for j in sorted(joins)],
            "subject_keys": {t: p[-1] for t, p in sorted(paths.items())},
            "subject_paths": dict(sorted(paths.items())),
            "subject_key": subject_key,
            "conflicts": sorted(conflicts),
            "notices": notices}
