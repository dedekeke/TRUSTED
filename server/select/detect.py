"""Column profiler and privacy-role detector.

Two stages: (1) infer a column's subtype from its values (validators, patterns, parse rates, cardinality),
with the column name as a weak hint only; (2) resolve the privacy role from the subtype plus table context
(does the table describe people? is it a health/financial table?).

Never reads metadata/field_catalog.csv, gold spans or truth/; those are only for scoring afterwards
(`pets-eval detect --pred <labels.csv>`).

usage: python -m server.select.detect --data <dir> [--out labels.csv] [--rows 20000]
       <dir> is either one dataset folder of CSVs or a folder of dataset folders.
"""
from __future__ import annotations

import argparse
import ipaddress
import re
from pathlib import Path

import pandas as pd

from pets_eval.check import hetu_ok, iban_ok, luhn_ok
from pets_eval.parse import to_datetime

SAMPLE = 2000  # values tested per column
REVIEW_BELOW = 0.6  # confidence below this goes to human review
COLUMNS = ["dataset", "table", "column", "privacy_role", "subtype", "confidence", "evidence"]

DIRECT = {"NATIONAL_ID", "EMAIL", "PHONE", "IBAN", "PAYMENT_CARD", "LICENSE_PLATE", "PERSON_NAME", "USERNAME"}
TECHNICAL = {"IP_ADDRESS", "MAC_ADDRESS", "HOSTNAME", "USER_AGENT", "DEVICE_ID", "METER_ID", "CARD_ID"}
PERSON_QI = {"BIRTH_DATE", "AGE", "SEX"}  # quasi-identifiers wherever they appear
CONTEXT_QI = {"POSTCODE", "MUNICIPALITY", "GPS_COORDINATE", "TIMESTAMP", "DATE", "LOCATION_NAME", "LANGUAGE",
              "STREET_ADDRESS", "OCCUPATION", "ORG_NAME"}  # quasi-identifiers only in tables about people
PERSON_IDS = {"CUSTOMER_ID", "PATIENT_ID", "STUDENT_ID", "EMPLOYEE_ID", "ACCOUNT_ID", "CARD_ID"}
PERSONAL_DEVICES = {"MAC_ADDRESS", "DEVICE_ID"}  # a phone or card in a log is a person's trace
ENTITY_IDS = {"CUSTOMER_ID", "PATIENT_ID", "STUDENT_ID", "EMPLOYEE_ID", "ACCOUNT_ID", "CARD_ID", "DEVICE_ID",
              "METER_ID", "PROPERTY_ID"}

SEX_VALUES = {"m", "f", "male", "female", "mies", "nainen", "man", "woman", "n", "x", "other", "muu", "k", "w",
              "kvinna", "unknown", "u", "1", "2"}
LANG_VALUES = {"fi", "sv", "en", "ru", "et", "so", "ar", "fa", "ku", "de", "fr", "es", "zh", "uk", "vi", "th",
               "finnish", "swedish", "english", "russian", "estonian", "suomi", "ruotsi", "svenska", "other", "muu"}
# Finnish municipalities (public reference list subset: largest cities + Southwest Finland region).
MUNICIPALITIES = {m.lower() for m in """Helsinki Espoo Tampere Vantaa Oulu Turku Jyväskylä Kuopio Lahti Pori Kouvola
    Joensuu Lappeenranta Hämeenlinna Vaasa Seinäjoki Rovaniemi Mikkeli Kotka Salo Porvoo Kokkola Hyvinkää Lohja
    Järvenpää Rauma Kirkkonummi Tuusula Kajaani Kerava Nokia Kangasala Ylöjärvi Vihti Raasepori Savonlinna Riihimäki
    Kaarina Raisio Naantali Lieto Masku Mynämäki Nousiainen Rusko Paimio Sauvo Parainen Uusikaupunki Laitila Loimaa
    Somero Kemiönsaari Aura Pöytyä Marttila Koski Oripää Taivassalo Kustavi Pyhäranta Vehmaa Kemi Tornio Imatra
    Iisalmi Varkaus Forssa Valkeakoski Akaa Sastamala Pirkkala Lempäälä Mariehamn Maarianhamina""".split()}

