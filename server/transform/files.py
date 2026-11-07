"""Canonical file formats for the release: CSV and JSON writers with matching readers."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import pandas as pd

FORMAT_VERSION = "pets-release-1"
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
MISSING_TOKENS = {"nan", "NaN", "None", "NaT", "<NA>"}


def safe_name(name: str) -> bool:
    """A table name usable as a file name: no separators, no traversal, no hidden files."""
    return bool(SAFE_NAME.fullmatch(name)) and ".." not in name


def read_csv(path: Path) -> pd.DataFrame:
    """The one string/blank read contract: every value a string, missing values as ""."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """UTF-8, header row, comma delimiter, minimal RFC-4180 quoting, no index. Values must already be strings."""
    if df.isna().any().any():
        raise ValueError(f"{Path(path).name}: missing values must be written as empty strings")
    if not all(isinstance(v, str) for col in df.columns for v in df[col].tolist()):
        raise ValueError(f"{Path(path).name}: every value must be a string before writing")
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def _clean(obj):
    """JSON-safe values only: NaN/Infinity become null, numpy scalars become Python scalars."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):
        try:
            obj = obj.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def write_json(obj, path: Path) -> None:
    Path(path).write_text(json.dumps(_clean(obj), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
                          encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def md_escape(text) -> str:
    """Escape source-derived labels for Markdown tables."""
    return re.sub(r"([\\`*_\[\]<>|#])", r"\\\1", str(text)).replace("\n", " ")
