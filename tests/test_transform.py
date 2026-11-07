"""Transformer contracts on small artificial tables."""
import pandas as pd
import pytest

from privacy_tool.transform import apply, apply_column, redact

KEY = b"test-key-not-secret"


def col(table, column, action, method=None, subtype="", **params):
    return {"table": table, "column": column, "action": action, "method": method, "subtype": subtype, "params": params}


def tables():
    visits = pd.DataFrame({
        "vid": ["V1", "V2", "V3", "V4"],
        "pid": ["010180-901A", "010180-901A", "", "020290-902B"],
        "dob": ["1980-01-01", "1980-01-01", "2000-06-30", "1990-02-02"],
        "arrival": ["2025-12-28 23:59:00", "2025-03-01 10:15:00", "not a time", "2025-06-30 00:01:00"],
        "icd": ["J18.9", "S52.5", "Q99.9", ""],
        "name": ["Anna Virtanen", "Anna Virtanen", "Mikko Laine", "Liisa Koski"],
        "note": ["Anna Virtanen called 040 1234567", "pain", "", "seen 3.2.2025"],
    })
    labs = pd.DataFrame({"lab": ["L1", "L2", "L3"], "vid": ["V2", "V1", "V9"], "value": ["5", "<3", "120"]})
    return {"visits": visits, "labs": labs}


def plan():
    return {
        "release_id": "TEST-S1/recipient",
        "status": "ready_for_transform",
        "tables": {"visits": {"action": "RELEASE", "record_key": "vid"}, "labs": {"action": "RELEASE", "record_key": "lab"},
                   "notes": {"action": "WITHHOLD"}},
        "columns": [
            col("visits", "vid", "HMAC", "hmac_sha256", "RECORD_ID", domain="visit"),
            col("visits", "pid", "HMAC", "hmac_sha256", "NATIONAL_ID", domain="patient"),
            col("visits", "dob", "DROP", subtype="BIRTH_DATE"),
            col("visits", "arrival", "GENERALISE", "floor_hour", "TIMESTAMP"),
            col("visits", "icd", "GENERALISE", "diagnosis_group", "DIAGNOSIS_CODE"),
            col("visits", "name", "DROP", subtype="PERSON_NAME"),
            col("visits", "note", "REDACT", "redact_spans", "FREE_TEXT", profile="default"),
            col("labs", "lab", "DROP", subtype="RECORD_ID"),
            col("labs", "vid", "HMAC", "hmac_sha256", "RECORD_ID", domain="visit"),
            col("labs", "value", "KEEP", subtype="MEASUREMENT"),
        ],
        "derived": [{"table": "visits", "column": "age", "sources": ["dob", "arrival"], "method": "derive_age_band",
                     "params": {"width": 10, "top": 80}}],
    }


def test_join_tokens_match_and_blanks_stay_blank():
    out, _ = apply(tables(), plan(), KEY)
    v, l = out["visits"], out["labs"]
    assert set(l.vid[:2]) <= set(v.vid) and l.vid[2] not in set(v.vid)  # join kept, orphan stays orphan
    assert v.pid[0] == v.pid[1] and v.pid[2] == "" and v.pid[0] != v.pid[3]
    assert "V1" not in set(v.vid) and len(v.vid[0]) == 32
    other = apply(tables(), {**plan(), "release_id": "OTHER/recipient"}, KEY)[0]
    assert other["visits"].vid[0] != v.vid[0]  # tokens are scoped to the release


def test_floor_hour_keeps_date_week_and_hhmm_text():
    out, stats = apply(tables(), plan(), KEY)
    a = out["visits"].arrival
    assert a[0] == "2025-12-28 23:00" and a[3] == "2025-06-30 00:00"
    assert a[2] == "" and stats["blanked"]["visits.arrival"] == 1  # unparseable -> blank, counted


def test_age_derived_from_original_dates_before_dropping():
    out, _ = apply(tables(), plan(), KEY)
    v = out["visits"]
    assert "dob" not in v and "name" not in v
    assert v.age[0] == "40-49" and v.age[3] == "30-39" and v.age[2] == ""  # unparseable event date -> blank
    assert list(v.columns)[-1] == "age"


def test_diagnosis_groups_and_unmapped_blank():
    out, stats = apply(tables(), plan(), KEY)
    assert list(out["visits"].icd) == ["respiratory", "injury", "", ""]
    assert stats["blanked"]["visits.icd"] == 1


def test_redaction_typed_placeholders():
    out, _ = apply(tables(), plan(), KEY)
    note = out["visits"].note
    assert "Anna" not in note[0] and "[PERSON]" in note[0] and "[PHONE]" in note[0]
    assert note[3] == "seen [DATE]"
    assert redact("Contact maija.m@example.com") == "Contact [EMAIL]"


def test_withheld_and_dropped_not_released():
    out, _ = apply(tables(), plan(), KEY)
    assert set(out) == {"visits", "labs"} and "lab" not in out["labs"]


def test_writes_fresh_dirs_with_private_rowmaps(tmp_path):
    out_dir, eval_dir = tmp_path / "protected", tmp_path / "evaluation"
    apply(tables(), plan(), KEY, out_dir, eval_dir)
    rm = pd.read_csv(eval_dir / "rowmap_visits.csv", dtype=str)
    assert list(rm.original_record_id) == ["V1", "V2", "V3", "V4"] and list(rm.protected_row) == ["0", "1", "2", "3"]
    assert not list(out_dir.glob("rowmap_*"))
    with pytest.raises(FileExistsError):
        apply(tables(), plan(), KEY, out_dir)


def test_fail_closed():
    with pytest.raises(ValueError):
        apply(tables(), plan(), b"")
    with pytest.raises(ValueError):
        apply(tables(), {**plan(), "status": "blocked"}, KEY)
    with pytest.raises(ValueError):
        apply_column(pd.Series(["a"]), col("t", "c", "GENERALISE", "magic"), KEY, "x")


def test_numeric_and_rare_methods():
    s = pd.Series(["1", "2", "2", "3", "", "100"])
    assert list(apply_column(s, col("t", "c", "GENERALISE", "merge_rare", min_count=2), KEY, "x")[0]) == \
        ["other", "2", "2", "other", "", "other"]
    assert list(apply_column(pd.Series(["12345", ""]), col("t", "c", "GENERALISE", "postcode_prefix", digits=3), KEY, "x")[0]) == ["123", ""]
    assert list(apply_column(pd.Series(["37.25", "x"]), col("t", "c", "GENERALISE", "round_numeric", step=0.5), KEY, "x")[0]) == ["37", ""]
