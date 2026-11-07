"""CLI.

  python -m server.transform --data <dataset dir> --plan <measured decisions.json> --out <new dir>
                             [--spans TABLE.COLUMN=FILE ...] [--text-fallback rules] [--no-scorecard]

The HMAC key is read from the PRIVACY_TOOL_HMAC_KEY environment variable and never written.
Exit codes: 0 validated release, 2 refused before export, 3 exported files failed validation (kept private).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .run import run

KEY_ENV = "PRIVACY_TOOL_HMAC_KEY"
EXIT = {"validated": 0, "refused": 2, "validation_failed": 3}


def _tasks(plan, data):
    """Required utility tasks for scenario plans, loaded exactly as `server.select search` loads them."""
    if plan.get("source") != "scenario":
        return None, None
    from pets_eval.io import load_tables
    from pets_eval.utility import all_tasks
    ids = {t for ts in plan.get("required", {}).values() for t in ts if not t.startswith("any_of:")}
    return [t for t in all_tasks([plan["dataset"]]) if t.id in ids], load_tables(data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m server.transform",
                                 description="Execute a measured plan and export a validated release.")
    ap.add_argument("--data", required=True, help="source dataset directory (read-only)")
    ap.add_argument("--plan", required=True, help="decisions.json from `server.select search` (status measured_ok)")
    ap.add_argument("--out", required=True, help="new run directory; must not exist")
    ap.add_argument("--spans", action="append", default=[], metavar="TABLE.COLUMN=FILE",
                    help="Detect span JSONL for a free-text column (repeatable)")
    ap.add_argument("--text-fallback", choices=["rules"],
                    help="explicitly allow rule-only redaction for free text without Detect spans")
    ap.add_argument("--no-scorecard", action="store_true", help="skip the toolkit scorecard (marked not run)")
    ap.add_argument("--max-adversary", type=int, default=3000)
    a = ap.parse_args(argv)

    key = os.environ.get(KEY_ENV, "").encode()
    if not key:
        sys.exit(f"set {KEY_ENV} (the HMAC key) in the environment")
    spans = {}
    for item in a.spans:
        ref, sep, path = item.partition("=")
        if not sep or "." not in ref or not path:
            sys.exit(f"--spans expects TABLE.COLUMN=FILE, got {item!r}")
        spans[ref] = path
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    try:
        tasks, orig = _tasks(plan, a.data)
        res = run(a.data, plan, key, a.out, spans, text_fallback=a.text_fallback == "rules",
                  scorecard=not a.no_scorecard, tasks=tasks, orig=orig, max_adversary=a.max_adversary)
    except (FileExistsError, ValueError) as e:
        sys.exit(str(e))
    print(f"{res['status']} -> {res['out']}")
    if res["status"] == "validated":
        print(f"  shareable: {res['out']}/protected   owner-private: {res['out']}/evaluation")
    for e in res.get("errors", [])[:20]:
        print("  ", e)
    return EXIT[res["status"]]


if __name__ == "__main__":
    sys.exit(main())
