"""Layer 5: merge spans from all layers and give the same entity the same id.

Priority on overlap: regex (checksummed formats) > spoken > tagger. A lower-priority span that overlaps a kept span
is dropped, except that a tagger span with the same label may widen the kept span (e.g. "Ahdepolku 32 A 1, 20250
Turku" where regex only saw the postcode part).
"""
from __future__ import annotations

import re

PRIORITY = {"regex": 0, "spoken": 1, "tagger": 2}


def merge(spans: list[dict]) -> list[dict]:
    spans = sorted(spans, key=lambda s: (PRIORITY.get(s.get("source"), 3), -(s["end"] - s["start"])))
    kept: list[dict] = []
    for s in spans:
        hit = [k for k in kept if s["start"] < k["end"] and k["start"] < s["end"]]
        if not hit:
            kept.append(dict(s))
            continue
        if s.get("source") == "tagger" and len(hit) == 1 and hit[0]["label"] == s["label"]:
            k = hit[0]
            k["start"], k["end"] = min(k["start"], s["start"]), max(k["end"], s["end"])
    return sorted(kept, key=lambda s: s["start"])


def _norm(t: str) -> str:
    return re.sub(r"[\s\-.,]", "", t.lower())


def assign_entities(groups: dict[str, list[tuple[str, str, list[dict]]]]) -> None:
    """groups: {group key (e.g. conversation): [(record_id, text, spans)]}. Adds entity_id in place.

    The same normalised value inside one group gets one id (P1, P2 ... per label prefix); a lone first name that
    matches the first token of a full name already seen joins that person."""
    prefix = {"PERSON": "P", "PHONE": "TEL", "EMAIL": "EM", "NATIONAL_ID": "ID", "ADDRESS": "ADR",
              "ACCOUNT_NUMBER": "ACC", "IBAN": "IBAN", "PAYMENT_CARD": "CARD"}
    for _, recs in groups.items():
        seen: dict[tuple[str, str], str] = {}
        first_of: dict[str, str] = {}
        count: dict[str, int] = {}
        for _, text, spans in recs:
            for s in spans:
                v = _norm(text[s["start"]:s["end"]])
                key = (s["label"], v)
                if key not in seen and s["label"] == "PERSON":
                    parts = text[s["start"]:s["end"]].lower().split()
                    if len(parts) == 1 and parts[0] in first_of:
                        seen[key] = first_of[parts[0]]
                if key not in seen:
                    p = prefix.get(s["label"], s["label"][:3])
                    count[p] = count.get(p, 0) + 1
                    seen[key] = f"{p}{count[p]}"
                    if s["label"] == "PERSON":
                        parts = text[s["start"]:s["end"]].lower().split()
                        if len(parts) > 1:
                            first_of.setdefault(parts[0], seen[key])
                s["entity_id"] = seen[key]
