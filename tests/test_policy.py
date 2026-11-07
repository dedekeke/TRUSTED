"""Rule matrix behaviour: hard constraints, ladder order, precision, review, escalation."""
import itertools

import pytest

from privacy_tool.policy import METHODS, TRUST_LEVELS, candidates, targets, violations

ROLES_SUBTYPES = [
    ("direct_identifier", s) for s in ("NATIONAL_ID", "EMAIL", "PHONE", "PERSON_NAME", "STREET_ADDRESS", "IBAN")
] + [
    ("technical_identifier", s) for s in ("IP_ADDRESS", "MAC_ADDRESS", "DEVICE_ID", "OTHER", "PATIENT_ID")
] + [("record_key", "RECORD_ID")] + [
    ("quasi_identifier", s) for s in ("BIRTH_DATE", "AGE", "SEX", "POSTCODE", "MUNICIPALITY", "TIMESTAMP", "DATE",
                                      "GPS_COORDINATE", "STREET_ADDRESS", "OCCUPATION", "URL")
] + [
    ("sensitive_attribute", s) for s in ("DIAGNOSIS_CODE", "MEASUREMENT", "FINANCIAL_DATA", "HEALTH_DATA", "OTHER")
] + [("free_text", "FREE_TEXT"), ("non_sensitive", "CATEGORY")]
IDS = {"direct_identifier", "technical_identifier", "record_key"}


def lab(role, sub, conf=0.9):
    return {"privacy_role": role, "subtype": sub, "confidence": conf}


def every_case():
    for (role, sub), t, req, join in itertools.product(ROLES_SUBTYPES, TRUST_LEVELS, (True, False), (True, False)):
        yield lab(role, sub), t, req, join


def methods(c):
    return [r["method"] for r in c["rungs"]]


def test_should_never_offer_keep_for_identifiers_in_any_context():
    for label, t, req, join in every_case():
        if label["privacy_role"] in IDS:
            assert "KEEP" not in [r["action"] for r in candidates(label, t, req, join)["rungs"]]


def test_should_produce_only_rungs_that_pass_violations_and_use_known_methods():
    for label, t, req, join in every_case():
        for r in candidates(label, t, req, join)["rungs"]:
            assert violations(label, r, t) == [], (label, t, r)
            assert r["method"] is None or r["method"] in METHODS


def test_should_number_levels_from_zero_in_order():
    for label, t, req, join in every_case():
        assert [r["level"] for r in candidates(label, t, req, join)["rungs"]] == list(range(len(candidates(label, t, req, join)["rungs"])))


def test_should_drop_unrequired_columns_except_non_sensitive():
    for role, sub in ROLES_SUBTYPES:
        actions = [r["action"] for r in candidates(lab(role, sub), "contractual", False)["rungs"]]
        assert actions == (["KEEP", "DROP"] if role == "non_sensitive" else ["DROP"])


def test_should_pseudonymise_identifiers_that_bind_a_join():
    for role, sub in ROLES_SUBTYPES:
        if role in IDS:
            assert methods(candidates(lab(role, sub), "public", False, in_join=True)) == ["hmac_sha256"]


def test_should_offer_ip_prefix_before_hmac_when_required_outside_a_join():
    assert methods(candidates(lab("technical_identifier", "IP_ADDRESS"), "internal", True)) == ["ipv4_prefix", "hmac_sha256"]


def test_should_order_time_ladders_finest_to_coarsest():
    ts = candidates(lab("quasi_identifier", "TIMESTAMP"), "contractual", True)
    assert methods(ts) == ["floor_hour", "date", "iso_week", "month"]
    assert methods(candidates(lab("quasi_identifier", "DATE"), "contractual", True)) == ["date", "iso_week", "month", "year"]


def test_should_widen_age_bands_down_the_ladder():
    for sub in ("AGE", "BIRTH_DATE"):
        widths = [r["params"]["width"] for r in candidates(lab("quasi_identifier", sub), "public", True)["rungs"]]
        assert widths == sorted(widths) and len(set(widths)) == len(widths)


def test_should_coarsen_postcodes_and_coordinates():
    pc = candidates(lab("quasi_identifier", "POSTCODE"), "public", True)["rungs"]
    assert pc[0]["action"] == "KEEP" and [r["params"]["digits"] for r in pc[1:]] == [3, 2]
    gps = candidates(lab("quasi_identifier", "GPS_COORDINATE"), "public", True)["rungs"]
    assert [r["params"]["digits"] for r in gps] == [3, 2, 1]


