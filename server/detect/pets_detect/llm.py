"""Tier 3: local LLM (Ollama) that decides ambiguous columns from the profile + retrieved examples (the "G" of RAG).

Design choices (inspired by typed decision models such as Jev, but fully local):
- the answer is constrained by a JSON schema whose role/subtype fields are enums -> never outside the taxonomy;
- temperature 0 + on-disk cache keyed by the prompt hash -> reproducible demos;
- the prompt holds the column profile (statistics, masked shapes, a few sample values) and the retrieved
  labelled examples; the data never leaves the machine because Ollama runs on localhost;
- any failure (server down, timeout, bad JSON) returns None and the pipeline falls back to tiers 1-2.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .patterns import ROLES, SUBTYPES
from .rules import Decision

ROLE_DEFS = """privacy_role definitions:
- direct_identifier: identifies a person on its own (name, national id/HETU, e-mail, phone, IBAN, card number, plate, customer number known outside the system)
- quasi_identifier: identifies in combination (birth date, age, sex, postcode, municipality, timestamps, coordinates, language, employer, occupation)
- sensitive_attribute: the protected fact itself, incl. GDPR Art. 9 (diagnosis, health measurement, special support, income, payment default, grades, religion)
- technical_identifier: device/network/system id that singles out a person or device, or a foreign key linking records of one person (IP, MAC, hostname, card id, meter id, employee id)
- free_text: unstructured text that may contain anything (notes, chat, descriptions, URLs with paths)
- record_key: row identifier with no meaning outside the table
- non_sensitive: safe as is (product category, counts, weather, reference data about places not people)"""

SCHEMA = {
    "type": "object",
    "properties": {
        "privacy_role": {"type": "string", "enum": ROLES},
        "subtype": {"type": "string", "enum": SUBTYPES},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["privacy_role", "subtype", "confidence", "reason"],
}


class LocalLLM:
    def __init__(self, model: str | None = None, host: str | None = None, cache_dir: str | Path = ".cache/llm",
                 timeout: int = 120):
        self.model = model or os.environ.get("DETECT_LLM_MODEL", "qwen2.5:7b")
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self._ok = None

    def available(self) -> bool:
        if self._ok is None:
            try:
                with urllib.request.urlopen(f"{self.host}/api/tags", timeout=3) as r:
                    models = [m["name"] for m in json.loads(r.read()).get("models", [])]
                self._ok = any(m == self.model or m.startswith(self.model + ":") for m in models)
                if not self._ok:
                    print(f"[llm] Ollama is running but model '{self.model}' is not pulled "
                          f"(run: ollama pull {self.model}); tier 3 disabled")
            except (urllib.error.URLError, OSError, ValueError):
                self._ok = False
                print(f"[llm] no Ollama server at {self.host}; tier 3 disabled (tiers 1-2 still run)")
        return self._ok

    @staticmethod
    def build_prompt(p: dict, neighbours: list[tuple[dict, float]], hint: Decision | None,
                     show_names: bool = True, context: str = "") -> str:
        stats = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in p.items()
                 if k.startswith("m_") and isinstance(v, float) and v >= .2}
        col = {
            "column": p["column"] if show_names else "(hidden)",
            "table": p["table"] if show_names else "(hidden)",
            "other_columns_in_table": p.get("table_columns", [])[:30] if show_names else [],
            "null_frac": p["null_frac"], "unique_ratio": p["unique_ratio"], "n_unique": p["n_unique"],
            "mean_words": round(p["mean_words"], 2), "mean_len": round(p["mean_len"], 1),
            "masked_shapes": p["shapes"], "sample_values": [str(v)[:80] for v in p["samples"][:5]],
            "pattern_match_rates": stats, "foreign_key_to": p["fk_to"],
            "table_has_person_data": bool(p.get("table_person_signals", 0)),
        }
        ex = []
        for d, s in neighbours[:5]:
            q = d["profile"]
            ex.append({"similarity": round(s, 3), "column": f"{q['table']}.{q['column']}",
                       "shapes": q["shapes"][:3], "privacy_role": d["privacy_role"], "subtype": d["subtype"],
                       "description": str(d["description"])[:200], "traps": str(d["traps"])[:200]})
        h = (f"Rule-based guess: {hint.privacy_role}/{hint.subtype} (confidence {hint.confidence:.2f}): {hint.reason}"
             if hint else "No rule-based guess.")
        return (
            "You classify one column of a dataset for privacy protection.\n"
            f"{ROLE_DEFS}\n\n"
            + (f"Dataset description from the data owner: {context}\n\n" if context else "")
            + f"Column profile (JSON):\n{json.dumps(col, ensure_ascii=False)}\n\n"
            f"Most similar labelled columns from other datasets:\n{json.dumps(ex, ensure_ascii=False)}\n\n"
            f"{h}\n\n"
            "Decide privacy_role and subtype. confidence is your probability (0-1) that the role is right. "
            "reason: one short sentence citing the evidence."
        )

    def classify(self, p: dict, neighbours, hint: Decision | None, show_names: bool = True,
                 context: str = "") -> Decision | None:
        if not self.available():
            return None
        prompt = self.build_prompt(p, neighbours, hint, show_names, context)
        key = hashlib.sha256(f"{self.model}\n{prompt}".encode()).hexdigest()[:32]
        f = self.cache / f"{key}.json"
        if f.exists():
            out = json.loads(f.read_text())
        else:
            body = {"model": self.model, "stream": False, "format": SCHEMA,
                    "options": {"temperature": 0, "seed": 0},
                    "messages": [{"role": "user", "content": prompt}]}
            req = urllib.request.Request(f"{self.host}/api/chat", data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = json.loads(json.loads(r.read())["message"]["content"])
            except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
                print(f"[llm] {p['table']}.{p['column']}: {e}; falling back")
                return None
            f.write_text(json.dumps(out, ensure_ascii=False))
        role, st = out.get("privacy_role"), out.get("subtype")
        if role not in ROLES or st not in SUBTYPES:
            return None
        conf = float(out.get("confidence", .5))
        return Decision(role, st, max(0.0, min(conf, 1.0)), str(out.get("reason", ""))[:300], "llm")
