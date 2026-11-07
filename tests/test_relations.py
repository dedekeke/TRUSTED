"""Key and join discovery on small artificial tables (no real rows)."""
import pandas as pd

from server.select import relations
from server.select.relations import NO_LABELS, discover


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


def test_should_be_deterministic_regardless_of_table_and_row_order():
    t = tables()
    reordered = {"b": t["b"].iloc[::-1].reset_index(drop=True), "a": t["a"].iloc[::-1].reset_index(drop=True)}
    assert discover(t) == discover(reordered)


def test_should_join_and_report_orphan_outside_parent_length_range():
    parent = [f"U{i:04d}" for i in range(500)]
    t = {"a": pd.DataFrame({"k": parent}), "b": pd.DataFrame({"r": parent * 2 + ["U99999"]})}
    assert [(j["parent"], j["child"], j["orphans"]) for j in discover(t)["joins"]] == [("a.k", "b.r", 1)]


def _measured(monkeypatch, t):
    calls = []
    real = relations._measure_join
    monkeypatch.setattr(relations, "_measure_join", lambda p, c: calls.append(1) or real(p, c))
    discover(t)
    return calls


def test_format_filter_alone_should_reject_other_shape(monkeypatch):
    t = tables()
    t["b"]["y"] = t["b"]["y"].str.replace("V", "V-")  # V-00001 vs V00001: shape differs
    assert _measured(monkeypatch, {"a": t["a"][["x"]], "b": t["b"][["y"]]}) == []


def test_format_filter_alone_should_reject_other_length(monkeypatch):
    t = {"a": pd.DataFrame({"k": [f"V{i:05d}" for i in range(100)]}),
         "b": pd.DataFrame({"r": [f"V{i:08d}" for i in range(100)]})}  # same shape, longer
    assert _measured(monkeypatch, t) == []


def test_should_not_join_integer_measure_to_dense_integer_key():
    t = {"a": pd.DataFrame({"id": [str(i) for i in range(1, 5001)]}),  # a row counter 1..N
         "b": pd.DataFrame({"duration_s": [str(1000 + i % 300) for i in range(400)]})}
    assert ("a.id" in [k["column"] for k in discover(t)["keys"]], discover(t)["joins"]) == (True, [])


def test_should_keep_declared_join_on_dense_integer_key():
    t = {"a": pd.DataFrame({"id": [str(i) for i in range(1, 501)]}),
         "b": pd.DataFrame({"a_id": [str(1 + i % 500) for i in range(800)]})}
    r = discover(t, declared={"joins": [["a.id", "b.a_id"]]})
    assert [(j["coverage"], j["declared"]) for j in r["joins"]] == [(1.0, True)]


def test_should_not_join_child_labelled_as_measure():
    t = {"a": pd.DataFrame({"id": [str(1000 + 7 * i) for i in range(500)]}),  # sparse integer key
         "b": pd.DataFrame({"n": [str(1000 + 7 * (i % 40)) for i in range(400)]})}
    lab = labels([("a", "id", "record_key", "RECORD_ID"), ("b", "n", "quasi_identifier", "OTHER")])
    assert (discover(t)["joins"] != [], discover(t, lab)["joins"]) == (True, [])


def test_should_not_take_names_or_spaced_values_as_keys():
    t = {"a": pd.DataFrame({"name": [f"Anna Person{i}" for i in range(50)],
                            "nick": [f"user{i}" for i in range(50)]})}
    lab = labels([("a", "name", "direct_identifier", "PERSON_NAME"), ("a", "nick", "direct_identifier", "PERSON_NAME")])
    assert (discover(t)["keys"][0]["column"], discover(t, lab)["keys"]) == ("a.nick", [])


def test_should_not_take_low_cardinality_labelled_column_as_subject():
    t = {"logs": pd.DataFrame({"app": [f"App{i % 3}" for i in range(100)]})}
    lab = labels([("logs", "app", "technical_identifier", "CUSTOMER_ID")])
    assert discover(t, lab)["subject_keys"] == {}


