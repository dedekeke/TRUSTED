"""Rule matrix and generalisation ladders (plan §6–§7).

Rules are keyed on privacy_role × subtype × trust level, never on column or dataset names. For each column,
`candidates()` returns the allowed rungs finest → coarsest; the search (PET-7) picks one, the transformer
(PET-6) applies it. `violations()` re-checks the hard constraints on any rung, including hand-edited plans.
Pure functions, no I/O.
"""
from __future__ import annotations

from .detect import REVIEW_BELOW

TRUST_LEVELS = ["internal", "contractual", "controlled_research", "public"]
ACTIONS = {"KEEP", "DROP", "HMAC", "GENERALISE", "REDACT", "DERIVE", "WITHHOLD"}  # WITHHOLD is table-level

# Operations the transformer must implement; each rung uses exactly one. Params:
METHODS = {
    "hmac_sha256",      # {domain}: HMAC context shared by join partners; None here, the selector sets it
    "ipv4_prefix",      # {}: prefix-preserving IPv4 pseudonymisation (baselines/_common.py)
    "derive_age_band",  # {width, top}: age at the row's event date from DOB, banded; top = open-ended top band start
    "age_band",         # {width, top}: band an age value
    "floor_hour",       # {}: YYYY-MM-DD HH:00, floored never rounded
    "date",             # {}: YYYY-MM-DD
    "iso_week",         # {}: YYYY-Www
    "month",            # {}: YYYY-MM
    "year",             # {}: YYYY
    "postcode_prefix",  # {digits}: keep the first n digits
    "suppress_rare",    # {min_count}: blank values seen < min_count times (local suppression, used by the search)
    "merge_rare",       # {min_count}: values seen < min_count times become "other"
    "round_decimals",   # {digits}: round coordinates to n decimals
    "round_numeric",    # {step}: round to the nearest multiple of step
    "top_bottom_code",  # {lower_q, upper_q}: clamp values outside these quantiles
    "icd_3char",        # {}: ICD-10 category, e.g. J18.9 -> J18
    "diagnosis_group",  # {mapping}: toolkit diagnosis groups; unmapped codes become blank, never raw
    "icd_chapter",      # {}: first letter of the ICD-10 code
    "redact_spans",     # {profile}: replace detected PII spans with typed placeholders
}
NEEDS_METHOD = {"HMAC", "GENERALISE", "DERIVE", "REDACT"}

PUBLIC_ESCALATION = "row-level release not suitable: needs aggregate/DP path"
TIME_SUBTYPES = {"TIMESTAMP", "DATE", "BIRTH_DATE"}
CATEGORICAL_QI = {"MUNICIPALITY", "LOCATION_NAME", "ORG_NAME", "OCCUPATION", "LANGUAGE", "SEX", "CATEGORY",
                  "NATIONALITY"}
NUMERIC = {"MEASUREMENT", "FINANCIAL_DATA", "DURATION"}
AGE_TOP = 80  # canonical bands 0-9 … 80+ (plan §9)


def _r(action, method=None, **params) -> dict:
    return {"action": action, "method": method, "params": params}


KEEP, DROP = _r("KEEP"), _r("DROP")
HMAC = _r("HMAC", "hmac_sha256", domain=None)

# Ladders: list of (precision tag, rung), finest → coarsest. The tag is what `precision=` refers to.
_AGE = [(str(w), _r("GENERALISE", "age_band", width=w, top=AGE_TOP)) for w in (5, 10, 20)]
_DOB = [(str(w), _r("DERIVE", "derive_age_band", width=w, top=AGE_TOP)) for w in (5, 10, 20)]
_TIMESTAMP = [("hour", _r("GENERALISE", "floor_hour")), ("date", _r("GENERALISE", "date")),
              ("week", _r("GENERALISE", "iso_week")), ("month", _r("GENERALISE", "month"))]
_DATE = [("date", _r("GENERALISE", "date")), ("week", _r("GENERALISE", "iso_week")),
         ("month", _r("GENERALISE", "month")), ("year", _r("GENERALISE", "year"))]
_POSTCODE = [("5", KEEP), ("3", _r("GENERALISE", "postcode_prefix", digits=3)),
             ("2", _r("GENERALISE", "postcode_prefix", digits=2))]
_GPS = [(str(d), _r("GENERALISE", "round_decimals", digits=d)) for d in (3, 2, 1)]
_DIAGNOSIS = [("exact", KEEP), ("3char", _r("GENERALISE", "icd_3char")),
              ("group", _r("GENERALISE", "diagnosis_group", mapping="pets_eval.utility.health.diagnosis_group")),
              ("chapter", _r("GENERALISE", "icd_chapter"))]
# proposal: step 1 and 1st/99th percentiles until a spec gives the analysis's minimum precision
_NUMERIC = [("exact", KEEP), ("rounded", _r("GENERALISE", "round_numeric", step=1)),
            ("coded", _r("GENERALISE", "top_bottom_code", lower_q=0.01, upper_q=0.99))]


def _categorical(k: int) -> list:
    return [("exact", KEEP), ("merged", _r("GENERALISE", "merge_rare", min_count=k))]


