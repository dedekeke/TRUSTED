"""Load and validate Detect free-text spans against the exact source text before they drive redaction.

Span files are Detect's JSONL format, one record per row of the text column, keyed by the table's record key:
  {"record_id": "N0000001", "spans": [{"start": 0, "end": 11, "label": "PERSON", "text": "...", ...}]}

Every span must carry its text: a span is accepted only if source_text[start:end] equals it, so spans made for
another revision of the data are rejected instead of redacting the wrong characters. Error messages name
record/span positions and counts only, never the text.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def load(path: Path) -> dict[str, list]:
    records: dict[str, list] = {}
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{Path(path).name}: line {n} is not valid JSON ({e.msg})") from None
            rid = rec.get("record_id") if isinstance(rec, dict) else None
            if not isinstance(rid, str) or not isinstance(rec.get("spans"), list):
                raise ValueError(f"{Path(path).name}: line {n} needs a string record_id and a spans list")
            if rid in records:
                raise ValueError(f"{Path(path).name}: record_id on line {n} is listed twice")
            records[rid] = rec["spans"]
    return records


def align(records: dict[str, list], texts: pd.Series, ids: pd.Series, ref: str) -> list[list]:
    """One validated span list per row, in row order. Raises on stale, missing or unknown records."""
    if ids.duplicated().any():
        raise ValueError(f"{ref}: record key is not unique, spans cannot be aligned to rows")
    errors, out = [], []
    known = set(ids.astype(str))
    unknown = [r for r in records if r not in known]
    if unknown:
        errors.append(f"{len(unknown)} span records name rows not in the source")
    missing = 0
    for rid, text in zip(ids.astype(str), texts.tolist()):
        text = text if isinstance(text, str) else ""
        spans = records.get(rid)
        if spans is None:
            missing += bool(text.strip())  # a blank cell needs no record
            out.append([])
            continue
        good = []
        for i, sp in enumerate(spans):
            if not isinstance(sp, dict) or not isinstance(sp.get("start"), int) or not isinstance(sp.get("end"), int) \
                    or isinstance(sp.get("start"), bool) or isinstance(sp.get("end"), bool):
                errors.append(f"record {rid} span {i}: integer start/end required")
                continue
            if not 0 <= sp["start"] < sp["end"] <= len(text):
                errors.append(f"record {rid} span {i}: offsets outside the source text")
                continue
            if not isinstance(sp.get("text"), str):
                errors.append(f"record {rid} span {i}: span text required to verify it matches the source")
                continue
            if text[sp["start"]:sp["end"]] != sp["text"]:
                errors.append(f"record {rid} span {i}: stale, does not match the current source text")
                continue
            good.append({"start": sp["start"], "end": sp["end"], "label": str(sp.get("label", "PII"))})
        out.append(good)
    if missing:
        errors.append(f"{missing} non-blank rows have no span record")
    if errors:
        shown = "; ".join(errors[:5]) + (f"; and {len(errors) - 5} more" if len(errors) > 5 else "")
        raise ValueError(f"{ref}: invalid Detect spans: {shown}")
    return out
