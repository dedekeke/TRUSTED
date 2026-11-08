"""Transformer contracts on small artificial tables."""
import pandas as pd
import pytest

from server.select.transform import apply, apply_column, redact

KEY = b"test-key-not-secret"


ROLE = {"RECORD_ID": "record_key", "NATIONAL_ID": "direct_identifier", "BIRTH_DATE": "quasi_identifier",
        "TIMESTAMP": "quasi_identifier", "DIAGNOSIS_CODE": "sensitive_attribute", "PERSON_NAME": "direct_identifier",
        "FREE_TEXT": "free_text", "MEASUREMENT": "sensitive_attribute"}


def col(table, column, action, method=None, subtype="", **params):
    return {"table": table, "column": column, "action": action, "method": method, "subtype": subtype, "params": params,
            "privacy_role": ROLE.get(subtype, "non_sensitive"), "confidence": 0.95}


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
        "status": "measured_ok", "outcome": {"approved": True},
        "trust_level": "controlled_research", "targets": {"k": 5},
        "tables": {"visits": {"action": "RELEASE", "record_key": "vid"}, "labs": {"action": "RELEASE", "record_key": "lab"},
                   "notes": {"action": "WITHHOLD"}},
        "columns": [
            col("visits", "vid", "HMAC", "hmac_sha256", "RECORD_ID", domain="visit"),
            col("visits", "pid", "HMAC", "hmac_sha256", "NATIONAL_ID", domain="patient"),
            col("visits", "dob", "DROP", subtype="BIRTH_DATE"),
            col("visits", "arrival", "GENERALISE", "floor_hour", "TIMESTAMP"),
            col("visits", "icd", "GENERALISE", "diagnosis_group", "DIAGNOSIS_CODE", mapping="pets_eval.utility.health.diagnosis_group"),
            col("visits", "name", "DROP", subtype="PERSON_NAME"),
            col("visits", "note", "REDACT", "redact_spans", "FREE_TEXT", profile="typed_placeholders"),
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


def test_ipv4_prefix_under_hmac_action():
    out = apply_column(pd.Series(["10.1.2.3", "", "bad"]), col("t", "c", "HMAC", "ipv4_prefix"), KEY, "x")[0]
    assert list(out) == ["10.1.2.0", "", ""]


def test_generalisers_never_pass_raw_values_through():
    def run(vals, method, action="GENERALISE", **p):
        return list(apply_column(pd.Series(vals), col("t", "c", action, method, **p), KEY, "x")[0])
    assert run(["20100", "99", "FI-00100"], "postcode_prefix", digits=3) == ["201", "", ""]
    assert run(["J18.9", "Mikko Laine", ""], "icd_3char") == ["J18", "", ""]
    assert run(["J18.9", "x1"], "icd_chapter") == ["J", ""]
    assert run(["10.1.2.3", "host.0", "12345.0"], "ipv4_prefix") == ["10.1.2.0", "", ""]
    assert run(["1234567.85", "2.5"], "round_decimals", digits=1) == ["1234567.8", "2.5"]  # no exponent notation
    assert run(["34", "-3", "30-39", "80+"], "age_band", width=10, top=80) == ["30-39", "", "30-39", "80+"]
    assert run(["2025-12-29 08:00", "x"], "iso_week") == ["2026-W01", ""]
    assert run(["2025-12-29 08:00"], "month") == ["2025-12"] and run(["2025-12-29"], "year") == ["2025"]
    assert run(["a", "a", "b"], "suppress_rare", min_count=2) == ["a", "a", ""]
    clipped = run([str(i) for i in range(100)], "top_bottom_code", lower_q=.1, upper_q=.9)
    assert clipped[0] == clipped[5] and clipped[-1] == clipped[-5]


def test_fail_closed_plan_contracts(tmp_path):
    with pytest.raises(ValueError):
        apply_column(pd.Series(["1"]), col("t", "c", "HMAC", "hmac_sha256", domain=None), KEY, "x")
    with pytest.raises(ValueError):
        apply_column(pd.Series([1, 2]), col("t", "c", "HMAC", "hmac_sha256", domain="d"), KEY, "x")
    with pytest.raises(ValueError):
        apply(tables(), {**plan(), "release_id": ""}, KEY)
    with pytest.raises(ValueError):
        apply(tables(), {**plan(), "status": "draft"}, KEY)
    with pytest.raises(ValueError):
        apply(tables(), plan(), KEY, tmp_path / "out", tmp_path / "out" / "eval")
    bad = plan()
    bad["derived"][0]["column"] = "dob"
    with pytest.raises(ValueError):
        apply(tables(), bad, KEY)
    nokey = plan()
    nokey["tables"]["labs"]["record_key"] = None
    with pytest.raises(ValueError):
        apply(tables(), nokey, KEY, tmp_path / "p", tmp_path / "e")


def test_key_never_written(tmp_path):
    apply(tables(), plan(), KEY, tmp_path / "p", tmp_path / "e")
    for f in tmp_path.rglob("*.csv"):
        assert KEY.decode() not in f.read_text()


def test_redaction_addresses_daymonth_and_bad_checksum_ids():
    out = redact("Asuu Kangaspolku 6 A 1, 20100 Turku. Käynti 29.12. ja 010180-9999 tarkistettu")
    assert "Kangaspolku" not in out and "29.12." not in out and "010180-9999" not in out


def test_hand_edited_plan_is_rechecked():
    bad = plan()
    for c in bad["columns"]:
        if c["column"] == "pid":
            c.update(action="KEEP", method=None, params={})
    with pytest.raises(ValueError, match="rule matrix"):
        apply(tables(), bad, KEY)
    other = {**plan(), "input_fingerprint": "0" * 16}
    with pytest.raises(ValueError, match="fingerprint"):
        apply(tables(), other, KEY)
    t = tables()
    t["visits"]["new_col"] = "x"
    with pytest.raises(ValueError, match="without a decision"):
        apply(t, plan(), KEY)


@pytest.mark.parametrize('status,outcome', [('policy_valid', {}), ('target_unmet', {'approved': False}),
                                            ('budget_exhausted', {'approved': False}),
                                            ('measured_ok', {'approved': False})])
def test_only_approved_measured_ok_exports_by_default(tmp_path, status, outcome):
    unapproved = {**plan(), 'status': status, 'outcome': outcome}
    with pytest.raises(ValueError, match='unapproved_plan'):
        apply(tables(), unapproved, KEY, tmp_path / 'p', tmp_path / 'e')
    assert not (tmp_path / 'p').exists()
    _, stats = apply(tables(), unapproved, KEY, tmp_path / 'p', tmp_path / 'e', allow_unapproved=True)
    assert stats['release_gate'] == {'status': status, 'approved': False, 'allow_unapproved': True, 'plan_sha256': None}
    assert 'NOT AN APPROVED RELEASE' in (tmp_path / 'p' / 'NOT_APPROVED.txt').read_text()


def test_blocked_plan_never_exports_even_with_override():
    with pytest.raises(ValueError, match='fix its errors'):
        apply(tables(), {**plan(), 'status': 'blocked'}, KEY, allow_unapproved=True)


def test_transform_cli_checks_input_binding(tmp_path, monkeypatch, capsys):
    import json
    from server.select.__main__ import main
    from server.select.artifacts import provenance
    data = tmp_path / 'data'
    data.mkdir()
    for t, df in tables().items():
        df.to_csv(data / f'{t}.csv', index=False)
    p = {**plan(), 'provenance': provenance(data, None)}
    (data / 'labs.csv').write_text((data / 'labs.csv').read_text().replace('120', '121'))
    (tmp_path / 'plan.json').write_text(json.dumps(p))
    monkeypatch.setenv('PRIVACY_TOOL_HMAC_KEY', 'test-key')
    assert main(['transform', '--data', str(data), '--plan', str(tmp_path / 'plan.json'), '--out', str(tmp_path / 'o')]) == 2
    assert '[input_mismatch]' in capsys.readouterr().err and not (tmp_path / 'o').exists()


def test_should_derive_age_at_ref_date_instead_of_row_event():
    from server.actions import derive_age_band
    df = pd.DataFrame({"dob": ["1990-06-01"], "opened": ["2000-01-01"]})
    assert derive_age_band(df, "dob", "opened", width=10)[0] == "0-9"
    assert derive_age_band(df, "dob", "opened", width=10, ref_date="2025-12-31")[0] == "30-39"
