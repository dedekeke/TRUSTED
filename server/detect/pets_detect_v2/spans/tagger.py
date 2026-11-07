"""Layer 3: a token tagger learnt from the public span labels (logistic regression, hashed features).

Each token is classified as O or one of the PII labels from its own shape and its neighbours (two words either
side), plus dictionary flags (first names, surnames, street suffixes, municipalities). Adjacent tokens with the
same label become one span. This is the "classic ML where we have data" part: ~90k labelled spans to learn from.
"""
from __future__ import annotations

import re

import numpy as np
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import SGDClassifier

from pets_detect.patterns import FIRST_NAMES, MUNICIPALITIES, SURNAME_SUFFIX

from .regex import RX_DATE
from .spoken import NUM_WORDS

TOK = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*|\d+|[^\w\s]")
STREET = re.compile(r"(tie|katu|kuja|polku|piha|rinne|kaari|ranta|mäki|väylä|puisto|aukio|tori|gatan|vägen|"
                    r"gränd|stigen|backen|kulma|lenkki|niitty|metsä|harju|laakso)$", re.I)


def tokenize(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in TOK.finditer(text)]


def _shape(w: str) -> str:
    s = re.sub(r"[A-ZÅÄÖ]", "A", w)
    s = re.sub(r"[a-zåäöéü]", "a", s)
    s = re.sub(r"\d", "9", s)
    return re.sub(r"(.)\1+", r"\1\1", s)[:6]


class Dictionaries:
    def __init__(self, first: set[str] | None = None, last: set[str] | None = None):
        self.first = set(FIRST_NAMES) | (first or set())
        self.last = last or set()


def date_tokens(text: str, toks) -> set[int]:
    spans = [(m.start(), m.end()) for m in RX_DATE.finditer(text)]
    return {k for k, (_, a, b) in enumerate(toks) if any(a < e and s < b for s, e in spans)} if spans else set()


def token_features(toks: list[tuple[str, int, int]], i: int, d: Dictionaries, dates: set[int] = frozenset()) -> list[str]:
    w = toks[i][0]
    lw = w.lower()
    f = [f"w={lw}", f"sh={_shape(w)}", f"p3={lw[:3]}", f"s3={lw[-3:]}", f"s4={lw[-4:]}", f"len={min(len(w), 12)}"]
    if w[:1].isupper():
        f.append("cap")
        if i == 0 or toks[i - 1][0] in ".!?:":
            f.append("cap_start")
    if w.isdigit():
        f.append(f"dig{min(len(w), 9)}")
    if lw in NUM_WORDS:
        f.append("numword")
    if i in dates:
        f.append("date_rx")
    if lw in d.first:
        f.append("first")
    if lw in d.last:
        f.append("last")
    if SURNAME_SUFFIX.search(w):
        f.append("surn_suffix")
    if STREET.search(lw):
        f.append("street")
    if lw in MUNICIPALITIES or lw.rstrip("ssa").rstrip("lla") in MUNICIPALITIES:
        f.append("muni")
    for o in (-2, -1, 1, 2):
        j = i + o
        if 0 <= j < len(toks):
            n = toks[j][0]
            ln = n.lower()
            f += [f"w{o}={ln}", f"sh{o}={_shape(n)}"]
            if ln in d.first:
                f.append(f"first{o}")
            if ln in d.last:
                f.append(f"last{o}")
            if ln in NUM_WORDS or n.isdigit():
                f.append(f"num{o}")
            if STREET.search(ln):
                f.append(f"street{o}")
        else:
            f.append(f"edge{o}")
    if i > 0:
        f.append(f"bi={toks[i - 1][0].lower()}|{lw}")
    return f


def token_labels(toks, spans) -> list[str]:
    lab = ["O"] * len(toks)
    for s in spans:
        for k, (_, a, b) in enumerate(toks):
            if a < s["end"] and s["start"] < b:
                lab[k] = s["label"]
    return lab


class Tagger:
    def __init__(self, dicts: Dictionaries, n_features: int = 2 ** 20):
        self.d = dicts
        self.h = FeatureHasher(n_features=n_features, input_type="string", alternate_sign=False)
        self.clf = SGDClassifier(loss="log_loss", alpha=2e-6, max_iter=12, tol=None, random_state=0)
        self.o_threshold = 0.5

    def _xy(self, records: list[tuple[str, list[dict]]]):
        feats, ys = [], []
        for text, spans in records:
            toks = tokenize(text)
            labs = token_labels(toks, spans)
            dts = date_tokens(text, toks)
            for i in range(len(toks)):
                feats.append(token_features(toks, i, self.d, dts))
                ys.append(labs[i])
        return self.h.transform(feats), np.array(ys)

    def fit(self, records):
        x, y = self._xy(records)
        self.clf.fit(x, y)
        self.classes_ = list(self.clf.classes_)
        self.o_idx = self.classes_.index("O")
        return self

    def tune_threshold(self, records, gold_score_fn, grid=(0.5, 0.6, 0.7, 0.8, 0.9)):
        """Pick the P(O) threshold that maximises recall-weighted F2 on a dev set (never on test)."""
        best = (-1, .5)
        for t in grid:
            self.o_threshold = t
            sc = gold_score_fn(self)
            if sc > best[0]:
                best = (sc, t)
        self.o_threshold = best[1]
        return best

    def precompute(self, texts: list[str], batch: int = 4000) -> None:
        """Token probabilities for many texts in one go (hashing + predict_proba per call is the slow part).
        The decision threshold is applied later, so tuning it costs nothing extra."""
        if not hasattr(self, "_cache"):
            self._cache = {}
        todo = [t for t in dict.fromkeys(texts) if t not in self._cache]
        for k in range(0, len(todo), batch):
            part = todo[k:k + batch]
            toks_all = [tokenize(t) for t in part]
            dts_all = [date_tokens(t, tk) for t, tk in zip(part, toks_all)]
            feats = [token_features(tk, i, self.d, dt) for tk, dt in zip(toks_all, dts_all) for i in range(len(tk))]
            pr = self.clf.predict_proba(self.h.transform(feats)) if feats else None
            pos = 0
            for t, tk in zip(part, toks_all):
                self._cache[t] = (tk, pr[pos:pos + len(tk)] if pr is not None else None)
                pos += len(tk)

    def predict(self, text: str) -> list[dict]:
        if not hasattr(self, "_cache") or text not in self._cache:
            self.precompute([text])
        toks, pr = self._cache[text]
        if not toks:
            return []
        labs, confs = [], []
        for row in pr:
            if row[self.o_idx] >= self.o_threshold:
                labs.append("O")
                confs.append(row[self.o_idx])
            else:
                r = row.copy()
                r[self.o_idx] = -1
                k = int(r.argmax())
                labs.append(self.classes_[k])
                confs.append(float(row[k]))
        spans, i = [], 0
        while i < len(toks):
            if labs[i] == "O":
                i += 1
                continue
            j = i
            while j + 1 < len(toks) and labs[j + 1] == labs[i]:
                j += 1
            # do not start or end a span on punctuation
            a, b = i, j
            while a <= b and not re.match(r"\w", toks[a][0]):
                a += 1
            while b >= a and not re.match(r"\w", toks[b][0]):
                b -= 1
            if a <= b:
                spans.append({"start": toks[a][1], "end": toks[b][2], "label": labs[i],
                              "confidence": round(float(np.mean(confs[a:b + 1])), 3), "source": "tagger"})
            i = j + 1
        return spans
