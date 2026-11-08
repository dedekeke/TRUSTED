"""Detect handoff contract v1: bind labels/spans/linkage to the exact input bytes; keep only counts and digests.

Rejections raise ArtifactError with a named `code`. Span/linkage problems become named plan issues instead.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

PROVENANCE_SCHEMA = "pets.select.provenance/1"
MANIFEST_SCHEMA = "pets.detect.manifest/1"
SPANS_SCHEMA = "pets.detect.spans/1"
LINKAGE_SCHEMA = "pets.detect.linkage/1"
ID_RX = re.compile(r"[0-9a-f]{16}")
SPAN_KEYS = {"span_id", "table", "column", "row_index", "start", "end", "entity_type", "entity_id", "confidence",
             "needs_review"}


class ArtifactError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def input_files(data) -> dict[str, Path]:
    """The CSVs selection loads, keyed by table name."""
    return {f.stem: f for f in sorted(Path(data).glob("*.csv")) if not f.stem.startswith(("rowmap_", "_"))}


def input_shas(data) -> dict[str, str]:
    return {t: sha256_file(f) for t, f in input_files(data).items()}


def dataset_fingerprint(shas: dict[str, str]) -> str:
    return sha256_bytes("\n".join(f"{t}:{shas[t]}" for t in sorted(shas)).encode())


def span_id(fingerprint, table, column, row_index, start, end) -> str:
    return sha256_bytes(f"{fingerprint}|{table}|{column}|{row_index}|{start}|{end}".encode())[:16]


def _compare_inputs(expected: dict, shas: dict, what: str) -> None:
    if set(expected) != set(shas):
        raise ArtifactError("table_set_mismatch", f"{what} lists tables {sorted(expected)} but the data has "
                                                  f"{sorted(shas)}")
    stale = sorted(t for t in shas if expected[t] != shas[t])
    if stale:
        raise ArtifactError("input_mismatch", f"{what} was made for other bytes of table(s) {', '.join(stale)}")


def load_manifest(labels_path, data, dataset, manifest_path=None) -> dict:
    """Validate manifest.json against the --data bytes and the labels file; return it with resolved artifact paths."""
    path = Path(manifest_path) if manifest_path else Path(labels_path).parent / "manifest.json"
    if not path.is_file():
        raise ArtifactError("manifest_missing", f"--labels needs the detect manifest {path} (or --manifest)")
    try:
        manifest = json.loads(path.read_text())
    except ValueError as e:
        raise ArtifactError("manifest_schema", f"{path} is not JSON: {e}") from None
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ArtifactError("manifest_schema", f"{path}: expected schema {MANIFEST_SCHEMA}")
    if manifest.get("dataset") != dataset:
        raise ArtifactError("dataset_mismatch", f"manifest is for dataset {manifest.get('dataset')!r}, data is {dataset!r}")
    inputs = manifest.get("inputs")
    if not isinstance(inputs, dict) or not all(isinstance(v, dict) and "sha256" in v for v in inputs.values()):
        raise ArtifactError("manifest_schema", "manifest inputs need {table: {sha256, ...}}")
    shas = input_shas(data)
    _compare_inputs({t: v["sha256"] for t, v in inputs.items()}, shas, "detect manifest")
    if manifest.get("dataset_fingerprint") != dataset_fingerprint(shas):
        raise ArtifactError("fingerprint_mismatch", "manifest dataset_fingerprint does not match its inputs")
    arts = manifest.get("artifacts") or {}
    if not isinstance(arts, dict) or "labels" not in arts or not all(
            isinstance(a, dict) and isinstance(a.get("file"), str) and isinstance(a.get("sha256"), str)
            and Path(a["file"]).name == a["file"] for a in arts.values()):
        raise ArtifactError("manifest_schema", "manifest artifacts need labels and {file, sha256} entries "
                                               "naming files in the detect directory")
    columns = arts.get("spans", {}).get("columns")
    if columns is not None and not (isinstance(columns, dict) and all(isinstance(v, dict) for v in columns.values())):
        raise ArtifactError("manifest_schema", "artifacts.spans.columns must map table.column to {cells, spans}")
    vocab = manifest.get("label_vocabulary") or []
    if not isinstance(vocab, list) or not all(isinstance(v, list) and len(v) == 2 for v in vocab):
        raise ArtifactError("manifest_schema", "label_vocabulary must be a list of [privacy_role, subtype] pairs")
    if not isinstance(manifest.get("detector") or {}, dict):
        raise ArtifactError("manifest_schema", "manifest detector must be an object")
    resolved = {}
    for name, art in arts.items():
        file = path.parent / art["file"]
        if name == "labels" and Path(labels_path).resolve() != file.resolve():
            raise ArtifactError("labels_mismatch", f"--labels {labels_path} is not the manifest's labels {file}")
        if not file.is_file():
            raise ArtifactError("artifact_missing", f"manifest {name} artifact {file} is missing")
        if sha256_file(file) != art.get("sha256"):
            raise ArtifactError("labels_mismatch" if name == "labels" else "artifact_mismatch",
                                f"{name} artifact {file.name} does not match its manifest sha256")
        resolved[name] = file
    if "spans" in arts and arts["spans"].get("schema") != SPANS_SCHEMA:
        raise ArtifactError("manifest_schema", f"spans artifact must declare schema {SPANS_SCHEMA}")
    return {**manifest, "_paths": resolved}


def provenance(data, manifest: dict | None, confirm_sha256: str | None = None, detector_version=None) -> dict:
    """decisions.json provenance; without a manifest (legacy built-in detector) it is marked unbound."""
    shas = input_shas(data)
    out = {"schema": PROVENANCE_SCHEMA, "bound": manifest is not None,
           "dataset_fingerprint": dataset_fingerprint(shas), "inputs": shas,
           "labels_sha256": None, "spans_sha256": None, "linkage_sha256": None, "confirm_sha256": confirm_sha256}
    if manifest is None:
        out["detector"] = {"name": "server.select.detect (legacy, unbound)", "version": detector_version,
                           "model_sha256": None}
        return out
    det = manifest.get("detector") or {}
    out["detector"] = {k: det.get(k) for k in ("name", "version", "model_sha256")}
    for name, art in (manifest.get("artifacts") or {}).items():
        out[f"{name}_sha256"] = art.get("sha256")
    return out


def check_plan(data, plan: dict, plan_bytes: bytes) -> str:
    """Search-side binding: the plan's provenance must describe the --data bytes. Returns plan_sha256."""
    prov = plan.get("provenance")
    if not isinstance(prov, dict) or prov.get("schema") != PROVENANCE_SCHEMA:
        raise ArtifactError("provenance_missing", "plan has no select provenance; re-run select on this data")
    shas = input_shas(data)
    _compare_inputs(prov.get("inputs") or {}, shas, "plan")
    if prov.get("dataset_fingerprint") != dataset_fingerprint(shas):
        raise ArtifactError("fingerprint_mismatch", "plan dataset_fingerprint does not match the data")
    return sha256_bytes(plan_bytes)


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def subject_suggestions(manifest: dict | None, tables: dict) -> list[dict]:
    """Detect's subject suggestions (linkage kind "subject") as {table, column, confidence, needs_review,
    non_blank_share}; only columns of the input. The linkage schema itself is checked in check_evidence."""
    path = (manifest or {}).get("_paths", {}).get("linkage")
    if not path:
        return []
    try:
        link = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return []
    schema = {(t, c) for t, df in tables.items() for c in df.columns}
    out = []
    for r in (link.get("relations") or []) if isinstance(link, dict) else []:
        left = r.get("left") if isinstance(r, dict) else None
        if not isinstance(left, dict) or r.get("kind") != "subject" or (left.get("table"), left.get("column")) not in schema:
            continue
        ev = r.get("evidence") if isinstance(r.get("evidence"), dict) else {}
        out.append({"table": left["table"], "column": left["column"], "confidence": float(r.get("confidence") or 0),
                    "needs_review": bool(r.get("needs_review")), "non_blank_share": float(ev.get("non_blank_share") or 0)})
    return out


