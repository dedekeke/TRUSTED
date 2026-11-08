"""Step 7b: linkage facts for the Select step, computed from the data and the base detector's column labels.

Per dataset, writes out/linkage/<dataset>.json with:
- join_keys: columns whose values are the key of another table (keep joins working -> consistent pseudonym);
- shared_identifiers: identifier columns whose values also appear in another dataset (cross-dataset linkage risk);
- embedded: information hidden inside an identifier (a HETU encodes birth date and sex);
- qi_risk: per table, the share of rows in groups smaller than k=5 on the detected quasi-identifiers, raw and after a
  default coarsening, and which single column hurts most (drop-one analysis).
Only counts and column names are written, never values.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from pets_detect.pipeline import load_profiles, root_paths
from pets_detect.profiler import load_dataset

EMBEDDED = {
    "NATIONAL_ID": ["birth date (DDMMYY + century sign)", "sex (odd/even individual number)"],
    "IBAN": ["bank (digits 5-7)"],
    "PAYMENT_CARD": ["card network and issuer (first 6 digits)"],
    "EMAIL": ["often the person's name", "employer or provider (domain)"],
    "LICENSE_PLATE": ["vehicle, and through it the owner (public vehicle register)"],
    "IP_ADDRESS": ["network provider and approximate location"],
    "PHONE": ["operator; often listed in public directories"],
    "STREET_ADDRESS": ["postcode and municipality"],
}
SHARE_SUBTYPES = {"NATIONAL_ID", "EMAIL", "PHONE", "IBAN", "PAYMENT_CARD", "LICENSE_PLATE", "PERSON_NAME",
                  "STREET_ADDRESS", "IP_ADDRESS", "MAC_ADDRESS", "CUSTOMER_ID", "EMPLOYEE_ID", "STUDENT_ID",
                  "PATIENT_ID", "DEVICE_ID", "USERNAME"}
K = 5


def coarsen(s: pd.Series, subtype: str) -> pd.Series:
    s = s.fillna("").astype(str)
    if subtype in ("TIMESTAMP", "DATE"):
        iso = s.str.extract(r"((?:19|20)\d{2}-\d{2})")[0]
        fi = s.str.extract(r"\d{1,2}\.(\d{1,2})\.((?:19|20)\d{2})")
        fi = fi[1] + "-" + fi[0].str.zfill(2)
        return iso.fillna(fi).fillna(s)
    if subtype == "BIRTH_DATE":
        y = s.str.extract(r"((?:19|20)\d{2})")[0]
        two = s.str.extract(r"^\d{1,2}[./]\d{1,2}[./](\d{2})$")[0]
        return y.fillna(two).fillna(s)
    if subtype == "AGE":
        n = pd.to_numeric(s, errors="coerce")
        return (n // 5 * 5).astype("Int64").astype(str).where(n.notna(), s)
    if subtype == "POSTCODE":
        return s.str[:3]
    if subtype == "GPS_COORDINATE":
        n = pd.to_numeric(s, errors="coerce")
        return n.round(2).astype(str).where(n.notna(), s)
    return s


def share_small(df: pd.DataFrame, cols: list[str]) -> tuple[float, int]:
    if not cols or df.empty:
        return 0.0, len(df)
    sizes = df.groupby(cols, dropna=False)[cols[0]].transform("size")
    return round(float((sizes < K).mean()), 4), int(sizes.min())


def main(root=None, base: str = ""):
    from .spans.run import choose_base, column_labels
    r, data_dir, _ = root_paths(root)
    base = choose_base(base)
    labels = column_labels(base, root)
    out_dir = Path("out/linkage")
    out_dir.mkdir(parents=True, exist_ok=True)
    datasets = sorted(labels.dataset.unique())
    tables = {ds: load_dataset(data_dir / ds) for ds in datasets}
    idsets = {}
    for _, row in labels[labels.subtype.isin(SHARE_SUBTYPES)].iterrows():
        df = tables[row.dataset].get(row.table)
        if df is not None and row.column in df:
            v = set(df[row.column].dropna().astype(str).str.strip().str.lower())
            v.discard("")
            if len(v) >= 20:
                idsets[(row.dataset, row.table, row.column, row.subtype)] = v
    summary = {"base": base, "k": K, "datasets": {}}
    for ds in datasets:
        lab = labels[labels.dataset == ds]
        profs = {(p["table"], p["column"]): p for p in load_profiles(ds, data_dir)}
        res = {"join_keys": [], "shared_identifiers": [], "embedded": [], "qi_risk": []}
        for _, row in lab.iterrows():
            p = profs.get((row.table, row.column))
            if p and p["fk_to"]:
                res["join_keys"].append({"column": f"{row.table}.{row.column}", "links_to": p["fk_to"],
                                         "role": row.privacy_role,
                                         "advice": "use the same keyed pseudonym in every table so joins keep working"})
            if row.subtype in EMBEDDED and row.privacy_role in ("direct_identifier", "technical_identifier"):
                res["embedded"].append({"column": f"{row.table}.{row.column}", "subtype": row.subtype,
                                        "reveals": EMBEDDED[row.subtype]})
        for (d1, t1, c1, st1), v1 in idsets.items():
            if d1 != ds:
                continue
            for (d2, t2, c2, st2), v2 in idsets.items():
                if d2 == ds or st2 != st1:
                    continue
                ov = len(v1 & v2)
                if ov >= 10:
                    res["shared_identifiers"].append({"column": f"{t1}.{c1}", "subtype": st1,
                                                      "also_in": f"{d2}.{t2}.{c2}", "shared_values": ov,
                                                      "share_of_column": round(ov / len(v1), 3)})
        for table, g in lab.groupby("table"):
            df = tables[ds].get(table)
            qis = [c for c in g[g.privacy_role == "quasi_identifier"].column if df is not None and c in df]
            if not qis:
                continue
            raw = df[qis].fillna("").astype(str)
            sub = dict(zip(g.column, g.subtype))
            gen = pd.DataFrame({c: coarsen(df[c], sub.get(c, "")) for c in qis})
            s_raw, k_raw = share_small(raw, qis)
            s_gen, k_gen = share_small(gen, qis)
            drop = {}
            if len(qis) > 1:
                for c in qis:
                    drop[c] = share_small(gen, [x for x in qis if x != c])[0]
            worst = min(drop, key=drop.get) if drop else (qis[0] if qis else None)
            res["qi_risk"].append({
                "table": table, "rows_sampled": len(df), "quasi_identifiers": qis,
                "share_rows_k_lt5_raw": s_raw, "min_k_raw": k_raw,
                "share_rows_k_lt5_coarsened": s_gen, "min_k_coarsened": k_gen,
                "coarsening": "dates -> month, birth dates -> year, age -> 5-year band, postcode -> 3 digits, "
                              "GPS -> 2 decimals",
                "drop_one_share_k_lt5": drop, "most_identifying_column": worst})
        (out_dir / f"{ds}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
        summary["datasets"][ds] = {"join_keys": len(res["join_keys"]),
                                   "shared_identifiers": len(res["shared_identifiers"]),
                                   "tables_with_qis": len(res["qi_risk"])}
        print(f"[linkage] {ds:18s} join keys {len(res['join_keys']):3d}  shared ids {len(res['shared_identifiers']):3d}"
              f"  QI tables {len(res['qi_risk'])}", flush=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary
