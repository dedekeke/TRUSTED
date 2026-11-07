"""Tier 2: knowledge base of labelled columns + retrieval (the "R" of RAG).

Each labelled column of the public catalog becomes a document = its profile (computed from the data) plus the
catalog label, description and traps. A query column is embedded the same way and its nearest labelled
neighbours vote for a role (weighted k-NN). The same neighbours are passed to the LLM in tier 3.

Embedders (both run locally):
- "tfidf" (default): scikit-learn TF-IDF over the profile text + scaled numeric statistics. No download.
- "ollama:<model>": embeddings from a local Ollama server (e.g. ollama:bge-m3), concatenated with the statistics.

Leakage guard: retrieve(..., exclude_dataset=X) never returns columns of dataset X, so evaluation is
leave-one-dataset-out and the detector cannot copy the answer of the column it is being scored on.
"""
from __future__ import annotations

import json
import urllib.request
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from .patterns import ROLES
from .profiler import profile_text

NUM_KEYS = ["null_frac", "unique_ratio", "frac_has_space", "frac_has_digit", "frac_has_alpha", "frac_numeric",
            "frac_int", "m_hetu", "m_email", "m_phone", "m_ipv4", "m_date", "m_month", "m_timestamp", "m_postcode",
            "m_coord", "m_address", "m_sex", "m_lang", "m_municipality", "m_icd10", "m_bool", "m_name_shape",
            "m_single_cap", "m_first_name", "m_surname_suffix", "m_org_suffix", "m_prefixed_id", "m_hex_hash",
            "m_domain", "m_hostname", "m_url"]


def numeric_vector(p: dict) -> np.ndarray:
    v = [float(p[k]) for k in NUM_KEYS]
    v += [min(p["mean_words"], 30) / 30, min(p["mean_len"], 200) / 200, np.log1p(p["n_unique"]) / 12,
          1.0 if p["fk_to"] else 0.0, 1.0 if p["is_key_target"] else 0.0,
          1.0 if p.get("table_person_signals", 0) else 0.0, 1.0 if p["col_index"] == 0 else 0.0]
    return np.array(v, dtype=float)


class TfidfEmbedder:
    name = "tfidf"

    def fit(self, texts: list[str]):
        self.word = TfidfVectorizer(analyzer="word", token_pattern=r"[a-zA-Z0-9]{2,}", sublinear_tf=True, min_df=1)
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True, min_df=2)
        self.word.fit(texts)
        self.char.fit(texts)
        return self

    def transform(self, texts: list[str]) -> np.ndarray:
        w = normalize(self.word.transform(texts)).toarray()
        c = normalize(self.char.transform(texts)).toarray()
        return np.hstack([w * .6, c * .4])


class OllamaEmbedder:
    def __init__(self, model: str, host: str = "http://localhost:11434"):
        self.model, self.host, self.name = model, host, f"ollama:{model}"

    def fit(self, texts):
        return self

    def transform(self, texts: list[str]) -> np.ndarray:
        req = urllib.request.Request(f"{self.host}/api/embed", method="POST",
                                     data=json.dumps({"model": self.model, "input": texts}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            emb = np.array(json.loads(r.read())["embeddings"], dtype=float)
        return normalize(emb)


def make_embedder(spec: str):
    if spec.startswith("ollama:"):
        return OllamaEmbedder(spec.split(":", 1)[1])
    return TfidfEmbedder()


class KnowledgeBase:
    def __init__(self, profiles: list[dict], catalog: pd.DataFrame, embedder: str = "tfidf",
                 text_weight: float = .65, num_weight: float = .35, use_names: bool = True):
        self.use_names = use_names
        cat = catalog.set_index(["dataset", "table", "column"])
        self.docs = []
        for p in profiles:
            k = (p["dataset"], p["table"], p.get("orig_column", p["column"]))
            if k in cat.index:
                row = cat.loc[k]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                self.docs.append({"profile": p, "privacy_role": row["privacy_role"], "subtype": row["subtype"],
                                  "description": row.get("description", ""), "traps": row.get("traps", "")})
        self.tw, self.nw = text_weight, num_weight
        self.embedder = make_embedder(embedder)
        texts = [self._text(d["profile"]) for d in self.docs]
        self.embedder.fit(texts)
        self.text_emb = self.embedder.transform(texts)
        self.num_emb = normalize(np.vstack([numeric_vector(d["profile"]) for d in self.docs]))
        self.datasets = np.array([d["profile"]["dataset"] for d in self.docs])

    def _text(self, p: dict) -> str:
        t = profile_text(p)
        if not self.use_names:  # name-blind mode: drop column/table names, like an obfuscated export
            t = " | ".join(x for x in t.split(" | ") if not x.startswith(("column ", "table ")))
        return t

    def retrieve(self, p: dict, k: int = 7, exclude_dataset: str | None = None) -> list[tuple[dict, float]]:
        q_text = self.embedder.transform([self._text(p)])[0]
        q_num = normalize(numeric_vector(p).reshape(1, -1))[0]
        sim = self.tw * (self.text_emb @ q_text) + self.nw * (self.num_emb @ q_num)
        if exclude_dataset is not None:
            sim = np.where(self.datasets == exclude_dataset, -np.inf, sim)
        idx = np.argsort(-sim)[:k]
        return [(self.docs[i], float(sim[i])) for i in idx if np.isfinite(sim[i])]

    @staticmethod
    def vote(neighbours: list[tuple[dict, float]], power: float = 4.0) -> tuple[dict, dict]:
        """Weighted k-NN vote -> (role probabilities, best subtype per role)."""
        score = defaultdict(float)
        sub = defaultdict(lambda: defaultdict(float))
        for d, s in neighbours:
            w = max(s, 0) ** power
            score[d["privacy_role"]] += w
            sub[d["privacy_role"]][d["subtype"]] += w
        tot = sum(score.values()) or 1.0
        probs = {r: (score[r] + .01) / (tot + .01 * len(ROLES)) for r in ROLES}
        best_sub = {r: max(v, key=v.get) for r, v in sub.items()}
        return probs, best_sub