NAME_HINTS = [  # (regex on column name, subtype); weak evidence only
    (r"hetu|ssn|national|personal_?id|henkilotunnus", "NATIONAL_ID"),
    (r"e_?mail", "EMAIL"), (r"phone|mobile|puhelin|gsm", "PHONE"), (r"iban|bank_?account", "IBAN"),
    (r"(^|_)pan$|card_?number|card_pan", "PAYMENT_CARD"), (r"plate|rekisteri", "LICENSE_PLATE"),
    (r"(^|_)ip($|_)|_ip$", "IP_ADDRESS"), (r"(^|_)mac($|_)", "MAC_ADDRESS"), (r"host", "HOSTNAME"),
    (r"user_?agent|(^|_)ua$", "USER_AGENT"), (r"upn|username|login|(^|_)user$", "USERNAME"),
    (r"imei|device", "DEVICE_ID"), (r"gsrn|meter|metering", "METER_ID"),
    (r"birth|dob|syntym", "BIRTH_DATE"), (r"(^|_)age($|_)|age_band", "AGE"), (r"(^|_)sex$|gender|sukupuoli", "SEX"),
    (r"postcode|zip|postal|postinumero", "POSTCODE"), (r"municipality|kunta|(^|_)city|town|home_city", "MUNICIPALITY"),
    (r"(^|_)lat|(^|_)lon|latitude|longitude", "GPS_COORDINATE"), (r"lang|kieli", "LANGUAGE"),
    (r"address|street|osoite", "STREET_ADDRESS"), (r"(first|last|given|family|full|sur|patient|customer|person|holder|guardian|author|sender|recipient|contact|officer|owner)_?name$|surname|(^|_)nimi$", "PERSON_NAME"),
    (r"_ts$|timestamp|time$|_at$|datetime", "TIMESTAMP"), (r"date|pvm|(^|_)day$", "DATE"),
    (r"icd|diagnos", "DIAGNOSIS_CODE"), (r"occupation|job|title|ammatti|nimike", "OCCUPATION"),
    (r"patient", "PATIENT_ID"), (r"customer|client|asiakas", "CUSTOMER_ID"), (r"student|pupil", "STUDENT_ID"),
    (r"employee|staff|emp_?no|personnel", "EMPLOYEE_ID"), (r"account", "ACCOUNT_ID"), (r"card", "CARD_ID"),
    (r"note|text|description|message|comment|complaint|body|subject|command|path|attachment|kuvaus|viesti", "FREE_TEXT"), (r"url|link", "URL"),
]
SENSITIVE_HINTS = re.compile(
    r"diagnos|icd|triage|disposition|readmit|medical|health|disab|accessib|special_support|sick|excused|"
    r"religio|ethnic|union|income|salary|wage|palkka|debt|default|late_payment|payment_plan|kyc|risk|pep|"
    r"grade|points|criminal|sexual|political|benefit|allowance|abnormal|lab_?value|second_language|ammattiliitto")
HEALTH_CONTEXT = re.compile(r"diagnos|icd|triage|patient|clinical|lab_|vital|ed_visit|hospital|nurse|blood|heart")
MEASURE_HINTS = re.compile(r"bp$|heart_rate|resp_rate|temp|spo2|pain|_minutes$|(^|_)value$")

