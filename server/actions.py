"""Shared pure protection actions: used by Select's in-memory previews and by the final Transform executor.

No file I/O here. Every function takes source values and returns protected values plus loss counts, so a
measured selection and the exported release run exactly the same code.

Plan contract (produced by server.select.select / server.select.search):
  plan["release_id"]                       context for HMAC domains (scenario/recipient), never a secret
  plan["tables"][t] = {"action": "RELEASE"|"WITHHOLD", "record_key": col|None, "reason"}
  plan["columns"]   = [{"table", "column", "subtype", "action", "method", "params", ...}]  one per source column
  plan["derived"]   = [{"table", "column", "sources": [birth_col, event_col], "method": "derive_age_band", "params"}]
  plan["suppression"][t] = {"qis": [...], "k": int, "subject": col|None}   local QI suppression chosen by search

Values are read as the evaluator reads them (pets_eval.parse). Values that cannot be parsed become blank and are
counted per column in the returned stats; they are never copied through raw.
"""
from __future__ import annotations

import hashlib
import hmac
import re

import numpy as np
import pandas as pd

from pets_eval import parse as Pz
from pets_eval.check import PATTERNS, VALIDATORS, ip_ok
from pets_eval.utility.health import diagnosis_group

from server.select.detect import normalise_hetu, safe_datetime

TIME_FORMATS = {"floor_hour": "%Y-%m-%d %H:00", "date": "%Y-%m-%d", "iso_week": "%G-W%V", "month": "%Y-%m", "year": "%Y"}
HOUR_ANCHORS = {  # hour of day kept, date replaced by an anchor of the stated period
    "week_hour": "Monday of the ISO week + HH:00",
    "month_hour": "first day of the month + HH:00",
    "year_hour": "1 January of the year + HH:00",
}
DATE_RX = re.compile(r"\b\d{1,2}[./]\d{1,2}[./](\d{4}|\d{2})\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\.\d{1,2}\.(?!\d)")
# street + house number (+ staircase/flat), e.g. "Kangaspolku 6 A 1": capitalised word with a street suffix
ADDRESS_RX = re.compile(r"\b[A-ZÅÄÖ][a-zåäö]*(?:tie|katu|kuja|polku|rinne|väylä|kaari|mäki|ranta|puisto|piha|tori|"
                        r"vägen|gatan|gränd|stigen|aukio|kallio|niitty|ahde|harju|linja|laakso|kulma)\s\d+[a-z]?"
                        r"(?:\s?[A-Z]\s?\d+)?(?:,?\s\d{5}(?:\s[A-ZÅÄÖ][a-zåäö]+)?)?")
DIAGNOSIS_MAPPING = "pets_eval.utility.health.diagnosis_group"
ICD_RX = r"^[A-Z]\d{2}"
NAME_PAIR_RX = re.compile(r"\b[A-ZÅÄÖ][a-zåäöé]+(?:-[A-ZÅÄÖ][a-zåäöé]+)?\s[A-ZÅÄÖ][a-zåäöé]+(?:-[A-ZÅÄÖ][a-zåäöé]+)?\b")
SPAN_LABEL = {"NATIONAL_ID": "NATIONAL_ID", "IBAN": "IBAN", "PAYMENT_CARD": "PAYMENT_CARD", "EMAIL": "EMAIL",
              "PHONE": "PHONE", "IP_ADDRESS": "IP_ADDRESS", "IPV6": "IP_ADDRESS", "MAC_ADDRESS": "DEVICE_ID",
              "LICENSE_PLATE": "LICENSE_PLATE"}
ROW_VALUE_LABELS = {"PERSON_NAME": "PERSON", "PHONE": "PHONE", "EMAIL": "EMAIL", "STREET_ADDRESS": "ADDRESS",
                    "NATIONAL_ID": "NATIONAL_ID"}
PLACEHOLDER_RX = re.compile(r"[A-Z][A-Z0-9_]{0,31}")
# Every (action, method) pair the executor implements; Transform refuses anything else before writing.
SUPPORTED = {("KEEP", None), ("DROP", None), ("HMAC", "hmac_sha256"), ("HMAC", "ipv4_prefix"),
             ("REDACT", "redact_spans")} | {("GENERALISE", m) for m in (
                 *TIME_FORMATS, *HOUR_ANCHORS, "age_band", "postcode_prefix", "suppress_rare", "merge_rare",
                 "round_decimals", "round_numeric", "top_bottom_code", "icd_3char", "icd_chapter",
                 "diagnosis_group", "ipv4_prefix")}
DERIVATIONS = {"derive_age_band"}


