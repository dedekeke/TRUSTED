"""Rule matrix and generalisation ladders.

Rules are keyed on privacy_role × subtype × trust level, never on column or dataset names. For each column,
`candidates()` returns the allowed rungs finest → coarsest; `search` picks one, `server.transform`
applies it. `violations()` accepts only DROP or a rung the matrix itself offers, so hand-edited plans
cannot bypass it. Pure functions, no I/O.
"""
from __future__ import annotations

from .detect import DIRECT, ENTITY_IDS, REVIEW_BELOW, TECHNICAL

TRUST_LEVELS = ["internal", "contractual", "controlled_research", "public"]
ENTITY_PSEUDONYM_TRUST = {"internal", "contractual"}
ACTIONS = {"KEEP", "DROP", "HMAC", "GENERALISE", "REDACT", "DERIVE", "WITHHOLD"}

METHODS = {
    "hmac_sha256",
    "ipv4_prefix",
    "derive_age_band",
    "age_band",
    "week_hour",
    "year_hour",
    "month_hour",
    "floor_hour",
    "date",
    "iso_week",
    "month",
    "year",
    "postcode_prefix",
    "suppress_rare",
    "merge_rare",
    "round_decimals",
    "round_numeric",
    "top_bottom_code",
    "icd_3char",
    "diagnosis_group",
    "icd_chapter",
    "url_host",
    "registrable_domain",
    "redact_spans",
}
NEEDS_METHOD = {"HMAC", "GENERALISE", "DERIVE", "REDACT"}

PUBLIC_ESCALATION = "row-level release not suitable: needs aggregate/DP path"
IDS = {"direct_identifier", "technical_identifier", "record_key"}
TIME_SUBTYPES = {"TIMESTAMP", "DATE", "BIRTH_DATE"}
CATEGORICAL_QI = {"MUNICIPALITY", "LOCATION_NAME", "ORG_NAME", "OCCUPATION", "LANGUAGE", "SEX", "CATEGORY",
                  "NATIONALITY"}
NUMERIC = {"MEASUREMENT", "FINANCIAL_DATA", "DURATION"}
ID_SUBTYPE_ROLE = {**{s: "direct_identifier" for s in DIRECT | {"NATIONAL_ID"}},
                   **{s: "technical_identifier" for s in TECHNICAL | ENTITY_IDS | {"IMEI"}},
                   "ENTITY_ID": "technical_identifier", "RECORD_ID": "record_key"}
SUBTYPE_REROUTE = {
    **{s: (r, IDS) for s, r in ID_SUBTYPE_ROLE.items()},
    "BIRTH_DATE": ("quasi_identifier", {"quasi_identifier", "sensitive_attribute"}),
    "FREE_TEXT": ("free_text", IDS | {"free_text"}),
    "DIAGNOSIS_CODE": ("sensitive_attribute", IDS | {"sensitive_attribute", "quasi_identifier"}),
    "STREET_ADDRESS": ("quasi_identifier", IDS | {"quasi_identifier", "sensitive_attribute"}),
}
AGE_TOP = 80
ROLES = IDS | {"quasi_identifier", "sensitive_attribute", "free_text", "non_sensitive"}
TAXONOMY_SUBTYPES = set("""PERSON_NAME NATIONAL_ID EMAIL PHONE STREET_ADDRESS POSTCODE MUNICIPALITY GPS_COORDINATE
    LOCATION_NAME BIRTH_DATE AGE SEX LANGUAGE NATIONALITY IBAN PAYMENT_CARD CUSTOMER_ID ACCOUNT_ID EMPLOYEE_ID
    STUDENT_ID PATIENT_ID CARD_ID DEVICE_ID IP_ADDRESS MAC_ADDRESS IMEI HOSTNAME USERNAME URL USER_AGENT LICENSE_PLATE
    PROPERTY_ID METER_ID TIMESTAMP DATE DURATION HEALTH_DATA DIAGNOSIS_CODE FINANCIAL_DATA EDUCATION_DATA SOCIAL_DATA
    OCCUPATION ORG_NAME MEASUREMENT CATEGORY AGGREGATE SECRET FREE_TEXT RECORD_ID OTHER""".split()) | {"ENTITY_ID"}
