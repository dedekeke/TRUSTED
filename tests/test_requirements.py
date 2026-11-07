"""Requirement resolver on artificial tables and fake tasks (no real rows)."""
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from privacy_tool import requirements as rq

TABLES = {
    "visits": pd.DataFrame({"vid": ["v1", "v2"], "arrival": ["2025-01-01 10:00", "2025-01-02 11:00"],
                            "leave": ["2025-01-01 12:00", "2025-01-02 13:00"], "los": ["120", "120"],
                            "dob": ["1980-01-01", "1990-01-01"], "flag": ["0", "1"], "pid": ["p1", "p2"],
                            "noise": ["x", "y"]}),
    "labs": pd.DataFrame({"vid": ["v1", "v2"], "code": ["A", "B"], "value": ["1", "2"]}),
}


def task(needs, table="visits", fn=None, id="T1"):
    return SimpleNamespace(id=id, table=table, needs=needs, fn=fn or (lambda o, p: {"score": 1.0}))


def parse(needs, table="visits"):
    return rq.parse_needs(task(needs, table), TABLES)


def test_should_put_pipe_alternatives_in_any_of():
    assert parse(["flag|pid"])["any_of"] == [["visits.flag", "visits.pid"]]


def test_should_keep_plus_alternative_as_joined_refs():
    assert parse(["los|arrival+leave"])["any_of"] == [["visits.los", "visits.arrival+visits.leave"]]


def test_should_require_both_sides_of_plus():
    assert parse(["dob+arrival"])["required"] == ["visits.dob", "visits.arrival"]


def test_should_resolve_qualified_and_unqualified_names():
    p = parse(["labs.vid", "visits.vid", "code"], table="labs")
    assert p["required"] == ["labs.vid", "visits.vid", "labs.code"]


def test_should_fall_back_to_a_table_the_needs_name():
    assert parse(["labs.vid", "dob"], table="labs")["required"] == ["labs.vid", "visits.dob"]


def test_should_apply_prefix_to_slash_list():
    assert parse(["labs.code/value"])["required"] == ["labs.code", "labs.value"]


def test_should_map_time_of_day_hint_to_hour():
    assert parse(["arrival (time of day)"])["precision"] == {"visits.arrival": "hour"}


def test_should_warn_and_ignore_informal_token():
    p = parse(["vitals", "flag"])
    assert (p["required"], len(p["warnings"])) == (["visits.flag"], 1)


def test_should_parse_k_and_l_targets_from_text():
    assert rq.parse_targets("k>=5 on (a, b); l ≥ 2 on c") == {"k": 5, "l": 2}


def test_should_mark_column_required_when_task_becomes_unanswerable():
    fn = lambda o, p: {"score": 1.0 if "dob" in p["visits"].columns else None}
    assert rq.probe_task(task([], fn=fn), TABLES, ["visits"])["required"] == ["visits.dob"]


def test_should_mark_column_required_only_when_drop_exceeds_tolerance():
    fn = lambda o, p: {"score": {"flag": 0.9, "pid": 0.97}.get(next(iter(set(o["visits"]) - set(p["visits"])), ""), 1.0)}
    p = rq.probe_task(task([], fn=fn), TABLES, ["visits"], tolerance=0.05)
    assert (p["required"], p["affected"]) == (["visits.flag"], {"visits.flag": 0.9, "visits.pid": 0.97})


def test_should_record_task_exception_as_warning():
    def fn(o, p):
        if "noise" not in p["visits"].columns:
            raise KeyError("noise")
        return {"score": 1.0}
    p = rq.probe_task(task([], fn=fn), TABLES, ["visits"])
    assert (p["required"], len(p["warnings"])) == (["visits.noise"], 1)