def test_should_allow_exact_diagnosis_only_internally():
    exact = {t: candidates(lab("sensitive_attribute", "DIAGNOSIS_CODE"), t, True)["rungs"][0]["action"] for t in TRUST_LEVELS}
    assert exact == {"internal": "KEEP", "contractual": "GENERALISE", "controlled_research": "GENERALISE", "public": "GENERALISE"}


def test_should_trim_rungs_coarser_than_precision_and_drop():
    c = candidates(lab("quasi_identifier", "TIMESTAMP"), "contractual", True, precision="date")
    assert methods(c) == ["floor_hour", "date"]
    assert methods(candidates(lab("non_sensitive", "CATEGORY"), "internal", False, precision="exact")) == [None]
    assert methods(candidates(lab("quasi_identifier", "AGE"), "public", True, precision=10)) == ["age_band", "age_band"]
    diag = candidates(lab("sensitive_attribute", "DIAGNOSIS_CODE"), "contractual", True, precision="group")
    assert methods(diag) == ["icd_3char", "diagnosis_group"]


def test_should_reject_precision_the_ladder_cannot_express():
    with pytest.raises(ValueError):
        candidates(lab("quasi_identifier", "DATE"), "internal", True, precision="hour")


def test_should_drop_low_confidence_columns_that_are_not_required():
    c = candidates(lab("non_sensitive", "CATEGORY", conf=0.45), "internal", False)
    assert c["needs_review"] and [r["action"] for r in c["rungs"]] == ["DROP"]


def test_should_keep_ladder_but_flag_review_for_low_confidence_required_columns():
    c = candidates(lab("quasi_identifier", "TIMESTAMP", conf=0.55), "internal", True)
    assert c["needs_review"] and methods(c)[0] == "floor_hour"


def test_should_escalate_required_sensitive_attributes_at_public_trust():
    for sub in ("DIAGNOSIS_CODE", "MEASUREMENT", "HEALTH_DATA"):
        c = candidates(lab("sensitive_attribute", sub), "public", True)
        assert c["escalate"] and c["rungs"]
        assert candidates(lab("sensitive_attribute", sub), "controlled_research", True)["escalate"] is None


def test_should_redact_free_text_below_public_and_drop_it_at_public():
    assert methods(candidates(lab("free_text", "FREE_TEXT"), "controlled_research", True)) == ["redact_spans"]
    pub = candidates(lab("free_text", "FREE_TEXT"), "public", True)
    assert [r["action"] for r in pub["rungs"]] == ["DROP"] and pub["escalate"]


def test_should_flag_required_street_address_for_review():
    c = candidates(lab("quasi_identifier", "STREET_ADDRESS"), "internal", True)
    assert c["needs_review"] and [r["action"] for r in c["rungs"]] == ["DROP"]


def test_should_reject_unknown_trust_level_and_role():
    with pytest.raises(ValueError):
        candidates(lab("quasi_identifier", "AGE"), "partner", True)
    with pytest.raises(ValueError):
        targets("secret")
    with pytest.raises(ValueError):
        candidates(lab("mystery", "AGE"), "internal", True)


def test_should_tighten_targets_with_trust_and_apply_overrides():
    assert targets("internal")["k"] < targets("contractual")["k"] < targets("public")["k"]
    assert targets("public")["free_text"] is False
    t = targets("contractual", {"k": 7})
    assert t["k"] == 7 and t["l"] == targets("contractual")["l"] and "max_suppression" in t


@pytest.mark.parametrize("label,rung,trust", [
    (lab("direct_identifier", "EMAIL"), {"action": "KEEP", "method": None, "params": {}}, "internal"),
    (lab("record_key", "RECORD_ID"), {"action": "KEEP", "method": None, "params": {}}, "internal"),
    (lab("quasi_identifier", "BIRTH_DATE"), {"action": "KEEP", "method": None, "params": {}}, "internal"),
    (lab("quasi_identifier", "BIRTH_DATE"), {"action": "GENERALISE", "method": "date", "params": {}}, "internal"),
    (lab("quasi_identifier", "TIMESTAMP"), {"action": "GENERALISE", "method": "round_numeric", "params": {"step": 3600}}, "internal"),
    (lab("non_sensitive", "CATEGORY"), {"action": "SHUFFLE", "method": None, "params": {}}, "internal"),
    (lab("non_sensitive", "CATEGORY"), {"action": "GENERALISE", "method": "bucketize", "params": {}}, "internal"),
    (lab("free_text", "FREE_TEXT"), {"action": "REDACT", "method": "redact_spans", "params": {}}, "public"),
    (lab("free_text", "FREE_TEXT"), {"action": "KEEP", "method": None, "params": {}}, "public"),
])
def test_should_catch_hand_made_bad_rungs(label, rung, trust):
    assert violations(label, rung, trust)