def visits_and_notes():
    visits = pd.DataFrame({"v": [f"V{i:05d}" for i in range(100)],
                           "p": [f"0101{50 + i % 40:02d}-9{i % 40:02d}A" for i in range(100)]})
    notes = pd.DataFrame({"n": [f"N{i:05d}" for i in range(300)], "v": [f"V{i % 100:05d}" for i in range(300)],
                          "staff": [f"S{i % 25:03d}" for i in range(300)]})
    lab = labels([("visits", "v", "record_key", "RECORD_ID"), ("visits", "p", "direct_identifier", "NATIONAL_ID"),
                  ("notes", "n", "record_key", "RECORD_ID"), ("notes", "v", "technical_identifier", "OTHER"),
                  ("notes", "staff", "technical_identifier", "EMPLOYEE_ID")])
    return {"visits": visits, "notes": notes}, lab


def test_should_inherit_subject_through_join_over_local_staff_id():
    t, lab = visits_and_notes()
    r = discover(t, lab)
    assert r["subject_paths"]["notes"] == ["notes.v", "visits.v", "visits.p"]
    assert (r["subject_keys"]["notes"], r["subject_key"]) == ("visits.p", "visits.p")


def test_should_fall_back_to_local_staff_id_without_reachable_subject():
    t, lab = visits_and_notes()
    assert discover({"notes": t["notes"]}, lab)["subject_paths"] == {"notes": ["notes.staff"]}


def test_should_flag_declared_subject_key_problems():
    t, lab = visits_and_notes()
    conflicts = lambda want: discover(t, lab, {"subject_key": want})["conflicts"]
    assert conflicts("visits.p") == []
    assert conflicts("visits.nope") == ["declared subject key visits.nope contradicts discovered visits.p",
                                        "declared subject key visits.nope: column not found"]
    assert "declared subject key visits.v: values do not repeat across rows" in conflicts("visits.v")
    assert conflicts("notes.staff") == ["declared subject key notes.staff contradicts discovered visits.p"]


def test_should_notice_missing_labels():
    r = discover(tables())
    assert (r["subject_keys"], r["notices"]) == ({}, [NO_LABELS])


def test_should_take_account_name_as_lowest_subject_tier():
    upns = [f"{n}.{m}@corp.example" for n in "abcde" for m in ["anna", "ville", "liisa", "matti", "eero"]]
    logs = pd.DataFrame({"upn": [upns[i % 25] for i in range(100)],
                         "cust": [f"C{i % 30:03d}" for i in range(100)]})
    lab = labels([("logs", "upn", "direct_identifier", "EMAIL"), ("logs", "cust", "technical_identifier", "CUSTOMER_ID")])
    assert discover({"logs": logs}, lab)["subject_keys"] == {"logs": "logs.cust"}
    assert discover({"logs": logs[["upn"]]}, lab)["subject_keys"] == {"logs": "logs.upn"}


def test_should_take_own_person_key_over_repeating_manager_email():
    upns = [f"user{i}@corp.example" for i in range(60)]
    identity = pd.DataFrame({"emp": [f"E{i:04d}" for i in range(60)], "upn": upns,
                             "manager": [upns[i % 6] for i in range(60)]})
    lab = labels([("identity", "emp", "technical_identifier", "EMPLOYEE_ID"),
                  ("identity", "upn", "direct_identifier", "EMAIL"), ("identity", "manager", "direct_identifier", "EMAIL")])
    assert discover({"identity": identity}, lab)["subject_paths"] == {"identity": ["identity.upn"]}


def test_should_keep_repeating_owner_over_card_key():
    cards = pd.DataFrame({"card": [f"K{i:05d}" for i in range(90)], "cust": [f"C{i % 30:04d}" for i in range(90)]})
    lab = labels([("cards", "card", "technical_identifier", "CARD_ID"),
                  ("cards", "cust", "technical_identifier", "CUSTOMER_ID")])
    assert discover({"cards": cards}, lab)["subject_keys"] == {"cards": "cards.cust"}


def test_should_keep_national_id_subject_when_some_values_carry_a_prefix():
    ids = [f"0101{50 + i % 40:02d}-9{i % 40:02d}A" for i in range(160)]
    t = pd.DataFrame({"c05": [f"HETU {v}" if i % 4 == 0 else v for i, v in enumerate(ids)],
                      "c09": [f"p{i % 30}@mail.example" for i in range(160)]})
    lab = labels([("t", "c05", "direct_identifier", "NATIONAL_ID"), ("t", "c09", "direct_identifier", "EMAIL")])
    assert discover({"t": t}, lab)["subject_keys"] == {"t": "t.c05"}


def test_should_inherit_subject_over_local_author_email():
    t, lab = visits_and_notes()
    t["notes"] = t["notes"].drop(columns="staff").assign(author=[f"doc{i % 25}@h.example" for i in range(300)])
    lab = pd.concat([lab, labels([("notes", "author", "direct_identifier", "EMAIL")])])
    assert discover(t, lab)["subject_paths"]["notes"] == ["notes.v", "visits.v", "visits.p"]


def test_should_keep_local_account_name_that_is_itself_the_join_child():
    upns = [f"user{i}@corp.example" for i in range(60)]
    t = {"identity": pd.DataFrame({"upn": upns}), "logs": pd.DataFrame({"upn": [upns[i % 60] for i in range(240)]})}
    lab = labels([("identity", "upn", "direct_identifier", "EMAIL"), ("logs", "upn", "direct_identifier", "EMAIL")])
    r = discover(t, lab)
    assert (r["subject_paths"], r["subject_key"]) == ({"identity": ["identity.upn"], "logs": ["logs.upn"]}, "logs.upn")


def energy_like(n=120):
    """customers: one row per person (hetu sometimes blank), meter key; readings repeat the meter id."""
    customers = pd.DataFrame({"customer_id": [f"C{i:05d}" for i in range(n)],
                              "metering_point_id": [f"6430000000{i:08d}" for i in range(n)],
                              "hetu": ["" if i % 9 == 0 else f"0101{i:02d}-9{i:02d}X" for i in range(n)]})
    readings = pd.DataFrame({"reading_id": [f"R{i:07d}" for i in range(n * 5)],
                             "metering_point_id": [f"6430000000{i % n:08d}" for i in range(n * 5)]})
    lab = labels([("customers", "customer_id", "record_key", "RECORD_ID"),
                  ("customers", "metering_point_id", "technical_identifier", "METER_ID"),
                  ("customers", "hetu", "direct_identifier", "NATIONAL_ID"),
                  ("readings", "reading_id", "record_key", "RECORD_ID"),
                  ("readings", "metering_point_id", "technical_identifier", "METER_ID")])
    return {"customers": customers, "readings": readings}, lab


def test_s1_person_rows_use_their_record_key_and_children_inherit_it():
    t, lab = energy_like()
    r = discover(t, lab)
    assert r["subject_keys"]["customers"] == "customers.customer_id"   # hetu 11% blank: not a key, yet rows are people
    assert r["subject_paths"]["readings"] == ["readings.metering_point_id", "customers.metering_point_id",
                                              "customers.customer_id"]


def test_s1_needs_a_person_identifier_unique_per_row():
    t, lab = energy_like()
    t["customers"]["hetu"] = "010101-901X"                              # the same value everywhere: not one per person
    assert "customers" not in discover(t, lab)["subject_keys"]


def test_s2_licence_plates_are_subjects():
    plates = [f"ABC-{i % 60:03d}" for i in range(300)]
    t = {"parking": pd.DataFrame({"event_id": [f"E{i:05d}" for i in range(300)], "plate": plates})}
    lab = labels([("parking", "event_id", "record_key", "RECORD_ID"),
                  ("parking", "plate", "direct_identifier", "LICENSE_PLATE")])
    assert discover(t, lab)["subject_keys"] == {"parking": "parking.plate"}


def test_s3_adopts_only_confident_complete_detect_suggestions_for_unresolved_tables():
    rel = {"subject_paths": {"a": ["a.x"]}, "subject_keys": {"a": "a.x"}, "subject_key": "a.x", "notices": []}
    sug = [{"table": "a", "column": "y", "confidence": .99, "needs_review": False, "non_blank_share": 1.0},
           {"table": "b", "column": "p", "confidence": .95, "needs_review": False, "non_blank_share": .22},
           {"table": "b", "column": "q", "confidence": .92, "needs_review": False, "non_blank_share": .99},
           {"table": "c", "column": "r", "confidence": .99, "needs_review": True, "non_blank_share": 1.0}]
    out = relations.adopt_detect_subjects(rel, sug)
    assert out["subject_keys"] == {"a": "a.x", "b": "b.q"}             # a kept; b.p too sparse; c under review
    assert any(n.startswith("subject_adopted: b.q") for n in out["notices"])