@pytest.fixture
def fake_scenario(monkeypatch):
    needs_join = lambda o, p: {"score": 1.0 if {"vid"} <= set(p["labs"]) and "vid" in p["visits"] else None}
    tasks = [task(["labs.vid", "visits.vid"], table="labs", fn=needs_join, id="J"),
             task(["flag|pid", "arrival (time of day)"], fn=lambda o, p: {"score": 1.0}, id="A"),
             task(["noise"], id="unused")]
    scen = {"id": "X-S1", "dataset": "x", "trust_level": "controlled_research", "utility_requirements": ["J", "A"],
            "suggested_privacy_targets": "k>=5 on (a, b)"}
    monkeypatch.setattr(rq, "get_scenario", lambda sid, root: scen if sid == "X-S1" else None)
    monkeypatch.setattr(rq, "all_tasks", lambda domains: tasks)


def test_should_resolve_scenario_from_parsing_and_probing(fake_scenario):
    r = rq.from_scenario("X-S1", TABLES, "/nowhere")
    assert ({k: r[k] for k in ("required", "any_of", "precision", "joins", "targets")} ==
            {"required": {"labs.vid": ["J"], "visits.vid": ["J"], "visits.arrival": ["A"]},
             "any_of": [["visits.flag", "visits.pid"]], "precision": {"visits.arrival": "hour"},
             "joins": [{"columns": ["labs.vid", "visits.vid"], "tasks": ["J"]}], "targets": {"k": 5}})


def test_should_raise_for_unknown_scenario(fake_scenario):
    with pytest.raises(ValueError, match="unknown scenario"):
        rq.from_scenario("NOPE", TABLES, "/nowhere")


def test_no_purpose_shape():
    r = rq.no_purpose("public", "x")
    assert (r["source"], r["trust_level"], r["required"], r["tasks"], r["warnings"]) == (
        "none", "public", {}, [], [rq.NO_PURPOSE_WARNING])


def test_should_have_same_keys_for_all_sources(fake_scenario):
    keys = set(rq.from_scenario("X-S1", TABLES, "/nowhere", probe=False))
    assert keys == set(rq.no_purpose()) == set(rq.from_spec(rq.Path(rq.__file__).parent / "examples/health_s1_spec.json"))


def write(tmp_path, spec):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec))
    return p


BASE = {"dataset": "d", "trust_level": "contractual", "required": [{"column": "t.a", "precision": "hour", "task": "q"}]}


def test_should_load_valid_spec(tmp_path):
    r = rq.from_spec(write(tmp_path, {**BASE, "joins": [["t.a", "u.a"]], "subject_key": "t.a"}))
    assert (r["required"], r["precision"], r["joins"][0]["columns"], r["subject_key"]) == (
        {"t.a": ["q"]}, {"t.a": "hour"}, ["t.a", "u.a"], "t.a")


def test_should_load_example_spec():
    r = rq.from_spec(rq.Path(rq.__file__).parent / "examples/health_s1_spec.json")
    assert r["precision"] == {"ed_visits.arrival_ts": "hour"}


@pytest.mark.parametrize("change, message", [
    ({"extra": 1}, "unknown keys"),
    ({"trust_level": "secret"}, "unknown trust_level"),
    ({"required": [{"column": "nodot"}]}, "not a 'table.column'"),
    ({"required": [{"column": "t.a", "precision": "fortnight"}]}, "precision"),
    ({"required": [{"column": "t.a", "colour": "x"}]}, "unknown keys"),
    ({"joins": [["t.a"]]}, r"\[ref, ref\]"),
    ({"joins": [["t.a", "t.b"]]}, "two different tables"),
    ({"any_of": [["t.a"]]}, "at least two"),
    ({"subject_key": "bad ref"}, "not a 'table.column'"),
    ({"targets": {"k": 0}}, "positive integer"),
])
def test_should_reject_invalid_spec(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        rq.from_spec(write(tmp_path, {**BASE, **change}))


def test_should_reject_missing_required_key(tmp_path):
    with pytest.raises(ValueError, match="missing required key 'trust_level'"):
        rq.from_spec(write(tmp_path, {"dataset": "d", "required": []}))
