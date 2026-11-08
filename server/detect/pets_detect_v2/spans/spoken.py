"""Layer 2: identifiers read aloud (ASR transcripts) or spelled out.

  "nolla neljä neljä, kuusi kolme yksi, ..."      -> PHONE
  "f i seitsemän kuusi, yhdeksän kuusi ..."       -> IBAN
  "070889 streck 965 2" / "050182 viiva 941 j"    -> NATIONAL_ID
  "akotkaaho snabel-a nordmail punkt example"     -> EMAIL

Instead of rewriting the text (which would shift every offset), we find runs of digit words / digits directly in
the original text, so spans always point at the original characters.
"""
from __future__ import annotations

import re

NUM_WORDS = {
    "nolla", "yksi", "kaksi", "kolme", "neljä", "viisi", "kuusi", "seitsemän", "kahdeksan", "yhdeksän",
    "noll", "ett", "en", "två", "tre", "fyra", "fem", "sex", "sju", "åtta", "nio",
    "zero", "oh", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
}
WEAK = {"en", "ett", "oh", "one", "sex", "tre"}
SEPS = {"viiva", "streck", "dash", "miinus", "väliviiva", "bindestreck"}

TOK = re.compile(r"[\wåäöÅÄÖ]+|[,\-]")

CONTEXT = [
    ("IBAN", r"iban|tilinumer|tilille|tili |konto|account number|bankkonto|f i\b|fi\b"),
    ("NATIONAL_ID", r"hetu|henkilötunnu|personbeteckning|personnummer|social security|identity code|id code"),
    ("DEVICE_ID", r"imei|laitetunn|serial"),
    ("PAYMENT_CARD", r"kortti|kortin|card|kort\b|kortnummer"),
    ("ACCOUNT_NUMBER", r"asiakasnumer|kundnummer|customer number|invoice|lasku|faktura|sopimusnumer|contract number"),
    ("PHONE", r"puhelin|numero|nummer|phone|soitti|ring|call|tekstiviesti|sms|liittymä"),
]


def _label_for(text: str, start: int, n_digits: int, has_fi: bool) -> tuple[str, float]:
    ctx = text[max(0, start - 60):start].lower()
    if has_fi:
        return "IBAN", .9
    best = None
    for label, rx in CONTEXT:
        m = None
        for m in re.finditer(rx, ctx):
            pass
        if m and (best is None or m.end() > best[1]):
            best = (label, m.end())
    if best:
        return best[0], .85
    if n_digits in (15, 16):
        return ("DEVICE_ID" if n_digits == 15 else "PAYMENT_CARD"), .7
    if 9 <= n_digits <= 12:
        return "PHONE", .7
    if n_digits == 8:
        return "ACCOUNT_NUMBER", .6
    return "PHONE", .5


def _digits(tok: str) -> int:
    t = tok.lower()
    if t.isdigit():
        return len(t)
    return 1 if t in NUM_WORDS else 0


def find(text: str) -> list[dict]:
    out = []
    toks = [(m.group(0), m.start(), m.end()) for m in TOK.finditer(text)]
    i, n = 0, len(toks)
    while i < n:
        w = toks[i][0].lower()
        has_fi = False
        j = i
        if w == "f" and i + 1 < n and toks[i + 1][0].lower() == "i":
            has_fi, j = True, i + 2
        if j < n and _digits(toks[j][0]) == 0:
            i += 1
            continue
        start_tok, k, digits, words, last = j, j, 0, 0, j
        while k < n:
            t = toks[k][0]
            d = _digits(t)
            if d:
                digits += d
                words += 0 if t.isdigit() else 1
                last = k
            elif t in (",", "-") or t.lower() in SEPS:
                pass
            else:
                break
            k += 1
        if words >= 3 and digits >= 4 or (words >= 1 and digits >= 7):
            first = toks[i if has_fi else start_tok]
            if not (words == digits and all(toks[x][0].lower() in WEAK for x in range(start_tok, last + 1)
                                            if _digits(toks[x][0]))):
                label, conf = _label_for(text, first[1], digits, has_fi)
                out.append({"start": first[1], "end": toks[last][2], "label": label, "confidence": conf,
                            "source": "spoken"})
            i = last + 1
        else:
            i = max(i + 1, j + 1 if has_fi else i + 1)
    out += hetu_spoken(text) + email_spoken(text)
    return out


RX_HETU_SPOKEN = re.compile(r"(?i)(?<!\d)(\d{2} ?\d{2} ?\d{2})\s*(?:viiva|streck|dash|miinus|plus|-)\s*"
                            r"(\d ?\d ?\d)\s*([0-9a-y])\b")


def hetu_spoken(text: str) -> list[dict]:
    return [{"start": m.start(), "end": m.end(), "label": "NATIONAL_ID", "confidence": .9, "source": "spoken"}
            for m in RX_HETU_SPOKEN.finditer(text)]


_AT = r"(?:snabel-a|snabel a|ät|at|@|miukumauku)"
_DOT = r"(?:piste|punkt|dot|\.)"
RX_EMAIL_SPOKEN = re.compile(
    rf"(?i)\b[\w.]+(?:\s+{_DOT}\s+[\w]+)*\s+{_AT}\s+[\w\-]+(?:\s+{_DOT}\s+[\w\-]+)+")


def email_spoken(text: str) -> list[dict]:
    out = []
    for m in RX_EMAIL_SPOKEN.finditer(text):
        s = m.group(0).lower()
        if not re.search(r"\b(?:piste|punkt|dot)\b", s):
            continue
        out.append({"start": m.start(), "end": m.end(), "label": "EMAIL", "confidence": .85, "source": "spoken"})
    return out
