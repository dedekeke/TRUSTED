"""Tier 3 (v2): one local-LLM call per table instead of one per column.

Why: a column of numbers like 132, 139, 145 is meaningless alone, but next to a national id, an ICD code and a
triage level it is obviously blood pressure. The model first states what the table describes (domain and data
subject), then labels only the columns the earlier tiers were unsure about, with every column as context.

- answer constrained by a JSON schema (role/subtype enums) -> never outside the taxonomy;
- temperature 0 + on-disk cache keyed by the prompt hash -> reproducible;
- runs on localhost (Ollama): no data leaves the machine;
- any failure -> None, the pipeline keeps the tier-2 answer.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from pets_detect.llm import ROLE_DEFS
from pets_detect.patterns import ROLES, SUBTYPES

EXTRA_GUIDE = """Guidance:
- First decide what the table is about and who the data subject is. Clues: job titles, employment start dates,
  contract types, working hours and pay -> employees; diagnoses, triage, vital signs -> patients; contracts,
  invoices, products -> customers; grades, courses -> students; device/network fields -> devices and their users.
- sensitive_attribute is the private fact about the data subject: health measurements and vital signs, diagnoses,
  disabilities, medication, salary/income/debt/benefits, payment defaults, grades and special needs, trade-union
  membership, religion, ethnicity, sexual life, criminal records, sick leave. Numbers can be sensitive when the table
  is about people (e.g. a blood-pressure column in a patient table).
- art9 = true only for GDPR Art. 9 special categories (health, union membership, religion, ethnicity, sexual life,
  biometrics, political opinion).
- quasi_identifier: facts that single a person out in combination (dates, age, sex, postcode, municipality,
  workplace, occupation, start date of employment, language).
