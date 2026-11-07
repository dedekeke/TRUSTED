"""Execute a selection plan: derive, pseudonymise, generalise, redact, drop; write protected tables + private row maps.

Plan contract (produced by privacy_tool.select):
  plan["release_id"]                       context for HMAC domains (scenario/recipient), never a secret
  plan["tables"][t] = {"action": "RELEASE"|"WITHHOLD", "record_key": col|None, "reason"}
  plan["columns"]   = [{"table", "column", "subtype", "action", "method", "params", ...}]  one per source column
  plan["derived"]   = [{"table", "column", "sources": [birth_col, event_col], "method": "derive_age_band", "params"}]

Values are read as the evaluator reads them (pets_eval.parse). Values that cannot be parsed become blank and are
counted per column in the returned stats; they are never copied through raw.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path

import numpy as np
import pandas as pd

from pets_eval import parse as Pz
from pets_eval.check import PATTERNS, VALIDATORS
from pets_eval.utility.health import diagnosis_group

from .detect import normalise_hetu, safe_datetime

TIME_FORMATS = {"floor_hour": "%Y-%m-%d %H:00", "date": "%Y-%m-%d", "iso_week": "%G-W%V", "month": "%Y-%m", "year": "%Y"}
DATE_RX = re.compile(r"\b\d{1,2}[./]\d{1,2}[./](\d{4}|\d{2})\b|\b\d{4}-\d{2}-\d{2}\b")
NAME_PAIR_RX = re.compile(r"\b[A-ZÅÄÖ][a-zåäöé]+(?:-[A-ZÅÄÖ][a-zåäöé]+)?\s[A-ZÅÄÖ][a-zåäöé]+(?:-[A-ZÅÄÖ][a-zåäöé]+)?\b")
SPAN_LABEL = {"NATIONAL_ID": "NATIONAL_ID", "IBAN": "IBAN", "PAYMENT_CARD": "PAYMENT_CARD", "EMAIL": "EMAIL",
              "PHONE": "PHONE", "IP_ADDRESS": "IP_ADDRESS", "IPV6": "IP_ADDRESS", "MAC_ADDRESS": "DEVICE_ID",
              "LICENSE_PLATE": "LICENSE_PLATE"}
ROW_VALUE_LABELS = {"PERSON_NAME": "PERSON", "PHONE": "PHONE", "EMAIL": "EMAIL", "STREET_ADDRESS": "ADDRESS",
                    "NATIONAL_ID": "NATIONAL_ID"}


def _blank(s: pd.Series) -> pd.Series:
    return s.isna() | (s.astype(str).str.strip() == "")


def hmac_token(values: pd.Series, key: bytes, context: str, subtype: str = "") -> pd.Series:
    """Keyed pseudonym (HMAC-SHA-256, 32 hex chars). Blank stays blank; one shared normalisation per subtype."""
    norm = normalise_hetu if subtype == "NATIONAL_ID" else (lambda v: v.strip())
    ctx = context.encode() + b"|"

    def one(v):
        return hmac.new(key, ctx + norm(str(v)).encode(), hashlib.sha256).hexdigest()[:32]
    out = values.astype(str).map(one)
    return out.where(~_blank(values), "")


def _time(s: pd.Series, method: str) -> pd.Series:
    dt = safe_datetime(s.where(~_blank(s)))
    if method == "floor_hour":
        dt = dt.dt.floor("h")  # floor, never round: rounding shifts the hour curve and late rows to the next day
    return dt.dt.strftime(TIME_FORMATS[method]).where(dt.notna(), "")


def _numeric(s: pd.Series) -> pd.Series:
    return Pz.parse_numeric(s.where(~_blank(s)).astype(str).str.replace(r"[\s ]", "", regex=True))


def _fmt(x: pd.Series) -> pd.Series:
    return x.map(lambda v: "" if pd.isna(v) else (str(int(v)) if float(v).is_integer() else f"{v:g}"))


def _rare(s: pd.Series, min_count: int, replacement: str) -> pd.Series:
    counts = s.map(s.value_counts())
    return s.where((counts >= min_count) | _blank(s), replacement)


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
                    if len(part) >= 3 and part[0].isupper():
                        text = re.sub(rf"\b{re.escape(part)}\b", "[PERSON]", text)
    for name, rx in PATTERNS.items():
        ok = VALIDATORS.get(name)
        text = rx.sub(lambda m: m.group(0) if ok and not ok(m.group(1)) else f"[{SPAN_LABEL[name]}]", text)
    text = DATE_RX.sub("[DATE]", text)
    return NAME_PAIR_RX.sub("[PERSON]", text)


def apply_column(s: pd.Series, d: dict, key: bytes, release_id: str, df: pd.DataFrame | None = None,
                 plan_columns: list | None = None) -> tuple[pd.Series | None, int]:
    """Transformed column (None = dropped) and the number of non-blank values that became blank."""
    action, method, p = d["action"], d.get("method"), d.get("params") or {}
    if action == "DROP":
        return None, 0
    if action == "KEEP":
        out = s
    elif action == "HMAC" and method != "ipv4_prefix":
        out = hmac_token(s, key, f"{release_id}/{p['domain']}", d.get("subtype", ""))
    elif action == "REDACT":
        ids = [c for c in (plan_columns or []) if c["table"] == d["table"] and c.get("subtype") in ROW_VALUE_LABELS]
        rows = [{ROW_VALUE_LABELS[c["subtype"]]: [df[c["column"]].iloc[i]] for c in ids} for i in range(len(s))] \
            if df is not None else [None] * len(s)
        out = pd.Series([redact(t, r) for t, r in zip(s.tolist(), rows)], index=s.index)
    elif method in TIME_FORMATS:
        out = _time(s, method)
    elif method == "age_band":
        out = Pz.to_age_band(_numeric(s), width=p.get("width", 10), top=p.get("top", 80)).fillna("")
    elif method == "postcode_prefix":
        out = s.astype(str).str.strip().str[: p["digits"]].where(~_blank(s), "")
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
    elif method == "icd_3char":
        out = s.astype(str).str.replace(".", "", regex=False).str.strip().str.upper().str[:3].where(~_blank(s), "")
    elif method == "icd_chapter":
        out = s.astype(str).str.strip().str.upper().str[:1].where(~_blank(s), "")
    elif method == "diagnosis_group":
        out = diagnosis_group(s.where(~_blank(s))).fillna("")
    elif method == "ipv4_prefix":
        out = s.astype(str).str.replace(r"^(\d{1,3}\.\d{1,3}\.\d{1,3})\.\d{1,3}$", r"\1.0", regex=True)
        out = out.where(out.str.endswith(".0") & ~_blank(s), "")
    else:
        raise ValueError(f"unsupported operation {action}/{method} for {d['table']}.{d['column']}")
    lost = int((~_blank(s) & _blank(out.astype(str))).sum()) if method not in ("suppress_rare",) else 0
    return out.astype(str).where(~_blank(out), ""), lost


def derive_age_band(df: pd.DataFrame, birth: str, event: str, width: int = 10, top: int = 80) -> pd.Series:
    """Age at the row's original event date (toolkit formula: days / 365.25), as canonical bands."""
    age = (safe_datetime(df[event].where(~_blank(df[event]))) - safe_datetime(df[birth].where(~_blank(df[birth])))).dt.days / 365.25
    return Pz.to_age_band(age.where(age >= 0), width=width, top=top).fillna("")


