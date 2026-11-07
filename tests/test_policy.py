"""Policy contract checks using schema names only, never patient records."""

import ast
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from privacy_tool.policy import HEALTH_S1


def test_complete_source_schema_and_explanations():
    schemas = {
        "ed_visits": """visit_id patient_hetu patient_name date_of_birth sex phone
            home_address postcode municipality arrival_ts arrival_mode ambulance_unit
            triage chief_complaint icd10_primary icd10_secondary systolic_bp diastolic_bp
            heart_rate resp_rate temp_c spo2 pain_nrs attending_physician_id
            attending_physician_name discharge_ts los_minutes disposition readmit_30d""".split(),
        "lab_results": """lab_id visit_id test_code test_name value unit ref_range
            abnormal_flag sampled_ts""".split(),
    }
    assert set(HEALTH_S1["fields"]) == set(schemas)
    for table, columns in schemas.items():
        assert set(HEALTH_S1["fields"][table]) == set(columns)
    decisions = [d for fields in HEALTH_S1["fields"].values() for d in fields.values()]
    decisions += list(HEALTH_S1["withheld_tables"].values())
    decisions += list(HEALTH_S1["derived_fields"].values())
    decisions.append(HEALTH_S1["unknown_optional_field"])
    for decision in decisions:
        assert decision["action"] in {"KEEP", "DROP", "HMAC", "GENERALISE", "REDACT", "DERIVE", "WITHHOLD"}
        assert isinstance(decision["parameters"], dict)
        assert isinstance(decision["required_by"], list)
        assert decision["reason"].strip()


def test_bindings_joins_and_domain_isolation():
    fields = HEALTH_S1["fields"]
    for reference in HEALTH_S1["bindings"].values():
        table, column = reference.split(".")
        assert column in fields[table]
    for join in HEALTH_S1["joins"]:
        for side in ("parent", "child"):
            table, column = join[side].split(".")
            decision = fields[table][column]
            assert decision["action"] == "HMAC"
            assert decision["parameters"]["domain"] == join["domain"]
    patient_domain = fields["ed_visits"]["patient_hetu"]["parameters"]["domain"]
    visit_domain = fields["ed_visits"]["visit_id"]["parameters"]["domain"]
    assert patient_domain != visit_domain
    for name in (patient_domain, visit_domain):
        domain = HEALTH_S1["token_domains"][name]
        assert domain["algorithm"] == "HMAC-SHA-256"
        assert domain["token_hex_length"] == 32
        assert domain["context_fields"] == ["scenario", "recipient", "release", "domain"]
        assert domain["input_type"] == "string"
        assert domain["preserve_leading_zeros"] is True
        assert domain["missing"] == "preserve_missing_no_token"
        assert domain["key_env"]
    assert HEALTH_S1["token_domains"][patient_domain]["normalisation"] == "trim_whitespace_uppercase_check_character"
    assert HEALTH_S1["token_domains"][visit_domain]["normalisation"] == "identity"


def test_age_uses_original_sources_before_removal():
    age = HEALTH_S1["derived_fields"]["ed_visits.age"]
    parameters = age["parameters"]
    assert age["action"] == "DERIVE"
    assert parameters["sources"] == [HEALTH_S1["bindings"]["date_of_birth"], HEALTH_S1["bindings"]["arrival"]]
    assert parameters["source_stage"] == "original"
    assert parameters["parser"] == "pets_eval.parse.to_datetime"
    assert parameters["banding"] == "pets_eval.parse.to_age_band"
    assert parameters["invalid"] == "blank_and_count"
    assert HEALTH_S1["fields"]["ed_visits"]["date_of_birth"]["action"] == "DROP"
    order = HEALTH_S1["execution_order"]
    assert order.index("derive_age") < order.index("transform_fields")


def test_presets_keep_hour_format_and_explain_week_tradeoff():
    assert HEALTH_S1["default_preset"] == "research_hour"
    assert set(HEALTH_S1["presets"]) == {"research_hour", "research_week"}
    hour, week = (HEALTH_S1["presets"][name] for name in ("research_hour", "research_week"))
    for preset in (hour, week):
        assert preset["parameters"]["ed_visits.age"] == {"width": 10, "top": 80}
    arrival = hour["parameters"]["ed_visits.arrival_ts"]
    assert arrival == HEALTH_S1["fields"]["ed_visits"]["arrival_ts"]["parameters"]
    assert arrival["method"] == "floor_hour"
    late = datetime(2025, 12, 28, 23, 59)
    assert late.strftime(arrival["output_format"]) == "2025-12-28 23:00"
    assert hour["unsupported_tasks"] == []
    assert week["unsupported_tasks"] == ["H-U8"]
    assert any("H-U8" in warning for warning in week["warnings"])
    week_arrival = week["parameters"]["ed_visits.arrival_ts"]
    assert week_arrival["method"] == "iso_week"
    assert datetime(2025, 12, 29).strftime(week_arrival["output_format"]) == "2026-W01"


def test_minimisation_and_fail_closed_contracts():
    assert set(HEALTH_S1["withheld_tables"]) == {"clinical_notes", "published_weekly_stats"}
    assert all(d["action"] == "WITHHOLD" for d in HEALTH_S1["withheld_tables"].values())
    visits = HEALTH_S1["fields"]["ed_visits"]
    for column in ("patient_name", "phone", "home_address", "postcode", "attending_physician_id", "attending_physician_name"):
        assert visits[column]["action"] == "DROP"
    assert visits["chief_complaint"]["action"] == "REDACT"
    assert visits["icd10_primary"]["parameters"]["unmapped"] == "blank_and_count"
    assert HEALTH_S1["unknown_optional_field"]["action"] == "DROP"
    assert HEALTH_S1["unknown_required_field"] == "block_until_mapped_and_labelled"
    assert HEALTH_S1["lab_rows"] == {"filter": None, "preserve_order": True}
    assert HEALTH_S1["privacy_validation"] == "pending"


def test_policy_is_only_literal_data():
    path = Path(__file__).resolve().parents[1] / "privacy_tool" / "policy.py"
    module = ast.parse(path.read_text())
    assert len(module.body) == 2  # Module docstring and one literal policy.
    assert isinstance(module.body[1], ast.Assign)
    assert ast.literal_eval(module.body[1].value) == HEALTH_S1
    assert json.loads(json.dumps(HEALTH_S1)) == HEALTH_S1
