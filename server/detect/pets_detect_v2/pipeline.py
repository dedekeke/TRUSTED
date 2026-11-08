"""Detect v2 pipeline.

profile (v1) -> tier 1 rules (v1) -> tier 2 calibrated classifier (or v1 kNN, for ablation)
            -> recall bias -> tier 3 table-level LLM (only for unsure columns) -> guardrail -> Select fields

Every classifier that labels dataset X is trained without X (leave-one-dataset-out), so scores are honest.
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pets_detect.kb import KnowledgeBase
from pets_detect.patterns import ROLES
from pets_detect.pipeline import blind, load_profiles, root_paths
from pets_detect.rules import Decision, context_adjust, tier1

from .classifier import ColumnClassifier, catalog_labels
from .table_llm import TableLLM

SENSITIVE = ["direct_identifier", "quasi_identifier", "sensitive_attribute", "technical_identifier", "free_text"]
GENERIC_SUBTYPES = {"OTHER", "CATEGORY", "MEASUREMENT"}
PKG_DIR = Path(__file__).resolve().parent
OUT_COLS = ["dataset", "table", "column", "privacy_role", "subtype", "confidence", "source", "reason",
            "data_kind", "art9", "needs_review", "table_domain", "t1_role", "t1_conf", "p_top3"]


@dataclass
class Config:
    tiers: tuple = (1, 2, 3)
    model: str = "logreg"
    rule_accept: float = 0.85
    llm_below: float = 0.65
    recall_margin: float = 0.10
    review_below: float = 0.60
    llm_min_prob: float = 0.15
    blind_names: bool = False
    llm_model: str | None = None
    context: str = ""
    k: int = 7


PATTERN_SUBTYPES = {"IBAN": "m_iban", "LICENSE_PLATE": "m_plate", "EMAIL": "m_email", "PHONE": "m_phone",
                    "NATIONAL_ID": "m_hetu", "IP_ADDRESS": "m_ipv4", "MAC_ADDRESS": "m_mac", "PAYMENT_CARD": "m_pan",
                    "GPS_COORDINATE": "m_coord"}
PATTERN_MIN_SHARE = {"GPS_COORDINATE": .2}


def guardrail(p: dict, role: str, subtype: str = "") -> str | None:
    """Reject LLM answers that contradict hard statistics. Returns a reason when rejected."""
    key = PATTERN_SUBTYPES.get(subtype)
    if key and p.get(key, 0) < PATTERN_MIN_SHARE.get(subtype, .3) and \
            not (subtype == "PAYMENT_CARD" and p.get("m_pan_masked", 0) >= .3):
        return f"{subtype} needs matching values, only {p.get(key, 0):.0%} match the pattern"
    if role == "record_key" and p["unique_ratio"] < .9:
        return f"record_key needs unique values, column is only {p['unique_ratio']:.0%} unique"
    if role == "free_text" and p["mean_words"] < 3 and p["m_url"] < .5:
        return f"free_text needs long text, average is {p['mean_words']:.1f} words"
    if role == "direct_identifier" and p["n_unique"] <= 3:
        return f"a direct identifier cannot have only {p['n_unique']} distinct values"
    return None


class DetectorV2:
    name = "v2"

    def __init__(self, cfg: Config, root: Path | None = None):
        self.cfg = cfg
        self.root, self.data_dir, cat_path = root_paths(root)
        self.catalog = pd.read_csv(cat_path, dtype=str)
        self.labelled = sorted(d for d in self.catalog.dataset.unique() if (self.data_dir / d).is_dir())
        kb = []
        for ds in self.labelled:
            ps = load_profiles(ds, self.data_dir)
            kb += [self._view(p) for p in ps]
        self.train = catalog_labels(kb, self.catalog)
        self.train_t1 = [tier1(p) for p, _, _ in self.train]
        self._models: dict[str, object] = {}
        self.llm = TableLLM(cfg.llm_model) if 3 in cfg.tiers else None
        self.kb = None
        if cfg.model == "knn" and 2 in cfg.tiers:
            self.kb = KnowledgeBase([p for p, _, _ in self.train], self.catalog, "tfidf",
                                    use_names=not cfg.blind_names)
        self.kind_of = self.catalog.groupby("subtype").data_kind.agg(lambda s: s.value_counts().index[0]).to_dict()
        a9 = self.catalog.assign(a=self.catalog.art9_special_category.eq("True"))
        self.art9_of = a9.groupby(["privacy_role", "subtype"]).a.mean().to_dict()
        self.pairs = set(zip(self.catalog.privacy_role, self.catalog.subtype))
        self.timings: dict[str, float] = {}

    def _view(self, p: dict) -> dict:
        return blind(p) if self.cfg.blind_names else p

    def _model_for(self, dataset: str) -> ColumnClassifier:
        """Classifier trained on every labelled dataset except `dataset` (all of them for unseen data)."""
        if dataset not in self._models:
            idx = [i for i, (p, _, _) in enumerate(self.train) if p["dataset"] != dataset]
            m = ColumnClassifier(self.cfg.model, use_names=not self.cfg.blind_names)
            m.fit([self.train[i][0] for i in idx], [self.train_t1[i] for i in idx],
                  [self.train[i][1] for i in idx], [self.train[i][2] for i in idx])
            self._models[dataset] = m
        return self._models[dataset]

    def _tier2(self, dataset: str, qs: list[dict], t1s: list[Decision]):
        cfg = self.cfg
        if self.kb is not None:
            out = []
            for q in qs:
                probs, best = self.kb.vote(self.kb.retrieve(q, cfg.k, dataset))
                out.append((probs, best))
            return [o[0] for o in out], [o[1] for o in out]
        m = self._model_for(dataset)
        probs = m.predict_proba(qs, t1s)
        return probs, m

    def detect(self, dataset: str) -> pd.DataFrame:
        t0 = time.time()
        cfg = self.cfg
        ps = load_profiles(dataset, self.data_dir)
        qs = [self._view(p) for p in ps]
        t1s = [tier1(q) for q in qs]
        recs = [{"dataset": p["dataset"], "table": p["table"], "column": p["column"],
                 "t1_role": t.privacy_role, "t1_conf": round(t.confidence, 3), "p_top3": "", "table_domain": ""}
                for p, t in zip(ps, t1s)]
        finals: list[Decision] = list(t1s)
        probs_all = [None] * len(ps)

        if 2 in cfg.tiers:
            probs, helper = self._tier2(dataset, qs, t1s)
            roles_tmp = []
            for i, (q, t1, pr) in enumerate(zip(qs, t1s, probs)):
                a = t1.confidence
                comb = {r: (1 - a) * pr[r] + (a if r == t1.privacy_role else 0.0) for r in ROLES}
                probs_all[i] = comb
                recs[i]["p_top3"] = ", ".join(f"{r}:{v:.2f}" for r, v in
                                              sorted(comb.items(), key=lambda x: -x[1])[:3])
                if t1.confidence >= cfg.rule_accept:
                    roles_tmp.append(None)
                    continue
                role = max(comb, key=comb.get)
                why_bias = ""
                if role == "non_sensitive" and cfg.recall_margin > 0:
                    alt = max(SENSITIVE, key=lambda r: comb[r])
                    if comb[alt] >= comb[role] - cfg.recall_margin:
                        why_bias = (f"; recall bias: {alt} ({comb[alt]:.2f}) is within {cfg.recall_margin:.2f} "
                                    f"of non_sensitive ({comb[role]:.2f})")
                        role = alt
                roles_tmp.append(role)
                if role == t1.privacy_role:
                    finals[i] = Decision(role, t1.subtype, comb[role], t1.reason + why_bias, "rules+classifier")
                else:
                    finals[i] = Decision(role, "", comb[role], "", "classifier")
                    finals[i].reason = (f"statistical model: {recs[i]['p_top3']}" +
                                        (f"; rules weakly suggested {t1.privacy_role}" if t1.confidence > .4 else "")
                                        + why_bias)
            need = [i for i, f in enumerate(finals) if f.subtype == ""]
            if need:
                if isinstance(helper, ColumnClassifier):
                    subs = helper.predict_subtypes([qs[i] for i in need], [t1s[i] for i in need],
                                                   [finals[i].privacy_role for i in need])
                else:
                    subs = [helper[i].get(finals[i].privacy_role, "OTHER") for i in need]
                for i, s in zip(need, subs):
                    finals[i].subtype = s
            finals = [context_adjust(q, f) if f.source != "rules" else f for q, f in zip(qs, finals)]

        domains: dict[str, str] = {}
        if self.llm is not None:
            by_table = defaultdict(list)
            for i, p in enumerate(ps):
                by_table[p["table"]].append(i)
            for table, idx in by_table.items():
                ask = [j for j, i in enumerate(idx) if finals[i].confidence < cfg.llm_below]
                if not ask:
                    continue
                guesses = [(finals[i].privacy_role, finals[i].subtype, finals[i].confidence) for i in idx]
                tname = qs[idx[0]]["table"] if not cfg.blind_names else "(hidden)"
                domain, ans = self.llm.label_table(tname, [qs[i] for i in idx], guesses, ask,
                                                   not cfg.blind_names, cfg.context)
                domains[table] = domain
                fix_sub = []
                for j, a in ans.items():
                    i = idx[j]
                    cur = finals[i]
                    role = a["privacy_role"]
                    lconf = max(0.0, min(float(a.get("confidence", .5)), .95))
                    reason = str(a.get("reason", ""))[:300]
                    recs[i]["llm_art9"] = bool(a.get("art9", False))
                    bad = guardrail(qs[i], role)
                    if bad:
                        cur.reason += f"; LLM suggested {role} but rejected ({bad})"
                        continue
                    sub = a["subtype"]
                    sub_ok = (role, sub) in self.pairs and guardrail(qs[i], role, sub) is None
                    if role == cur.privacy_role:
                        st = sub if sub_ok and (cur.subtype in GENERIC_SUBTYPES or not cur.subtype) else cur.subtype
                        finals[i] = Decision(role, st, (cur.confidence + lconf) / 2 + .1,
                                             f"LLM agrees: {reason}", cur.source + "+llm")
                    elif probs_all[i] is not None and probs_all[i].get(role, 0) < cfg.llm_min_prob:
                        cur.reason += (f"; LLM suggested {role} but the statistical model gives it only "
                                       f"{probs_all[i].get(role, 0):.2f}, kept {cur.privacy_role}")
                    elif lconf >= .5:
                        finals[i] = Decision(role, sub if sub_ok else "", lconf,
                                             f"LLM (table context): {reason}; before: {cur.privacy_role} "
                                             f"({cur.confidence:.2f})", "table-llm")
                        if not sub_ok:
                            fix_sub.append(i)
                if fix_sub:
                    if 2 in cfg.tiers and self.kb is None:
                        subs = self._model_for(dataset).predict_subtypes(
                            [qs[i] for i in fix_sub], [t1s[i] for i in fix_sub],
                            [finals[i].privacy_role for i in fix_sub])
                    else:
                        subs = ["OTHER"] * len(fix_sub)
                    for i, s_ in zip(fix_sub, subs):
                        finals[i].subtype = s_
        for i, (p, f) in enumerate(zip(ps, finals)):
            r = recs[i]
            r.update({"privacy_role": f.privacy_role, "subtype": f.subtype or "OTHER",
                      "confidence": round(f.confidence, 3), "source": f.source, "reason": f.reason,
                      "table_domain": domains.get(p["table"], "")})
            r["data_kind"] = self.kind_of.get(r["subtype"], "")
            prior = self.art9_of.get((f.privacy_role, r["subtype"]), 0.0) >= .5
            r["art9"] = bool(r.pop("llm_art9", prior)) and f.privacy_role in ("sensitive_attribute", "free_text")
            r["needs_review"] = f.confidence < cfg.review_below
        self.timings[dataset] = round(time.time() - t0, 1)
        return pd.DataFrame(recs)[OUT_COLS]
