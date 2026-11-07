"""Rule matrix behaviour: hard constraints, ladder order, precision, review, escalation."""
import itertools

import pytest

from server.select import detect
from server.select.policy import TRUST_LEVELS, candidates, targets, violations

ROLES = ["direct_identifier", "technical_identifier", "record_key", "quasi_identifier", "sensitive_attribute",
         "free_text", "non_sensitive"]
# every subtype detect.py can emit
SUBTYPES = sorted(detect.DIRECT | detect.TECHNICAL | detect.PERSON_QI | detect.CONTEXT_QI | detect.ENTITY_IDS
                  | {"NATIONAL_ID", "URL", "DIAGNOSIS_CODE", "FINANCIAL_DATA", "RECORD_ID", "MEASUREMENT",
                     "FREE_TEXT", "CATEGORY", "OTHER", "ENTITY_ID"})
IDS = {"direct_identifier", "technical_identifier", "record_key"}
ID_SUBTYPES = detect.DIRECT | detect.TECHNICAL | detect.ENTITY_IDS | {"NATIONAL_ID", "RECORD_ID", "ENTITY_ID"}
REROUTED = ID_SUBTYPES | {"BIRTH_DATE", "STREET_ADDRESS"}  # handled by their subtype's own rules (DROP + review)


def lab(role, sub, conf=0.9):
    return {"privacy_role": role, "subtype": sub, "confidence": conf}


def keep():
    return {"action": "KEEP", "method": None, "params": {}}


def G(method, **params):
    return {"action": "GENERALISE", "method": method, "params": params}


def every_case(conf=0.9):
    for role, sub, t, req, join in itertools.product(ROLES, SUBTYPES, TRUST_LEVELS, (True, False), (True, False)):
        label = lab(role, sub, conf)
        yield label, t, req, join, candidates(label, t, req, join)


def actions(c):
    return [r["action"] for r in c["rungs"]]


def methods(c):
    return [r["method"] for r in c["rungs"]]


def with_domain(r):
    return {**r, "params": {**r["params"], "domain": "rel/x"}} if r["action"] == "HMAC" else r


# --- hard constraints across every role × subtype × trust × required × in_join

def test_should_never_keep_identifiers_whatever_role_the_label_claims():
    for label, t, req, join, c in every_case():
        if label["privacy_role"] in IDS or label["subtype"] in ID_SUBTYPES:
            assert "KEEP" not in actions(c), (label, t, req, join)


def test_should_only_offer_rungs_that_violations_accepts():
    for label, t, req, join, c in every_case():
        for r in c["rungs"]:
            assert violations(label, with_domain(r), t) == [], (label, t, req, join, r)


def test_should_only_derive_age_bands_from_birth_dates_in_any_role():
    for label, t, req, join, c in every_case():
        if label["subtype"] == "BIRTH_DATE":
            assert set(methods(c)) <= {"derive_age_band", None} and "KEEP" not in actions(c)


def test_should_release_no_row_level_sensitive_or_free_text_at_public():
    for label, t, req, join, c in every_case():
        if t == "public" and label["privacy_role"] in ("sensitive_attribute", "free_text") \
                and label["subtype"] not in REROUTED:
            assert actions(c) == ["DROP"], (label, req, join)
            assert req is False or c["escalate"]


def test_should_never_keep_low_confidence_columns():
    for label, t, req, join, c in every_case(conf=0.5):
        assert "KEEP" not in actions(c) and c["needs_review"] and actions(c)[-1] == "DROP"


# --- ladders and context

def test_should_drop_unrequired_columns_except_non_sensitive():
    for sub in ("AGE", "DIAGNOSIS_CODE", "FREE_TEXT", "CATEGORY"):
        for role in ("quasi_identifier", "sensitive_attribute", "free_text"):
            assert actions(candidates(lab(role, sub), "contractual", False)) == ["DROP"]
    assert actions(candidates(lab("non_sensitive", "CATEGORY"), "contractual", False)) == ["KEEP", "DROP"]


def test_should_pseudonymise_identifiers_that_bind_a_join():
    assert methods(candidates(lab("record_key", "RECORD_ID"), "public", False, in_join=True)) == ["hmac_sha256"]


