"""Selector behaviour on small artificial inputs (no real rows)."""
import json

import pandas as pd

from privacy_tool.select import confirm, render, select


def lab(table, column, role, subtype, conf=0.95, evidence="test; person table"):
    return {"dataset": "d", "table": table, "column": column, "privacy_role": role, "subtype": subtype,
            "confidence": conf, "evidence": evidence}


def inputs():
    tables = {
        "visits": pd.DataFrame({"vid": ["V1", "V2"], "pid": ["010180-901A", "020290-902B"], "dob": ["1980-01-01", "1990-02-02"],
                                "arrival": ["2025-01-01 10:00", "2025-01-02 11:00"], "city": ["Turku", "Salo"],
                                "name": ["Anna Virtanen", "Mikko Laine"], "extra": ["x", "y"]}),
        "labs": pd.DataFrame({"lab": ["L1", "L2"], "vid": ["V1", "V2"], "code": ["CRP", "HB"], "ts": ["2025-01-01", "2025-01-02"]}),
        "notes": pd.DataFrame({"nid": ["N1"], "text": ["Anna Virtanen visited"]}),
    }
    labels = pd.DataFrame([
        lab("visits", "vid", "record_key", "RECORD_ID"), lab("visits", "pid", "direct_identifier", "NATIONAL_ID"),
        lab("visits", "dob", "quasi_identifier", "BIRTH_DATE"), lab("visits", "arrival", "quasi_identifier", "TIMESTAMP"),
        lab("visits", "city", "quasi_identifier", "MUNICIPALITY"), lab("visits", "name", "direct_identifier", "PERSON_NAME"),
        lab("visits", "extra", "non_sensitive", "CATEGORY", 0.4),
        lab("labs", "lab", "record_key", "RECORD_ID", evidence="test"), lab("labs", "vid", "technical_identifier", "OTHER", evidence="test"),
        lab("labs", "code", "non_sensitive", "CATEGORY", 0.9, "test"), lab("labs", "ts", "non_sensitive", "DATE", 0.9, "test"),
        lab("notes", "nid", "record_key", "RECORD_ID"), lab("notes", "text", "free_text", "FREE_TEXT"),
    ])
    relations = {"keys": [{"column": "visits.vid"}, {"column": "labs.lab"}, {"column": "notes.nid"}],
                 "joins": [{"parent": "visits.vid", "child": "labs.vid", "coverage": 1.0, "orphans": 0}],
                 "subject_keys": {"visits": "visits.pid", "labs": "visits.pid"}, "subject_key": "visits.pid"}
    requirements = {"source": "scenario", "scenario": "T-S1", "dataset": "d", "trust_level": "controlled_research",
                    "targets": {"k": 5}, "required": {"visits.city": ["U1"], "labs.code": ["U2"], "visits.dob": ["U3"],
                                                      "visits.arrival": ["U3", "U4"]},
                    "any_of": [[["visits.readmit"], ["visits.pid"]]], "precision": {"visits.arrival": "hour"},
                    "joins": [{"columns": ["visits.vid", "labs.vid"], "tasks": ["U2"], "kind": "same_name"}],
                    "warnings": []}
    return tables, labels, relations, requirements


def by_ref(plan):
    return {f"{c['table']}.{c['column']}": c for c in plan["columns"]}


def test_complete_plan_one_decision_per_column():
    tables, labels, rel, req = inputs()
    plan = select(tables, labels, rel, req)
    assert plan["status"] == "ready_for_transform", plan["errors"]
    released = [t for t, d in plan["tables"].items() if d["action"] == "RELEASE"]
    assert sorted(released) == ["labs", "visits"] and plan["tables"]["notes"]["action"] == "WITHHOLD"
    assert {f"{c['table']}.{c['column']}" for c in plan["columns"]} == {f"{t}.{c}" for t in released for c in tables[t].columns}
    assert all(c["reason"] for c in plan["columns"])
    assert plan["tables"]["visits"]["record_key"] == "vid"


