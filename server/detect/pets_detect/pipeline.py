"""Detect pipeline: profile -> tier 1 rules -> tier 2 retrieval vote -> tier 3 local LLM (only when unsure)."""
from __future__ import annotations

import copy
import hashlib
import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .kb import KnowledgeBase
from .llm import LocalLLM
from .patterns import ROLES
from .profiler import profile_dataset
from .rules import Decision, context_adjust, tier1

PKG_DIR = Path(__file__).resolve().parent
def _find_root() -> Path:
    """The organisers' package: env PETS_ROOT, else the first parent folder (or its sibling
    TRUSTED_PETS_PROVING_GROUND_2026) that contains metadata/field_catalog.csv."""
    if os.environ.get("PETS_ROOT"):
        return Path(os.environ["PETS_ROOT"])
    for d in PKG_DIR.parents:
        for cand in (d, d / "TRUSTED_PETS_PROVING_GROUND_2026"):
            if (cand / "metadata" / "field_catalog.csv").exists():
                return cand
    return PKG_DIR.parents[2] / "TRUSTED_PETS_PROVING_GROUND_2026"


DEFAULT_ROOT = _find_root()
CACHE = PKG_DIR.parent / ".cache"


@dataclass
class Config:
    tiers: tuple = (1, 2, 3)
    embedder: str = "tfidf"
    k: int = 7
    rule_accept: float = 0.85      # tier-1 decisions at or above this confidence are final
    llm_below: float = 0.60        # call the LLM when the combined confidence is below this
    llm_model: str | None = None
    blind_names: bool = False      # ignore column/table names (simulates obfuscated exports)
    exclude_self: bool = True      # never retrieve labelled columns of the dataset being detected
    context: str = ""              # one-sentence description of the dataset, given by the data owner
    extra: dict = field(default_factory=dict)


def root_paths(root: Path | None = None):
    r = Path(root or DEFAULT_ROOT)
    return r, r / "data", r / "metadata" / "field_catalog.csv"


def load_profiles(dataset: str, data_dir: Path, refresh: bool = False) -> list[dict]:
    CACHE.mkdir(exist_ok=True)
    code = hashlib.sha256(b"".join((PKG_DIR / m).read_bytes() for m in ("profiler.py", "patterns.py"))).hexdigest()[:10]
    f = CACHE / f"profiles_{dataset}_{code}.pkl"
    src = data_dir / dataset
    newest = max((x.stat().st_mtime for x in src.glob("*.csv")), default=0)
    if f.exists() and not refresh and f.stat().st_mtime >= newest:
        return pickle.loads(f.read_bytes())
    ps = profile_dataset(dataset, src)
    f.write_bytes(pickle.dumps(ps))
    return ps


def blind(p: dict) -> dict:
    """Copy of a profile with uninformative names (keeps the original key for output)."""
    q = copy.copy(p)
    q["orig_column"] = p["column"]
    q["column"] = f"c{p['col_index'] + 1:02d}"
    q["table_columns"] = []
    return q


def implausible(role: str, p: dict) -> str | None:
    """Guardrail: reject an LLM answer that contradicts the column statistics (taxonomy definitions, not labels)."""
    if role == "record_key" and p["unique_ratio"] < .95:
        return f"a row key must be unique per row, but only {p['unique_ratio']:.0%} of values are unique"
    if role in ("technical_identifier", "direct_identifier") and p["n_unique"] < 20:
        return f"an identifier singles out people/devices, but the column has only {p['n_unique']} distinct values"
    if role == "free_text" and (p["n_unique"] < 30 or p["mean_len"] < 15):
        return f"free text needs varied, longer values ({p['n_unique']} distinct, avg {p['mean_len']:.0f} chars)"
    return None


class Detector:
    def __init__(self, cfg: Config, root: Path | None = None, refresh: bool = False):
        self.cfg = cfg
        self.root, self.data_dir, cat_path = root_paths(root)
        self.catalog = pd.read_csv(cat_path, dtype=str)
        labelled = sorted(self.catalog.dataset.unique())
        kb_profiles = []
        for ds in labelled:
            if (self.data_dir / ds).is_dir():
                ps = load_profiles(ds, self.data_dir, refresh)
                kb_profiles += [blind(p) for p in ps] if cfg.blind_names else ps
        self.kb = KnowledgeBase(kb_profiles, self.catalog, cfg.embedder, use_names=not cfg.blind_names) \
            if 2 in cfg.tiers or 3 in cfg.tiers else None
        self.llm = LocalLLM(cfg.llm_model) if 3 in cfg.tiers else None

    def classify(self, p: dict) -> dict:
        cfg = self.cfg
        q = blind(p) if cfg.blind_names else p
        t1 = tier1(q)
        rec = {"dataset": p["dataset"], "table": p["table"], "column": p["column"],
               "t1_role": t1.privacy_role, "t1_subtype": t1.subtype, "t1_conf": round(t1.confidence, 3),
               "neighbours": ""}
        final = t1
        neighbours = []
        if self.kb is not None and t1.confidence < cfg.rule_accept:
            neighbours = self.kb.retrieve(q, cfg.k, p["dataset"] if cfg.exclude_self else None)
            rec["neighbours"] = "; ".join(f"{d['profile']['dataset']}.{d['profile']['table']}.{d['profile']['column']}"
                                          f"={d['privacy_role']}({s:.2f})" for d, s in neighbours[:3])
            if 2 in cfg.tiers:
                probs, best_sub = self.kb.vote(neighbours)
                a = t1.confidence  # trust the rules in proportion to their confidence
                comb = {r: (1 - a) * probs[r] + (a if r == t1.privacy_role else 0.0) for r in ROLES}
                role = max(comb, key=comb.get)
                if role == t1.privacy_role:
                    st, why = t1.subtype, t1.reason
                else:
                    st = best_sub.get(role, "OTHER")
                    top = [f"{d['profile']['table']}.{d['profile']['column']}" for d, _ in neighbours
                           if d["privacy_role"] == role][:2]
                    why = f"most similar labelled columns ({', '.join(top)}) are {role}"
                    if t1.confidence > .4:
                        why += f"; rules weakly suggested {t1.privacy_role}"
                final = context_adjust(q, Decision(role, st, comb[role], why, "rules+retrieval"))
        if self.llm is not None and final.confidence < cfg.llm_below:
            d = self.llm.classify(q, neighbours, final, show_names=not cfg.blind_names,
                                    context=cfg.context)
            veto = implausible(d.privacy_role, q) if d is not None else None
            if d is not None and veto is None:
                final = d
            elif d is not None:
                rec["llm_rejected"] = f"{d.privacy_role}: {veto}"
        rec.update({"privacy_role": final.privacy_role, "subtype": final.subtype,
                    "confidence": round(final.confidence, 3), "source": final.source, "reason": final.reason})
        return rec

    def detect(self, dataset: str, refresh: bool = False) -> pd.DataFrame:
        ps = load_profiles(dataset, self.data_dir, refresh)
        cols = ["dataset", "table", "column", "privacy_role", "subtype", "confidence", "source", "reason",
                "t1_role", "t1_subtype", "t1_conf", "neighbours", "llm_rejected"]
        return pd.DataFrame([self.classify(p) for p in ps]).reindex(columns=cols)
