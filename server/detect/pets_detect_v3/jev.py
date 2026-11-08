"""Tier 3 on AutoTrust-JEV-27B (MLX build, served locally by `python -m jev27b_mlx serve`).

JEV is a decision model: it never writes text, it returns a probability for each option we supply. So the v3
JSON prompts become choice questions over the same column cards:
- table domain -> choice over DOMAINS (worded so pipeline.ART9_DOMAIN still matches the person/health ones);
- privacy_role -> choice over ROLES (descriptions from ROLE_DEFS); confidence = P(chosen role);
- subtype -> choice over SUBTYPES (the pipeline rejects pairs the catalogue does not allow);
- art9 -> yes/no, asked only for sensitive_attribute / free_text (the only roles the pipeline reads it for).
`reason` is written here from the probabilities. Same cache / worker pool / fallback as TableLLMv3.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request

from pets_detect.llm import ROLE_DEFS
from pets_detect.patterns import ROLES, SUBTYPES

from .llm_v3 import TableLLMv3, column_card, table_summary

ROLE_DESC = {r: d.strip() for r, d in (l[2:].split(":", 1) for l in ROLE_DEFS.splitlines() if l.startswith("- "))}
DOMAINS = [
    "patients and their health care (hospital, clinic, emergency, diagnoses)",
    "employees and personnel (staff, payroll, sick leave)",
    "clients of welfare or social care services (benefits, counselling)",
    "customers (contracts, invoices, orders, payments)",
    "students (grades, courses, special support)",
    "devices or accounts and their users (network, telemetry, logins)",
    "no person: places, sensors, products or reference data",
]


def make_llm(model: str | None = None):
    """DETECT_LLM_BACKEND=jev (default) or ollama (the previous TableLLMv3; `model` is the Ollama tag)."""
    return TableLLMv3(model) if os.environ.get("DETECT_LLM_BACKEND", "jev") == "ollama" else JevLLM()


class JevLLM(TableLLMv3):
    def __init__(self, host: str | None = None, cache_dir=".cache/v3/jev", **kw):
        super().__init__(None, host or os.environ.get("JEV_HOST", "http://127.0.0.1:8001"), cache_dir, **kw)
        self.model = "jev"

    def available(self) -> bool:
        if self._ok is None:
            try:
                with urllib.request.urlopen(f"{self.host}/health", timeout=3) as r:
                    info = json.loads(r.read())
                self._ok = info.get("prompt_attention", {}).get("attention") == "bidirectional"
                self.model = str(info.get("model", self.model))
                if not self._ok:
                    print(f"[jev] {self.host} does not read prompts bidirectionally; tier 3 disabled")
            except (urllib.error.URLError, OSError, ValueError):
                self._ok = False
                print(f"[jev] no jev27b_mlx server at {self.host}; tier 3 disabled (tiers 1-2 still run)")
        return self._ok

    def _decide(self, state: str, question: dict) -> dict | None:
        body = json.dumps({"state": state, "question": question}, ensure_ascii=False)
        key = hashlib.sha256(f"{self.model}\n{body}".encode()).hexdigest()[:32]
        f = self.cache / f"{key}.json"
        if f.exists():
            self.cache_hits += 1
            return json.loads(f.read_text())
        req = urllib.request.Request(f"{self.host}/v1/decide", data=body.encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.loads(r.read())
            out = dict(zip(out["options"], map(float, out["probabilities"])))
        except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as e:
            print(f"[jev] call failed: {e}")
            return None
        self.calls += 1
        f.write_text(json.dumps(out, ensure_ascii=False))
        return out

    @staticmethod
    def _choice(instructions: str, criteria: dict) -> dict:
        return {"type": "choice", "instructions": instructions, "criteria": criteria}

    def domain(self, table: str, ps: list[dict], show_names: bool, context: str = "") -> str:
        if not self.available():
            return ""
        cards = [column_card(i, p, None, show_names) for i, p in enumerate(ps)]
        state = (f"Dataset description from the data owner: {context}\n" if context else "") + \
            f"Table: {table}\nColumns (frequent values; words may be Finnish or Swedish):\n{table_summary(cards)}"
        p = self._decide(state, self._choice("Who is the data subject of this table (what each row is about)?",
                                             dict.fromkeys(DOMAINS)))
        return max(p, key=p.get) if p else ""

    def label_columns(self, table: str, ps: list[dict], guesses, ask: list[int], domain: str,
                      show_names: bool, context: str = "") -> dict[int, dict]:
        if not ask or not self.available():
            return {}
        cards = [column_card(i, p, None if i in ask else g, show_names) for i, (p, g) in enumerate(zip(ps, guesses))]

        def one(i: int) -> dict | None:
            target = {k: v for k, v in cards[i].items() if k not in ("id", "current_guess")}
            state = ((f"Dataset description from the data owner: {context}\n" if context else "")
                     + f"Table: {table}. It records: {domain}\n"
                     f"Other columns (for context):\n{table_summary([c for j, c in enumerate(cards) if j != i])}\n\n"
                     f"Column to classify: {json.dumps(target, ensure_ascii=False)}\n"
                     "(`values` lists the frequent values with their share of rows.)")
            pr = self._decide(state, self._choice("What is the privacy role of the column to classify?",
                                                  {r: ROLE_DESC.get(r) for r in ROLES}))
            if not pr:
                return None
            role = max(pr, key=pr.get)
            ps_ = self._decide(state + f"\nIts privacy role: {role}.",
                               self._choice("Which subtype best describes the column to classify?",
                                            dict.fromkeys(SUBTYPES)))
            if not ps_:
                return None
            art9 = False
            if role in ("sensitive_attribute", "free_text"):
                a = self._decide(state, {"type": "noul", "instructions":
                                         "Does the column hold GDPR Art. 9 special-category data (health, "
                                         "trade-union membership, religion, ethnicity, sexual life, biometrics, "
                                         "political opinion)?"})
                art9 = bool(a) and a.get("true", 0) > .5
            top = sorted(pr.items(), key=lambda x: -x[1])[:3]
            return {"privacy_role": role, "subtype": max(ps_, key=ps_.get), "art9": art9, "confidence": pr[role],
                    "reason": "JEV " + ", ".join(f"{r} {v:.2f}" for r, v in top)}

        return {i: out for i, out in zip(ask, self._map(one, ask))
                if out and out["privacy_role"] in ROLES and out["subtype"] in SUBTYPES}
