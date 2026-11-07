"""Selector behaviour on small artificial inputs (no real rows)."""
import json

import pandas as pd
import pytest

from server.select.relations import discover
from server.select.select import confirm, render, select


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
    assert plan["status"] == "blocked" and any("relations found no join" in e for e in plan["errors"])
    req["joins"][0]["columns"] = ["visits.arrival", "labs.ts"]  # non-identifier name match: warn, don't join
    plan = select(tables, labels, rel, req)
    assert any("not treated as a join" in w for w in plan["warnings"])


def test_confirm_refuses_identifier_downgrade_and_bad_files():
    tables, labels, rel, req = inputs()
    down = pd.DataFrame([{"table": "visits", "column": "pid", "privacy_role": "non_sensitive", "subtype": "CATEGORY"}])
    with pytest.raises(ValueError, match="downgrade"):
        confirm(labels, down)
    assert confirm(labels, down, allow_downgrade=True).set_index("column").loc["pid", "detected_role"] == "direct_identifier"
    with pytest.raises(ValueError):
        confirm(labels, pd.concat([down, down]), allow_downgrade=True)
    with pytest.raises(ValueError):
        confirm(labels, down.drop(columns="subtype"))


@pytest.mark.parametrize("table,column", [("visits", "dob"), ("notes", "text"), ("visits", "pid")])
def test_protection_downgrade_requires_permission_and_warns(table, column):
    tables, labels, rel, req = inputs()
    ref = f"{table}.{column}"
    req["required"][ref] = ["U5"]
    down = pd.DataFrame([{"table": table, "column": column, "privacy_role": "non_sensitive", "subtype": "CATEGORY"}])
    with pytest.raises(ValueError, match="downgrade"):
        confirm(labels, down)
    fixed = confirm(labels, down, allow_downgrade=True)
    plan = select(tables, fixed, rel, req)
    assert plan["status"] == "ready_for_transform", plan["errors"]
    assert by_ref(plan)[ref]["action"] == "KEEP"
    assert any(ref in w and "downgrade explicitly allowed" in w for w in plan["warnings"])
    assert "downgrade explicitly allowed" in render(plan)


@pytest.mark.parametrize("table,column", [("visits", "dob"), ("notes", "text"), ("visits", "pid")])
def test_retained_protected_subtype_is_not_a_downgrade(table, column):
    tables, labels, rel, req = inputs()
    ref = f"{table}.{column}"
    req["required"][ref] = ["U5"]
    m = (labels.table == table) & (labels.column == column)
    unchanged = labels.loc[m, ["table", "column", "privacy_role", "subtype"]].copy()
    unchanged["privacy_role"] = "non_sensitive"
    fixed = confirm(labels, unchanged)
    plan = select(tables, fixed, rel, req)
    assert plan["status"] == "ready_for_transform", plan["errors"]
    assert not any("downgrade" in w for w in plan["warnings"])
    assert by_ref(plan)[ref]["action"] != "KEEP"
    down = unchanged.assign(subtype="CATEGORY")
    with pytest.raises(ValueError, match="downgrade"):
        confirm(fixed, down)


def test_discovered_relation_conflict_blocks_but_notice_only_warns():
    tables = {t: pd.DataFrame({"id": [f"V{i:03}" for i in range(20)]}) for t in ("a", "b", "c")}
    labels = pd.DataFrame([lab(t, "id", "record_key", "RECORD_ID", evidence="test") for t in tables])
    rel = discover(tables, labels, {"joins": [["a.id", "c.id"]]})
    assert rel["conflicts"]
    rel["notices"].append("subject key was not declared")
    req = {"source": "spec", "dataset": "d", "trust_level": "controlled_research",
           "joins": [{"columns": ["a.id", "c.id"], "tasks": ["U1"], "kind": "declared"}]}
    plan = select(tables, labels, rel, req)
    assert plan["status"] == "blocked"
    assert all(f"relations: {c}" in plan["errors"] for c in rel["conflicts"])
    assert "relations: subject key was not declared" in plan["warnings"]
    rel["conflicts"] = []
    plan = select(tables, labels, rel, req)
    assert plan["status"] == "ready_for_transform", plan["errors"]


def test_low_coverage_join_not_trusted_and_same_subtype_ids_share_domain():
    tables, labels, rel, req = inputs()
    rel["joins"][0]["coverage"] = 0.0
    plan = select(tables, labels, rel, req)
    assert plan["status"] == "blocked"
    tables, labels, rel, req = inputs()
    tables["visits"]["pid2"] = ["020290-902B", "010180-901A"]
    labels = pd.concat([labels, pd.DataFrame([lab("visits", "pid2", "direct_identifier", "NATIONAL_ID")])], ignore_index=True)
    req["required"]["visits.pid2"] = ["U5"]
    req["required"]["visits.pid"] = ["U5"]
    c = by_ref(select(tables, labels, rel, req))
    assert c["visits.pid"]["params"]["domain"] == c["visits.pid2"]["params"]["domain"]


def test_person_context_not_spread_to_unlinked_tables():
    tables, labels, rel, req = inputs()
    tables["weather"] = pd.DataFrame({"wid": ["W1", "W2"], "day": ["2025-01-01", "2025-01-02"]})
    labels = pd.concat([labels, pd.DataFrame([lab("weather", "wid", "record_key", "RECORD_ID", evidence="t"),
                                              lab("weather", "day", "non_sensitive", "DATE", evidence="t")])], ignore_index=True)
    req["required"]["weather.day"] = ["U6"]
    c = by_ref(select(tables, labels, rel, req))
    assert c["weather.day"]["privacy_role"] == "non_sensitive"