QI_LADDERS = {"AGE": _AGE, "BIRTH_DATE": _DOB, "TIMESTAMP": _TIMESTAMP, "DATE": _DATE, "POSTCODE": _POSTCODE,
              "GPS_COORDINATE": _GPS, **{s: _NUMERIC for s in NUMERIC}}

# Default risk targets per trust level. Proposals (plan §6), to confirm; a scenario's own target overrides them.
DEFAULT_TARGETS = {
    "internal": {"k": 3},
    "contractual": {"k": 5, "l": 2},
    "controlled_research": {"k": 5, "l": 2},
    "public": {"k": 10, "l": 3, "free_text": False},
}
MAX_SUPPRESSION = 0.02  # local suppression budget, share of rows (plan §7.5)


def _check_trust(trust_level: str) -> None:
    if trust_level not in TRUST_LEVELS:
        raise ValueError(f"unknown trust level {trust_level!r}; expected one of {TRUST_LEVELS}")


def targets(trust_level: str, scenario_targets: dict | None = None) -> dict:
    """Risk target for a trust level; scenario_targets overrides individual keys."""
    _check_trust(trust_level)
    return {**DEFAULT_TARGETS[trust_level], "max_suppression": MAX_SUPPRESSION, **(scenario_targets or {})}


def _ladder(role: str, sub: str, trust_level: str, required: bool, in_join: bool, notes: list) -> tuple:
    """(tagged ladder, escalate). Ladders here never include DROP; DROP is appended by the caller."""
    k = DEFAULT_TARGETS[trust_level]["k"]
    if role in ("direct_identifier", "technical_identifier", "record_key"):
        if not (required or in_join):
            return [], None
        if role == "technical_identifier" and sub == "IP_ADDRESS" and not in_join:
            return [(None, _r("HMAC", "ipv4_prefix")), (None, HMAC)], None
        return [(None, HMAC)], None
    if role == "quasi_identifier":
        if not required:
            return [], None
        if sub == "STREET_ADDRESS":
            notes.append("street address has no safe row-level form; dropped although required, review")
            return [], None
        if sub in QI_LADDERS:
            return QI_LADDERS[sub], None
        if sub in CATEGORICAL_QI:
            return _categorical(k), None
        notes.append(f"no ladder for quasi-identifier subtype {sub}; dropped, review")
        return [], None
    if role == "sensitive_attribute":
        if not required:
            return [], None
        esc = PUBLIC_ESCALATION if trust_level == "public" else None
        if sub == "DIAGNOSIS_CODE":
            return (_DIAGNOSIS if trust_level == "internal" else _DIAGNOSIS[1:]), esc
        if sub in NUMERIC:
            return _NUMERIC, esc
        return _categorical(k), esc
    if role == "free_text":
        if not required:
            return [], None
        if trust_level == "public":
            return [], "free text not releasable at public trust: needs aggregate/DP path"
        return [(None, _r("REDACT", "redact_spans", profile="typed_placeholders"))], None
    if role == "non_sensitive":
        return [("exact", KEEP)], None
    raise ValueError(f"unknown privacy_role {role!r}")


def candidates(label: dict, trust_level: str, required: bool, in_join: bool = False,
               precision: str | int | None = None) -> dict:
    """Allowed rungs for one column, finest → coarsest, plus review/escalation flags."""
    _check_trust(trust_level)
    role, sub = label["privacy_role"], label.get("subtype")
    needs_review = float(label.get("confidence", 0.0)) < REVIEW_BELOW
    notes = []
    ladder, escalate = _ladder(role, sub, trust_level, required, in_join, notes)
    needs_review = needs_review or bool(notes)
    if needs_review and not required and not in_join:
        notes.append("low-confidence label, not required: dropped (deny by default)")
        ladder = []
    if precision is not None and ladder:
        tags = [t for t, _ in ladder]
        if all(t is None for t in tags):
            notes.append(f"precision {precision!r} not applicable to this ladder; ignored")
        elif str(precision) not in tags:
            raise ValueError(f"precision {precision!r} not in ladder {tags} for {role}/{sub}")
        else:
            ladder = ladder[: tags.index(str(precision)) + 1]
    rungs = [r for _, r in ladder]
    # DROP closes the ladder unless the column is needed (required, joined, or a precision was asked for)
    if not rungs or not (required or in_join or precision is not None):
        rungs.append(DROP)
    rungs = [{**r, "params": dict(r["params"]), "level": i} for i, r in enumerate(rungs)]
    return {"rungs": rungs, "needs_review": needs_review, "escalate": escalate, "notes": notes}


def violations(label: dict, rung: dict, trust_level: str) -> list[str]:
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
    if action == "KEEP" and role in ("direct_identifier", "technical_identifier", "record_key"):
        out.append(f"{role} must never be kept raw")
    if sub == "BIRTH_DATE" and (action == "KEEP" or method in ("date", "floor_hour")):
        out.append("exact birth date must never be released")
    if sub in TIME_SUBTYPES and method in ("round_numeric", "round_decimals"):
        out.append("time must be floored, never rounded")
    if role == "free_text" and trust_level == "public" and action in ("KEEP", "REDACT"):
        out.append("free text must not be released at public trust")
    return out
