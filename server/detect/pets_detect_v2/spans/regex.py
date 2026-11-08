"""Layer 1: structured identifiers in text, with checksums where the format has one.

Returns spans {start, end, label, confidence, source}. Labels follow metadata/pii_span_guidelines.md.
"""
from __future__ import annotations

import re

from pets_detect.patterns import hetu_valid, iban_valid, luhn_valid

Span = dict


def _sp(m, label, conf, g=0, src="regex") -> Span:
    return {"start": m.start(g), "end": m.end(g), "label": label, "confidence": conf, "source": src}


_TRAIL = ".,;:!?)]}'\""

RX_URL = re.compile(r"https?://[^\s<>\"]+")
RX_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
RX_HETU = re.compile(r"(?<![\w-])\d{6}[-+A-FU-Ya-fu-y]?\d{3}[0-9A-Ya-y](?![\w-])")
RX_IBAN = re.compile(r"(?<!\w)[Ff][Ii] ?\d{2}(?: ?\d{4}){3} ?\d{2}(?!\d)")
RX_CARD = re.compile(r"(?<![\d-])(?:\d{4}[ -]?){3}\d{4}(?![\d-])")
RX_CARD_END = re.compile(r"(?i)\b(?:ending(?: in)?|päättyy|päättyvä\w*|slutar på|loppuu|ending with)\s+(\d{4})\b")
RX_IMEI = re.compile(r"(?<![\d-])(?:\d{15}|\d{5} \d{5} \d{5})(?![\d-])")
RX_DEVICE = re.compile(r"\b[A-Z]{2}-[A-Z]{4,8}-\d{3,5}\b")
RX_PROPERTY = re.compile(r"(?<![\d-])\d{3}-\d{3}-\d{1,4}-\d{1,4}(?![\d-])")
RX_PHONE = re.compile(r"(?<![\w+])(?:\+358|00358)(?:[ \-]*\d){7,10}(?!\d)|(?<![\w-])0\d{1,2}(?:[ \-]?\d){6,8}(?![\d-])")
RX_IPV4 = re.compile(r"(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\d.])")
RX_PLATE = re.compile(r"(?<![\w-])[A-ZÅÄÖ]{2,3}-\d{1,3}(?![\w-])")
RX_DATE = re.compile(r"(?<![\d.])(?:[0-3]?\d)\.(?:[01]?\d)\.(?:(?:19|20)\d{2})?(?![\d])|\b(?:19|20)\d{2}-[01]\d-[0-3]\d\b")
RX_ACCOUNT = re.compile(r"(?<![\d\-+.])(?:4\d{7}|4\d{3} \d{4})(?![\d\-.])")
RX_AGE = re.compile(r"(?i)\b(\d{1,3})(?:-vuotias\w*| vuotta(?: vanha)?| vuoden ikäinen| år(?: gammal)?| years? old| v\.)")
RX_AGE2 = re.compile(r"(?i)\b(?:i'm|i am|olen|jag är|age|ikä)\s+(\d{2,3})\b(?!\s*(?:€|eur|euro|kr|%|min|h\b|tuntia|kertaa))")
RX_SECRET = re.compile(r"(?i)\b(?:salasana(?:ni|n)?|password|lösenord(?:et)?|pin(?:-koodi)?|wifin salasana)"
                       r"(?:\s+(?:on|is|är|was|oli))?(?:\s+(?:varmaan|probably|nog|kai))?\s*:?\s+([^\s,]+[^\s,.!?])")
RX_USERNAME = re.compile(r"(?i)\b(?:käyttäjätunnu\w*|username(?: there| three)?|användarnamn(?:et)?|user ?name)"
                         r"(?:\s+(?:on|is|är))?\s*:?\s+([^\s,]+[^\s,.!?])")

PRIVATE_IP = ("10.", "127.", "192.168.", "0.", "255.")


def find(text: str) -> list[Span]:
    out: list[Span] = []
    for m in RX_URL.finditer(text):
        e = m.end()
        while e > m.start() and text[e - 1] in _TRAIL:
            e -= 1
        out.append({"start": m.start(), "end": e, "label": "URL", "confidence": .97, "source": "regex"})
    for m in RX_USERNAME.finditer(text):
        out.append(_sp(m, "USERNAME", .9, 1))
    for m in RX_SECRET.finditer(text):
        out.append(_sp(m, "SECRET", .85, 1))
    for m in RX_EMAIL.finditer(text):
        out.append(_sp(m, "EMAIL", .97))
    for m in RX_HETU.finditer(text):
        v = m.group(0).upper()
        if hetu_valid(v):
            out.append(_sp(m, "NATIONAL_ID", .99))
    for m in RX_IBAN.finditer(text):
        if iban_valid(m.group(0).replace(" ", "").upper()):
            out.append(_sp(m, "IBAN", .99))
    for m in RX_CARD.finditer(text):
        if luhn_valid(re.sub(r"\D", "", m.group(0))):
            out.append(_sp(m, "PAYMENT_CARD", .95))
    for m in RX_CARD_END.finditer(text):
        out.append(_sp(m, "PAYMENT_CARD", .85, 1))
    for m in RX_IMEI.finditer(text):
        out.append(_sp(m, "DEVICE_ID", .85))
    for m in RX_DEVICE.finditer(text):
        out.append(_sp(m, "DEVICE_ID", .8))
    for m in RX_PROPERTY.finditer(text):
        out.append(_sp(m, "PROPERTY_ID", .9))
    for m in RX_PHONE.finditer(text):
        out.append(_sp(m, "PHONE", .9))
    for m in RX_IPV4.finditer(text):
        if all(int(g) <= 255 for g in m.groups()) and not m.group(0).startswith(PRIVATE_IP):
            out.append(_sp(m, "IP_ADDRESS", .9))
    for m in RX_PLATE.finditer(text):
        out.append(_sp(m, "LICENSE_PLATE", .85))
    for m in RX_ACCOUNT.finditer(text):
        out.append(_sp(m, "ACCOUNT_NUMBER", .6))
    for m in RX_AGE.finditer(text):
        out.append(_sp(m, "AGE", .85, 1))
    for m in RX_AGE2.finditer(text):
        out.append(_sp(m, "AGE", .6, 1))
    return out


B2_RX = [
    ("NATIONAL_ID", re.compile(r"\b\d{6}[-+A-FU-Y]\d{3}[0-9A-Y]\b")),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[0-9A-Z]{4}){2,7}(?: ?[0-9A-Z]{1,3})?\b")),
    ("URL", re.compile(r"https?://\S+")),
    ("PAYMENT_CARD", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    ("PHONE", re.compile(r"(?:\+\d{2,3}[\s-]?|\b0)\d{1,3}[\s-]?\d{3,4}[\s-]?\d{2,4}\b")),
    ("IP_ADDRESS", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")),
    ("MAC", re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")),
    ("LICENSE_PLATE", re.compile(r"\b[A-ZÅÄÖ]{2,3}-\d{1,3}\b")),
]


def b2_spans(text: str) -> list[Span]:
    """Copy of baselines/_common.py::_RX applied in order (as regex_redact does), returned as spans."""
    out: list[Span] = []
    for label, rx in B2_RX:
        for m in rx.finditer(text):
            if not any(m.start() < s["end"] and s["start"] < m.end() for s in out):
                out.append({"start": m.start(), "end": m.end(), "label": label})
    return out