- Columns of tables about places, sensors or products (not people) are usually non_sensitive.
- A hash of an identifier is still a technical_identifier when it repeats across rows of the same person."""

DOMAIN_SCHEMA = {
    "type": "object",
    "properties": {"table_domain": {"type": "string"}, "data_subject": {"type": "string"}},
    "required": ["table_domain", "data_subject"],
}

COLUMN_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence": {"type": "string"},
        "privacy_role": {"type": "string", "enum": ROLES},
        "subtype": {"type": "string", "enum": SUBTYPES},
        "art9": {"type": "boolean"},
        "confidence": {"type": "number"},
    },
    "required": ["evidence", "privacy_role", "subtype", "art9", "confidence"],
}


def column_card(i: int, p: dict, guess: tuple[str, str, float] | None, show_names: bool) -> dict:
    card = {
        "id": i + 1,
        "name": p["column"],
        "shapes": p["shapes"][:3],
        "samples": [str(v)[:40] for v in p["samples"][:4]],
        "unique_ratio": p["unique_ratio"], "n_unique": p["n_unique"], "null_frac": p["null_frac"],
    }
    if p["num_min"] is not None and p["frac_numeric"] > .8:
        card["range"] = [round(p["num_min"], 2), round(p["num_max"], 2)]
    if p["mean_words"] > 2:
        card["avg_words"] = round(p["mean_words"], 1)
    if p["fk_to"]:
        card["foreign_key_to"] = p["fk_to"][:2] if show_names else True
    if guess:
        card["current_guess"] = f"{guess[0]}/{guess[1]} ({guess[2]:.2f})"
    return card


def table_summary(cards: list[dict]) -> str:
    """One line per column: the whole table as context, compact enough for a small model."""
    lines = []
    for c in cards:
        g = f" [{c['current_guess']}]" if "current_guess" in c else ""
        lines.append(f"- {c['name']}: e.g. {', '.join(c['samples'][:3])}{g}")
    return "\n".join(lines)


def domain_prompt(table: str, cards: list[dict], context: str = "") -> str:
    return (
        "Here is a sample of a table. Say in one sentence what the table records, and who the data subject is "
        "(the kind of person or thing each row is about). Read the values: words may be Finnish or Swedish.\n"
        + (f"Dataset description from the data owner: {context}\n" if context else "")
        + f"Table: {table}\n{table_summary(cards)}\n\n"
        "Clues: job titles, employment start dates, contract types, working hours and pay -> employees; diagnoses, "
        "triage, vital signs -> patients; contracts, invoices -> customers; grades, courses -> students; "
        "network/device fields -> devices and their users; stops, sensors, places -> no person."
    )


def column_prompt(table: str, domain: str, cards: list[dict], i: int, context: str = "") -> str:
    target = {k: v for k, v in cards[i].items() if k not in ("id", "current_guess")}
    return (
        "You classify ONE column of a table for privacy protection.\n"
        f"{ROLE_DEFS}\n\n{EXTRA_GUIDE}\n\n"
        + (f"Dataset description from the data owner: {context}\n" if context else "")
        + f"Table: {table}. It records: {domain}\n"
        f"Other columns of the table (for context):\n{table_summary([c for j, c in enumerate(cards) if j != i])}\n\n"
        f"COLUMN TO CLASSIFY: {json.dumps(target, ensure_ascii=False)}\n\n"
        "First write `evidence`: what the sample values of THIS column are (quote one) and what they mean in this "
        "table. Then give privacy_role, subtype, art9 and confidence (your probability that the role is right)."
    )


class TableLLM:
    def __init__(self, model: str | None = None, host: str | None = None, cache_dir: str | Path = ".cache/v2/llm",
                 timeout: int = 300, chunk: int = 12):
        self.model = model or os.environ.get("DETECT_LLM_MODEL", "qwen2.5:7b")
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.timeout, self.chunk = timeout, chunk
        self._ok = None
        self.calls = self.cache_hits = 0

    def available(self) -> bool:
        if self._ok is None:
            try:
                with urllib.request.urlopen(f"{self.host}/api/tags", timeout=3) as r:
                    names = [m["name"] for m in json.loads(r.read()).get("models", [])]
                self._ok = any(n == self.model or n.startswith(self.model + ":") for n in names)
                if not self._ok:
                    print(f"[v2-llm] model {self.model} not pulled; tier 3 disabled")
            except (urllib.error.URLError, OSError, ValueError):
                self._ok = False
                print(f"[v2-llm] no Ollama at {self.host}; tier 3 disabled")
        return self._ok

    def _ask(self, prompt: str, schema: dict) -> dict | None:
        key = hashlib.sha256(f"{self.model}\n{json.dumps(schema)}\n{prompt}".encode()).hexdigest()[:32]
        f = self.cache / f"{key}.json"
        if f.exists():
            self.cache_hits += 1
            return json.loads(f.read_text())
        body = {"model": self.model, "stream": False, "format": schema,
                "options": {"temperature": 0, "seed": 0, "num_ctx": 8192},
                "messages": [{"role": "user", "content": prompt}]}
        req = urllib.request.Request(f"{self.host}/api/chat", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.loads(json.loads(r.read())["message"]["content"])
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            print(f"[v2-llm] call failed: {e}")
            return None
        self.calls += 1
        f.write_text(json.dumps(out, ensure_ascii=False))
        return out

    def label_table(self, table: str, ps: list[dict], guesses: list[tuple[str, str, float]], ask: list[int],
                    show_names: bool, context: str = "") -> tuple[str, dict[int, dict]]:
        """Returns (table_domain, {column index: answer}). Empty dict when unavailable or on failure.

        Stage 1: one call per table -> what the table records and who the data subject is.
        Stage 2: one short call per unsure column, with the domain and every other column as context.
        (A single call that labels many columns at once made a 7B model mix columns up.)"""
        if not ask or not self.available():
            return "", {}
        cards = [column_card(i, p, None if i in ask else g, show_names) for i, (p, g) in enumerate(zip(ps, guesses))]
        d = self._ask(domain_prompt(table, cards, context), DOMAIN_SCHEMA) or {}
        domain = str(d.get("table_domain", ""))[:200]
        subject = str(d.get("data_subject", ""))[:60]
        if subject and subject.lower() not in domain.lower():
            domain = f"{domain} (subject: {subject})"
        answers = {}
        for i in ask:
            out = self._ask(column_prompt(table, domain, cards, i, context), COLUMN_SCHEMA)
            if out and out.get("privacy_role") in ROLES and out.get("subtype") in SUBTYPES:
                out["reason"] = str(out.get("evidence", ""))[:300]
                answers[i] = out
        return domain, answers