SENSITIVE_CATEGORICAL = CATEGORICAL_QI | {"HEALTH_DATA", "EDUCATION_DATA", "SOCIAL_DATA"}
NEVER_RAW = {"SECRET", "HEALTH_DATA", "EDUCATION_DATA", "SOCIAL_DATA"}


def _r(action, method=None, **params) -> dict:
    return {"action": action, "method": method, "params": params}


KEEP, DROP = _r("KEEP"), _r("DROP")
HMAC = _r("HMAC", "hmac_sha256", domain=None)

_AGE = [(str(w), _r("GENERALISE", "age_band", width=w, top=AGE_TOP)) for w in (5, 10, 20)]
_DOB = [(str(w), _r("DERIVE", "derive_age_band", width=w, top=AGE_TOP)) for w in (5, 10, 20)]
_TIMESTAMP = [("hour", _r("GENERALISE", "floor_hour")), ("hour", _r("GENERALISE", "week_hour")),
              ("hour", _r("GENERALISE", "month_hour")), ("hour", _r("GENERALISE", "year_hour")),
              ("date", _r("GENERALISE", "date")),
              ("week", _r("GENERALISE", "iso_week")), ("month", _r("GENERALISE", "month"))]
_DATE = [("date", _r("GENERALISE", "date")), ("week", _r("GENERALISE", "iso_week")),
         ("month", _r("GENERALISE", "month")), ("year", _r("GENERALISE", "year"))]
_POSTCODE = [("5", KEEP), ("3", _r("GENERALISE", "postcode_prefix", digits=3)),
             ("2", _r("GENERALISE", "postcode_prefix", digits=2))]
_GPS = [(str(d), _r("GENERALISE", "round_decimals", digits=d)) for d in (3, 2, 1)]
_DIAGNOSIS = [("exact", KEEP), ("3char", _r("GENERALISE", "icd_3char")),
              ("group", _r("GENERALISE", "diagnosis_group", mapping="pets_eval.utility.health.diagnosis_group")),
              ("chapter", _r("GENERALISE", "icd_chapter"))]
_NUMERIC = [("exact", KEEP)] + [(str(s), _r("GENERALISE", "round_numeric", step=s)) for s in (1, 10, 100)]


def _categorical(k: int) -> list:
    return [("exact", KEEP), ("merged", _r("GENERALISE", "merge_rare", min_count=k)),
            ("merged", _r("GENERALISE", "merge_rare", min_count=k * 20)),
            ("merged", _r("GENERALISE", "merge_rare", min_count=k * 200))]


_URL = [("host", _r("GENERALISE", "url_host")), ("domain", _r("GENERALISE", "registrable_domain"))]

SUBTYPE_LADDERS = {"AGE": _AGE, "BIRTH_DATE": _DOB, "TIMESTAMP": _TIMESTAMP, "DATE": _DATE, "POSTCODE": _POSTCODE,
                   "GPS_COORDINATE": _GPS, "URL": _URL, **{s: _NUMERIC for s in NUMERIC}}

DEFAULT_TARGETS = {
    "internal": {"k": 3},
    "contractual": {"k": 5, "l": 2},
    "controlled_research": {"k": 5, "l": 2},
    "public": {"k": 10, "l": 3, "free_text": False},
}
MAX_SUPPRESSION = 0.02
MAX_UNKNOWN_SUBJECTS = 0.05


def _check_trust(trust_level: str) -> None:
    if trust_level not in TRUST_LEVELS:
        raise ValueError(f"unknown trust level {trust_level!r}; expected one of {TRUST_LEVELS}")


def targets(trust_level: str, scenario_targets: dict | None = None) -> dict:
    """Risk target for a trust level; scenario_targets overrides individual keys. Loosening is noted, never silent."""
    _check_trust(trust_level)
    base = {**DEFAULT_TARGETS[trust_level], "max_suppression": MAX_SUPPRESSION,
            "max_unknown_subjects": MAX_UNKNOWN_SUBJECTS}
    over = scenario_targets or {}
    notes = []
    for key, new in over.items():
        old = base.get(key)
        looser = (key in ("k", "l") and (old is None or new < old)) or \
                 (key in ("max_suppression", "max_unknown_subjects") and new > old) or \
                 (key == "free_text" and old is False and new)
        if looser:
            notes.append(f"scenario loosens {key}: {old} -> {new} (trust-level default for {trust_level})")
    return {**base, **over, "notes": notes}


