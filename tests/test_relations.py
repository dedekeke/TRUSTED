"""Key and join discovery on small artificial tables (no real rows)."""
import pandas as pd

from privacy_tool.relations import discover


def tables(n_parent=100, n_child=300, shift=0):
    """a.x: visit key; b.y references it (shift > 0 points some rows outside the key); both share category z."""
    cats = [f"C{i:02d}" for i in range(25)]
    a = pd.DataFrame({"x": [f"V{i:05d}" for i in range(n_parent)], "z": [cats[i % 25] for i in range(n_parent)]})
    b = pd.DataFrame({"q": [f"L{i:06d}" for i in range(n_child)],
                      "y": [f"V{(i % n_parent) + (shift if i % 10 == 0 else 0):05d}" for i in range(n_child)],
                      "z": [cats[i % 25] for i in range(n_child)]})
    return {"a": a, "b": b}


def labels(rows):
    return pd.DataFrame([{"dataset": "", "table": t, "column": c, "privacy_role": r, "subtype": s,
                          "confidence": .9, "evidence": ""} for t, c, r, s in rows])


def pairs(result):
    return [(j["parent"], j["child"]) for j in result["joins"]]


def test_should_find_join_when_no_hints_and_meaningless_names():
    r = discover(tables())
    assert pairs(r) == [("a.x", "b.y")]


def test_should_report_full_coverage_and_no_orphans_for_clean_reference():
    j = discover(tables())["joins"][0]
    assert (j["coverage"], j["orphans"], j["confidence"] > .9) == (1.0, 0, True)


def test_should_find_keys_of_both_tables():
    assert [k["column"] for k in discover(tables())["keys"]] == ["a.x", "b.q"]


def test_should_not_join_on_shared_category_column():
    # z has 25 distinct values (passes the distinct floor) and full overlap, but is not a key in either table
    assert all("z" not in ref for p in pairs(discover(tables())) for ref in p)


def test_should_not_join_on_few_distinct_values():
    t = {"a": pd.DataFrame({"k": [f"K{i:03d}" for i in range(50)]}),
         "b": pd.DataFrame({"r": [f"K{i % 10:03d}" for i in range(200)]})}  # only 10 distinct: category-like
    assert discover(t)["joins"] == []


def test_should_reject_join_below_coverage_threshold():
    # every 10th child row points past the key: 10% of the child's distinct values are orphans
    assert discover(tables(shift=1000))["joins"] == []


def test_should_not_treat_dates_as_keys():
    t = {"a": pd.DataFrame({"d": [f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(100)]})}
    assert discover(t)["keys"] == []


def test_should_pick_subject_key_ignoring_blanks():
    hetus = [f"0101{50 + i % 30:02d}-9{i % 30:02d}A" for i in range(120)]
    visits = pd.DataFrame({"v": [f"V{i:05d}" for i in range(120)],
                           "staff": [f"S{i % 5}" for i in range(120)],
                           "p": [h if i % 4 else "" for i, h in enumerate(hetus)]})
    lab = labels([("visits", "v", "record_key", "RECORD_ID"),
                  ("visits", "staff", "technical_identifier", "EMPLOYEE_ID"),
                  ("visits", "p", "direct_identifier", "NATIONAL_ID")])
    r = discover({"visits": visits}, lab)
    assert (r["subject_keys"], r["subject_key"]) == ({"visits": "visits.p"}, "visits.p")


def test_should_not_count_all_blank_column_as_subject():
    visits = pd.DataFrame({"v": [f"V{i:05d}" for i in range(50)], "p": [""] * 50})
    lab = labels([("visits", "p", "direct_identifier", "NATIONAL_ID")])
    assert discover({"visits": visits}, lab)["subject_key"] is None


def test_should_override_discovery_with_declared_join_and_flag_low_coverage():
    t = tables(shift=1000)
    t["b"]["w"] = t["a"]["x"].reindex(range(300)).fillna("").tolist()  # discovered: a.x -> b.w (full coverage)
    r = discover(t, declared={"joins": [["a.x", "b.y"], ["a.x", "b.missing"]]})
    j = {(x["parent"], x["child"]): x for x in r["joins"]}
    assert set(j) == {("a.x", "b.w"), ("a.x", "b.y"), ("a.x", "b.missing")}
    assert j[("a.x", "b.y")]["declared"] and j[("a.x", "b.y")]["coverage"] < .95
    assert [c.split(":")[0] for c in r["conflicts"]] == ["declared join a.x -> b.missing", "declared join a.x -> b.y"]


def test_should_use_declared_subject_key():
    r = discover(tables(), declared={"subject_key": "b.y"})
    assert (r["subject_key"], r["subject_keys"], r["conflicts"]) == ("b.y", {"b": "b.y"}, [])


def test_should_be_deterministic_regardless_of_table_order():
    t = tables()
    reordered = {"b": t["b"].iloc[::-1].reset_index(drop=True), "a": t["a"]}
    assert discover(t) == discover(t) and pairs(discover(reordered)) == pairs(discover(t))
