"""CLI.

  python -m server.select select    --data <dataset dir> (--scenario ID | --spec FILE | --no-purpose TRUST) --out <new dir>
  python -m server.select search    --data <dataset dir> --plan <decisions.json> --out <new dir>
  python -m server.select transform --data <dataset dir> --plan <decisions.json> --out <new dir>

The HMAC key is read from the PRIVACY_TOOL_HMAC_KEY environment variable and never written.
`transform` delegates to `python -m server.transform`: <out>/protected/ (shareable), <out>/evaluation/ (private).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

from pets_eval.io import find_package_root, load_tables

from . import labels as detection_labels
from . import preview, relations, requirements, search, select
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
    if a.labels:
        labels = detection_labels.from_detection(
            pd.read_csv(a.labels, dtype=str, keep_default_na=False), tables, dataset)
    else:
        labels = pd.concat([detect_table(df.head(a.rows), t, dataset) for t, df in tables.items()], ignore_index=True)
    if a.confirm:
        labels = select.confirm(labels, pd.read_csv(a.confirm, dtype=str, keep_default_na=False), a.allow_downgrade)
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
    n = sum(c["action"] != "DROP" for c in plan["columns"])
    print(f"{plan['status']}: {n} columns planned, "
          f"{len(plan['errors'])} errors, {len(plan['review_queue'])} to review -> {out}")
    for e in plan["errors"]:
        print("  error:", e)
    return 0 if plan["status"] != "blocked" else 2


def cmd_search(a) -> int:
    key = os.environ.get(KEY_ENV, "").encode()
    if not key:
        sys.exit(f"set {KEY_ENV} (the HMAC key) in the environment")
    out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to write into existing {out}")
    plan = json.loads(Path(a.plan).read_text())
    tasks, orig = None, None
    if plan.get("source") == "scenario":
        from pets_eval.utility import all_tasks
        ids = {t for ts in plan["required"].values() for t in ts if not t.startswith("any_of:")}
        tasks = [t for t in all_tasks([plan["dataset"]]) if t.id in ids]
        orig = load_tables(a.data)
    tables = read_tables(a.data)
    preview.check_plan(tables, plan)
    res = search.search(tables, plan, key, tasks, orig, budget=a.budget, tau=a.tau)
    out.mkdir(parents=True)
    (out / "decisions.json").write_text(json.dumps(res, indent=2, default=str))
    (out / "decisions.md").write_text(select.render(res))
    m = res["measured"]
    print(f"{res['status']}: k<{plan['targets']['k']} share "
          f"{max((r['share_below_k'] for r in m['risk'].values()), default=0):.3f}, utility {m['utility']}, "
          f"{m['evaluations']} evaluations -> {out}")
    if res.get('conflict'):
        print('  stop:', res['conflict']['reason'])
        for violation in res['conflict'].get('violations', []):
            print('  unmet:', violation)
    return 0 if res["status"] == "measured_ok" else 3


def cmd_transform(a) -> int:
    """Delegates to the one final executor (`python -m server.transform`), with its release gate and checks."""
    from server.transform.__main__ import main as transform_main
    argv = ["--data", a.data, "--plan", a.plan, "--out", a.out]
    for item in a.spans or []:
        argv += ["--spans", item]
    if a.text_fallback:
        argv += ["--text-fallback", a.text_fallback]
    if a.no_scorecard:
        argv.append("--no-scorecard")
    return transform_main(argv)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m server.select")
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
    s.add_argument("--labels", help="explained labels CSV from server/detect; replaces built-in detection")
    s.add_argument("--confirm", help="CSV table,column,privacy_role,subtype of reviewer-confirmed labels")
    s.add_argument("--allow-downgrade", action="store_true", help="let --confirm lower protection, with a plan warning")
    s.set_defaults(fn=cmd_select)
    q = sub.add_parser("search", help="coarsen decisions.json until the risk target is met (measured)")
    q.add_argument("--data", required=True)
    q.add_argument("--plan", required=True)
    q.add_argument("--out", required=True)
    q.add_argument("--budget", type=int, default=50)
    q.add_argument("--tau", type=float, default=0.8, help="minimum task score as a share of its unsearched score")
    q.set_defaults(fn=cmd_search)
    t = sub.add_parser("transform", help="export a validated release (same as python -m server.transform)")
    t.add_argument("--data", required=True)
    t.add_argument("--plan", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--spans", action="append", metavar="TABLE.COLUMN=FILE")
    t.add_argument("--text-fallback", choices=["rules"])
    t.add_argument("--no-scorecard", action="store_true")
    t.set_defaults(fn=cmd_transform)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
