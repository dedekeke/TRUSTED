"""Rule matrix and generalisation ladders (plan §6–§7).

Rules are keyed on privacy_role × subtype × trust level, never on column or dataset names. For each column,
`candidates()` returns the allowed rungs finest → coarsest; the search (PET-7) picks one, the transformer
(PET-6) applies it. `violations()` accepts only DROP or a rung the matrix itself offers, so hand-edited plans
cannot bypass it. Pure functions, no I/O.
"""
from __future__ import annotations

from .detect import DIRECT, ENTITY_IDS, REVIEW_BELOW, TECHNICAL

TRUST_LEVELS = ["internal", "contractual", "controlled_research", "public"]
ACTIONS = {"KEEP", "DROP", "HMAC", "GENERALISE", "REDACT", "DERIVE", "WITHHOLD"}  # WITHHOLD is table-level

# Operations the transformer must implement; each rung uses exactly one. Params:
METHODS = {
    "hmac_sha256",      # {domain}: HMAC context shared by join partners; None here, the selector sets it
    "ipv4_prefix",      # {}: truncate an IPv4 address to its /24 (a.b.c.0); generalisation, not pseudonymisation
    "derive_age_band",  # {width, top}: age at the row's event date from DOB, banded; top = start of the open top band.
                        #   Only used through plan["derived"]: the selector turns the DERIVE rung into a derived column
    "age_band",         # {width, top}: band an age value
    "week_hour",        # {}: Monday of the ISO week + HH:00 (exact date removed, hour and week kept)
    "year_hour",        # {}: 1 January of the year + HH:00 (only year and hour of day kept)
    "month_hour",       # {}: first day of the month + HH:00 (exact date and week removed, hour kept)
    "floor_hour",       # {}: YYYY-MM-DD HH:00, floored never rounded
    "date",             # {}: YYYY-MM-DD
    "iso_week",         # {}: YYYY-Www
    "month",            # {}: YYYY-MM
    "year",             # {}: YYYY
    "postcode_prefix",  # {digits}: keep the first n digits
    "suppress_rare",    # {min_count}: blank values seen < min_count times (search's local suppression, not a rung)
    "merge_rare",       # {min_count}: values seen < min_count times become "other"
    "round_decimals",   # {digits}: round coordinates to n decimals
    "round_numeric",    # {step}: round to the nearest multiple of step
    "top_bottom_code",  # {lower_q, upper_q}: clamp values outside these quantiles (transformer supports it; no rung yet)
    "icd_3char",        # {}: ICD-10 category, e.g. J18.9 -> J18
    "diagnosis_group",  # {mapping}: must be "pets_eval.utility.health.diagnosis_group"; unmapped codes become blank
    "icd_chapter",      # {}: first letter of the ICD-10 code
    "redact_spans",     # {profile}: replace detected PII spans with typed placeholders
}
NEEDS_METHOD = {"HMAC", "GENERALISE", "DERIVE", "REDACT"}

PUBLIC_ESCALATION = "row-level release not suitable: needs aggregate/DP path"
IDS = {"direct_identifier", "technical_identifier", "record_key"}
TIME_SUBTYPES = {"TIMESTAMP", "DATE", "BIRTH_DATE"}
CATEGORICAL_QI = {"MUNICIPALITY", "LOCATION_NAME", "ORG_NAME", "OCCUPATION", "LANGUAGE", "SEX", "CATEGORY",
                  "NATIONALITY"}
NUMERIC = {"MEASUREMENT", "FINANCIAL_DATA", "DURATION"}
# Identifier subtypes are handled as identifiers whatever role a label gives them (a raw email is never KEEP).
ID_SUBTYPE_ROLE = {**{s: "direct_identifier" for s in DIRECT | {"NATIONAL_ID"}},
                   **{s: "technical_identifier" for s in TECHNICAL | ENTITY_IDS | {"IMEI"}},
                   "ENTITY_ID": "technical_identifier", "RECORD_ID": "record_key"}
# Subtypes handled by their own rules when the label's role doesn't fit them: subtype -> (role used, roles accepted).
SUBTYPE_REROUTE = {
    **{s: (r, IDS) for s, r in ID_SUBTYPE_ROLE.items()},
    "BIRTH_DATE": ("quasi_identifier", {"quasi_identifier", "sensitive_attribute"}),  # derive-only in any role
    # identifier roles are stricter than these subtypes' own rules, so they are never rerouted
    "FREE_TEXT": ("free_text", IDS | {"free_text"}),
    "DIAGNOSIS_CODE": ("sensitive_attribute", IDS | {"sensitive_attribute", "quasi_identifier"}),
    "STREET_ADDRESS": ("quasi_identifier", IDS | {"quasi_identifier", "sensitive_attribute"}),
}
AGE_TOP = 80  # canonical bands 0-9 … 80+ (plan §9)