def test_should_coarsen_ip_from_hmac_to_prefix_when_required_outside_a_join():
    c = candidates(lab("technical_identifier", "IP_ADDRESS"), "internal", True)
    assert [(r["action"], r["method"]) for r in c["rungs"]] == [("HMAC", "hmac_sha256"), ("GENERALISE", "ipv4_prefix")]
    assert methods(candidates(lab("technical_identifier", "IP_ADDRESS"), "internal", True, in_join=True)) == ["hmac_sha256"]


def test_should_never_keep_text_diagnoses_or_addresses_labelled_non_sensitive_at_public():
    for sub in ("FREE_TEXT", "DIAGNOSIS_CODE", "STREET_ADDRESS"):
        for req in (True, False):
            c = candidates(lab("non_sensitive", sub), "public", req)
            assert actions(c) == ["DROP"] and c["needs_review"], (sub, req)


def test_should_merge_rare_values_below_the_effective_k():
    lang = lab("quasi_identifier", "LANGUAGE")
    rungs = candidates(lang, "contractual", True, k=11)['rungs']
    assert [r['params']['min_count'] for r in rungs[1:]] == [11, 220, 2200]
    merge = rungs[1]
    assert merge["params"]["min_count"] == 11
    assert violations(lang, merge, "contractual", k=11) == [] and violations(lang, merge, "contractual")
    assert candidates(lang, "public", True)["rungs"][1]["params"]["min_count"] == targets("public")["k"]
    with pytest.raises(ValueError):
        candidates(lang, "public", True, k=0)


def test_should_order_time_ladders_finest_to_coarsest():
    assert methods(candidates(lab("quasi_identifier", "TIMESTAMP"), "contractual", True)) == \
        ["floor_hour", "week_hour", "month_hour", "year_hour", "date", "iso_week", "month"]
    assert methods(candidates(lab("quasi_identifier", "DATE"), "contractual", True)) == ["date", "iso_week", "month", "year"]


def test_should_widen_age_bands_down_the_ladder():
    widths = [r["params"]["width"] for r in candidates(lab("quasi_identifier", "AGE"), "public", True)["rungs"]]
    assert widths == sorted(set(widths)) and len(widths) > 1


def test_should_use_strictly_coarser_steps_down_the_numeric_ladder():
    for sub in ("MEASUREMENT", "FINANCIAL_DATA"):
        rungs = candidates(lab("sensitive_attribute", sub), "contractual", True)["rungs"]
        assert rungs[0]["action"] == "KEEP"
        steps = [r["params"]["step"] for r in rungs[1:]]
        assert len(steps) > 1 and all(a < b for a, b in zip(steps, steps[1:]))


def test_should_use_the_subtype_ladder_for_sensitive_temporal_columns():
    c = candidates(lab("sensitive_attribute", "TIMESTAMP"), "controlled_research", True)
    assert methods(c)[0] == "floor_hour" and "KEEP" not in actions(c)


def test_should_allow_exact_diagnosis_only_internally():
    first = {t: actions(candidates(lab("sensitive_attribute", "DIAGNOSIS_CODE"), t, True))[0] for t in TRUST_LEVELS}
    assert first == {"internal": "KEEP", "contractual": "GENERALISE", "controlled_research": "GENERALISE",
                     "public": "DROP"}


def test_should_redact_free_text_below_public():
    assert methods(candidates(lab("free_text", "FREE_TEXT"), "controlled_research", True)) == ["redact_spans"]


def test_should_flag_required_street_address_for_review():
    c = candidates(lab("quasi_identifier", "STREET_ADDRESS"), "internal", True)
    assert c["needs_review"] and actions(c) == ["DROP"]


def test_should_offer_only_coarsest_rung_and_drop_for_low_confidence_required():
    c = candidates(lab("quasi_identifier", "TIMESTAMP", conf=0.55), "internal", True)
    assert methods(c) == ["month", None] and c["needs_review"]


# --- precision