def blank(s: pd.Series) -> pd.Series:
    return s.isna() | (s.astype(str).str.strip() == "")


_blank = blank  # name used by older imports


def normaliser(subtype: str):
    """The one identifier normalisation shared by HMAC tokens, subject resolution and join checks."""
    return normalise_hetu if subtype == "NATIONAL_ID" else (lambda v: v.strip())


def hmac_token(values: pd.Series, key: bytes, context: str, subtype: str = "") -> pd.Series:
    """Keyed pseudonym (HMAC-SHA-256, 32 hex chars). Blank stays blank; one shared normalisation per subtype."""
    norm = normaliser(subtype)
    ctx = context.encode() + b"|"

    def one(v):
        return hmac.new(key, ctx + norm(str(v)).encode(), hashlib.sha256).hexdigest()[:32]
    out = values.astype(str).map(one)
    return out.where(~blank(values), "")


def _time(s: pd.Series, method: str) -> pd.Series:
    dt = safe_datetime(s.where(~blank(s)))
    if method == "floor_hour":
        dt = dt.dt.floor("h")  # floor, never round: rounding shifts the hour curve and late rows to the next day
    return dt.dt.strftime(TIME_FORMATS[method]).where(dt.notna(), "")


def _hour_anchor(s: pd.Series, method: str) -> pd.Series:
    dt = safe_datetime(s.where(~blank(s))).dt.floor("h")
    if method == "week_hour":
        dt = dt - pd.to_timedelta(dt.dt.day_of_week, unit="D")
    elif method == "month_hour":
        dt = dt - pd.to_timedelta(dt.dt.day - 1, unit="D")
    fmt = "%Y-01-01 %H:00" if method == "year_hour" else "%Y-%m-%d %H:00"
    return dt.dt.strftime(fmt).where(dt.notna(), "")


def _numeric(s: pd.Series) -> pd.Series:
    return Pz.parse_numeric(s.where(~blank(s)).astype(str).str.replace(r"[\s ]", "", regex=True))


def _fmt(x: pd.Series) -> pd.Series:
    return x.map(lambda v: "" if pd.isna(v) else np.format_float_positional(float(v), precision=10, trim="-"))


def _rare(s: pd.Series, min_count: int, replacement: str) -> pd.Series:
    counts = s.map(s.value_counts())
    return s.where((counts >= min_count) | blank(s), replacement)


def redact(text: str, row_values: dict | None = None) -> str:
    """Typed placeholders for identifiers in free text: values of the same row's identifier columns, validated
    patterns (pets_eval.check), dates and capitalised name pairs."""
    if not isinstance(text, str) or not text:
        return text
    for label, vals in (row_values or {}).items():
        for v in sorted({str(x) for x in vals if isinstance(x, str) and len(x.strip()) >= 3}, key=len, reverse=True):
            text = re.sub(re.escape(v.strip()), f"[{label}]", text, flags=re.I)
            if label == "PERSON":
                for part in v.replace(",", " ").split():
                    if len(part) >= 2:
                        text = re.sub(rf"\b{re.escape(part)}\b", "[PERSON]", text, flags=re.I)
    text = ADDRESS_RX.sub("[ADDRESS]", text)
    for name, rx in PATTERNS.items():
        ok = None if name == "NATIONAL_ID" else VALIDATORS.get(name)  # over-redact ID-shaped strings
        text = rx.sub(lambda m: m.group(0) if ok and not ok(m.group(1)) else f"[{SPAN_LABEL[name]}]", text)
    text = DATE_RX.sub("[DATE]", text)
    return NAME_PAIR_RX.sub("[PERSON]", text)


def redact_spans(text: str, spans: list[dict]) -> str:
    """Replace validated Detect spans (character offsets into the original text) with typed placeholders.

    Overlapping spans are merged and take the first span's label. Offsets must already be validated."""
    if not isinstance(text, str) or not text or not spans:
        return text
    merged: list[list] = []
    for sp in sorted(spans, key=lambda x: (x["start"], -x["end"])):
        if merged and sp["start"] < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], sp["end"])
        else:
            merged.append([sp["start"], sp["end"], sp.get("label", "")])
    for start, end, label in reversed(merged):
        label = str(label).upper()
        text = text[:start] + f"[{label if PLACEHOLDER_RX.fullmatch(label) else 'PII'}]" + text[end:]
    return text


