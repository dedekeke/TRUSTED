"""Runtime guard: Detect, Select, Search and Transform never open evaluation-only files.

`guard(root)` installs an audit hook that refuses metadata/field_catalog.csv, metadata/pii_spans/, truth/ and
holdout/ under root. Scoring is the one step allowed to read them: `with evaluation():` lifts the refusal for the
current thread only, so a pipeline running on another thread stays guarded.
"""
from __future__ import annotations

import contextlib
import os
import sys
import threading
from pathlib import Path

_scoring = threading.local()


@contextlib.contextmanager
def evaluation():
    """Allow evaluation-only reads on this thread (the report-only scorecard after export)."""
    _scoring.on = True
    try:
        yield
    finally:
        _scoring.on = False


def guard(root: Path) -> list[str]:
    """Install the hook; returns the list it appends refused paths to."""
    root = Path(root).resolve()
    banned = [root / "metadata" / "field_catalog.csv", root / "metadata" / "pii_spans", root / "truth",
              root / "holdout"]
    refused: list[str] = []

    def hook(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)) and not getattr(_scoring, "on", False):
            p = Path(os.fsdecode(args[0]))
            if not p.is_absolute():
                p = Path.cwd() / p
            p = Path(os.path.normpath(p))
            if any(p == b or b in p.parents for b in banned):
                refused.append(str(p))
                raise PermissionError(f"guard: evaluation-only file opened at runtime: {p}")

    sys.addaudithook(hook)
    return refused
