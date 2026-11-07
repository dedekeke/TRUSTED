"""Tier 1: deterministic rules over a column profile.

Order of evidence: value patterns with checksums (strongest) > structure (keys, foreign keys, cardinality) >
column-name hints (weakest; useless on obfuscated headers) > table context (is this table about people?).
Every decision carries a confidence and a human-readable reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from . import patterns as P


@dataclass
class Decision:
    privacy_role: str
    subtype: str
    confidence: float
    reason: str
    source: str = "rules"

    def to_dict(self):
        return asdict(self)


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def _id_subtype(name: str, default: str = "RECORD_ID") -> str:
    for rx, st in P.ID_SUBTYPE_HINTS:
        if re.search(rx, name):
            return st
    return default


def _name_hint(name: str):
    for rx, role, st, w in P.NAME_HINTS:
        if re.search(rx, name):
            return role, st, w
    return None


def value_rules(p: dict) -> Decision | None:
    """Strong evidence from the values themselves (works on obfuscated headers)."""
    name = p["column"].lower()
    checks = [
        ("m_hetu_valid", .5, "direct_identifier", "NATIONAL_ID", .98, "valid Finnish identity codes (checksum ok)"),
        ("m_iban", .5, "direct_identifier", "IBAN", .97, "valid IBANs (mod-97 ok)"),
        ("m_email_list", .3, "direct_identifier", "EMAIL", .93, "lists of e-mail addresses"),
        ("m_email", .6, "direct_identifier", "EMAIL", .93, "e-mail addresses"),
        ("m_pan_masked", .5, "direct_identifier", "PAYMENT_CARD", .9, "masked card numbers"),
        ("m_mac", .6, "technical_identifier", "MAC_ADDRESS", .95, "MAC addresses"),
        ("m_user_agent", .5, "technical_identifier", "USER_AGENT", .93, "browser user-agent strings"),
        ("m_ipv4", .6, "technical_identifier", "IP_ADDRESS", .93, "IPv4 addresses"),
        ("m_plate", .6, "direct_identifier", "LICENSE_PLATE", .9, "Finnish licence plates"),
        ("m_url", .6, "free_text", "URL", .85, "full URLs (paths and query strings may hold secrets)"),
        ("m_icd10", .6, "sensitive_attribute", "DIAGNOSIS_CODE", .9, "ICD-10 diagnosis codes"),
    ]
    for key, thr, role, st, conf, why in checks:
        if p[key] >= thr:
            return Decision(role, st, conf, f"{_pct(p[key])} of values are {why}")
    # card numbers: Luhn-valid 13-19 digits that are not mostly phone numbers
    if p["m_pan"] >= .6 and p["m_phone"] < .3:
        return Decision("direct_identifier", "PAYMENT_CARD", .92, f"{_pct(p['m_pan'])} Luhn-valid card numbers")
    if p["m_phone"] >= .6:
        return Decision("direct_identifier", "PHONE", .9, f"{_pct(p['m_phone'])} of values are phone numbers")
    if p["m_address"] >= .6 and p["unique_ratio"] > .1:
        return Decision("direct_identifier", "STREET_ADDRESS", .85,
                        f"{_pct(p['m_address'])} of values look like street addresses")
    # free text: long, multi-word values
    if p["mean_words"] >= 5 and p["unique_ratio"] > .3:
        return Decision("free_text", "FREE_TEXT", .9,
                        f"long free text (avg {p['mean_words']:.1f} words, {_pct(p['unique_ratio'])} unique)")
    # timestamps / dates
    if p["m_timestamp"] >= .6:
        return Decision("quasi_identifier", "TIMESTAMP", .8, f"{_pct(p['m_timestamp'])} of values are date-times")
    if p["m_date"] >= .6 or (p["m_month"] >= .6 and p["n_unique"] > 3):
        ym, span = p["year_median"], p["year_span"]
        if ym and ym < 2008 and span and span >= 20:
            return Decision("quasi_identifier", "BIRTH_DATE", .85,
                            f"dates spanning {span} years with median year {ym:.0f}: looks like birth dates")
        return Decision("quasi_identifier", "DATE", .75, f"{_pct(max(p['m_date'], p['m_month']))} of values are dates")
    if p["m_coord"] >= .6:
        return Decision("quasi_identifier", "GPS_COORDINATE", .85, "decimal coordinates with >= 4 decimals")
    if p["m_postcode"] >= .8 and p["num_min"] is not None and p["num_min"] >= 1000 and p["n_unique"] > 5:
        return Decision("quasi_identifier", "POSTCODE", .85, "5-digit Finnish postcodes")
    if p["m_sex"] >= .95 and p["n_unique"] <= 4:
        return Decision("quasi_identifier", "SEX", .9, f"values {[v for v, _ in p['top_values'][:4]]} encode sex")
    if p["m_lang"] >= .9 and p["n_unique"] <= 15:
        return Decision("quasi_identifier", "LANGUAGE", .85, "ISO language codes")
    if p["m_municipality"] >= .6:
        return Decision("quasi_identifier", "MUNICIPALITY", .8, f"{_pct(p['m_municipality'])} known municipalities")
    if p["m_country"] >= .7:
        return Decision("quasi_identifier", "LOCATION_NAME", .7, "country names/codes")
    # person names: 2-4 capitalised tokens, high cardinality, not organisations
    if (p["m_name_shape"] >= .7 and p["unique_ratio"] >= .1 and p["n_unique"] > 20 and p["m_org_suffix"] < .2
            and (p["m_first_name"] >= .2 or p["m_surname_suffix"] >= .4)):
        conf = .95 if p["m_first_name"] >= .3 else .85
        return Decision("direct_identifier", "PERSON_NAME", conf,
                        f"{_pct(p['m_name_shape'])} look like person names ({_pct(p['m_first_name'])} known first names)")
    if (p["m_single_cap"] >= .8 and p["n_unique"] > 30 and p["m_municipality"] < .3
            and (p["m_first_name"] >= .4 or p["m_surname_suffix"] >= .6)):
        return Decision("direct_identifier", "PERSON_NAME", .8, "single-token names (first names or surnames)")
    if p["m_hostname"] >= .7 and p["n_unique"] > 10 and p["frac_has_digit"] > .5:
        return Decision("technical_identifier", "HOSTNAME", .75, "device host names")
    if p["m_hex_hash"] >= .9:
        st = "SECRET" if re.search(r"pass|secret|token", name) else "OTHER"
        return Decision("technical_identifier" if p["unique_ratio"] < .99 else "non_sensitive", st, .5,
                        "hexadecimal hashes (could be a hashed identifier: test for dictionary attacks)")
    return None


def structure_rules(p: dict) -> Decision | None:
    """Keys and foreign keys, from uniqueness and cross-table links."""
    name = p["column"].lower()
    id_like = p["frac_has_space"] < .05 and p["frac_has_digit"] > .8 and p["mean_len"] <= 40
    if not id_like:
        return None
    if p["fk_to"] and p["unique_ratio"] < .99:
        st = _id_subtype(name + " " + " ".join(p["fk_to"]).lower())
        return Decision("technical_identifier", st, .8,
                        f"foreign key to {', '.join(p['fk_to'][:2])}: links all records of one entity")
    if p["unique_ratio"] >= .99 and (p["col_index"] == 0 or p["is_key_target"]) and p["m_prefixed_id"] + p["frac_int"] > .8:
        why = "first column, unique per row" + (", referenced by other tables" if p["is_key_target"] else "")
        return Decision("record_key", "RECORD_ID", .8, why)
    if p["m_prefixed_id"] >= .8 and p["n_unique"] > 10:
        st = _id_subtype(name, "OTHER")
        return Decision("technical_identifier", st, .55,
                        f"opaque prefixed identifiers ({', '.join(p['shapes'][:2])}), {_pct(p['unique_ratio'])} unique")
    return None


def name_rules(p: dict) -> Decision | None:
    h = _name_hint(p["column"].lower())
    if not h:
        return None
    role, st, w = h
    return Decision(role, st, w, f"column name '{p['column']}' suggests {st.lower().replace('_', ' ')}")


def context_adjust(p: dict, d: Decision) -> Decision:
    """Columns of tables that hold no person-related data (stops, sensors, weather) are not personal."""
    if p.get("table_person_signals", 1) == 0 and d.privacy_role in ("quasi_identifier", "technical_identifier"):
        return Decision("non_sensitive", d.subtype, min(d.confidence, .7),
                        d.reason + "; but the table has no person-related columns, so it is reference data",
                        d.source)
    return d


def tier1(p: dict) -> Decision:
    """Best tier-1 decision. Low confidence means 'ask tier 2/3'."""
    d = value_rules(p)
    if d is None:
        d = structure_rules(p)
    nh = name_rules(p)
    if d is None and nh is not None:
        d = nh
    elif d is not None and nh is not None and nh.privacy_role == d.privacy_role and d.subtype in ("DATE", "OTHER"):
        d = Decision(d.privacy_role, nh.subtype, max(d.confidence, nh.confidence), d.reason + "; " + nh.reason)
    if d is None:
        kind = "MEASUREMENT" if p["frac_numeric"] > .9 else "CATEGORY"
        d = Decision("non_sensitive", kind, .35, "no identifying pattern found")
    return context_adjust(p, d)
