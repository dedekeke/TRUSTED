"""Tier 3 (v3): the v2 table-context LLM, with value distributions instead of four random samples (fix B1).

v2 showed `readmit_30d` as "0, 0, 0, 0" and the model concluded "one unique value"; `disposition` as two values and
the model guessed "a location". Now low-cardinality columns are shown with every frequent value and its share
(home 76%, admitted_ward 19%, icu 1%, died <1%), numeric columns with their range and mean.
The table domain can be asked first and reused (the Art. 9-aware rules need it before the column calls).
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

from pets_detect.patterns import ROLES, SUBTYPES
from pets_detect_v2 import table_llm as T


def _pct(x: float) -> str:
    return "<1%" if x < .01 else f"{x:.0%}"


def distribution(p: dict) -> str | None:
    nonnull = max(p["n_rows"] * (1 - p["null_frac"]), 1)
    if p["n_unique"] <= 30 and p["top_values"]:
        vals = ", ".join(f"{str(v)[:30]} {_pct(c / nonnull)}" for v, c in p["top_values"])
        more = p["n_unique"] - len(p["top_values"])
        return vals + (f", … {more} more values" if more > 0 else "")
    return None


def column_card(i: int, p: dict, guess, show_names: bool) -> dict:
    card = T.column_card(i, p, guess, show_names)
    d = distribution(p)
    if d:
        card.pop("samples", None)
        card["values"] = d
    if p["num_min"] is not None and p["frac_numeric"] > .8:
        card["range"] = [round(p["num_min"], 2), round(p["num_max"], 2)]
        card["mean"] = round(p["num_mean"], 2)
        card["decimals"] = round(p["num_decimals"], 1)
    if p["null_frac"] > .05:
        card["empty"] = _pct(p["null_frac"])
    return card


def table_summary(cards: list[dict]) -> str:
    lines = []
    for c in cards:
        g = f" [{c['current_guess']}]" if "current_guess" in c else ""
        what = c.get("values") or ", ".join(c.get("samples", [])[:3])
        lines.append(f"- {c['name']}: {what[:160]}{g}")
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
        f"{T.ROLE_DEFS}\n\n{T.EXTRA_GUIDE}\n\n"
        + (f"Dataset description from the data owner: {context}\n" if context else "")
        + f"Table: {table}. It records: {domain}\n"
        f"Other columns of the table (for context):\n{table_summary([c for j, c in enumerate(cards) if j != i])}\n\n"
        f"COLUMN TO CLASSIFY: {json.dumps(target, ensure_ascii=False)}\n"
        "(`values` lists the frequent values with their share of rows.)\n\n"
        "First write `evidence`: what the values of THIS column are (quote one) and what they say about the data "
        "subject in this table. Then give privacy_role, subtype, art9 and confidence (your probability that the "
        "role is right)."
    )


class TableLLMv3(T.TableLLM):
    """workers: concurrent Ollama requests (DETECT_LLM_WORKERS, default 4). Ollama only runs them in parallel up to
    its OLLAMA_NUM_PARALLEL; beyond that they queue, so a high value is harmless. 1 = the old sequential behaviour.
    With workers > 1 the parent's calls / cache_hits counters can, rarely, miss an increment (they are only reported)."""

    def __init__(self, model=None, host=None, cache_dir=".cache/v3/llm", workers: int | None = None, **kw):
        super().__init__(model, host, cache_dir, **kw)
        self.workers = max(1, int(workers or os.environ.get("DETECT_LLM_WORKERS", 4)))

    def _map(self, fn, items: list) -> list:
        if self.workers == 1 or len(items) < 2:
            return [fn(x) for x in items]
        with ThreadPoolExecutor(min(self.workers, len(items))) as ex:
            return list(ex.map(fn, items))

    def map_tables(self, jobs: dict) -> dict:
        """Run {key: zero-arg call} concurrently, keep the keys."""
        keys = list(jobs)
        return dict(zip(keys, self._map(lambda k: jobs[k](), keys)))

    def domain(self, table: str, ps: list[dict], show_names: bool, context: str = "") -> str:
        if not self.available():
            return ""
        cards = [column_card(i, p, None, show_names) for i, p in enumerate(ps)]
        d = self._ask(domain_prompt(table, cards, context), T.DOMAIN_SCHEMA) or {}
        dom = str(d.get("table_domain", ""))[:200]
        subj = str(d.get("data_subject", ""))[:60]
        return f"{dom} (subject: {subj})" if subj and subj.lower() not in dom.lower() else dom

    def label_columns(self, table: str, ps: list[dict], guesses, ask: list[int], domain: str,
                      show_names: bool, context: str = "") -> dict[int, dict]:
        if not ask or not self.available():
            return {}
        cards = [column_card(i, p, None if i in ask else g, show_names) for i, (p, g) in enumerate(zip(ps, guesses))]
        answers = {}
        outs = self._map(lambda i: self._ask(column_prompt(table, domain, cards, i, context), T.COLUMN_SCHEMA), ask)
        for i, out in zip(ask, outs):
            if out and out.get("privacy_role") in ROLES and out.get("subtype") in SUBTYPES:
                out["reason"] = str(out.get("evidence", ""))[:300]
                answers[i] = out
        return answers