R = {
    "NATIONAL_ID": re.compile(r"^\d{6}[-+A-FU-Y]\d{3}[0-9A-Y]$"),
    "EMAIL": re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$"),
    "IBAN": re.compile(r"^[A-Z]{2}\d{2}[ A-Z0-9]{11,32}$"),
    "PHONE": re.compile(r"^(\+\d{3}|00[1-9]\d{2}|0[1-9])\d{5,10}$"),  # after stripping separators
    "MAC_ADDRESS": re.compile(r"^([0-9A-F]{2}[:-]){5}[0-9A-F]{2}$", re.I),
    "URL": re.compile(r"^(https?://|www\.)\S+$", re.I),
    "USER_AGENT": re.compile(r"^(Mozilla/|curl/|python-requests|Wget/|okhttp)", re.I),
    "LICENSE_PLATE": re.compile(r"^[A-ZÅÄÖ]{2,3}-\d{1,3}$"),
    "DIAGNOSIS_CODE": re.compile(r"^[A-TV-Z]\d{2}(\.\d{1,2})?$"),
    "POSTCODE": re.compile(r"^\d{5}$"),
    "HEX_HASH": re.compile(r"^[0-9a-f]{32,128}$", re.I),
    "STREET_ADDRESS": re.compile(r"^[A-ZÅÄÖ][\wåäöÅÄÖ.-]+(\s[\wåäöÅÄÖ.-]+){0,2}\s\d+[a-zA-Z]?(\s[A-Za-z]\s?\d+)?(,?\s*\d{5}(\s+\S+){1,2})?$"),
    "PERSON_NAME": re.compile(r"^[A-ZÅÄÖ][A-Za-zÅÄÖåäöéü'-]+(,?\s[A-ZÅÄÖ][A-Za-zÅÄÖåäöéü'-]+){1,3}$"),
    "MONEY": re.compile(r"^-?\d{1,3}([ \u00a0]\d{3})+([.,]\d{2})?$|^-?\d+,\d{2}$"),
    "ID_LIKE": re.compile(r"^(?=.*\d)[A-Za-z0-9][A-Za-z0-9_/:.-]{2,40}$"),
    "TIME": re.compile(r"(^|[ T])\d{1,2}[:.]\d{2}(?![.\d])"),
    "AGE_BAND": re.compile(r"^\d{1,3}\s*[-–]\s*\d{1,3}$|^\d{1,3}\+$"),
    "DATE_SHAPE": re.compile(r"^\d{1,4}[-./]\d{1,2}([-./]\d{1,4})?([ T]|$)|^\d{4}-?W\d{1,2}$"),
    "MASKED_CARD": re.compile(r"^\d{4,6}[ -]?[*xX#]{2,4}([ -]?[*xX#]{4}){0,2}[ -]?[*xX#]{0,6}[ -]?\d{4}$"),
    "NUMBER": re.compile(r"^[-+]?(\d{1,3}([ \u00a0]\d{3})+|\d+)([.,]\d+)?$"),
}


def safe_datetime(vals: pd.Series) -> pd.Series:
    """pets_eval.parse.to_datetime, tz-naive; values it cannot handle (e.g. '2022-23', mixed offsets) become NaT."""
    def naive(ts):  # keep local wall-clock time; mixed offsets cannot share one tz-aware dtype
        return ts.tz_localize(None) if getattr(ts, "tzinfo", None) is not None else ts

    try:
        out = to_datetime(vals)
        if isinstance(out.dtype, pd.DatetimeTZDtype):
            out = out.dt.tz_localize(None)
        if pd.api.types.is_datetime64_any_dtype(out):
            return out
    except (ValueError, OverflowError, TypeError):
        pass

    def one(v):
        try:
            return naive(to_datetime(pd.Series([v])).iloc[0])
        except (ValueError, OverflowError, TypeError):
            return pd.NaT
    return pd.to_datetime(vals.map(one), errors="coerce")


def normalise_hetu(v: str) -> str:
    """Strip a 'HETU'/'SSN' prefix and restore a missing century sign so the checksum can be tested."""
    v = re.sub(r"^(hetu|ssn|htun?)[:\s]*", "", v.strip(), flags=re.I).upper()
    return v[:6] + "-" + v[6:] if re.fullmatch(r"\d{9}[0-9A-Y]", v) else v


def _is_ip(v: str) -> bool:
    try:
        ipaddress.ip_address(v)
        return True
    except ValueError:
        return False


def _rate(vals: pd.Series, fn) -> float:
    return float(vals.map(fn).mean()) if len(vals) else 0.0


def _rx(name):
    rx = R[name]
    return lambda v: bool(rx.match(v))


def _nonblank(s: pd.Series) -> pd.Series:
    raw = s.astype("string").str.strip()
    return raw[raw.notna() & (raw != "") & ~raw.str.lower().isin(["nan", "none", "null", "n/a", "-"])]


def profile(s: pd.Series) -> dict:
    """Value statistics for one column (no values are returned)."""
    nonnull = _nonblank(s)
    vals = nonnull.head(SAMPLE)
    n = len(nonnull)
    p = {"rows": len(s), "null_rate": round(1 - n / len(s), 4) if len(s) else 1.0,
         "distinct": int(nonnull.nunique()), "distinct_ratio": round(nonnull.nunique() / n, 4) if n else 0.0,
         "mean_len": round(float(vals.str.len().mean()), 2) if n else 0.0,
         "mean_words": round(float(vals.str.split().str.len().mean()), 2) if n else 0.0}
    if not n:
        return p
    num = vals.str.replace("\u00a0", " ").map(lambda v: bool(R["NUMBER"].match(v)))
    p["numeric_rate"] = round(float(num.mean()), 4)
    p["integer_rate"] = round(_rate(vals, lambda v: bool(re.fullmatch(r"[-+]?\d+", v))), 4)
    p["time_rate"] = round(_rate(vals, lambda v: bool(R["TIME"].search(v))), 4)
    dt = safe_datetime(vals[vals.map(lambda v: bool(R["DATE_SHAPE"].match(v)))])
    p["datetime_rate"] = round(float(dt.notna().sum() / len(vals)), 4)
    if dt.notna().any():
        years = dt.dropna().dt.year
        p["year_min"], p["year_max"] = int(years.min()), int(years.max())
    return p


