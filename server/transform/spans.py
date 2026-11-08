"""Load Detect spans (handoff contract v1) for free-text redaction, bound to the exact input bytes.

A Detect output directory holds manifest.json and spans.jsonl (schema pets.detect.spans/1), one span per line:
  {"span_id", "table", "column", "row_index", "start", "end", "entity_type", "entity_id", "confidence", ...}

Spans carry no text. They are accepted only when
- the manifest's dataset_fingerprint equals the current input bytes and the plan's provenance,
- spans.jsonl matches the manifest sha256 (and the plan's provenance spans_sha256 when bound),
- every span_id recomputes from (fingerprint, table, column, row_index, start, end) and the offsets fit the cell.
Errors name counts and 16-hex ids only, never text.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from server.select import artifacts as A


def load(detect_dir, data_dir, plan: dict) -> tuple[dict, dict]:
    """(manifest, {table.column: {row_index: [span, ...]}}) for every column Detect scanned."""
    detect_dir = Path(detect_dir)
    path = detect_dir / "manifest.json"
    if not path.is_file():
        raise A.ArtifactError("manifest_missing", f"--detect needs {path}")
    try:
        manifest = json.loads(path.read_text())
    except ValueError as e:
        raise A.ArtifactError("manifest_schema", f"{path.name} is not JSON: {e}") from None
    if not isinstance(manifest, dict) or manifest.get("schema") != A.MANIFEST_SCHEMA:
        raise A.ArtifactError("manifest_schema", f"expected schema {A.MANIFEST_SCHEMA}")
    fp = A.dataset_fingerprint(A.input_shas(data_dir))
    if manifest.get("dataset_fingerprint") != fp:
        raise A.ArtifactError("fingerprint_mismatch", "detect manifest was made for other input bytes")
    if (plan.get("provenance") or {}).get("dataset_fingerprint") not in (None, fp):
        raise A.ArtifactError("fingerprint_mismatch", "plan and detect manifest describe different input bytes")
    art = (manifest.get("artifacts") or {}).get("spans")
    if not isinstance(art, dict) or art.get("schema") != A.SPANS_SCHEMA or not isinstance(art.get("file"), str) \
            or Path(art["file"]).name != art["file"]:
        raise A.ArtifactError("manifest_schema", f"manifest has no spans artifact with schema {A.SPANS_SCHEMA}")
    file = detect_dir / art["file"]
    if not file.is_file():
        raise A.ArtifactError("artifact_missing", f"spans artifact {file.name} is missing")
    sha = A.sha256_file(file)
    if sha != art.get("sha256"):
        raise A.ArtifactError("artifact_mismatch", "spans.jsonl does not match its manifest sha256")
    bound = (plan.get("provenance") or {}).get("spans_sha256")
    if bound and bound != sha:
        raise A.ArtifactError("artifact_mismatch", "spans.jsonl is not the spans artifact the plan was selected with")
    by_ref: dict[str, dict[int, list]] = {ref: {} for ref in (art.get("columns") or {})}
    return {**manifest, "_spans_file": file, "_spans_sha256": sha}, by_ref


def align(manifest: dict, by_ref: dict, tables: dict[str, pd.DataFrame], refs: set[str]) -> dict[str, list[list]]:
    """Validated span lists per row for the requested free-text columns. Raises on any stale or malformed span."""
    fp = manifest["dataset_fingerprint"]
    stale, n = [], 0
    for line in manifest["_spans_file"].read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        n += 1
        try:
            s = json.loads(line)
            ok = isinstance(s, dict) and A.SPAN_KEYS <= set(s) and all(A._int(s[k]) for k in ("row_index", "start", "end"))
            ref = f"{s['table']}.{s['column']}" if ok else None
            if ok and ref in refs:
                cell = tables[s["table"]][s["column"]]
                ok = 0 <= s["row_index"] < len(cell) and 0 <= s["start"] < s["end"] <= len(str(cell.iat[s["row_index"]])) \
                    and s["span_id"] == A.span_id(fp, s["table"], s["column"], s["row_index"], s["start"], s["end"])
        except (ValueError, TypeError, KeyError):
            ok, s = False, None
        if not ok:
            sid = s.get("span_id") if isinstance(s, dict) else None
            stale.append(sid if isinstance(sid, str) and A.ID_RX.fullmatch(sid) else f"line {n}")
            continue
        if ref in refs:
            by_ref.setdefault(ref, {}).setdefault(s["row_index"], []).append(
                {"start": s["start"], "end": s["end"], "label": str(s["entity_type"]),
                 "entity_id": s["entity_id"] if isinstance(s.get("entity_id"), str) else None})
    if stale:
        raise A.ArtifactError("stale_span", f"{len(stale)} span(s) do not match the current data/offsets "
                                            f"(e.g. {', '.join(stale[:3])}); re-run detect")
    out = {}
    for ref in sorted(refs):
        t, c = ref.split(".", 1)
        rows = by_ref.get(ref)
        if rows is None:
            continue
        out[ref] = [rows.get(i, []) for i in range(len(tables[t][c]))]
    return out
