"""Detector behaviour on small artificial tables (no real rows)."""
import pandas as pd

from pets_eval.check import HETU_CHECK
from privacy_tool.detect import detect_table, review_queue


def hetu(d, m, y, n):
    body = f"{d:02d}{m:02d}{y:02d}{n:03d}"
    return f"{body[:6]}-{body[6:]}{HETU_CHECK[int(body) % 31]}"


def label(df, col, table="t"):
    return detect_table(df, table).set_index("column").loc[col]


def people(n=60):
    return pd.DataFrame({
        "c1": [hetu(1 + i % 28, 1 + i % 12, 50 + i % 40, 900 + i) for i in range(n)],
        "c2": [f"{1940 + i % 60}-{1 + i % 12:02d}-{1 + i % 28:02d}" for i in range(n)],
        "c3": [f"2025-03-{1 + i % 28:02d} {i % 24:02d}:{i % 60:02d}" for i in range(n)],
        "c4": [f"person{i}@mail.example" for i in range(n)],
        "c5": ["Turku", "Salo", "Kaarina", "Naantali"] * (n // 4),
        "c6": [f"Patient reports {w} pain since day {i}, no fever" for i, w in enumerate(["chest", "back", "knee"] * (n // 3))],
        "c7": [f"V{i:05d}" for i in range(n)],
        "c8": [f"K{i % 7:03d}" for i in range(n)],
    })


def test_values_beat_meaningless_names():
    df = people()
    assert tuple(label(df, "c1")[["privacy_role", "subtype"]]) == ("direct_identifier", "NATIONAL_ID")
    assert tuple(label(df, "c4")[["privacy_role", "subtype"]]) == ("direct_identifier", "EMAIL")
    assert label(df, "c6").privacy_role == "free_text"


def test_hetu_variants_without_separator_or_with_prefix():
    ids = [hetu(1 + i % 28, 1 + i % 12, 70 + i % 20, 900 + i) for i in range(40)]
    mixed = [h.replace("-", "") if i % 3 == 0 else (f"HETU {h}" if i % 3 == 1 else h) for i, h in enumerate(ids)]
    assert label(pd.DataFrame({"x": mixed}), "x").subtype == "NATIONAL_ID"


def test_birth_dates_separated_from_event_times():
    df = people()
    assert tuple(label(df, "c2")[["privacy_role", "subtype"]]) == ("quasi_identifier", "BIRTH_DATE")
    assert label(df, "c3").subtype == "TIMESTAMP"
    finnish = pd.DataFrame({"d": ["25.09.2017", "1.11.2019", "02.01.2020", "14.3.2021"] * 10})
    assert label(finnish, "d").subtype == "DATE"  # dotted dates are not times


def test_keys_and_entity_ids():
    df = people()
    assert label(df, "c7").privacy_role == "record_key"
    assert label(df, "c8").privacy_role == "technical_identifier"  # repeating identifier of an entity


def test_role_depends_on_table_context():
    stations = pd.DataFrame({"station": [f"S{i}" for i in range(40)], "city": ["Turku", "Salo"] * 20})
    assert label(stations, "city").privacy_role == "non_sensitive"
    assert label(people(), "c5").privacy_role == "quasi_identifier"


def test_uncertain_columns_go_to_review():
    df = pd.DataFrame({"code": ["a", "b", "c", "d", "e"] * 20, "x": [hetu(1, 1, 80, 900)] * 100})
    queue = review_queue(detect_table(df, "t"))
    assert "code" in set(queue.column)
    assert "x" not in set(queue.column)


def test_review_regressions():
    n = 40
    df = pd.DataFrame({
        "ts": [f"2020-01-0{1 + i % 9}T10:00:00{'+02:00' if i % 3 else 'Z'}" for i in range(n)],  # mixed offsets
        "mac": [f"aa:bb:cc:dd:ee:{i:02x}" for i in range(n)],
        "clock": [f"{i % 24:02d}:{i % 60:02d}:00" for i in range(n)],
        "padded": [f"{i:08d}" for i in range(n)],
        "course_name": ["Mathematics A", "Physics B", "History C", "Biology D"] * (n // 4),
        "hetu": [hetu(1 + i % 28, 1, 80, 900 + i) if i % 3 else "NULL" for i in range(n)],
    })
    labels = detect_table(df, "t").set_index("column")
    assert labels.loc["ts", "subtype"] == "TIMESTAMP"
    assert labels.loc["mac", "subtype"] == "MAC_ADDRESS"
    assert labels.loc["clock", "subtype"] != "IP_ADDRESS"
    assert labels.loc["padded", "subtype"] != "PHONE"
    assert labels.loc["course_name", "privacy_role"] != "direct_identifier"
    assert labels.loc["hetu", "confidence"] >= .9  # NULL placeholders don't dilute the match rate
    assert label(pd.DataFrame({"e": [""] * 10}), "e").confidence < .6


def test_repeating_station_id_does_not_make_people():
    readings = pd.DataFrame({"station_id": [f"ST{i % 5}" for i in range(50)], "city": ["Turku", "Salo"] * 25,
                             "count": [str(i) for i in range(50)]})
    assert label(readings, "city").privacy_role == "non_sensitive"


def test_weak_but_value_detected_identifier_still_marks_people():
    n = 60
    trips = pd.DataFrame({
        "user_account": [f"user{i % 20}@mail.example" if i % 3 else f"user{i % 20}" for i in range(n)],  # ~67% emails
        "start_ts": [f"2025-05-{1 + i % 28:02d} {i % 24:02d}:{i % 60:02d}" for i in range(n)],
        "start_lat": [f"60.{4500 + i:05d}" for i in range(n)],
    })
    labels = detect_table(trips, "trips").set_index("column")
    assert labels.loc["user_account", "privacy_role"] == "direct_identifier"
    assert labels.loc["start_ts", "privacy_role"] == "quasi_identifier"
    assert labels.loc["start_lat", "privacy_role"] == "quasi_identifier"
