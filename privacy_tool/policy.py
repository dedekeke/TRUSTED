"""Static HEALTH-S1 selection policy; no data access or transformation execution.

Fields refer to shared token domains by name. Preset parameters override the
parameters of the named output field; all other field decisions stay unchanged.
Recipient and release scope must be supplied before executing HMAC operations.
Named operations are contracts for the later transformer, not implementations.
"""

HEALTH_S1 = {
    "scenario": "HEALTH-S1",
    "default_preset": "research_hour",
    "privacy_validation": "pending",
    "required_tasks": ["H-U2", "H-U4", "H-U6", "H-U7", "H-U8"],
    "bindings": {
        "patient": "ed_visits.patient_hetu",
        "visit": "ed_visits.visit_id",
        "date_of_birth": "ed_visits.date_of_birth",
        "arrival": "ed_visits.arrival_ts",
        "diagnosis": "ed_visits.icd10_primary",
        "municipality": "ed_visits.municipality",
        "triage": "ed_visits.triage",
        "length_of_stay": "ed_visits.los_minutes",
        "temperature": "ed_visits.temp_c",
        "revisit": "ed_visits.readmit_30d",
        "disposition": "ed_visits.disposition",
        "chief_complaint": "ed_visits.chief_complaint",
        "lab_visit": "lab_results.visit_id",
        "lab_test": "lab_results.test_code",
        "lab_value": "lab_results.value",
        "lab_unit": "lab_results.unit",
    },
    "joins": [
        {
            "parent": "ed_visits.visit_id",
            "child": "lab_results.visit_id",
            "domain": "visit",
            "required_by": ["H-U7"],
            "reason": "Join CRP results to visit temperature and diagnosis groups.",
        },
    ],
    "token_domains": {
        "patient": {
            "algorithm": "HMAC-SHA-256",
            "token_hex_length": 32,
            "context_fields": ["scenario", "recipient", "release", "domain"],
            "normalisation": "trim_whitespace_uppercase_check_character",
            "input_type": "string",
            "preserve_leading_zeros": True,
            "missing": "preserve_missing_no_token",
            "key_env": "PRIVACY_TOOL_HMAC_KEY",
        },
        "visit": {
            "algorithm": "HMAC-SHA-256",
            "token_hex_length": 32,
            "context_fields": ["scenario", "recipient", "release", "domain"],
            "normalisation": "identity",
            "input_type": "string",
            "preserve_leading_zeros": True,
            "missing": "preserve_missing_no_token",
            "key_env": "PRIVACY_TOOL_HMAC_KEY",
        },
    },
    "withheld_tables": {
        "clinical_notes": {
            "action": "WITHHOLD",
            "parameters": {},
            "required_by": [],
            "reason": "Full clinical notes are outside the confirmed text-release scope.",
        },
        "published_weekly_stats": {
            "action": "WITHHOLD",
            "parameters": {},
            "required_by": [],
            "reason": "Existing unsuppressed statistics are outside this controlled row-level release.",
        },
    },
    "fields": {
        "ed_visits": {
            "visit_id": {
                "action": "HMAC", "parameters": {"domain": "visit"},
                "required_by": ["H-U7"],
                "reason": "Preserve the lab join without disclosing the original sequential visit key.",
            },
            "patient_hetu": {
                "action": "HMAC", "parameters": {"domain": "patient"},
                "required_by": ["patient_linkage"],
                "reason": "Keep stable patient linkage separately from the precomputed revisit flag; retain the toolkit column name.",
            },
            "patient_name": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Patient names have no approved research purpose.",
            },
            "date_of_birth": {
                "action": "DROP", "parameters": {}, "required_by": ["H-U6"],
                "reason": "Use original DOB to derive age before dropping the unnecessary exact birth date.",
            },
            "sex": {
                "action": "KEEP", "parameters": {}, "required_by": [],
                "reason": "Retain the initial scenario QI; joint small-group risk still requires measurement.",
            },
            "phone": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Patient contact details are unnecessary for the selected analyses.",
            },
            "home_address": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Exact street addresses are unnecessary identifying detail.",
            },
            "postcode": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Fine geography is unnecessary when municipality supports the selected analysis.",
            },
            "municipality": {
                "action": "KEEP", "parameters": {}, "required_by": ["H-U4"],
                "reason": "Retain municipality for diagnosis mix; assess joint QI risk before freezing the release.",
            },
            "arrival_ts": {
                "action": "GENERALISE",
                "parameters": {
                    "method": "floor_hour",
                    "parser": "pets_eval.parse.to_datetime",
                    "output_format": "%Y-%m-%d %H:00",
                },
                "required_by": ["H-U6", "H-U8"],
                "reason": "Derive age from the original date first; floor, never round, to retain HH:00 for H-U8 without shifting date or ISO week.",
            },
            "arrival_mode": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Arrival mode is outside the five selected analyses.",
            },
            "ambulance_unit": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Ambulance call signs add unnecessary identifying detail.",
            },
            "triage": {
                "action": "KEEP", "parameters": {}, "required_by": ["H-U2"],
                "reason": "Group length of stay by triage level.",
            },
            "chief_complaint": {
                "action": "REDACT",
                "parameters": {"profile": "health_s1_local", "placeholders": "typed"},
                "required_by": ["confirmed_text_scope"],
                "reason": "Retain the confirmed short-text scope with typed placeholders; measure residual identifiers and dates separately.",
            },
            "icd10_primary": {
                "action": "GENERALISE",
                "parameters": {
                    "method": "diagnosis_group",
                    "mapping": "pets_eval.utility.health.diagnosis_group",
                    "unmapped": "blank_and_count",
                },
                "required_by": ["H-U4", "H-U7"],
                "reason": "Replace detailed diagnoses in this column with recognised groups; never pass unmapped raw codes through.",
            },
            "icd10_secondary": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Secondary diagnoses add clinical detail outside the first release purpose.",
            },
            "systolic_bp": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Blood pressure is unnecessary for the selected HEALTH-S1 tasks.",
            },
            "diastolic_bp": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Blood pressure is unnecessary for the selected HEALTH-S1 tasks.",
            },
            "heart_rate": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Heart rate is required by other scenarios, not the selected tasks.",
            },
            "resp_rate": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Respiratory rate is outside the selected analyses.",
            },
            "temp_c": {
                "action": "KEEP", "parameters": {}, "required_by": ["H-U7"],
                "reason": "Retain temperature for the CRP relationship analysis.",
            },
            "spo2": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Oxygen saturation is outside the selected HEALTH-S1 tasks.",
            },
            "pain_nrs": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Pain scores are outside the selected analyses.",
            },
            "attending_physician_id": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Staff identification is unnecessary for the recipient.",
            },
            "attending_physician_name": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Staff names are unnecessary for the recipient.",
            },
            "discharge_ts": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Length of stay already supports H-U2 without precise discharge timing.",
            },
            "los_minutes": {
                "action": "KEEP", "parameters": {}, "required_by": ["H-U2"],
                "reason": "Retain clinical length of stay for median LOS by triage.",
            },
            "disposition": {
                "action": "KEEP", "parameters": {},
                "required_by": ["H-U2", "H-U4", "H-U6", "H-U7", "H-U8"],
                "reason": "Allow consistent cancelled_duplicate exclusion and retain research context; still sensitive clinical data.",
            },
            "readmit_30d": {
                "action": "KEEP", "parameters": {}, "required_by": ["H-U6"],
                "reason": "Retain the revisit flag for age-band rates; it does not establish patient linkage quality.",
            },
        },
        "lab_results": {
            "lab_id": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "The recipient does not need lab IDs; private row maps use original IDs before removal.",
            },
            "visit_id": {
                "action": "HMAC", "parameters": {"domain": "visit"},
                "required_by": ["H-U7"],
                "reason": "Use exactly the visits' token domain, scope and normalisation for the CRP join.",
            },
            "test_code": {
                "action": "KEEP", "parameters": {}, "required_by": ["H-U7"],
                "reason": "Identify P-CRP results without filtering other lab rows in the starting release.",
            },
            "test_name": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Test names duplicate meaning already retained in the code.",
            },
            "value": {
                "action": "KEEP", "parameters": {}, "required_by": ["H-U7"],
                "reason": "Retain quantitative lab values for CRP analysis.",
            },
            "unit": {
                "action": "KEEP", "parameters": {}, "required_by": ["H-U7"],
                "reason": "Retain units to interpret lab measurements.",
            },
            "ref_range": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Reference ranges are outside the minimal required analysis.",
            },
            "abnormal_flag": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Additional clinical interpretation is outside the selected tasks.",
            },
            "sampled_ts": {
                "action": "DROP", "parameters": {}, "required_by": [],
                "reason": "Sample timing adds unnecessary time linkage.",
            },
        },
    },
    "derived_fields": {
        "ed_visits.age": {
            "action": "DERIVE",
            "parameters": {
                "sources": ["ed_visits.date_of_birth", "ed_visits.arrival_ts"],
                "output": "age",
                "method": "age_at_visit",
                "age_method": "completed_years",
                "parser": "pets_eval.parse.to_datetime",
                "banding": "pets_eval.parse.to_age_band",
                "width": 10,
                "top": 80,
                "source_stage": "original",
                "invalid": "blank_and_count",
            },
            "required_by": ["H-U6"],
            "reason": "Derive age at the original visit date before DOB removal or time generalisation; emit 0-9 through 70-79, then 80+.",
        },
    },
    "presets": {
        "research_hour": {
            "parameters": {
                "ed_visits.age": {"width": 10, "top": 80},
                "ed_visits.arrival_ts": {
                    "method": "floor_hour",
                    "parser": "pets_eval.parse.to_datetime",
                    "output_format": "%Y-%m-%d %H:00",
                },
            },
            "unsupported_tasks": [],
            "warnings": ["Hour precision may leave small QI groups and linkage risk; privacy validation is pending."],
        },
        "research_week": {
            "parameters": {
                "ed_visits.age": {"width": 10, "top": 80},
                "ed_visits.arrival_ts": {
                    "method": "iso_week",
                    "parser": "pets_eval.parse.to_datetime",
                    "output_format": "%G-W%V",
                },
            },
            "unsupported_tasks": ["H-U8"],
            "warnings": ["ISO week removes time of day: H-U8 is unsupported. Privacy validation is pending."],
        },
    },
    "unknown_optional_field": {
        "action": "DROP", "parameters": {}, "required_by": [],
        "reason": "Unmapped or unlabelled optional fields have no justified release purpose; warn rather than copy through.",
    },
    "unknown_required_field": "block_until_mapped_and_labelled",
    "invalid_values": {"output": "blank", "report": "per_column_counts"},
    "lab_rows": {"filter": None, "preserve_order": True},
    "execution_order": [
        "read_original_sources_and_private_row_map_ids",
        "derive_age",
        "transform_fields",
        "omit_dropped_fields_and_withheld_tables",
        "validate_release",
    ],
}