def _ladder(role: str, sub: str, trust_level: str, required: bool, in_join: bool, k: int, notes: list) -> tuple:
    """(tagged ladder, escalate). Ladders here never include DROP; DROP is appended by the caller."""
    if role in IDS:
        if not (required or in_join):
            return [], None
        if role == "technical_identifier" and sub == "IP_ADDRESS" and not in_join:
            return [(None, HMAC), (None, _r("GENERALISE", "ipv4_prefix"))], None
        return [(None, HMAC)], None
    if role == "quasi_identifier":
        if not required:
            return [], None
        if sub == "STREET_ADDRESS":
            notes.append("street address has no safe row-level form; dropped although required, review")
            return [], None
        if sub in SUBTYPE_LADDERS:
            return SUBTYPE_LADDERS[sub], None
        if sub in CATEGORICAL_QI:
            return _categorical(k), None
        notes.append(f"no ladder for quasi-identifier subtype {sub}; dropped, review")
        return [], None
    if role == "sensitive_attribute":
        if not required:
            return [], None
        if trust_level == "public":
            return [], PUBLIC_ESCALATION
        if sub == "DIAGNOSIS_CODE":
            return (_DIAGNOSIS if trust_level == "internal" else _DIAGNOSIS[1:]), None
        if sub == "STREET_ADDRESS":
            notes.append("street address has no safe row-level form; dropped although required, review")
            return [], None
        if sub in SUBTYPE_LADDERS:
            return SUBTYPE_LADDERS[sub], None
        return _categorical(k), None
    if role == "free_text":
        if not required:
            return [], None
        if trust_level == "public":
            return [], "free text not releasable at public trust: needs aggregate/DP path"
        profile = "entity_pseudonyms" if trust_level in ENTITY_PSEUDONYM_TRUST else "typed_placeholders"
        return [(None, _r("REDACT", "redact_spans", profile=profile))], None
    if role == "non_sensitive":
        return [("exact", KEEP)], None
    raise ValueError(f"unknown privacy_role {role!r}")


def _route(role, sub):
    if sub in SUBTYPE_REROUTE and role not in SUBTYPE_REROUTE[sub][1]:
        return SUBTYPE_REROUTE[sub][0], True
    return role, False


def unsupported(role: str, sub: str) -> str | None:
    """Why a (role, subtype) pair has no protective policy (handled as DROP + unsupported_label review), else None."""
    if role not in ROLES:
        return f"unknown privacy_role {role!r}"
    if sub not in TAXONOMY_SUBTYPES:
        return f"subtype {sub!r} is not in the taxonomy"
    role, _ = _route(role, sub)
    if role == "quasi_identifier" and sub not in SUBTYPE_LADDERS and sub not in CATEGORICAL_QI:
        return f"no generalisation ladder for quasi-identifier subtype {sub}"
    if role == "sensitive_attribute" and sub != "DIAGNOSIS_CODE" and sub not in SUBTYPE_LADDERS \
            and sub not in SENSITIVE_CATEGORICAL:
        return f"no protective rule for sensitive subtype {sub}"
    if role == "non_sensitive" and sub in NEVER_RAW:
        return f"{sub} cannot be kept raw as non_sensitive"
    return None


def coverage(pairs) -> dict:
    """Coverage of (role, subtype) pairs by the rule matrix; unsupported ones are listed, never KEEP."""
    pairs = sorted({(str(r), str(s)) for r, s in pairs})
    bad = [{"role": r, "subtype": s, "reason": why} for r, s in pairs if (why := unsupported(r, s))]
    return {"pairs": len(pairs), "unsupported": bad}


