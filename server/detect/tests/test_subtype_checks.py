"""D1/D3: subtypes must fit the values; an id column's own name decides its id subtype."""
import numpy as np
import pandas as pd

from pets_detect.profiler import profile_column
from pets_detect.rules import structure_rules
from pets_detect_v2.pipeline import guardrail


def prof(values, name="c", fk_to=()):
    p = profile_column("d", "t", name, pd.Series(values), 3, 6, np.random.default_rng(0))
    p["fk_to"] = list(fk_to)
    return p


def test_gps_subtype_needs_coordinate_shaped_values():
    money = prof([f"{i}.{i % 100:02d}" for i in range(10, 300)])               # 2-decimal amounts
    coords = prof([f"60.{450000 + i}" for i in range(200)] + ["22.267"] * 100)  # some coordinates with 3 decimals
    assert guardrail(money, "", "GPS_COORDINATE") is not None
    assert guardrail(coords, "", "GPS_COORDINATE") is None
    assert guardrail(money, "", "MEASUREMENT") is None                          # other subtypes are untouched


def test_payment_card_still_needs_luhn_or_masking():
    ids = prof([f"CRD{9000000 + i}" for i in range(200)])
    assert guardrail(ids, "", "PAYMENT_CARD") is not None


def test_own_name_decides_the_id_subtype_before_the_referenced_table():
    vals = [f"64300000000{i:07d}" for i in range(40)] * 3
    meter = structure_rules(prof(vals, "metering_point_id", ["customers.metering_point_id"]))
    assert meter.subtype == "METER_ID"
    anon = structure_rules(prof(vals, "ref", ["customers.customer_id"]))   # no hint in the name: use the target
    assert anon.subtype == "CUSTOMER_ID"
