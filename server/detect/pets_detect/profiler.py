"""Column profiler: turns every column into a compact, privacy-safe description (the "state" the detectors read).

A profile holds statistics, masked shapes and pattern-match rates. It also keeps a few sample values, which are
used only locally and never leave the machine.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from . import patterns as P

SAMPLE_ROWS = 20000      # rows read per table (enough for statistics, fast on 50 MB files)
VALUE_SAMPLE = 600       # values used for pattern tests


def load_dataset(folder: Path, nrows: int = SAMPLE_ROWS) -> dict[str, pd.DataFrame]:
    """Read every CSV of a dataset folder as strings (identifiers break when parsed as numbers)."""
    out = {}
    for f in sorted(Path(folder).glob("*.csv")):
        if f.name.startswith("rowmap_"):
            continue
        out[f.stem] = pd.read_csv(f, dtype=str, nrows=nrows, keep_default_na=False, na_values=[""])
    return out


def mask_shape(v: str, maxlen: int = 32) -> str:
    """'070889-9652' -> '9x6-9x4'; 'Oscar Lindberg' -> 'Aax4 Aax7'. Values are never stored, only their shape."""
    if len(v) > maxlen:
        return "LONGTEXT" if " " in v else "LONGTOKEN"
    m = []
    for ch in v:
        m.append("9" if ch.isdigit() else "A" if ch.isupper() else "a" if ch.isalpha() else ch)
    s = "".join(m)
    return re.sub(r"(9|A|a)\1+", lambda g: f"{g.group(1)}x{len(g.group(0))}", s)


def _frac(vals: list[str], fn) -> float:
    if not vals:
        return 0.0
    return sum(1 for v in vals if fn(v)) / len(vals)


def _rx(name):
    rx = P.RX[name]
    return lambda v: bool(rx.match(v))


def _any_rx(rxs):
    return lambda v: any(r.match(v) for r in rxs)


def _to_number(v: str):
    s = v.replace(" ", "").replace(" ", "")
    if s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _year(v: str):
    m = re.search(r"\b(19\d{2}|20\d{2})\b", v)
    if m:
        return int(m.group(1))
    m = re.match(r"^\d{1,2}[./]\d{1,2}[./](\d{2})$", v)
    if m:
        y = int(m.group(1))
        return 2000 + y if y <= 26 else 1900 + y
    return None


def profile_column(dataset: str, table: str, col: str, s: pd.Series, col_index: int, n_cols: int,
                   rng: np.random.Generator) -> dict:
    n = len(s)
    nonnull = s.dropna().astype(str).str.strip()
    nonnull = nonnull[nonnull != ""]
    vals_all = nonnull.tolist()
    n_unique = int(nonnull.nunique())
    if len(vals_all) > VALUE_SAMPLE:
        idx = rng.choice(len(vals_all), VALUE_SAMPLE, replace=False)
        vals = [vals_all[i] for i in idx]
    else:
        vals = vals_all
    lens = [len(v) for v in vals] or [0]
    words = [len(v.split()) for v in vals] or [0]
    nums = [x for x in (_to_number(v) for v in vals) if x is not None]
    years = [y for y in (_year(v) for v in vals) if y is not None]
    low = [v.lower() for v in vals]

    def tokens_first_name(v):
        return any(t.lower().strip(",") in P.FIRST_NAMES for t in re.split(r"[\s-]+", v))

    def tokens_surname(v):
        return any(P.SURNAME_SUFFIX.search(t.strip(",")) for t in v.split())

    prof = {
        "dataset": dataset, "table": table, "column": col,
        "col_index": col_index, "n_cols": n_cols, "n_rows": n,
        "null_frac": round(1 - len(vals_all) / n, 4) if n else 1.0,
        "n_unique": n_unique,
        "unique_ratio": round(n_unique / len(vals_all), 4) if vals_all else 0.0,
        "mean_len": float(np.mean(lens)),
        "max_len": int(max(lens)),
        "mean_words": float(np.mean(words)),
        "frac_has_space": _frac(vals, lambda v: " " in v),
        "frac_has_digit": _frac(vals, lambda v: any(c.isdigit() for c in v)),
        "frac_has_alpha": _frac(vals, lambda v: any(c.isalpha() for c in v)),
        "frac_numeric": len(nums) / len(vals) if vals else 0.0,
        "frac_int": _frac(vals, _rx("INT")),
        "num_min": float(min(nums)) if nums else None,
        "num_max": float(max(nums)) if nums else None,
        "num_mean": float(np.mean(nums)) if nums else None,
        "num_decimals": float(np.mean([len(v.split(".")[-1]) if "." in v else 0 for v in vals])) if nums else 0.0,
        "year_median": float(np.median(years)) if years else None,
        "year_span": (max(years) - min(years)) if years else None,
        # identifier patterns
        "m_hetu": _frac(vals, P.hetu_shape),
        "m_hetu_valid": _frac(vals, P.hetu_valid),
        "m_email": _frac(vals, _rx("EMAIL")),
        "m_email_list": _frac(vals, _rx("EMAIL_LIST")),
        "m_iban": _frac(vals, P.iban_valid),
        "m_pan": _frac(vals, P.luhn_valid),
        "m_pan_masked": _frac(vals, _rx("PAN_MASKED")),
        "m_phone": _frac(vals, _rx("PHONE")),
        "m_ipv4": _frac(vals, _rx("IPV4")),
        "m_ipv6": _frac(vals, _rx("IPV6")),
        "m_cidr": _frac(vals, _rx("CIDR")),
        "m_mac": _frac(vals, _rx("MAC")),
        "m_plate": _frac(vals, _rx("PLATE")),
        "m_url": _frac(vals, _rx("URL")),
        "m_domain": _frac(vals, _rx("DOMAIN")),
        "m_user_agent": _frac(vals, _rx("USER_AGENT")),
        "m_hex_hash": _frac(vals, _rx("HEX_HASH")),
        "m_uuid": _frac(vals, _rx("UUID")),
        "m_hostname": _frac(vals, _rx("HOSTNAME")),
        "m_prefixed_id": _frac(vals, _rx("PREFIXED_ID")),
        # quasi-identifier patterns
        "m_date": _frac(vals, _any_rx(P.DATE_RXS)),
        "m_month": _frac(vals, _any_rx(P.MONTH_RXS)),
        "m_timestamp": _frac(vals, _any_rx(P.TS_RXS)),
        "m_postcode": _frac(vals, _rx("POSTCODE_FI")),
        "m_coord": _frac(vals, _rx("COORD")),
        "m_address": _frac(vals, _rx("STREET_ADDRESS")),
        "m_sex": _frac(low, lambda v: v in P.SEX_VALUES),
        "m_lang": _frac(vals, _rx("LANG_CODE")),
        "m_municipality": _frac(low, lambda v: v in P.MUNICIPALITIES),
        "m_country": _frac(low, lambda v: v in P.COUNTRIES),
        "m_icd10": _frac(vals, _rx("ICD10")),
        "m_bool": _frac(vals, _rx("BOOL")),
        # name patterns
        "m_name_shape": _frac(vals, _rx("PERSON_NAME_SHAPE")),
        "m_single_cap": _frac(vals, _rx("SINGLE_CAP_WORD")),
        "m_first_name": _frac(vals, tokens_first_name),
        "m_surname_suffix": _frac(vals, tokens_surname),
        "m_org_suffix": _frac(vals, lambda v: bool(P.ORG_SUFFIX.search(v))),
        "shapes": [s for s, _ in Counter(mask_shape(v) for v in vals).most_common(5)],
        "top_values": [(v, c) for v, c in Counter(vals_all).most_common(8)],
        "samples": vals[:6],
        "fk_to": [],          # filled by link_columns()
        "is_key_target": False,
    }
    return prof


def _id_like(p: dict) -> bool:
    return p["frac_has_space"] < 0.05 and p["frac_has_digit"] > 0.8 and p["mean_len"] <= 40 and p["n_unique"] > 1


def link_columns(profiles: list[dict], tables: dict[str, pd.DataFrame]) -> None:
    """Mark foreign keys: an id-like column whose values are the (unique) key of another table of the dataset."""
    keys = {}
    for p in profiles:
        if p["unique_ratio"] >= 0.95 and p["n_unique"] >= 20 and _id_like(p):
            keys[(p["table"], p["column"])] = set(tables[p["table"]][p["column"]].dropna().astype(str))
    for p in profiles:
        if not _id_like(p):
            continue
        vals = set(tables[p["table"]][p["column"]].dropna().astype(str))
        if not vals:
            continue
        for (t, c), kv in keys.items():
            if t == p["table"]:
                continue
            ov = len(vals & kv) / len(vals)
            if ov >= 0.2:
                p["fk_to"].append(f"{t}.{c}")
                for q in profiles:
                    if q["table"] == t and q["column"] == c:
                        q["is_key_target"] = True


def profile_dataset(dataset: str, folder: Path, seed: int = 0, tables: dict | None = None) -> list[dict]:
    """tables: already loaded as load_dataset() would (default: read folder)."""
    rng = np.random.default_rng(seed)
    tables = load_dataset(folder) if tables is None else tables
    profiles = []
    for t, df in tables.items():
        for i, c in enumerate(df.columns):
            profiles.append(profile_column(dataset, t, c, df[c], i, len(df.columns), rng))
    link_columns(profiles, tables)
    add_table_context(profiles)
    return profiles


def add_table_context(profiles: list[dict]) -> None:
    """Table-level context: does this table describe people? (columns of a 'bus stop' table are not personal)."""
    by_table: dict[str, list[dict]] = {}
    for p in profiles:
        by_table.setdefault(p["table"], []).append(p)
    for t, ps in by_table.items():
        person_signals = 0
        for p in ps:
            if (p["m_hetu"] > .5 or p["m_email"] > .5 or p["m_phone"] > .5 or p["m_iban"] > .5 or p["m_pan"] > .5
                    or p["m_pan_masked"] > .3 or p["m_plate"] > .5 or p["m_mac"] > .5 or p["m_ipv4"] > .5
                    or (p["m_name_shape"] > .6 and p["unique_ratio"] > .2) or p["m_address"] > .6
                    or p["m_sex"] > .9 or (p["fk_to"] and p["unique_ratio"] < .95) or p["mean_words"] > 6):
                person_signals += 1
        for p in ps:
            p["table_person_signals"] = person_signals
            p["table_columns"] = [q["column"] for q in ps]


def profile_text(p: dict) -> str:
    """Text rendering of a profile for retrieval (embedding) and for the LLM prompt."""
    name = re.sub(r"[_\-.]+", " ", p["column"]).lower()
    table = re.sub(r"[_\-.]+", " ", p["table"]).lower()
    kind = ("text" if p["mean_words"] > 5 else "number" if p["frac_numeric"] > .9 else
            "date" if max(p["m_date"], p["m_timestamp"], p["m_month"]) > .6 else "token")
    uniq = ("unique" if p["unique_ratio"] > .95 else "high-cardinality" if p["unique_ratio"] > .3 else
            "low-cardinality" if p["n_unique"] > 12 else "categorical")
    flags = [k[2:] for k, v in p.items() if k.startswith("m_") and isinstance(v, float) and v >= 0.5]
    vals = " ".join(str(v)[:40] for v, _ in p["top_values"][:6]) if p["n_unique"] <= 200 else ""
    parts = [f"column {name}", f"table {table}", f"kind {kind}", uniq, "patterns " + " ".join(flags),
             "shapes " + " ".join(p["shapes"]), f"values {vals}" if vals else "",
             "foreign key" if p["fk_to"] else "", "key target" if p["is_key_target"] else "",
             "person table" if p.get("table_person_signals", 0) else "non person table"]
    return " | ".join(x for x in parts if x)