def _value_subtype(vals: pd.Series, p: dict) -> tuple[str | None, float, str]:
    """Best subtype from values alone: (subtype, match rate, evidence)."""
    if not len(vals):
        return "CATEGORY", 0.3, "empty column"
    lower = vals.str.lower()
    compact = vals.str.replace(r"[\s()-]", "", regex=True)
    tests = [
        ("NATIONAL_ID", lambda: _rate(vals.map(normalise_hetu), lambda v: bool(R["NATIONAL_ID"].match(v)) and hetu_ok(v)), "HETU checksum"),
        ("EMAIL", lambda: _rate(vals, _rx("EMAIL")), "email pattern"),
        ("IBAN", lambda: _rate(vals, lambda v: bool(R["IBAN"].match(v)) and iban_ok(v)), "IBAN mod-97"),
        ("PAYMENT_CARD", lambda: _rate(compact, lambda v: v.isdigit() and len(v) in (13, 16, 19) and luhn_ok(v)), "Luhn 13/16/19 digits"),
        ("PAYMENT_CARD", lambda: _rate(vals, _rx("MASKED_CARD")), "masked card number"),
        ("DEVICE_ID", lambda: _rate(compact, lambda v: v.isdigit() and len(v) == 15 and luhn_ok(v)), "IMEI Luhn 15 digits"),
        ("MAC_ADDRESS", lambda: _rate(vals, _rx("MAC_ADDRESS")), "MAC pattern"),
        ("IP_ADDRESS", lambda: _rate(vals, _is_ip), "IP address"),
        ("URL", lambda: _rate(vals, _rx("URL")), "URL pattern"),
        ("USER_AGENT", lambda: _rate(vals, _rx("USER_AGENT")), "user-agent prefix"),
        ("LICENSE_PLATE", lambda: _rate(vals, _rx("LICENSE_PLATE")), "plate pattern"),
        ("PHONE", lambda: _rate(vals[~vals.str.contains(r"[.,:/]")].str.replace(r"[\s()-]", "", regex=True), _rx("PHONE"))
            * (~vals.str.contains(r"[.,:/]")).mean(), "phone pattern"),
        ("DIAGNOSIS_CODE", lambda: _rate(vals.str.upper(), _rx("DIAGNOSIS_CODE"))
            if p["distinct"] >= 5 and vals.str[:1].nunique() >= 3 else 0.0, "ICD-10 pattern"),
        ("TECH_HASH", lambda: _rate(vals, _rx("HEX_HASH")), "hex digest"),
        ("SEX", lambda: float(lower.isin(SEX_VALUES).mean()) if p["distinct"] <= 4 and not set(lower.unique()) <= {"1", "2", "0"} else 0.0, "sex vocabulary"),
        ("LANGUAGE", lambda: float(lower.isin(LANG_VALUES).mean()) if p["distinct"] <= 30 else 0.0, "language codes"),
        ("MUNICIPALITY", lambda: float(lower.isin(MUNICIPALITIES | {"non-resident", "unknown", "muu"}).mean()), "municipality list"),
        ("POSTCODE", lambda: _rate(vals, _rx("POSTCODE")) if p.get("integer_rate", 0) > .9 and p["distinct"] > 3 else 0.0, "5-digit code"),
        ("STREET_ADDRESS", lambda: _rate(vals, _rx("STREET_ADDRESS")), "street + number"),
        ("PERSON_NAME", lambda: _rate(vals, _rx("PERSON_NAME")) if p["distinct"] >= 5 and p["mean_words"] >= 1.8 else 0.0, "capitalised name tokens"),
    ]
    best = (None, 0.0, "")
    for sub, fn, ev in tests:
        r = fn()
        if r >= .8:
            return sub, r, f"{ev} {r:.0%}"
        if r > best[1]:
            best = (sub, r, f"{ev} {r:.0%}")
    dtr = p.get("datetime_rate", 0)
    if dtr >= .8 and p.get("numeric_rate", 0) < .5:
        span = p.get("year_max", 0) - p.get("year_min", 0)
        if p.get("year_min", 9999) < 1995 and span >= 25 and p.get("time_rate", 0) < .2:
            return "BIRTH_DATE", dtr, f"dates spanning {p['year_min']}-{p['year_max']}"
        if p.get("time_rate", 0) >= .8:
            return "TIMESTAMP", dtr, f"datetime with time {dtr:.0%}"
        return "DATE", dtr, f"date {dtr:.0%}"
    if _rate(vals, _rx("AGE_BAND")) >= .8:
        return "AGE", .8, "age-band notation"
    if p.get("numeric_rate", 0) >= .9:
        num = pd.to_numeric(vals.str.replace(r"[\s\u00a0]", "", regex=True).str.replace(",", "."), errors="coerce")
        decimals = vals.str.extract(r"[.,](\d+)$")[0].str.len().fillna(0)
        if _rate(vals, _rx("MONEY")) >= .8:
            return "FINANCIAL_DATA", .6, "money format"
        if num.abs().max() <= 180 and decimals.mean() >= 4:
            return "GPS_COORDINATE", .7, "high-precision coordinates"
        if p.get("integer_rate", 0) >= .95 and p["distinct_ratio"] >= .98 and p["null_rate"] == 0:
            return "RECORD_ID", .6, "unique integers"
        return "MEASUREMENT", .65, "numeric"
    if p["mean_len"] >= 25 and p["mean_words"] >= 4 and p["distinct_ratio"] > .3:
        return "FREE_TEXT", .8, f"text, mean {p['mean_words']:.0f} words"
    if p["mean_len"] >= 20 and p["mean_words"] >= 2.5 and p["distinct_ratio"] > .3:
        return "FREE_TEXT", .65, f"short text, mean {p['mean_words']:.0f} words"
    if _rate(vals, _rx("ID_LIKE")) >= .9 and p["mean_words"] <= 1.05:
        return ("RECORD_ID" if p["distinct_ratio"] >= .98 else "ENTITY_ID"), .7, f"identifier-like, distinct {p['distinct_ratio']:.0%}"
    if best[1] >= .5:
        return best[0], best[1], best[2]
    return "CATEGORY", .55 if p["distinct"] <= 50 else .45, f"{p['distinct']} distinct values"