def candidates(label: dict, trust_level: str, required: bool, in_join: bool = False,
               precision: str | int | None = None, k: int | None = None) -> dict:
    """Allowed rungs for one column, finest → coarsest, plus review/escalation flags.

    k: effective risk target (pass targets(...)["k"]); sets merge_rare's min_count. Defaults to the trust level's k.
    """
    _check_trust(trust_level)
    role, sub = label["privacy_role"], label.get("subtype")
    notes = []
    if role not in ROLES:
        raise ValueError(f"unknown privacy_role {role!r}")
    why = unsupported(role, sub)
    if why:
        return {"rungs": [{**DROP, "params": {}, "level": 0}], "needs_review": True, "escalate": None,
                "notes": [f"unsupported_label: {why}"], "unsupported": why}
    routed, moved = _route(role, sub)
    if moved:
        notes.append(f"{sub} labelled {role}: handled as {routed}, review")
        role = routed
    low_conf = float(label.get("confidence", 0.0)) < REVIEW_BELOW
    k = DEFAULT_TARGETS[trust_level]["k"] if k is None else int(k)
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    ladder, escalate = _ladder(role, sub, trust_level, required, in_join, k, notes)
    needs_review = low_conf or bool(notes)
    needed = required or in_join
    if precision is not None and ladder:
        tags = [t for t, _ in ladder]
        if all(t is None for t in tags):
            notes.append(f"precision {precision!r} not applicable to this ladder; ignored")
        elif str(precision) not in tags:
            raise ValueError(f"precision {precision!r} not in ladder {tags} for {role}/{sub}")
        else:
            ladder = ladder[: len(tags) - tags[::-1].index(str(precision))]
    rungs = [r for _, r in ladder]
    if low_conf:
        rungs = [r for r in rungs[-1:] if r["action"] != "KEEP"] if needed else []
        notes.append("low-confidence label: " + ("coarsest rung or DROP only" if needed else "dropped (deny by default)"))
    if not rungs or low_conf or not (needed or precision is not None):
        rungs.append(DROP)
    rungs = [{**r, "params": dict(r["params"]), "level": i} for i, r in enumerate(rungs)]
    return {"rungs": rungs, "needs_review": needs_review, "escalate": escalate, "notes": notes, "unsupported": None,
            "uncertain": low_conf}


def _matches(rung: dict, allowed: dict) -> bool:
    """Same action, method and params; an allowed param of None (HMAC domain) accepts any set value."""
    p, q = rung.get("params") or {}, allowed["params"]
    return (rung.get("action"), rung.get("method")) == (allowed["action"], allowed["method"]) and p.keys() == q.keys() \
        and all((p[key] is not None) if v is None else p[key] == v for key, v in q.items())


def violations(label: dict, rung: dict, trust_level: str, k: int | None = None) -> list[str]:
    """Hard-constraint breaches of one rung for one column; empty list means allowed."""
    _check_trust(trust_level)
    role, sub = label.get("privacy_role"), label.get("subtype")
    action, method = rung.get("action"), rung.get("method")
    out = []
    if action not in ACTIONS:
        out.append(f"unknown action {action!r}")
    if method is not None and method not in METHODS:
        out.append(f"unknown method {method!r}")
    if action in NEEDS_METHOD and method is None:
        out.append(f"{action} needs a method")
    if action in ("KEEP", "DROP", "WITHHOLD") and method is not None:
        out.append(f"{action} takes no method")
    if action == "KEEP" and (role in IDS or sub in ID_SUBTYPE_ROLE):
        out.append(f"{role}/{sub} must never be kept raw")
    if sub == "BIRTH_DATE" and (action == "KEEP" or method in ("date", "floor_hour")):
        out.append("exact birth date must never be released")
    if sub in TIME_SUBTYPES and method in ("round_numeric", "round_decimals"):
        out.append("time must be floored, never rounded")
    if role == "free_text" and trust_level == "public" and action in ("KEEP", "REDACT"):
        out.append("free text must not be released at public trust")
    if out or (action == "DROP" and method is None):
        return out
    try:
        allowed = [r for join in (True, False) for r in candidates(label, trust_level, True, join, k=k)["rungs"]]
    except (KeyError, ValueError) as e:
        return [f"label not covered by the rule matrix: {e}"]
    if not any(_matches(rung, a) for a in allowed):
        out.append(f"{action}/{method} {rung.get('params')} is not an allowed rung for {role}/{sub} at {trust_level}")
    return out
