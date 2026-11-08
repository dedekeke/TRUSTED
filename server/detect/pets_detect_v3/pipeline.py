"""Detect v3 pipeline.

profile (v1) -> tier 1 rules (v1) -> name_info per column -> tier 2 router (kNN on names / LogReg on values)
            -> table domain (LLM) -> recall bias (margin by name_info, wider in Art. 9 person tables)
            -> tier 3 LLM on unsure columns, shown value distributions (B1)
            -> guardrails (v2) + asymmetric constraint (B3) -> honest confidence / needs_review (B2)
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pets_detect.patterns import ROLES
from pets_detect.pipeline import blind, load_profiles, root_paths
from pets_detect.rules import Decision, context_adjust, tier1

from pets_detect_v2.classifier import catalog_labels
from pets_detect_v2.pipeline import GENERIC_SUBTYPES, SENSITIVE, guardrail

from .jev import make_llm
from .naming import NameScorer, mixed_view
from .router import Router

ART9_DOMAIN = re.compile(r"health|patient|medic|hospital|clinic|nurs|diagnos|treatment|emergency|employee|payroll|"
                         r"personnel|staff|trade union|sick|disab|welfare|social care|counsel|religio|ethnic", re.I)
OUT_COLS = ["dataset", "table", "column", "privacy_role", "subtype", "confidence", "source", "reason", "data_kind",
            "art9", "needs_review", "table_domain", "art9_table", "name_info", "tier2_used", "t1_role", "t1_conf",
            "p_top3"]


@dataclass
class Config:
    tiers: tuple = (1, 2, 3)
    view: str = "names"            # names | blind | mixed
    router: str = "A2"             # knn | logreg | A1 | A2
    rule_accept: float = 0.85
    llm_below: float = 0.65
    margin_names: float = 0.03     # recall-bias margin when the name is fully informative
    margin_values: float = 0.10    # ... when the name says nothing (v2 default)
    margin_art9: float = 0.0       # B4: margin used in Art. 9 person tables (0 = off)
    llm_min_prob: float = 0.15     # v2 constraint: LLM may only move to roles the model finds plausible
    b2_honest_conf: bool = False   # B2: LLM agreement does not raise confidence; review flag from model margin
    b3_art9_llm: bool = False      # B3: in Art. 9 tables the LLM may raise a column to sensitive_attribute
    review_gap: float = 0.25
    review_below: float = 0.60
    llm_model: str | None = None
    context: str = ""


class DetectorV3:
    name = "v3"

    def __init__(self, cfg: Config, root: Path | None = None):
        self.cfg = cfg
        self.root, self.data_dir, cat_path = root_paths(root)
        self.catalog = pd.read_csv(cat_path, dtype=str)
        self.labelled = sorted(d for d in self.catalog.dataset.unique() if (self.data_dir / d).is_dir())
        train = []
        for ds in self.labelled:
            train += catalog_labels(load_profiles(ds, self.data_dir), self.catalog)
        self.router = Router(train, self.catalog, cfg.router) if 2 in cfg.tiers else None
        self.names = NameScorer(self.catalog)
        self.llm = make_llm(cfg.llm_model) if 3 in cfg.tiers else None
        self.kind_of = self.catalog.groupby("subtype").data_kind.agg(lambda s: s.value_counts().index[0]).to_dict()
        a9 = self.catalog.assign(a=self.catalog.art9_special_category.eq("True"))
        self.art9_of = a9.groupby(["privacy_role", "subtype"]).a.mean().to_dict()
        self.pairs = set(zip(self.catalog.privacy_role, self.catalog.subtype))
        self.timings: dict[str, float] = {}

    def prefit(self, datasets) -> "DetectorV3":
        """Fit the tier-2 value models for these datasets in parallel up front (otherwise each is fitted on first use)."""
        if self.router is not None:
            self.router.prefit(datasets)
        return self

    def _view(self, p: dict) -> dict:
        v = self.cfg.view
        if v == "blind":  # like an obfuscated export: column AND table names hidden (v1 blind() keeps the table)
            q = blind(p)
            q["table"] = "t"
            return q
        return mixed_view(p) if v == "mixed" else p

    def margin(self, info: float, art9: bool, person: bool) -> float:
        m = self.cfg.margin_values * (1 - info) + self.cfg.margin_names * info
        if art9 and person and self.cfg.margin_art9 > 0:
            m = max(m, self.cfg.margin_art9)
        return m

    def detect(self, dataset: str, profiles: list[dict] | None = None) -> pd.DataFrame:
        """profiles: precomputed column profiles (deployed inference); default: profile data_dir/<dataset>."""
        t0 = time.time()
        cfg = self.cfg
        ps = profiles if profiles is not None else load_profiles(dataset, self.data_dir)
        qs = [self._view(p) for p in ps]
        t1s = [tier1(q) for q in qs]
        by_table = defaultdict(list)
        for i, p in enumerate(ps):
            by_table[p["table"]].append(i)
        infos, info_why = [0.0] * len(ps), [""] * len(ps)
        for idx in by_table.values():
            names = [qs[i]["column"] for i in idx]
            for i in idx:
                infos[i], info_why[i] = self.names.score(qs[i]["column"], names, dataset)
        recs = [{"dataset": p["dataset"], "table": p["table"], "column": p["column"], "t1_role": t.privacy_role,
                 "t1_conf": round(t.confidence, 3), "name_info": infos[i], "tier2_used": "rules",
                 "p_top3": "", "table_domain": "", "art9_table": False}
                for i, (p, t) in enumerate(zip(ps, t1s))]

        # table domain first: the Art. 9-aware rules need it before deciding
        domains, art9_tab = {}, {}
        use_llm = self.llm is not None and self.llm.available()
        doms = {}
        if use_llm:
            doms = self.llm.map_tables(
                {table: (lambda idx=idx: self.llm.domain(qs[idx[0]]["table"] if cfg.view != "blind" else "(hidden)",
                                                          [qs[i] for i in idx], cfg.view != "blind", cfg.context))
                 for table, idx in by_table.items()})
        for table, idx in by_table.items():
            dom = doms.get(table, "")
            domains[table] = dom
            rule_hint = any(t1s[i].subtype in ("DIAGNOSIS_CODE", "HEALTH_DATA") for i in idx)
            art9_tab[table] = bool(ART9_DOMAIN.search(dom)) or rule_hint

        finals: list[Decision] = list(t1s)
        combs: list[dict | None] = [None] * len(ps)
        if self.router is not None:
            routed = self.router.predict(dataset, qs, infos, table_visible=cfg.view != "blind")
            need_sub = []
            for i, (q, t1, (pr, sub_for, w, used)) in enumerate(zip(qs, t1s, routed)):
                a = t1.confidence
                comb = {r: (1 - a) * pr[r] + (a if r == t1.privacy_role else 0.0) for r in ROLES}
                combs[i] = comb
                recs[i]["tier2_used"] = used
                recs[i]["p_top3"] = ", ".join(f"{r}:{v:.2f}" for r, v in sorted(comb.items(), key=lambda x: -x[1])[:3])
                if t1.confidence >= cfg.rule_accept:
                    continue
                role = max(comb, key=comb.get)
                why_bias = ""
                tab = ps[i]["table"]
                m = self.margin(infos[i], art9_tab[tab], q.get("table_person_signals", 0) > 0)
                if role == "non_sensitive" and m > 0:
                    alt = max(SENSITIVE, key=lambda r: comb[r])
                    if comb[alt] >= comb[role] - m:
                        why_bias = (f"; recall bias: {alt} ({comb[alt]:.2f}) within {m:.2f} of non_sensitive "
                                    f"({comb[role]:.2f})" + (" [Art. 9 table]" if art9_tab[tab] and m == cfg.margin_art9 else ""))
                        role = alt
                if role == t1.privacy_role:
                    finals[i] = Decision(role, t1.subtype, comb[role], t1.reason + why_bias, "rules+" + used)
                else:
                    sub = sub_for(role)
                    # D1: the subtype the neighbours suggest must fit the values (subtype check only: role "" skips
                    # the role rules, which the router's probabilities already weigh)
                    bad = guardrail(q, "", sub)
                    if bad and t1.confidence >= .5 and guardrail(q, "", t1.subtype) is None:
                        # the router's role rested on a subtype the values contradict: keep the rule decision
                        finals[i] = Decision(t1.privacy_role, t1.subtype, t1.confidence,
                                             t1.reason + f"; router suggested {role}/{sub} but {bad}", "rules")
                        continue
                    if bad:
                        sub = t1.subtype if (role, t1.subtype) in self.pairs and \
                            guardrail(q, "", t1.subtype) is None else "OTHER"
                    finals[i] = Decision(role, sub, comb[role],
                                         f"{used}: {recs[i]['p_top3']}" +
                                         (f"; rules weakly suggested {t1.privacy_role}" if t1.confidence > .4 else "")
                                         + (f"; subtype from neighbours rejected ({bad})" if bad else "")
                                         + why_bias, used)
            finals = [context_adjust(q, f) if f.source != "rules" else f for q, f in zip(qs, finals)]

        # ---- tier 3 ----
        if use_llm:
            for table, idx in by_table.items():
                ask = [j for j, i in enumerate(idx) if finals[i].confidence < cfg.llm_below]
                if not ask:
                    continue
                guesses = [(finals[i].privacy_role, finals[i].subtype, finals[i].confidence) for i in idx]
                tname = qs[idx[0]]["table"] if cfg.view != "blind" else "(hidden)"
                ans = self.llm.label_columns(tname, [qs[i] for i in idx], guesses, ask, domains[table],
                                             cfg.view != "blind", cfg.context)
                for j, a in ans.items():
                    i = idx[j]
                    cur, role = finals[i], a["privacy_role"]
                    lconf = max(0.0, min(float(a.get("confidence", .5)), .95))
                    reason = str(a.get("reason", ""))[:300]
                    recs[i]["llm_art9"] = bool(a.get("art9", False))
                    bad = guardrail(qs[i], role)
                    if bad:
                        cur.reason += f"; LLM suggested {role} but rejected ({bad})"
                        continue
                    sub = a["subtype"]
                    sub_ok = (role, sub) in self.pairs and guardrail(qs[i], role, sub) is None
                    p_role = combs[i].get(role, 0) if combs[i] else 1.0
                    b3 = (cfg.b3_art9_llm and role == "sensitive_attribute" and art9_tab[table] and lconf >= .7)
                    if role == cur.privacy_role:
                        st = sub if sub_ok and (cur.subtype in GENERIC_SUBTYPES or not cur.subtype) else cur.subtype
                        conf = cur.confidence if cfg.b2_honest_conf else (cur.confidence + lconf) / 2 + .1
                        finals[i] = Decision(role, st, conf, f"LLM agrees: {reason}", cur.source + "+llm")
                    elif p_role < cfg.llm_min_prob and not b3:
                        cur.reason += (f"; LLM suggested {role} but the statistical model gives it only {p_role:.2f}, "
                                       f"kept {cur.privacy_role}")
                    elif lconf >= .5:
                        why = "LLM (Art. 9 table, may raise to sensitive)" if b3 and p_role < cfg.llm_min_prob \
                            else "LLM (table context)"
                        conf = min(lconf, max(p_role, .5)) if cfg.b2_honest_conf else lconf
                        st = sub if sub_ok else (self.router._value_model(dataset).predict_subtypes(
                            [blind(qs[i]) if not qs[i].get("orig_column") else qs[i]], [t1s[i]], [role])[0]
                            if self.router else "OTHER")
                        finals[i] = Decision(role, st, conf, f"{why}: {reason}; before: {cur.privacy_role} "
                                                             f"({cur.confidence:.2f})", "table-llm")
        # ---- output ----
        for i, (p, f) in enumerate(zip(ps, finals)):
            r = recs[i]
            r.update({"privacy_role": f.privacy_role, "subtype": f.subtype or "OTHER",
                      "confidence": round(min(f.confidence, 1.0), 3), "source": f.source,
                      "reason": f.reason + (f" [name_info {infos[i]:.2f}: {info_why[i]}]" if self.router else ""),
                      "table_domain": domains.get(p["table"], ""), "art9_table": art9_tab.get(p["table"], False)})
            r["data_kind"] = self.kind_of.get(r["subtype"], "")
            prior = self.art9_of.get((f.privacy_role, r["subtype"]), 0.0) >= .5
            r["art9"] = bool(r.pop("llm_art9", prior)) and f.privacy_role in ("sensitive_attribute", "free_text")
            review = f.confidence < cfg.review_below
            if cfg.b2_honest_conf and combs[i] is not None and t1s[i].confidence < cfg.rule_accept:
                top = sorted(combs[i].values(), reverse=True)
                review = review or (top[0] - top[1] < cfg.review_gap) or f.source == "table-llm"
            r["needs_review"] = review
        self.timings[dataset] = round(time.time() - t0, 1)
        return pd.DataFrame(recs)[OUT_COLS]