def _name_subtype(col: str) -> str | None:
    name = col.lower()
    for rx, sub in NAME_HINTS:
        if re.search(rx, name):
            return sub
    return None


def classify_column(col: str, s: pd.Series, table: str = "") -> dict:
    """Subtype + confidence + evidence for one column (role is resolved per table)."""
    p = profile(s)
    vals = _nonblank(s).head(SAMPLE)
    vsub, vconf, ev = _value_subtype(vals, p)
    nsub = _name_subtype(col)
    sub, conf, own_key = vsub, vconf, False
    if vsub in ("RECORD_ID", "ENTITY_ID"):
        if nsub in ENTITY_IDS:
            sub, conf, ev = (nsub, .8, ev + f"; name suggests {nsub}")
        own_key = vsub == "RECORD_ID" and col.lower().split("_")[0] in {t.removesuffix("s") for t in table.lower().split("_")}
        if own_key:
            conf, ev = .85, ev + "; key of its own table"
    elif nsub and nsub != vsub and vconf < .8:
        # weak value evidence: let a specific name hint win, but stay below auto-accept confidence
        generic = vsub in (None, "CATEGORY", "MEASUREMENT", "FREE_TEXT") or vconf < .5
        if generic and not (nsub == "FREE_TEXT" and p["distinct"] < 50):
            sub, conf, ev = nsub, .55, f"column name suggests {nsub}; values: {ev}"
    elif nsub == vsub:
        conf = min(.99, vconf + .1)
        ev += "; name agrees"
    if sub == "TECH_HASH":
        sub, ev = "OTHER", ev + " (hashed identifier)"
    if sub == "MEASUREMENT" and nsub == "AGE":
        sub = "AGE"
    return {"column": col, "subtype": sub, "confidence": round(conf, 2), "evidence": ev, "own_key": own_key,
            "from_values": sub == vsub, "profile": p}


