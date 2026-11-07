"""CLI.

  python -m privacy_tool select    --data <dataset dir> (--scenario ID | --spec FILE | --no-purpose TRUST) --out <new dir>
  python -m privacy_tool transform --data <dataset dir> --plan <decisions.json> --out <new dir>

The HMAC key is read from the PRIVACY_TOOL_HMAC_KEY environment variable and never written.
`transform` writes <out>/protected/ (shareable) and <out>/evaluation/ (tables + private row maps, scoring only).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

from pets_eval.io import find_package_root, load_tables

from . import relations, requirements, select, transform
from .detect import detect_table

KEY_ENV = "PRIVACY_TOOL_HMAC_KEY"


def read_tables(data: Path) -> dict[str, pd.DataFrame]:
    return {f.stem: pd.read_csv(f, dtype=str, keep_default_na=False) for f in sorted(Path(data).glob("*.csv"))
            if not f.stem.startswith(("rowmap_", "_"))}


def cmd_select(a) -> int:
    out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to write into existing {out}")
    tables = read_tables(a.data)
    if not tables:
        sys.exit(f"no CSV tables in {a.data}")
    dataset = Path(a.data).name
    labels = pd.concat([detect_table(df.head(a.rows), t, dataset) for t, df in tables.items()], ignore_index=True)
    if a.confirm:
        labels = select.confirm(labels, pd.read_csv(a.confirm, dtype=str, keep_default_na=False))
    if a.scenario:
        root = find_package_root(Path(a.data))
        if root is None:
            sys.exit("cannot find the challenge package root for scenario metadata")
        req = requirements.from_scenario(a.scenario, load_tables(a.data), root, probe=not a.no_probe)
    elif a.spec:
        req = requirements.from_spec(a.spec)
    else:
        req = requirements.no_purpose(a.no_purpose, dataset)
    rel = relations.discover(tables, labels, {"joins": [j["columns"] for j in req.get("joins") or []]}
                             if a.declare_joins else None)
    plan = select.select(tables, labels, rel, req, a.release_id)
    out.mkdir(parents=True)
    labels.to_csv(out / "field_labels.csv", index=False)
    (out / "decisions.json").write_text(json.dumps(plan, indent=2, default=str))
    (out / "decisions.md").write_text(select.render(plan))
    print(f"{plan['status']}: {sum(c['action'] != 'DROP' for c in plan['columns'])} columns released, "
          f"{len(plan['errors'])} errors, {len(plan['review_queue'])} to review -> {out}")
    for e in plan["errors"]:
        print("  error:", e)
    return 0 if plan["status"] != "blocked" else 2


def cmd_transform(a) -> int:
    key = os.environ.get(KEY_ENV, "").encode()
    if not key:
        sys.exit(f"set {KEY_ENV} (the HMAC key) in the environment")
    plan = json.loads(Path(a.plan).read_text())
    out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to write into existing {out}")
    _, stats = transform.apply(read_tables(a.data), plan, key, out / "protected", out / "evaluation")
    (out / "transform_stats.json").write_text(json.dumps(stats, indent=2))
    print(f"wrote {len(stats['rows'])} tables -> {out}/protected (shareable), {out}/evaluation (private)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m privacy_tool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select", help="detect, resolve requirements and write decisions.json")
    s.add_argument("--data", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--scenario")
    g.add_argument("--spec")
    g.add_argument("--no-purpose", metavar="TRUST_LEVEL")
    s.add_argument("--out", required=True)
    s.add_argument("--release-id")
    s.add_argument("--no-probe", action="store_true", help="parse task needs only (faster, less accurate)")
    s.add_argument("--declare-joins", action="store_true", help="treat requirement joins as declared")
    s.add_argument("--rows", type=int, default=20000, help="rows sampled for detection")
    s.add_argument("--confirm", help="CSV table,column,privacy_role,subtype of reviewer-confirmed labels")
    s.set_defaults(fn=cmd_select)
    t = sub.add_parser("transform", help="apply decisions.json")
    t.add_argument("--data", required=True)
    t.add_argument("--plan", required=True)
    t.add_argument("--out", required=True)
    t.set_defaults(fn=cmd_transform)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
