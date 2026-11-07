"""CLI.

  python -m server.select select    --data <dataset dir> (--scenario ID | --spec FILE | --no-purpose TRUST) --out <new dir>
                                    [--labels <detect out>/labels.csv [--manifest FILE]] [--confirm FILE]
  python -m server.select search    --data <dataset dir> --plan <decisions.json> --out <new dir>

Exit codes: 0 policy_valid (select) / measured_ok (search); 2 blocked or rejected artifact (named code);
3 target_unmet (candidate space covered); 4 budget_exhausted (unexplored candidates remain).
  python -m server.select transform --data <dataset dir> --plan <decisions.json> --out <new dir>

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

from . import artifacts, policy, preview, relations, requirements, search, select, transform
from . import labels as detection_labels
from .detect import detect_table

KEY_ENV = "PRIVACY_TOOL_HMAC_KEY"
EXIT = {"policy_valid": 0, "measured_ok": 0, "blocked": 2, "target_unmet": 3, "budget_exhausted": 4}


def read_tables(data: Path) -> dict[str, pd.DataFrame]:
    return {t: pd.read_csv(f, dtype=str, keep_default_na=False) for t, f in artifacts.input_files(data).items()}


def cmd_select(a) -> int:
    out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to write into existing {out}")
    tables = read_tables(a.data)
    if not tables:
        sys.exit(f"no CSV tables in {a.data}")
    dataset = Path(a.data).name
    manifest = None
    if a.labels:
        manifest = artifacts.load_manifest(a.labels, a.data, dataset, a.manifest)
        labels = detection_labels.from_detection(
            pd.read_csv(a.labels, dtype=str, keep_default_na=False), tables, dataset)
    else:
        labels = pd.concat([detect_table(df.head(a.rows), t, dataset) for t, df in tables.items()], ignore_index=True)
    confirm_sha = None
    if a.confirm:
        confirm_sha = artifacts.sha256_file(a.confirm)
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
    plan["provenance"] = artifacts.provenance(a.data, manifest, confirm_sha, select.DETECTOR_VERSION)
    if manifest is None:
        plan["warnings"].append("provenance unbound: legacy built-in detector, no detect manifest")
    else:
        errors, warnings, plan["evidence"] = artifacts.check_evidence(plan, tables, labels, manifest)
        plan["errors"] += errors
        plan["warnings"] += warnings
        vocabulary = policy.coverage(map(tuple, manifest.get("label_vocabulary") or []))
        plan["label_coverage"]["vocabulary"] = vocabulary
        if vocabulary["unsupported"]:
            plan["warnings"].append(f"unsupported_label: {len(vocabulary['unsupported'])} of {vocabulary['pairs']} "
                                    "vocabulary pairs have no protective policy (listed in label_coverage); "
                                    "columns with them are dropped and queued for review")
        select.set_status(plan)
    out.mkdir(parents=True)
    labels.to_csv(out / "field_labels.csv", index=False)
    (out / "decisions.json").write_text(json.dumps(plan, indent=2, default=str))
    (out / "decisions.md").write_text(select.render(plan))
    n = sum(c["action"] != "DROP" for c in plan["columns"])
    print(f"{plan['status']}: {n} columns planned, "
          f"{len(plan['errors'])} errors, {len(plan['review_queue'])} to review -> {out}")
    for e in plan["errors"]:
        print("  error:", e)
    return EXIT[plan["status"]]


def cmd_search(a) -> int:
    key = os.environ.get(KEY_ENV, "").encode()
    if not key:
        sys.exit(f"set {KEY_ENV} (the HMAC key) in the environment")
    out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to write into existing {out}")
    plan_bytes = Path(a.plan).read_bytes()
    plan = json.loads(plan_bytes)
    plan_sha = artifacts.check_plan(a.data, plan, plan_bytes)
    tasks, orig = None, None
    if plan.get("source") == "scenario":
        from pets_eval.utility import all_tasks
        ids = {t for ts in plan["required"].values() for t in ts if not t.startswith("any_of:")}
        tasks = [t for t in all_tasks([plan["dataset"]]) if t.id in ids]
        orig = load_tables(a.data)
    tables = read_tables(a.data)
    try:
        preview.check_plan(tables, plan)
        res = search.search(tables, plan, key, tasks, orig, budget=a.budget, tau=a.tau)
    except ValueError as e:
        print(f"blocked: {e}", file=sys.stderr)
        return EXIT["blocked"]
    res["plan_sha256"] = plan_sha
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
    print(f"  approved: {res['outcome']['approved']}; budget {res['outcome']['budget']}")
    return EXIT[res["status"]]


def cmd_transform(a) -> int:
    key = os.environ.get(KEY_ENV, "").encode()
    if not key:
        sys.exit(f"set {KEY_ENV} (the HMAC key) in the environment")
    plan = json.loads(Path(a.plan).read_text())
    if plan.get('suppression') or any(c.get('method') in ('week_hour', 'month_hour', 'year_hour')
                                      for c in plan.get('columns', [])):
        sys.exit('this plan needs preview-only operations; complete the transform integration before export')
    out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to write into existing {out}")
    _, stats = transform.apply(read_tables(a.data), plan, key, out / "protected", out / "evaluation")
    (out / "transform_stats.json").write_text(json.dumps(stats, indent=2))
    print(f"wrote {len(stats['rows'])} tables -> {out}/protected (shareable), {out}/evaluation (private)")
    return 0


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
    s.add_argument("--labels", help="labels.csv in a detect output dir (needs its manifest.json); replaces built-in detection")
    s.add_argument("--manifest", help="detect manifest.json when it is not next to --labels")
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
    t = sub.add_parser("transform", help="apply decisions.json")
    t.add_argument("--data", required=True)
    t.add_argument("--plan", required=True)
    t.add_argument("--out", required=True)
    t.set_defaults(fn=cmd_transform)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except artifacts.ArtifactError as e:
        print(f"rejected: {e}", file=sys.stderr)
        return EXIT["blocked"]


if __name__ == "__main__":
    sys.exit(main())
