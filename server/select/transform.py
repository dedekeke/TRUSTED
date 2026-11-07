"""Execute a selection plan: derive, pseudonymise, generalise, redact, drop; write protected tables + private row maps.

Plan contract (produced by server.select.select):
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
from pets_eval.check import PATTERNS, VALIDATORS, ip_ok
from pets_eval.utility.health import diagnosis_group

from .detect import normalise_hetu, safe_datetime

TIME_FORMATS = {"floor_hour": "%Y-%m-%d %H:00", "date": "%Y-%m-%d", "iso_week": "%G-W%V", "month": "%Y-%m", "year": "%Y"}
DATE_RX = re.compile(r"\b\d{1,2}[./]\d{1,2}[./](\d{4}|\d{2})\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\.\d{1,2}\.(?!\d)")
# street + house number (+ staircase/flat), e.g. "Kangaspolku 6 A 1": capitalised word with a street suffix
ADDRESS_RX = re.compile(r"\b[A-ZÅÄÖ][a-zåäö]*(?:tie|katu|kuja|polku|rinne|väylä|kaari|mäki|ranta|puisto|piha|tori|"
                        r"vägen|gatan|gränd|stigen|aukio|kallio|niitty|ahde|harju|linja|laakso|kulma)\s\d+[a-z]?"
                        r"(?:\s?[A-Z]\s?\d+)?(?:,?\s\d{5}(?:\s[A-ZÅÄÖ][a-zåäö]+)?)?")
UNAPPROVED_STATUS = {"policy_valid", "target_unmet", "budget_exhausted", "measured_ok"}  # need --allow-unapproved
UNAPPROVED_NOTICE = "NOT_APPROVED.txt"
DIAGNOSIS_MAPPING = "pets_eval.utility.health.diagnosis_group"
ICD_RX = r"^[A-Z]\d{2}"
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
    return x.map(lambda v: "" if pd.isna(v) else np.format_float_positional(float(v), precision=10, trim="-"))


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
                    if len(part) >= 2:
                        text = re.sub(rf"\b{re.escape(part)}\b", "[PERSON]", text, flags=re.I)
    text = ADDRESS_RX.sub("[ADDRESS]", text)
    for name, rx in PATTERNS.items():
        ok = None if name == "NATIONAL_ID" else VALIDATORS.get(name)  # over-redact ID-shaped strings
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
        if not p.get("domain"):
            raise ValueError(f"HMAC without a token domain for {d['table']}.{d['column']}")
        if pd.api.types.is_numeric_dtype(s):
            raise ValueError(f"{d['table']}.{d['column']} must be read as strings before tokenising")
        out = hmac_token(s, key, f"{release_id}/{p['domain']}", d.get("subtype", ""))
    elif action == "REDACT":
        ids = [c for c in (plan_columns or []) if c["table"] == d["table"] and c.get("subtype") in ROW_VALUE_LABELS]
        recs = df[[c["column"] for c in ids]].to_dict("records") if df is not None else [{}] * len(s)
        rows = [{ROW_VALUE_LABELS[c["subtype"]]: [r[c["column"]]] for c in ids} for r in recs]
        out = pd.Series([redact(t, r) for t, r in zip(s.tolist(), rows)], index=s.index)
    elif method in TIME_FORMATS:
        out = _time(s, method)
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
        out = diagnosis_group(s.where(~_blank(s))).fillna("")
    elif method == "ipv4_prefix":  # generalise to the /24 network
        ip = s.astype(str).str.strip()
        out = ip.str.replace(r"\.\d{1,3}$", ".0", regex=True).where(ip.map(lambda v: ip_ok(v) and v.count(".") == 3), "")
    else:
        raise ValueError(f"unsupported operation {action}/{method} for {d['table']}.{d['column']}")
    lost = int((~_blank(s) & _blank(out.astype(str))).sum()) if method not in ("suppress_rare",) else 0
    return out.astype(str).where(~_blank(out), ""), lost


def derive_age_band(df: pd.DataFrame, birth: str, event: str, width: int = 10, top: int = 80) -> pd.Series:
    """Age at the row's original event date (toolkit formula: days / 365.25), as canonical bands."""
    age = (safe_datetime(df[event].where(~_blank(df[event]))) - safe_datetime(df[birth].where(~_blank(df[birth])))).dt.days / 365.25
    return Pz.to_age_band(age.where(age >= 0), width=width, top=top).fillna("")