def apply_column(s: pd.Series, d: dict, key: bytes, release_id: str, df: pd.DataFrame | None = None,
                 plan_columns: list | None = None, spans: list | None = None) -> tuple[pd.Series | None, int]:
    """Transformed column (None = dropped) and the number of non-blank values that became blank.

    spans: for REDACT only, one validated span list per row (aligned with s). Spans are applied first; the
    rule-based redactor then runs on the result as a second line of defence. Without spans only the rules run."""
    action, method, p = d["action"], d.get("method"), d.get("params") or {}
    if action == "DROP":
        return None, 0
    if action == "KEEP":
        out = s
    elif action == "HMAC" and method != "ipv4_prefix":
        if not p.get("domain"):
            raise ValueError(f"HMAC without a token domain for {d.get('table')}.{d.get('column')}")
        if pd.api.types.is_numeric_dtype(s):
            raise ValueError(f"{d.get('table')}.{d.get('column')} must be read as strings before tokenising")
        out = hmac_token(s, key, f"{release_id}/{p['domain']}", d.get("subtype", ""))
    elif action == "REDACT":
        ids = [c for c in (plan_columns or []) if c["table"] == d.get("table") and c.get("subtype") in ROW_VALUE_LABELS]
        recs = df[[c["column"] for c in ids]].to_dict("records") if df is not None else [{}] * len(s)
        rows = [{ROW_VALUE_LABELS[c["subtype"]]: [r[c["column"]]] for c in ids} for r in recs]
        texts = s.tolist() if spans is None else [redact_spans(t, sp) for t, sp in zip(s.tolist(), spans)]
        out = pd.Series([redact(t, r) for t, r in zip(texts, rows)], index=s.index)
    elif method in TIME_FORMATS:
        out = _time(s, method)
    elif method in HOUR_ANCHORS:
        out = _hour_anchor(s, method)
    elif method == "age_band":
        x = _numeric(s)
        out = Pz.to_age_band(x.where(x >= 0), width=p.get("width", 10), top=p.get("top", 80)).fillna("")
    elif method == "postcode_prefix":
        code = s.astype(str).str.strip()
        out = code.str[: p["digits"]].where(code.str.fullmatch(r"\d{5}"), "")  # only valid 5-digit codes
    elif method == "suppress_rare":
        out = _rare(s, p["min_count"], "")
    elif method == "merge_rare":
        out = _rare(s, p["min_count"], "other")
    elif method == "round_decimals":
        out = _fmt(_numeric(s).round(p["digits"]))
    elif method == "round_numeric":
        out = _fmt((_numeric(s) / p["step"]).round() * p["step"])
    elif method == "top_bottom_code":
        x = _numeric(s)
        out = _fmt(x.clip(x.quantile(p.get("lower_q", .01)), x.quantile(p.get("upper_q", .99))))
    elif method in ("icd_3char", "icd_chapter"):
        code = s.astype(str).str.replace(".", "", regex=False).str.strip().str.upper()
        out = code.str[: 3 if method == "icd_3char" else 1].where(code.str.match(ICD_RX), "")
    elif method == "diagnosis_group":
        if p.get("mapping", DIAGNOSIS_MAPPING) != DIAGNOSIS_MAPPING:
            raise ValueError(f"unsupported diagnosis mapping {p['mapping']}")
        out = diagnosis_group(s.where(~blank(s))).fillna("")
    elif method == "ipv4_prefix":  # generalise to the /24 network
        ip = s.astype(str).str.strip()
        out = ip.str.replace(r"\.\d{1,3}$", ".0", regex=True).where(ip.map(lambda v: ip_ok(v) and v.count(".") == 3), "")
    else:
        raise ValueError(f"unsupported operation {action}/{method} for {d.get('table')}.{d.get('column')}")
    lost = int((~blank(s) & blank(out.astype(str))).sum()) if method not in ("suppress_rare",) else 0
    return out.astype(str).where(~blank(out), ""), lost


def derive_age_band(df: pd.DataFrame, birth: str, event: str, width: int = 10, top: int = 80) -> pd.Series:
    """Age at the row's original event date (toolkit formula: days / 365.25), as canonical bands."""
    age = (safe_datetime(df[event].where(~blank(df[event]))) - safe_datetime(df[birth].where(~blank(df[birth])))).dt.days / 365.25
    return Pz.to_age_band(age.where(age >= 0), width=width, top=top).fillna("")


def small_classes(protected: pd.DataFrame, qis: list, subjects: pd.Series, k: int) -> pd.Series:
    """Rows whose QI class holds fewer than k distinct subjects (unknown subjects are not counted as people)."""
    if not qis:
        return pd.Series(False, index=protected.index)
    keys = pd.util.hash_pandas_object(protected[qis].astype(str), index=False)
    people = pd.Series(subjects.values, index=protected.index).groupby(keys.values).transform('nunique')
    return people < k