def test_should_trim_rungs_coarser_than_precision_and_drop():
    assert methods(candidates(lab("quasi_identifier", "TIMESTAMP"), "contractual", True, precision="date")) == \
        ["floor_hour", "week_hour", "month_hour", "year_hour", "date"]
    assert methods(candidates(lab("quasi_identifier", "AGE"), "public", True, precision=10)) == ["age_band", "age_band"]
    assert actions(candidates(lab("non_sensitive", "CATEGORY"), "internal", False, precision="exact")) == ["KEEP"]


def test_should_reject_precision_the_ladder_cannot_express():
    with pytest.raises(ValueError):
        candidates(lab("quasi_identifier", "DATE"), "internal", True, precision="hour")


def test_should_reject_unknown_trust_level_and_role():
    with pytest.raises(ValueError):
        candidates(lab("quasi_identifier", "AGE"), "partner", True)
    with pytest.raises(ValueError):
        targets("secret")
    with pytest.raises(ValueError):
        candidates(lab("mystery", "AGE"), "internal", True)


# --- targets

def test_should_tighten_targets_with_trust():
    assert targets("internal")["k"] < targets("contractual")["k"] < targets("public")["k"]
    assert targets("public")["free_text"] is False


def test_should_apply_overrides_and_note_only_loosening():
    t = targets("contractual", {"k": 7})
    assert t["k"] == 7 and t["l"] == targets("contractual")["l"] and t["notes"] == []
    loose = targets("public", {"k": 4, "l": 2, "free_text": True})
    assert loose["k"] == 4 and len(loose["notes"]) == 3


# --- violations on hand-made rungs (reviewer probe cases included)

@pytest.mark.parametrize("label,rung,trust", [
    (lab("direct_identifier", "EMAIL"), keep(), "internal"),
    (lab("non_sensitive", "EMAIL"), keep(), "internal"),
    (lab("record_key", "RECORD_ID"), keep(), "internal"),
    (lab("quasi_identifier", "BIRTH_DATE"), keep(), "internal"),
    (lab("quasi_identifier", "BIRTH_DATE"), G("date"), "internal"),
    (lab("quasi_identifier", "BIRTH_DATE"), G("merge_rare", min_count=1), "public"),
    (lab("quasi_identifier", "BIRTH_DATE"), {"action": "DERIVE", "method": "year", "params": {}}, "public"),
    (lab("quasi_identifier", "TIMESTAMP"), G("round_numeric", step=3600), "internal"),
    (lab("non_sensitive", "CATEGORY"), {"action": "SHUFFLE", "method": None, "params": {}}, "internal"),
    (lab("non_sensitive", "CATEGORY"), G("bucketize"), "internal"),
    (lab("free_text", "FREE_TEXT"), {"action": "REDACT", "method": "redact_spans", "params": {}}, "public"),
    (lab("free_text", "FREE_TEXT"), keep(), "public"),
    (lab("free_text", "FREE_TEXT"), G("merge_rare", min_count=1), "public"),
    (lab("sensitive_attribute", "FINANCIAL_DATA"), keep(), "public"),
    (lab("sensitive_attribute", "MEASUREMENT"), G("round_numeric", step=1), "public"),
    (lab("direct_identifier", "EMAIL"), G("suppress_rare", min_count=1), "public"),
    (lab("direct_identifier", "EMAIL"), G("postcode_prefix", digits=999), "public"),
    (lab("direct_identifier", "EMAIL"), {"action": "HMAC", "method": "icd_chapter", "params": {}}, "public"),
    (lab("direct_identifier", "EMAIL"), {"action": "HMAC", "method": "hmac_sha256", "params": {"domain": None}}, "internal"),
    (lab("quasi_identifier", "POSTCODE"), G("postcode_prefix", digits=1), "internal"),
    (lab("quasi_identifier", "TIMESTAMP", conf=0.4), G("floor_hour"), "internal"),
])
def test_should_catch_hand_made_bad_rungs(label, rung, trust):
    assert violations(label, rung, trust)


def test_should_accept_drop_and_a_selector_filled_hmac_domain():
    email = lab("direct_identifier", "EMAIL")
    assert violations(email, {"action": "DROP", "method": None, "params": {}}, "public") == []
    assert violations(email, {"action": "HMAC", "method": "hmac_sha256", "params": {"domain": "r/email"}}, "public") == []