def check_plan(tables: dict[str, pd.DataFrame], plan: dict) -> None:
    """Re-validate a (possibly hand-edited) plan against its input and the rule matrix before executing it."""
    from .policy import violations
    from .select import fingerprint
    if plan.get("input_fingerprint") and plan["input_fingerprint"] != fingerprint(tables):
        raise ValueError("plan was made for different input (schema/row-count fingerprint mismatch)")
    released = [t for t, d in plan["tables"].items() if d["action"] == "RELEASE"]
    missing = [t for t in released if t not in tables]
    if missing:
        raise ValueError(f"plan releases tables missing from the input: {missing}")
    planned = {(c["table"], c["column"]) for c in plan["columns"]}
    for t in released:
        extra = [c for c in tables[t].columns if (t, c) not in planned]
        if extra:
            raise ValueError(f"{t}: columns without a decision: {extra}")
    bad = []
    for c in plan["columns"]:
        if c["action"] == "DROP":
            continue
        label = {"privacy_role": c.get("privacy_role"), "subtype": c.get("subtype"), "confidence": c.get("confidence")}
        rung = {"action": c["action"], "method": c.get("method"), "params": c.get("params") or {}}
        bad += [f"{c['table']}.{c['column']}: {v}" for v in violations(label, rung, plan["trust_level"],
                                                                        k=plan.get("targets", {}).get("k"))]
    if bad:
        raise ValueError("plan violates the rule matrix: " + "; ".join(bad))


def apply(tables: dict[str, pd.DataFrame], plan: dict, key: bytes, out_dir: Path | None = None,
          eval_dir: Path | None = None, allow_unapproved: bool = False) -> tuple[dict[str, pd.DataFrame], dict]:
    """Protected tables (original names, retained column names, original row order) and per-column stats.

    Writes <out_dir>/<table>.csv (shareable) and, for scoring only, <eval_dir>/<table>.csv + rowmap_<table>.csv
    (private: never publish). Both directories must not exist yet."""
    if not key:
        raise ValueError("an HMAC key is required (pass it from an environment variable)")
    status = plan.get("status")
    approved = status == "measured_ok" and (plan.get("outcome") or {}).get("approved") is True
    if not approved and (status not in UNAPPROVED_STATUS or not allow_unapproved):
        raise ValueError(f"unapproved_plan: status {status!r} is not an approved measured_ok release"
                         + ("; fix its errors first" if status not in UNAPPROVED_STATUS else
                            "; pass allow_unapproved (--allow-unapproved) to export it anyway, recorded in the output"))
    if not plan.get("release_id"):
        raise ValueError("plan needs a release_id (scenario/recipient) to scope pseudonyms")
    check_plan(tables, plan)
    for d in (out_dir, eval_dir):
        if d is not None and Path(d).exists():
            raise FileExistsError(f"refusing to write into existing {d}")
    if out_dir is not None and eval_dir is not None:
        o, e = Path(out_dir).resolve(), Path(eval_dir).resolve()
        if o == e or o in e.parents or e in o.parents:
            raise ValueError("eval_dir (row maps) must be outside the shareable out_dir")
    out, stats = {}, {"blanked": {}, "rows": {},
                      "release_gate": {"status": status, "approved": approved, "allow_unapproved": allow_unapproved,
                                       "plan_sha256": plan.get("plan_sha256")}}
    cols = plan["columns"]
    for t, td in sorted(plan["tables"].items()):
        if td["action"] != "RELEASE" or t not in tables:
            continue
        src = tables[t]
        res = {}
        for dv in (x for x in plan.get("derived", []) if x["table"] == t):
            if dv["method"] != "derive_age_band":
                raise ValueError(f"unsupported derivation {dv['method']}")
            if dv["column"] in src.columns:
                raise ValueError(f"derived column {t}.{dv['column']} would collide with a source column")
            res[dv["column"]] = derive_age_band(src, *dv["sources"], **(dv.get("params") or {}))
            lost = int((res[dv["column"]] == "").sum())
            if lost:
                stats["blanked"][f"{t}.{dv['column']}"] = lost
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
            if not approved:
                (Path(d) / UNAPPROVED_NOTICE).write_text(
                    f"NOT AN APPROVED RELEASE: plan status {status}, exported with allow_unapproved.\n")
    if eval_dir is not None:
        for t in out:
            rk = plan["tables"][t].get("record_key")
            if not rk:  # positional ids match nothing in the scorer and would report false zero risk
                raise ValueError(f"table {t} needs a record_key for its scoring row map")
            ids = tables[t][rk].astype(str).values
            pd.DataFrame({"protected_row": np.arange(len(out[t])), "original_record_id": ids}).to_csv(
                Path(eval_dir) / f"rowmap_{t}.csv", index=False)
    return out, stats
