"""Tier 2 (v3): per-column choice between name evidence and value evidence.

- name evidence  = v1 kNN retrieval over labelled columns (strong when names are meaningful);
- value evidence = v2 logistic regression trained on name-blind profiles (works on any header).

mode "knn" / "logreg" use one source; "A1" switches on name_info >= 0.5; "A2" blends p = w*kNN + (1-w)*LogReg
with w = name_info. Both models are leave-one-dataset-out.
"""
from __future__ import annotations

from pets_detect.kb import KnowledgeBase
from pets_detect.patterns import ROLES
from pets_detect.pipeline import blind
from pets_detect.rules import tier1

from pets_detect_v2.classifier import ColumnClassifier


class Router:
    def __init__(self, train: list[tuple[dict, str, str]], catalog, mode: str = "A2", k: int = 7):
        """train: [(named profile, role, subtype)] for every labelled column."""
        self.mode, self.k = mode, k
        self.train = train
        self.kb = KnowledgeBase([p for p, _, _ in train], catalog, "tfidf", use_names=True)
        self.blind_train = [blind(p) for p, _, _ in train]
        self.blind_t1 = [tier1(q) for q in self.blind_train]
        self._lr: dict[str, ColumnClassifier] = {}

    def _value_model(self, dataset: str) -> ColumnClassifier:
        if dataset not in self._lr:
            idx = [i for i, (p, _, _) in enumerate(self.train) if p["dataset"] != dataset]
            m = ColumnClassifier("logreg", use_names=False)
            m.fit([self.blind_train[i] for i in idx], [self.blind_t1[i] for i in idx],
                  [self.train[i][1] for i in idx], [self.train[i][2] for i in idx])
            self._lr[dataset] = m
        return self._lr[dataset]

    def weight(self, info: float, table_visible: bool = True) -> float:
        if self.mode == "knn":
            return 1.0
        if self.mode == "logreg":
            return 0.0
        if info == 0.0 and table_visible:
            # code-like column name, but kNN still sees the table name; the ablation (mixed view) showed kNN alone
            # beats a 50/50 blend here (0.810 vs 0.796), so any name context -> kNN; no name at all -> LogReg
            return 1.0
        if self.mode == "A1":
            return 1.0 if info >= 0.5 else 0.0
        return info

    def predict(self, dataset: str, views: list[dict], infos: list[float], table_visible: bool = True):
        """Returns per column: (role probabilities, subtype per role function, weight, label of what was used)."""
        m = self._value_model(dataset)
        bviews = [q if q.get("orig_column") else blind(q) for q in views]
        bt1 = [tier1(q) for q in bviews]
        p_val = m.predict_proba(bviews, bt1)
        out = []
        for q, bq, t, pv, info in zip(views, bviews, bt1, p_val, infos):
            w = self.weight(info, table_visible)
            if w > 0:
                pk, best_sub = self.kb.vote(self.kb.retrieve(q, self.k, dataset))
            else:
                pk, best_sub = {r: 0.0 for r in ROLES}, {}
            probs = {r: w * pk[r] + (1 - w) * pv[r] for r in ROLES}
            used = "kNN (names)" if w >= .99 else "LogReg (values)" if w <= .01 else f"blend {w:.2f} kNN"

            def sub_for(role, bq=bq, t=t, best_sub=best_sub, w=w):
                if w >= .5 and role in best_sub:
                    return best_sub[role]
                return m.predict_subtypes([bq], [t], [role])[0]
            out.append((probs, sub_for, w, used))
        return out
