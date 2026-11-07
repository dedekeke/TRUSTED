"""Column profile -> feature vector for the tier-2 classifier.

Numeric part: pattern-match rates, cardinality, length, numeric range, key structure, table context and the
tier-1 guess (stacking). Text part: character n-grams of the masked value shapes, and (only when names are
allowed) of the column and table names.
"""
from __future__ import annotations

import math
import re

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

from pets_detect.patterns import ROLES


def _log(x) -> float:
    return math.log1p(abs(float(x))) if x is not None else 0.0


def numeric_features(p: dict, t1) -> list[float]:
    m = [float(v) for k, v in sorted(p.items()) if k.startswith("m_") and isinstance(v, float)]
    has_num = p["num_min"] is not None
    f = m + [
        p["null_frac"], p["unique_ratio"], _log(p["n_unique"]), _log(p["n_rows"]),
        _log(p["mean_len"]), _log(p["max_len"]), _log(p["mean_words"]),
        p["frac_has_space"], p["frac_has_digit"], p["frac_has_alpha"], p["frac_numeric"], p["frac_int"],
        float(has_num), _log(p["num_min"]) if has_num else 0.0, _log(p["num_max"]) if has_num else 0.0,
        float(has_num and p["num_min"] < 0), p["num_decimals"],
        float(p["year_median"] is not None), (p["year_median"] - 1990) / 30 if p["year_median"] else 0.0,
        _log(p["year_span"]) if p["year_span"] else 0.0,
        float(bool(p["fk_to"])), float(p["is_key_target"]), float(p["col_index"] == 0),
        p["col_index"] / max(p["n_cols"], 1), float(p.get("table_person_signals", 0) > 0),
        _log(p.get("table_person_signals", 0)),
        float(p["n_unique"] <= 2), float(p["n_unique"] <= 12), float(p["unique_ratio"] >= .99),
    ]
    f += [float(t1.privacy_role == r) for r in ROLES] + [t1.confidence]
    return f


def shape_text(p: dict) -> str:
    return " ".join(p["shapes"])


def name_text(p: dict) -> str:
    return re.sub(r"[_\-.]+", " ", f"{p['column']} | {p['table']}").lower()


class Featurizer:
    def __init__(self, use_names: bool):
        self.use_names = use_names
        self.shape_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2, max_features=3000)
        self.name_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=3000) \
            if use_names else None
        self.mu = self.sd = None

    def _num(self, ps, t1s):
        return np.array([numeric_features(p, t) for p, t in zip(ps, t1s)], dtype=float)

    def fit(self, ps, t1s):
        x = self._num(ps, t1s)
        self.mu, self.sd = x.mean(0), x.std(0) + 1e-6
        self.shape_vec.fit([shape_text(p) for p in ps])
        if self.name_vec is not None:
            self.name_vec.fit([name_text(p) for p in ps])
        return self

    def transform(self, ps, t1s):
        x = sparse.csr_matrix((self._num(ps, t1s) - self.mu) / self.sd)
        parts = [x, self.shape_vec.transform([shape_text(p) for p in ps])]
        if self.name_vec is not None:
            parts.append(self.name_vec.transform([name_text(p) for p in ps]))
        return sparse.hstack(parts).tocsr()