def apply(tables: dict[str, pd.DataFrame], plan: dict, key: bytes, out_dir: Path | None = None,
          eval_dir: Path | None = None) -> tuple[dict[str, pd.DataFrame], dict]:
    """Protected tables (original names, retained column names, original row order) and per-column stats.

    Writes <out_dir>/<table>.csv (shareable) and, for scoring only, <eval_dir>/<table>.csv + rowmap_<table>.csv
    (private: never publish). Both directories must not exist yet."""
    if not key:
        raise ValueError("an HMAC key is required (pass it from an environment variable)")
    if plan.get("status") == "blocked":
        raise ValueError("plan is blocked; fix its errors before transforming")
    for d in (out_dir, eval_dir):
        if d is not None and Path(d).exists():
            raise FileExistsError(f"refusing to write into existing {d}")
    out, stats = {}, {"blanked": {}, "rows": {}}
    cols = plan["columns"]
    for t, td in sorted(plan["tables"].items()):
        if td["action"] != "RELEASE" or t not in tables:
            continue
        src = tables[t]
        res = {}
        for dv in (x for x in plan.get("derived", []) if x["table"] == t):
            if dv["method"] != "derive_age_band":
                raise ValueError(f"unsupported derivation {dv['method']}")
            res[dv["column"]] = derive_age_band(src, *dv["sources"], **(dv.get("params") or {}))
        for d in (c for c in cols if c["table"] == t):
            if d["column"] not in src.columns:
                raise ValueError(f"plan column {t}.{d['column']} missing from source")
            v, lost = apply_column(src[d["column"]], d, key, plan.get("release_id", ""), src, cols)
            if v is not None:
                res[d["column"]] = v
            if lost:
                stats["blanked"][f"{t}.{d['column']}"] = lost
        order = [c for c in src.columns if c in res] + [c for c in res if c not in src.columns]
        out[t] = pd.DataFrame(res, index=src.index)[order].reset_index(drop=True)
        stats["rows"][t] = len(out[t])
    for d in (out_dir, eval_dir):
        if d is not None:
            Path(d).mkdir(parents=True)
            for t, df in out.items():
                df.to_csv(Path(d) / f"{t}.csv", index=False)
    if eval_dir is not None:
        for t in out:
            rk = plan["tables"][t].get("record_key")
            ids = tables[t][rk].astype(str).values if rk else np.arange(len(tables[t])).astype(str)
            pd.DataFrame({"protected_row": np.arange(len(out[t])), "original_record_id": ids}).to_csv(
                Path(eval_dir) / f"rowmap_{t}.csv", index=False)
    return out, stats