def _role(c: dict, person_table: bool, health_table: bool) -> tuple[str, float]:
    sub, conf, col = c["subtype"], c["confidence"], c["column"].lower()
    if sub in DIRECT:
        return "direct_identifier", conf
    if sub == "STREET_ADDRESS":
        return ("direct_identifier" if person_table else "quasi_identifier"), conf
    if sub in TECHNICAL or sub == "OTHER":
        return "technical_identifier", conf
    if sub == "RECORD_ID" or c["own_key"]:
        return "record_key", conf
    if sub in ENTITY_IDS or sub == "ENTITY_ID":
        return "technical_identifier", conf
    if sub == "FREE_TEXT":
        return "free_text", conf
    if sub == "DIAGNOSIS_CODE" or SENSITIVE_HINTS.search(col):
        return "sensitive_attribute", min(conf, .75)
    if sub == "FINANCIAL_DATA" and person_table:
        return "sensitive_attribute", conf
    if sub == "MEASUREMENT" and health_table and (MEASURE_HINTS.search(col) or person_table):
        return "sensitive_attribute", min(conf, .65)
    if sub in PERSON_QI:
        return "quasi_identifier", conf
    if sub in CONTEXT_QI or sub == "URL":
        return ("quasi_identifier" if person_table else "non_sensitive"), conf
    return "non_sensitive", conf


def detect_table(df: pd.DataFrame, table: str, dataset: str = "") -> pd.DataFrame:
    """Labels for every column of one table, in taxonomy vocabulary plus confidence and evidence."""
    cols = [classify_column(c, df[c], table) for c in df.columns]
    subs = {c["subtype"] for c in cols}
    # a table is about people only on value evidence of personal identifiers or person attributes, or an
    # identifier the column name ties to a person; name-only guesses and generic repeating ids don't count
    person_table = any((c["from_values"] and c["confidence"] >= REVIEW_BELOW and c["subtype"] in DIRECT)
                       or (c["from_values"] and c["confidence"] >= .8 and c["subtype"] in PERSON_QI | PERSONAL_DEVICES)
                       or (c["subtype"] in PERSON_IDS and c["confidence"] >= REVIEW_BELOW) for c in cols)
    health_table = "DIAGNOSIS_CODE" in subs or bool(HEALTH_CONTEXT.search(" ".join([table, *df.columns]).lower()))
    rows = []
    for c in cols:
        role, conf = _role(c, person_table, health_table)
        sub = {"ENTITY_ID": "OTHER"}.get(c["subtype"], c["subtype"])
        ev = c["evidence"] + ("; person table" if person_table else "")
        rows.append({"dataset": dataset, "table": table, "column": c["column"], "privacy_role": role,
                     "subtype": sub, "confidence": round(conf, 2), "evidence": ev})
    return pd.DataFrame(rows, columns=COLUMNS)


def review_queue(labels: pd.DataFrame) -> pd.DataFrame:
    """Columns needing human confirmation; until resolved they get the most protective handling."""
    return labels[labels.confidence < REVIEW_BELOW]


def _dataset_dirs(data: Path) -> list[Path]:
    return [data] if any(data.glob("*.csv")) else sorted(d for d in data.iterdir() if d.is_dir() and any(d.glob("*.csv")))


def detect_dir(data: Path, rows: int = 20000) -> pd.DataFrame:
    out = []
    for d in _dataset_dirs(Path(data)):
        for f in sorted(d.glob("*.csv")):
            if f.stem.startswith(("rowmap_", "_")):
                continue
            df = pd.read_csv(f, dtype=str, keep_default_na=False, nrows=rows)
            out.append(detect_table(df, f.stem, d.name))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=COLUMNS)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="-")
    ap.add_argument("--rows", type=int, default=20000, help="rows read per table")
    a = ap.parse_args(argv)
    labels = detect_dir(Path(a.data), a.rows)
    if a.out == "-":
        print(labels.to_csv(index=False), end="")
    else:
        out = Path(a.out)
        if out.exists():
            raise SystemExit(f"refusing to overwrite {out}")
        labels.to_csv(out, index=False)
        print(f"wrote {len(labels)} labels ({len(review_queue(labels))} for review) -> {out}")


if __name__ == "__main__":
    main()