def test_join_shares_domain_and_identifiers_never_kept():
    tables, labels, rel, req = inputs()
    c = by_ref(select(tables, labels, rel, req))
    assert c["visits.vid"]["action"] == c["labs.vid"]["action"] == "HMAC"
    assert c["visits.vid"]["params"]["domain"] == c["labs.vid"]["params"]["domain"]
    assert c["visits.pid"]["action"] == "HMAC"  # any_of: the only usable alternative
    assert c["visits.pid"]["params"]["domain"] != c["visits.vid"]["params"]["domain"]
    assert c["visits.name"]["action"] == "DROP"


def test_age_derived_at_event_and_dob_dropped():
    tables, labels, rel, req = inputs()
    plan = select(tables, labels, rel, req)
    d = plan["derived"][0]
    assert d["column"] == "age" and d["sources"] == ["dob", "arrival"] and d["method"] == "derive_age_band"
    assert by_ref(plan)["visits.dob"]["action"] == "DROP"
    assert by_ref(plan)["visits.arrival"]["method"] == "floor_hour"


def test_minimisation_and_low_confidence():
    tables, labels, rel, req = inputs()
    plan = select(tables, labels, rel, req)
    assert by_ref(plan)["visits.extra"]["action"] == "DROP"
    assert "visits.extra" in {r["column"] for r in plan["review_queue"]}


def test_person_context_crosses_joins():
    tables, labels, rel, req = inputs()
    c = by_ref(select(tables, labels, rel, req))
    assert c["labs.ts"]["privacy_role"] == "quasi_identifier"


def test_blocks_missing_or_uncertain_required_columns():
    tables, labels, rel, req = inputs()
    req["required"]["visits.gone"] = ["U9"]
    plan = select(tables, labels, rel, req)
    assert plan["status"] == "blocked" and any("visits.gone" in e for e in plan["errors"])
    tables, labels, rel, req = inputs()
    labels.loc[labels.column == "code", "confidence"] = 0.4
    plan = select(tables, labels, rel, req)
    assert plan["status"] == "blocked" and any("confirm" in e for e in plan["errors"])
    fixed = confirm(labels, pd.DataFrame([{"table": "labs", "column": "code", "privacy_role": "non_sensitive",
                                           "subtype": "CATEGORY"}]))
    assert select(tables, fixed, rel, req)["status"] == "ready_for_transform"


def test_any_of_without_usable_alternative_blocks():
    tables, labels, rel, req = inputs()
    req["any_of"] = [["visits.readmit", "visits.other+visits.more"]]  # legacy string form
    assert select(tables, labels, rel, req)["status"] == "blocked"


def test_public_required_sensitive_escalates():
    tables, labels, rel, req = inputs()
    labels.loc[labels.column == "code", ["privacy_role", "subtype"]] = ["sensitive_attribute", "HEALTH_DATA"]
    req["trust_level"] = "public"
    plan = select(tables, labels, rel, req)
    assert plan["status"] == "blocked" and any("aggregate" in e for e in plan["errors"])


def test_deterministic_and_no_raw_values():
    tables, labels, rel, req = inputs()
    a, b = select(tables, labels, rel, req), select(tables, labels, rel, req)
    text = json.dumps(a) + render(a)
    assert json.dumps(a) == json.dumps(b)
    for raw in ("010180-901A", "Anna Virtanen", "Turku", "V1"):
        assert raw not in text


def test_unconfirmed_same_name_join_does_not_share_domain():
    tables, labels, rel, req = inputs()
    rel["joins"] = []
    plan = select(tables, labels, rel, req)
    c = by_ref(plan)
    assert c["labs.vid"]["action"] == "DROP" or c["labs.vid"]["params"]["domain"] != c["visits.vid"]["params"]["domain"]
    assert any("not treated as a join" in w for w in plan["warnings"])
