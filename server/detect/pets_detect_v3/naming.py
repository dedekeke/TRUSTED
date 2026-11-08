"""How much does a column name tell us? (name_info in [0, 1])

Signals, all measurable without labels of the dataset being scored:
- code-like names (c07, x3, f_12, hex) carry nothing -> 0;
- share of name tokens found in a vocabulary of column-name tokens from OTHER datasets of the catalog;
- whether a v1 name hint (hetu, phone, birth, postcode, ...) matches;
- whether most columns of the same table are code-like (an obfuscated export).

Also: the "mixed" evaluation mode, which hides the names of a random half of the columns of every table.
"""
from __future__ import annotations

import hashlib
import re

import pandas as pd

from pets_detect.patterns import NAME_HINTS
from pets_detect.pipeline import blind

CODE_LIKE = re.compile(r"^(?:[a-z]{0,4}[_\-]?\d+|[0-9a-f]{6,}|[a-z]|col(?:umn)?[_\-]?\d*|field[_\-]?\d*|unnamed.*)$")


def tokens(name: str) -> list[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return [t for t in re.split(r"[^a-zA-Zåäö]+", s.lower()) if len(t) >= 2]


def is_code_like(name: str) -> bool:
    return bool(CODE_LIKE.match(name.strip().lower()))


class NameScorer:
    def __init__(self, catalog: pd.DataFrame):
        self.vocab_by_ds = {ds: {t for c in g.column for t in tokens(c)} for ds, g in catalog.groupby("dataset")}

    def vocab(self, exclude: str | None) -> set[str]:
        return set().union(*(v for d, v in self.vocab_by_ds.items() if d != exclude))

    def score(self, name: str, table_names: list[str], exclude_dataset: str | None) -> tuple[float, str]:
        """Returns (name_info, short explanation)."""
        if is_code_like(name):
            return 0.0, f"'{name}' is a code, not a word"
        _cache = self.__dict__.setdefault("_cache", {})
        key = exclude_dataset
        if key not in _cache:
            _cache[key] = self.vocab(exclude_dataset)
        voc = _cache[key]
        tk = tokens(name)
        words = [t for t in tk if len(t) >= 3 and re.search(r"[aeiouyåäö]", t)]
        if not words:
            return 0.1, f"'{name}' has no word-like part"
        cov = sum(t in voc for t in tk) / len(tk)
        hint = 1.0 if any(re.search(rx, name.lower()) for rx, *_ in NAME_HINTS) else 0.0
        code_frac = sum(is_code_like(n) for n in table_names) / len(table_names) if table_names else 0.0
        info = 0.7 + 0.3 * max(cov, hint)
        why = "name is made of words" + (f", {cov:.0%} of tokens seen in other datasets" if cov else "") + \
              (", matches a name hint" if hint else "")
        if code_frac > .5:
            info -= 0.2
            why += f", but {code_frac:.0%} of the table's names are codes"
        return round(info, 3), why


def mixed_view(p: dict, seed: int = 0) -> dict:
    """Hide the name of about half of the columns, chosen by a stable hash (same columns every run)."""
    h = int(hashlib.md5(f"{seed}|{p['dataset']}|{p['table']}|{p['column']}".encode()).hexdigest(), 16)
    return blind(p) if h % 2 == 0 else p
