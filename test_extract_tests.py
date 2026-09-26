# test_extract_tests.py
__version__ = "0.1.0"

"""
Tests for tools/extract_tests.py, the debug-feed reducer.

Run with:  python -m pytest test_extract_tests.py -v

Each test builds a tiny synthetic export shaped like a real Adafruit IO
download, so the reducer's episode logic is exercised on the same record
structure it sees in the field.
"""

import json

from tools.extract_tests import extract, load_records, main, merge, read_csv

_seq = [0]


def rec(t, reason, pump_on=False, runtime=0, flow=20.0, ret=20.0, plate=20.0, **extra):
    """One export item. t is HH:MM:SS local (== UTC here for simplicity)."""
    _seq[0] += 1
    value = {
        "pump_reason": reason,
        "pump_on": pump_on,
        "pump_runtime_s": runtime,
        "local_time": t[:5],
        "fw_version": extra.pop("fw", "1.3.1"),
        "temps": {"tFlow": flow, "tReturn": ret, "tSolarPlate": plate,
                  "tSolarRef": 19.0, "tAmbient": 18.0},
    }
    value.update(extra)
    return {"id": f"R{_seq[0]:04d}", "created_at": f"2026-09-19T{t}.000Z",
            "value": json.dumps(value)}


def export(tmp_path, items, name="export.json"):
    path = tmp_path / name
    path.write_text(json.dumps(items))
    return str(path)


def rows_from(tmp_path, items):
    records, _ = load_records([export(tmp_path, items)])
    return extract(records)


# -------------------------------------------------------------------------

def test_wasted_test_is_insufficient_with_no_heat(tmp_path):
    rows = rows_from(tmp_path, [
        rec("10:00:00", "waiting for solar gain (0.0C)", plate=22.0),
        rec("10:00:30", "periodic test", True, 0, plate=22.0),
        rec("10:01:00", "periodic test", True, 30, ret=21.0, plate=22.0),
        rec("10:01:30", "insufficient gain (0.0C)"),
    ])
    assert len(rows) == 1
    r = rows[0]
    assert (r["decision"], r["exact"], r["outcome"], r["heat_min"]) == ("ran", True, "insufficient", 0)
    assert r["gate_delta"] == 2.0            # tSolarPlate - tFlow, pre-1.3.0 style
    assert r["delta_peak"] == 1.0
    assert r["test_s"] == 60


def test_converting_test_measures_heating_until_pump_stops(tmp_path):
    rows = rows_from(tmp_path, [
        rec("10:00:00", "periodic test", True, 0, plate=26.0),
        rec("10:01:30", "solar heating (0.6C)", True, 90),
        rec("10:30:00", "solar heating (0.3C)", True, 1800),
        rec("10:31:30", "insufficient gain (0.1C)"),
    ])
    assert rows[0]["outcome"] == "heating"
    assert rows[0]["heat_min"] == 30         # 10:01:30 to 10:31:30


def test_dropped_decision_record_falls_back_and_is_marked_inexact(tmp_path):
    rows = rows_from(tmp_path, [
        rec("08:00:00", "sleep (hour 7)", plate=15.0),
        rec("08:00:30", "periodic test", True, 30, plate=18.0),
        rec("08:01:30", "insufficient gain (0.0C)"),
    ])
    r = rows[0]
    assert r["exact"] is False
    assert r["gate_delta"] == -5.0           # from the preceding record
    assert r["test_s"] == 90                 # 60 s seen + 30 s already elapsed


def test_gate_fields_from_1_3_payloads(tmp_path):
    rows = rows_from(tmp_path, [
        rec("17:27:00", "test skipped (gate 0.1C)", plate_pool_delta=0.12, test_gate_open=False),
        rec("17:27:30", "waiting for solar gain (-0.2C)", test_gate_open=False),
        rec("17:50:00", "periodic test", True, 0, plate_pool_delta=0.05, test_gate_open=False),
        rec("17:51:30", "insufficient gain (0.0C)"),
    ])
    skip, forced = rows
    assert (skip["decision"], skip["gate_delta"], skip["outcome"]) == ("skipped", 0.12, None)
    assert forced["decision"] == "forced"    # ran with the gate closed = fallback
    assert forced["gate_delta"] == 0.05      # reported field wins over temps


def test_test_cut_short_by_sleep_is_other(tmp_path):
    rows = rows_from(tmp_path, [
        rec("17:59:30", "periodic test", True, 0),
        rec("18:00:00", "sleep (hour 18)"),
    ])
    assert rows[0]["outcome"] == "other"


def test_non_debug_and_malformed_items_are_skipped(tmp_path):
    items = [
        {"id": "X1", "created_at": "2026-09-19T10:00:00.000Z", "value": "21.5"},
        {"id": "X2", "created_at": "2026-09-19T10:00:01.000Z", "value": "{not json"},
        rec("10:00:30", "periodic test", True, 0),
        rec("10:01:30", "insufficient gain (0.0C)"),
    ]
    records, skipped = load_records([export(tmp_path, items)])
    assert skipped == 2
    assert len(extract(records)) == 1


def test_newer_export_fills_in_an_unfinished_test_without_duplicating(tmp_path):
    out = tmp_path / "data"
    first = [rec("10:00:00", "periodic test", True, 0, plate=26.0)]
    later = first + [
        rec("10:01:30", "solar heating (0.6C)", True, 90),
        rec("10:11:30", "insufficient gain (0.1C)"),
    ]

    main([export(tmp_path, first, "a.json"), "--out-dir", str(out)])
    row = next(iter(read_csv(str(out / "tests.csv")).values()))
    assert row["outcome"] == ""              # still running when exported

    main([export(tmp_path, later, "b.json"), "--out-dir", str(out)])
    rows = read_csv(str(out / "tests.csv"))
    assert len(rows) == 1
    only = next(iter(rows.values()))
    assert (only["outcome"], only["heat_min"]) == ("heating", "10")
    assert (out / "daily.csv").exists()


def test_merge_keeps_rows_from_earlier_exports(tmp_path):
    older = {"OLD": {"id": "OLD", "date": "2026-09-01", "time": "09:00"}}
    rows = rows_from(tmp_path, [
        rec("10:00:30", "periodic test", True, 0),
        rec("10:01:30", "insufficient gain (0.0C)"),
    ])
    merged = merge(older, rows)
    assert [r["id"] for r in merged][0] == "OLD"
    assert len(merged) == 2
