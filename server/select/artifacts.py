"""Detect handoff contract v1: bind labels/spans/linkage to the exact input bytes; keep only counts and digests.

Rejections raise ArtifactError with a named `code`. Span/linkage problems become named plan issues instead.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROVENANCE_SCHEMA = "pets.select.provenance/1"
MANIFEST_SCHEMA = "pets.detect.manifest/1"
SPANS_SCHEMA = "pets.detect.spans/1"
LINKAGE_SCHEMA = "pets.detect.linkage/1"
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
    if "labels" not in arts:
        raise ArtifactError("manifest_schema", "manifest artifacts need labels")
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
            stale.append(s.get("span_id") if isinstance(s, dict) and isinstance(s.get("span_id"), str) else f"line {n}")
            continue
        ref = f"{s['table']}.{s['column']}"
        by_column[ref] = by_column.get(ref, 0) + 1
    if stale:
        errors.append(f"stale_span: {len(stale)} span(s) do not match the current data/offsets "
                      f"(e.g. {', '.join(stale[:3])}); re-run detect")
    for r in labels.to_dict("records"):
        ref = f"{r['table']}.{r['column']}"
        if (r["privacy_role"] == "free_text" or r["subtype"] == "FREE_TEXT") and ref not in by_column:
            (errors if ref in released else warnings).append(
                f"missing_span_evidence: free-text column {ref} has no detect spans")

    relations, ambiguous, path = [], set(), manifest["_paths"].get("linkage")
    if path:
        link = json.loads(path.read_text())
        if not isinstance(link, dict) or link.get("schema") != LINKAGE_SCHEMA:
            raise ArtifactError("manifest_schema", f"linkage artifact must declare schema {LINKAGE_SCHEMA}")
        relations = link.get("relations") or []
    ours = {frozenset((j["parent"], j["child"])) for j in plan.get("joins", [])}
    joins = [r for r in relations if r.get("kind") == "join" and r.get("right")]
    partners = {}
    try:
        refs = [tuple(f"{r[s]['table']}.{r[s]['column']}" for s in ("left", "right")) for r in joins]
    except (KeyError, TypeError):
        raise ArtifactError("manifest_schema", "linkage join relations need left/right {table, column}") from None
    for a, b in refs:
        partners.setdefault(a, set()).add(b)
        partners.setdefault(b, set()).add(a)
    parents = {j["parent"] for j in plan.get("joins", [])}
    for r, (a, b) in zip(joins, refs):
        # under review, a non-key column linked to several partners, or a link selection's own joins contradict
        if r.get("needs_review") or any(len(partners[x]) > 1 and x not in parents for x in (a, b)) or \
                ((a in plan_join or b in plan_join) and frozenset((a, b)) not in ours):
            ambiguous.add(r.get("relation_id"))
            (errors if {a, b} & (plan_join | released) else warnings).append(
                f"ambiguous_join: detect relation {r.get('relation_id')} ({a} -> {b}) is under review, "
                "conflicting or not confirmed by selection's joins")
    ours_subjects = set((plan.get("subject_keys") or {}).values())
    for r in relations:
        if r.get("kind") != "subject" or not isinstance(r.get("left"), dict):
            continue
        ref = f"{r['left'].get('table')}.{r['left'].get('column')}"
        if ref not in ours_subjects:  # selection keeps its own subject resolution; never adopt the suggestion
            ambiguous.add(r.get("relation_id"))
            warnings.append(f"ambiguous_subject: detect relation {r.get('relation_id')} suggests {ref} as a subject "
                            f"key; selection resolved {sorted(ours_subjects) or 'none'} and does not adopt it")
    summary = {"spans": {"count": sum(by_column.values()), "by_column": by_column, "stale": len(stale)},
               "linkage": {"relations": len(relations), "joins": len(joins),
                           "subjects": sum(r.get("kind") == "subject" for r in relations),
                           "ambiguous": sorted(map(str, ambiguous))}}
    return errors, warnings, summary
