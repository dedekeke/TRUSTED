"""Tier 2 (v3): per-column choice between name evidence and value evidence.

- name evidence  = v1 kNN retrieval over labelled columns (strong when names are meaningful);
- value evidence = v2 logistic regression trained on name-blind profiles (works on any header).

mode "knn" / "logreg" use one source; "A1" switches on name_info >= 0.5; "A2" blends p = w*kNN + (1-w)*LogReg
with w = name_info. Both models are leave-one-dataset-out.
"""
from __future__ import annotations

import hashlib
import os
import pickle
from pathlib import Path

import numpy as np
import sklearn
from sklearn.preprocessing import normalize

from pets_detect.kb import KnowledgeBase, numeric_vector
from pets_detect.patterns import ROLES
from pets_detect.pipeline import blind
from pets_detect.rules import tier1

import pets_detect_v2.classifier as _clf_mod
import pets_detect_v2.features as _feat_mod
from pets_detect_v2.classifier import ColumnClassifier

_FIT_MEMO: dict[str, ColumnClassifier] = {}
_CODE = hashlib.sha256(b"".join(Path(m.__file__).read_bytes() for m in (_clf_mod, _feat_mod))
                       + sklearn.__version__.encode()).hexdigest()[:12]


def _fit_one(ps, t1s, roles, subtypes) -> ColumnClassifier:
    """Top level so joblib can run it in a worker process."""
    return ColumnClassifier("logreg", use_names=False).fit(ps, t1s, roles, subtypes)


class Router:
    def __init__(self, train: list[tuple[dict, str, str]], catalog, mode: str = "A2", k: int = 7,
                 cache_dir: str | Path | None = ".cache/v3/models"):
        """train: [(named profile, role, subtype)] for every labelled column.
        cache_dir: where fitted value models are pickled (None or DETECT_V3_NO_MODEL_CACHE=1 to disable)."""
        self.mode, self.k = mode, k
        self.train = train
        self.kb = KnowledgeBase([p for p, _, _ in train], catalog, "tfidf", use_names=True)
        self.blind_train = [blind(p) for p, _, _ in train]
        self.blind_t1 = [tier1(q) for q in self.blind_train]
        self._lr: dict[str, ColumnClassifier] = {}
        self.cache = None if cache_dir is None or os.environ.get("DETECT_V3_NO_MODEL_CACHE") else Path(cache_dir)
        self._train_hash: str | None = None

    def _fit_args(self, dataset: str):
        idx = [i for i, (p, _, _) in enumerate(self.train) if p["dataset"] != dataset]
        return ([self.blind_train[i] for i in idx], [self.blind_t1[i] for i in idx],
                [self.train[i][1] for i in idx], [self.train[i][2] for i in idx])

    def _key(self, dataset: str) -> str:
        if self._train_hash is None:
            blob = pickle.dumps((self.blind_train, self.blind_t1, [(r, s) for _, r, s in self.train]), protocol=4)
            self._train_hash = hashlib.sha256(blob).hexdigest()[:16]
        return f"lr_{_CODE}_{self._train_hash}_{hashlib.sha256(dataset.encode()).hexdigest()[:8]}"

    def _lookup(self, dataset: str) -> ColumnClassifier | None:
        if dataset in self._lr:
            return self._lr[dataset]
        key = self._key(dataset)
        m = _FIT_MEMO.get(key)
        if m is None and self.cache is not None and (self.cache / f"{key}.pkl").exists():
            try:
                m = pickle.loads((self.cache / f"{key}.pkl").read_bytes())
            except Exception:
                m = None
        if m is not None:
            self._store(dataset, m, disk=False)
        return m

    def _store(self, dataset: str, m: ColumnClassifier, disk: bool = True):
        key = self._key(dataset)
        self._lr[dataset] = _FIT_MEMO[key] = m
        if disk and self.cache is not None:
            self.cache.mkdir(parents=True, exist_ok=True)
            tmp = self.cache / f"{key}.{os.getpid()}.tmp"
            tmp.write_bytes(pickle.dumps(m, protocol=4))
            tmp.replace(self.cache / f"{key}.pkl")

    def prefit(self, datasets, n_jobs: int = -1):
        """Fit the value models of several datasets at once, in worker processes (each fit is CPU-bound L-BFGS)."""
        todo = [d for d in dict.fromkeys(datasets) if self._lookup(d) is None]
        if not todo:
            return
        if len(todo) > 1 and n_jobs != 1:
            try:
                from joblib import Parallel, delayed
                models = Parallel(n_jobs=min(len(todo), os.cpu_count() or 1) if n_jobs == -1 else n_jobs)(
                    delayed(_fit_one)(*self._fit_args(d)) for d in todo)
                for d, m in zip(todo, models):
                    self._store(d, m)
                return
            except Exception as e:
                print(f"[v3] parallel fit failed ({e!r}), fitting sequentially", flush=True)
        for d in todo:
            self._store(d, _fit_one(*self._fit_args(d)))

    def _value_model(self, dataset: str) -> ColumnClassifier:
        m = self._lookup(dataset)
        if m is None:
            m = _fit_one(*self._fit_args(dataset))
            self._store(dataset, m)
        return m

    def _knn_batch(self, views: list[dict], dataset: str) -> list[list[tuple[dict, float]]]:
        """KnowledgeBase.retrieve for many columns at once: one embedding call and one matrix product."""
        if not views:
            return []
        kb = self.kb
        q_text = kb.embedder.transform([kb._text(q) for q in views])
        q_num = normalize(np.vstack([numeric_vector(q) for q in views]))
        sim = kb.tw * (q_text @ kb.text_emb.T) + kb.nw * (q_num @ kb.num_emb.T)
        if dataset is not None:
            sim[:, kb.datasets == dataset] = -np.inf
        k = min(self.k, sim.shape[1])
        top = np.argpartition(-sim, k - 1, axis=1)[:, :k] if k < sim.shape[1] else np.tile(np.arange(k), (len(sim), 1))
        out = []
        for row, cand in zip(sim, top):
            cand = cand[np.argsort(-row[cand], kind="stable")]
            out.append([(kb.docs[i], float(row[i])) for i in cand if np.isfinite(row[i])])
        return out

    def weight(self, info: float, table_visible: bool = True) -> float:
        if self.mode == "knn":
            return 1.0
        if self.mode == "logreg":
            return 0.0
        if info == 0.0 and table_visible:
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
        ws = [self.weight(info, table_visible) for info in infos]
        need = [i for i, w in enumerate(ws) if w > 0]
        knn = dict(zip(need, self._knn_batch([views[i] for i in need], dataset)))
        out = []
        for j, (q, bq, t, pv, w) in enumerate(zip(views, bviews, bt1, p_val, ws)):
            if w > 0:
                pk, best_sub = self.kb.vote(knn[j])
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