def check_evidence(plan: dict, tables: dict, labels, manifest: dict) -> tuple[list, list, dict]:
    """(errors, warnings, summary) for spans/linkage. Summary holds counts and ids only, never text or values."""
    errors, warnings = [], []
    fp = manifest["dataset_fingerprint"]
    released = {f"{c['table']}.{c['column']}" for c in plan["columns"] if c["action"] != "DROP"}
    plan_join = {r for j in plan.get("joins", []) for r in (j["parent"], j["child"])}

    by_column, stale, path = {}, [], manifest["_paths"].get("spans")
    for n, line in enumerate(path.read_text().splitlines() if path else [], 1):
        if not line.strip():
            continue
        s = None
        try:
            s = json.loads(line)
            ok = isinstance(s, dict) and SPAN_KEYS <= set(s) and s["table"] in tables and \
                s["column"] in tables[s["table"]] and all(_int(s[k]) for k in ("row_index", "start", "end"))
            cell = tables[s["table"]][s["column"]] if ok else None
            ok = ok and 0 <= s["row_index"] < len(cell) and 0 <= s["start"] < s["end"] <= len(cell.iat[s["row_index"]]) \
                and s["span_id"] == span_id(fp, s["table"], s["column"], s["row_index"], s["start"], s["end"])
        except (ValueError, TypeError, KeyError):
            ok = False
        if not ok:
            sid = s.get("span_id") if isinstance(s, dict) else None
            stale.append(sid if isinstance(sid, str) and ID_RX.fullmatch(sid) else f"line {n}")
            continue
        ref = f"{s['table']}.{s['column']}"
        by_column[ref] = by_column.get(ref, 0) + 1
    if stale:
        errors.append(f"stale_span: {len(stale)} span(s) do not match the current data/offsets "
                      f"(e.g. {', '.join(stale[:3])}); re-run detect")
    scanned = manifest.get("artifacts", {}).get("spans", {}).get("columns")
    scanned = by_column if scanned is None else scanned
    for r in labels.to_dict("records"):
        ref = f"{r['table']}.{r['column']}"
        if (r["privacy_role"] == "free_text" or r["subtype"] == "FREE_TEXT") and ref not in scanned:
            (errors if ref in released else warnings).append(
                f"missing_span_evidence: free-text column {ref} has no detect spans")

    relations, ambiguous, path = [], set(), manifest["_paths"].get("linkage")
    subjects = set((plan.get("subject_keys") or {}).values())
    if path:
        try:
            link = json.loads(path.read_text())
        except ValueError:
            link = None
        if not isinstance(link, dict) or link.get("schema") != LINKAGE_SCHEMA or \
                not isinstance(link.get("relations") or [], list):
            raise ArtifactError("manifest_schema", f"linkage artifact must be JSON with schema {LINKAGE_SCHEMA}")
        relations = [r for r in link.get("relations") or [] if isinstance(r, dict)]
        if len(relations) != len(link.get("relations") or []):
            raise ArtifactError("manifest_schema", "linkage relations must be objects")
    else:
        keyed = sorted(released & (plan_join | subjects))
        (errors if keyed else warnings).append(
            "missing_linkage_evidence: no detect linkage artifact" +
            (f"; released join/subject columns {', '.join(keyed)} are unchecked" if keyed else ""))
    schema = {f"{t}.{c}" for t, df in tables.items() for c in df.columns}

    def ref(side):
        x = f"{side.get('table')}.{side.get('column')}" if isinstance(side, dict) else None
        return x if x in schema else None

    def rid(r, i):
        x = r.get("relation_id")
        return x if isinstance(x, str) and ID_RX.fullmatch(x) else f"relation {i}"

    ours = {frozenset((j["parent"], j["child"])) for j in plan.get("joins", [])}
    parents = {j["parent"] for j in plan.get("joins", [])}
    joins = [(i, r, ref(r.get("left")), ref(r.get("right"))) for i, r in enumerate(relations) if r.get("kind") == "join"]
    partners = {}
    for _, _, a, b in joins:
        if a and b:
            partners.setdefault(a, set()).add(b)
            partners.setdefault(b, set()).add(a)
    for i, r, a, b in joins:
        if not (a and b):
            ambiguous.add(rid(r, i))
            warnings.append(f"ambiguous_join: detect relation {rid(r, i)} names a column missing from the input")
            continue
        if r.get("needs_review") or any(len(partners[x]) > 1 and x not in parents for x in (a, b)) or \
                ((a in plan_join or b in plan_join) and frozenset((a, b)) not in ours):
            ambiguous.add(rid(r, i))
            (errors if {a, b} & (plan_join | released) else warnings).append(
                f"ambiguous_join: detect relation {rid(r, i)} ({a} -> {b}) is under review, "
                "conflicting or not confirmed by selection's joins")
    for i, r in enumerate(relations):
        if r.get("kind") != "subject":
            continue
        x = ref(r.get("left"))
        if x not in subjects:
            ambiguous.add(rid(r, i))
            warnings.append(f"ambiguous_subject: detect relation {rid(r, i)} suggests "
                            f"{x or 'a column missing from the input'} as a subject key; selection resolved "
                            f"{sorted(subjects) or 'none'} and does not adopt it")
    decisions = {f"{c['table']}.{c['column']}": c for c in plan["columns"]}
    embedded = 0
    for i, r in enumerate(relations):
        if r.get("kind") != "embedded":
            continue
        embedded += 1
        x, c = ref(r.get("left")), decisions.get(ref(r.get("left")) or "")
        if x and c and c["action"] not in ("DROP", "REDACT") and \
                not (c["action"] == "HMAC" and c.get("method") == "hmac_sha256"):
            warnings.append(f"embedded_qi: detect relation {rid(r, i)} says {x} encodes other attributes; it is "
                            f"released as {c['action']}/{c.get('method')}, which keeps them; check the "
                            "quasi-identifier risk or tokenise it")
    summary = {"spans": {"count": sum(by_column.values()), "by_column": by_column, "stale": len(stale)},
               "linkage": {"present": path is not None, "relations": len(relations), "joins": len(joins),
                           "subjects": sum(r.get("kind") == "subject" for r in relations), "embedded": embedded,
                           "ambiguous": sorted(map(str, ambiguous))}}
    return errors, warnings, summary