def resolved_subjects(tables: dict, plan: dict, table: str) -> pd.Series:
    """Resolve subjects through unique-parent joins without inventing IDs for missing people."""
    target = (plan.get('subject_keys') or {}).get(table)

    def walk(name, seen):
        df = tables[name]
        if target and target.split('.', 1)[0] == name:
            column = target.split('.', 1)[1]
            if column in df:
                subtype = next((c.get('subtype') for c in plan.get('columns', [])
                                if c['table'] == name and c['column'] == column), '')
                return df[column].astype(str).map(normaliser(subtype)).where(~blank(df[column]))
        for join in plan.get('joins', []):
            child, cc = join['child'].split('.', 1)
            parent, pc = join['parent'].split('.', 1)
            if child != name or parent in seen or parent not in tables or cc not in df or pc not in tables[parent]:
                continue
            values = walk(parent, seen | {parent})
            keys = tables[parent][pc]
            good = ~blank(keys) & ~keys.duplicated(keep=False)
            mapped = df[cc].map(pd.Series(values[good].values, index=keys[good]))
            if mapped.notna().any():
                return mapped
        return pd.Series(np.nan, index=df.index)

    return walk(table, {table})


def execute(tables: dict[str, pd.DataFrame], plan: dict, key: bytes, spans: dict | None = None,
            text_fallback: bool = True) -> tuple[dict[str, pd.DataFrame], dict]:
    """Apply the exact selected plan in memory: derive, per-column rungs, then the selected local suppression.

    Returns protected tables (original table names, retained column names in source order followed by derived
    columns, original row order, every value a string, blanks as "") and execution stats.

    spans: {"table.column": [span list per row]} validated Detect spans for REDACT columns.
    text_fallback: if False, a REDACT column without spans is an error instead of rule-only redaction."""
    spans = spans or {}
    out = {}
    stats = {"rows": {}, "columns": {}, "blanked": {}, "suppressed_rows": {}, "suppressed_cells": {},
             "redaction": {}}
    cols = plan["columns"]
    for t, td in sorted(plan["tables"].items()):
        if td["action"] != "RELEASE" or t not in tables:
            continue
        src = tables[t]
        res = {}
        for dv in (x for x in plan.get("derived", []) if x["table"] == t):  # from the original dates, first
            if dv["method"] not in DERIVATIONS:
                raise ValueError(f"unsupported derivation {dv['method']}")
            if dv["column"] in src.columns or dv["column"] in res:
                raise ValueError(f"derived column {t}.{dv['column']} would collide with another column")
            res[dv["column"]] = derive_age_band(src, *dv["sources"], **(dv.get("params") or {})).astype(str)
            lost = int((res[dv["column"]] == "").sum())
            if lost:
                stats["blanked"][f"{t}.{dv['column']}"] = lost
        for d in (c for c in cols if c["table"] == t):
            ref = f"{t}.{d['column']}"
            if d["column"] not in src.columns:
                raise ValueError(f"plan column {ref} missing from source")
            row_spans = spans.get(ref) if d["action"] == "REDACT" else None
            if d["action"] == "REDACT":
                if row_spans is None and not text_fallback:
                    raise ValueError(f"{ref}: free text needs validated Detect spans (or an explicit rule fallback)")
                stats["redaction"][ref] = "detect_spans+rules" if row_spans is not None else "rules_only"
            v, lost = apply_column(src[d["column"]], d, key, plan.get("release_id", ""), src, cols, row_spans)
            if v is not None:
                res[d["column"]] = v
            if lost:
                stats["blanked"][ref] = lost
        order = [c for c in src.columns if c in res] + [c for c in res if c not in src.columns]
        df = pd.DataFrame(res, index=src.index)[order]
        rule = (plan.get("suppression") or {}).get(t)
        if rule:
            missing = [q for q in rule["qis"] if q not in df.columns]
            if missing:
                raise ValueError(f"{t}: suppression QIs not released: {missing}")
            rows = small_classes(df, rule["qis"], resolved_subjects(tables, plan, t), rule["k"])
            n = int(rows.sum())
            if n:
                stats["suppressed_cells"][t] = int((~blank(df.loc[rows, rule["qis"]].stack())).sum())
                df.loc[rows, rule["qis"]] = ""  # blank the QIs; the rows stay
            stats["suppressed_rows"][t] = n
        out[t] = df.reset_index(drop=True)
        stats["rows"][t] = len(out[t])
        stats["columns"][t] = list(out[t].columns)
    return out, stats
