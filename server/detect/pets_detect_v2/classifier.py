"""Tier 2 (v2): a supervised column classifier trained on the labelled catalog.

Trained leave-one-dataset-out: the model that labels dataset X never saw a column of X. Two model families are
available (logistic regression, gradient boosting); `select_model()` picks one by leave-one-dataset-out score.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

from pets_detect.patterns import ROLES

from .features import Featurizer


def catalog_labels(profiles: list[dict], catalog: pd.DataFrame) -> list[tuple[dict, str, str]]:
    cat = catalog.drop_duplicates(["dataset", "table", "column"]).set_index(["dataset", "table", "column"])
    out = []
    for p in profiles:
        k = (p["dataset"], p["table"], p.get("orig_column", p["column"]))
        if k in cat.index:
            out.append((p, cat.loc[k, "privacy_role"], cat.loc[k, "subtype"]))
    return out


class ColumnClassifier:
    def __init__(self, kind: str = "logreg", use_names: bool = True):
        self.kind, self.use_names = kind, use_names
        self.feat = Featurizer(use_names)
        self.model = None
        self.classes_: list[str] = []
        self.subtype_by_role: dict[str, dict[str, float]] = {}

    def fit(self, ps: list[dict], t1s: list, roles: list[str], subtypes: list[str]):
        x = self.feat.fit(ps, t1s).transform(ps, t1s)
        y = np.array(roles)
        if self.kind == "gbm":
            self.model = HistGradientBoostingClassifier(max_iter=200, learning_rate=.08, max_leaf_nodes=15,
                                                        l2_regularization=1.0, class_weight="balanced",
                                                        random_state=0)
            self.model.fit(x.toarray(), y)
        else:
            self.model = LogisticRegression(C=2.0, max_iter=3000, class_weight="balanced")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self.model.fit(x, y)
        self.classes_ = list(self.model.classes_)
        # subtype model (same features); at prediction time it is restricted to subtypes seen with the chosen role
        self.sub_model = LogisticRegression(C=2.0, max_iter=3000)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.sub_model.fit(x, np.array(subtypes))
        df = pd.DataFrame({"r": roles, "s": subtypes})
        self.subtype_by_role = {r: g.s.value_counts(normalize=True).to_dict() for r, g in df.groupby("r")}
        return self

    def predict_subtypes(self, ps: list[dict], t1s: list, roles: list[str]) -> list[str]:
        pr = self.sub_model.predict_proba(self.feat.transform(ps, t1s))
        out = []
        for row, role in zip(pr, roles):
            allowed = self.subtype_by_role.get(role, {})
            best = max(((v, c) for c, v in zip(self.sub_model.classes_, row) if c in allowed), default=None)
            out.append(best[1] if best else "OTHER")
        return out

    def predict_proba(self, ps: list[dict], t1s: list) -> list[dict[str, float]]:
        x = self.feat.transform(ps, t1s)
        pr = self.model.predict_proba(x.toarray() if self.kind == "gbm" else x)
        out = []
        for row in pr:
            d = {r: 0.0 for r in ROLES}
            for c, v in zip(self.classes_, row):
                d[c] = float(v)
            out.append(d)
        return out

    def default_subtype(self, role: str) -> str:
        s = self.subtype_by_role.get(role)
        return max(s, key=s.get) if s else "OTHER"