def _r(action, method=None, **params) -> dict:
    return {"action": action, "method": method, "params": params}


KEEP, DROP = _r("KEEP"), _r("DROP")
HMAC = _r("HMAC", "hmac_sha256", domain=None)

# Ladders: list of (precision tag, rung), finest → coarsest. The tag is what `precision=` refers to.
_AGE = [(str(w), _r("GENERALISE", "age_band", width=w, top=AGE_TOP)) for w in (5, 10, 20)]
_DOB = [(str(w), _r("DERIVE", "derive_age_band", width=w, top=AGE_TOP)) for w in (5, 10, 20)]
# hour-preserving rungs first (week/month start + HH:00 keep the hour-of-day curve, drop the exact date)
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
# shortcut: fixed absolute steps ignore the column's scale; switch to spec-given minimum precision when specs exist
_NUMERIC = [("exact", KEEP)] + [(str(s), _r("GENERALISE", "round_numeric", step=s)) for s in (1, 10, 100)]


def _categorical(k: int) -> list:
    # merging only values rarer than k rarely closes small classes; the stronger rungs keep only common values
    return [("exact", KEEP), ("merged", _r("GENERALISE", "merge_rare", min_count=k)),
            ("merged", _r("GENERALISE", "merge_rare", min_count=k * 20)),
            ("merged", _r("GENERALISE", "merge_rare", min_count=k * 200))]


# Ladders keyed on subtype; also used when a sensitive attribute has one of these subtypes.
SUBTYPE_LADDERS = {"AGE": _AGE, "BIRTH_DATE": _DOB, "TIMESTAMP": _TIMESTAMP, "DATE": _DATE, "POSTCODE": _POSTCODE,
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
    """Risk target for a trust level; scenario_targets overrides individual keys. Loosening is noted, never silent."""
    _check_trust(trust_level)
    base = {**DEFAULT_TARGETS[trust_level], "max_suppression": MAX_SUPPRESSION}
    over = scenario_targets or {}
    notes = []
    for key, new in over.items():
        old = base.get(key)
        looser = (key in ("k", "l") and (old is None or new < old)) or \
                 (key == "max_suppression" and new > old) or (key == "free_text" and old is False and new)
        if looser:
            notes.append(f"scenario loosens {key}: {old} -> {new} (trust-level default for {trust_level})")
    return {**base, **over, "notes": notes}


def _ladder(role: str, sub: str, trust_level: str, required: bool, in_join: bool, k: int, notes: list) -> tuple:
    """(tagged ladder, escalate). Ladders here never include DROP; DROP is appended by the caller."""
    if role in IDS:
        if not (required or in_join):
            return [], None
        if role == "technical_identifier" and sub == "IP_ADDRESS" and not in_join:
            # HMAC keeps addresses distinct; the /24 groups them (a location-type QI), so it is the coarser rung
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
        return [(None, _r("REDACT", "redact_spans", profile="typed_placeholders"))], None
    if role == "non_sensitive":
        return [("exact", KEEP)], None
    raise ValueError(f"unknown privacy_role {role!r}")


def candidates(label: dict, trust_level: str, required: bool, in_join: bool = False,
               precision: str | int | None = None, k: int | None = None) -> dict:
    """Allowed rungs for one column, finest → coarsest, plus review/escalation flags.

    k: effective risk target (pass targets(...)["k"]); sets merge_rare's min_count. Defaults to the trust level's k.
    """
    _check_trust(trust_level)
    role, sub = label["privacy_role"], label.get("subtype")
    notes = []
    if sub in SUBTYPE_REROUTE and role not in SUBTYPE_REROUTE[sub][1]:
        notes.append(f"{sub} labelled {role}: handled as {SUBTYPE_REROUTE[sub][0]}, review")
        role = SUBTYPE_REROUTE[sub][0]
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
            ladder = ladder[: len(tags) - tags[::-1].index(str(precision))]  # keep every rung at that precision
    rungs = [r for _, r in ladder]
    if low_conf:
        # deny by default: unconfirmed labels get only the coarsest protective rung, never KEEP
        rungs = [r for r in rungs[-1:] if r["action"] != "KEEP"] if needed else []
        notes.append("low-confidence label: " + ("coarsest rung or DROP only" if needed else "dropped (deny by default)"))
    # DROP closes the ladder unless the column is needed and confirmed (precision asked for = needed)
    if not rungs or low_conf or not (needed or precision is not None):
        rungs.append(DROP)
    rungs = [{**r, "params": dict(r["params"]), "level": i} for i, r in enumerate(rungs)]
    return {"rungs": rungs, "needs_review": needs_review, "escalate": escalate, "notes": notes}


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
