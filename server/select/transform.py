"""Plan re-validation and the legacy in-memory `apply` API.

The protection operations live in `server.actions` (shared with Select's previews); the final export stage,
with its release gate, output layout and serialized validation, is `server.transform`. `apply` remains for
programmatic use and tests: it runs the shared executor on a policy-valid plan and can write a minimal layout.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from server.actions import (  # noqa: F401  re-exported for older imports
    ADDRESS_RX, DATE_RX, DIAGNOSIS_MAPPING, ICD_RX, NAME_PAIR_RX, ROW_VALUE_LABELS, SPAN_LABEL, TIME_FORMATS,
    _blank, _fmt, _numeric, _rare, _time, apply_column, derive_age_band, execute, hmac_token, redact,
)

UNAPPROVED_STATUS = {"policy_valid", "target_unmet", "budget_exhausted", "measured_ok"}
UNAPPROVED_NOTICE = "NOT_APPROVED.txt"


def release_gate(plan: dict, allow_unapproved: bool = False) -> dict:
    """The one approval rule: only an approved measured_ok plan is a release. `blocked` never exports;
    other statuses export only with allow_unapproved, and the gate is recorded in the output."""
    status = plan.get("status")
    approved = status == "measured_ok" and (plan.get("outcome") or {}).get("approved") is True
    if not approved and (status not in UNAPPROVED_STATUS or not allow_unapproved):
        raise ValueError(f"unapproved_plan: status {status!r} is not an approved measured_ok release"
                         + ("; fix its errors first" if status not in UNAPPROVED_STATUS else
                            "; pass allow_unapproved (--allow-unapproved) to export it anyway, recorded in the output"))
    return {"status": status, "approved": approved, "allow_unapproved": allow_unapproved,
            "plan_sha256": plan.get("plan_sha256")}


def check_plan(tables: dict[str, pd.DataFrame], plan: dict) -> None:
    """Re-validate a (possibly hand-edited) plan against its input and the rule matrix before executing it."""
    from .policy import violations
    from .select import fingerprint
    if plan.get("input_fingerprint") and plan["input_fingerprint"] != fingerprint(tables):
        raise ValueError("plan was made for different input (schema/row-count fingerprint mismatch)")
    released = [t for t, d in plan["tables"].items() if d["action"] == "RELEASE"]
    missing = [t for t in released if t not in tables]
    if missing:
        raise ValueError(f"plan releases tables missing from the input: {missing}")
    planned = {(c["table"], c["column"]) for c in plan["columns"]}
    for t in released:
        extra = [c for c in tables[t].columns if (t, c) not in planned]
        if extra:
            raise ValueError(f"{t}: columns without a decision: {extra}")
    bad = []
    for c in plan["columns"]:
        if c["action"] == "DROP":
            continue
        label = {"privacy_role": c.get("privacy_role"), "subtype": c.get("subtype"), "confidence": c.get("confidence")}
        rung = {"action": c["action"], "method": c.get("method"), "params": c.get("params") or {}}
        bad += [f"{c['table']}.{c['column']}: {v}" for v in violations(label, rung, plan["trust_level"],
                                                                        k=plan.get("targets", {}).get("k"))]
    if bad:
        raise ValueError("plan violates the rule matrix: " + "; ".join(bad))


def apply(tables: dict[str, pd.DataFrame], plan: dict, key: bytes, out_dir: Path | None = None,
          eval_dir: Path | None = None, allow_unapproved: bool = False) -> tuple[dict[str, pd.DataFrame], dict]:
    """Protected tables (original names, retained column names, original row order) and per-column stats.

    Legacy, unvalidated layout: <out_dir>/<table>.csv and <eval_dir>/<table>.csv + rowmap_<table>.csv
    (private: never publish). For a validated release use `python -m server.transform`."""
    from server.transform.files import write_csv
    if not key:
        raise ValueError("an HMAC key is required (pass it from an environment variable)")
    gate = release_gate(plan, allow_unapproved)
    if not plan.get("release_id"):
        raise ValueError("plan needs a release_id (scenario/recipient) to scope pseudonyms")
    check_plan(tables, plan)
    for d in (out_dir, eval_dir):
        if d is not None and Path(d).exists():
            raise FileExistsError(f"refusing to write into existing {d}")
    if out_dir is not None and eval_dir is not None:
        o, e = Path(out_dir).resolve(), Path(eval_dir).resolve()
        if o == e or o in e.parents or e in o.parents:
            raise ValueError("eval_dir (row maps) must be outside the shareable out_dir")
    if eval_dir is not None:
        for t, td in plan["tables"].items():
            if td["action"] == "RELEASE" and t in tables and not td.get("record_key"):
                raise ValueError(f"table {t} needs a record_key for its scoring row map")
    out, stats = execute(tables, plan, key)
    stats = {"blanked": stats["blanked"], "rows": stats["rows"], "release_gate": gate}
    for d in (out_dir, eval_dir):
        if d is not None:
            Path(d).mkdir(parents=True)
            for t, df in out.items():
                write_csv(df, Path(d) / f"{t}.csv")
            if not gate["approved"]:
                (Path(d) / UNAPPROVED_NOTICE).write_text(
                    f"NOT AN APPROVED RELEASE: plan status {gate['status']}, exported with allow_unapproved.\n")
    if eval_dir is not None:
        for t in out:
            ids = tables[t][plan["tables"][t]["record_key"]].astype(str).values
            write_csv(pd.DataFrame({"protected_row": np.arange(len(out[t])).astype(str), "original_record_id": ids}),
                      Path(eval_dir) / f"rowmap_{t}.csv")
    return out, stats
