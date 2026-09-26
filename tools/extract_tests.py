# tools/extract_tests.py
__version__ = "0.1.0"

"""
Reduce an Adafruit IO debug-feed export to one row per periodic-test decision.

Desktop tool — never deployed to the Pico.

The debug feed publishes the full controller state every 30 s, which over a
season is tens of megabytes. Almost none of that matters for tuning the test
gate: what matters is the moment each test was decided, and what happened
next. This script keeps exactly that, so the result is small enough to share.

Usage:
    python tools/extract_tests.py EXPORT.json [EXPORT.json ...] [--out-dir data]

Writes (merging into anything already there):
    <out-dir>/tests.csv   one row per test decision (ran, forced, skipped)
    <out-dir>/daily.csv   one row per day, rolled up from tests.csv

Re-running against a newer, larger export is safe. Rows are keyed on the
Adafruit record id of the decision, and a newer export replaces an older row
with the same id — so a test that was still running when the last export was
taken gets its outcome filled in rather than duplicated.

WHY the decision record is exact: starting a test (or logging a gate skip)
changes pump_reason, and a reason change publishes the debug payload in the
same loop the gate was evaluated in. So that record carries the exact
plate_pool_delta the gate saw, not a 30 s sample. The 10 s MQTT rate limit can
occasionally drop it; the row is then marked exact=0 and takes its values from
the preceding record instead.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime

TEST_COLUMNS = [
    "id", "date", "time", "fw", "decision", "exact",
    "gate_delta", "gate_open", "delta_start", "delta_peak",
    "outcome", "test_s", "heat_min",
    "tFlow", "tReturn", "tSolarPlate", "tSolarRef", "tAmbient",
]

DAILY_COLUMNS = [
    "date", "fw", "ran", "forced", "skipped",
    "heating", "insufficient", "other", "test_min", "heat_min",
]

# Next-episode reason -> what the test turned into.
_OUTCOMES = {
    "solar heating": "heating",
    "insufficient gain": "insufficient",
    "waiting for solar gain": "insufficient",
}


# -------------------------------------------------------------------------
# Loading
# -------------------------------------------------------------------------

def load_records(paths):
    """
    Read one or more exports into debug payloads, oldest first.

    Returns (records, skipped). Records from other feeds, or values that are
    not a debug payload, are skipped rather than failing the whole run.
    """
    records, skipped, seen = [], 0, set()
    for path in paths:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        for item in raw:
            value = item.get("value")
            try:
                payload = json.loads(value) if isinstance(value, str) else value
            except ValueError:
                skipped += 1
                continue
            if not isinstance(payload, dict) or "pump_reason" not in payload:
                skipped += 1
                continue
            if item["id"] in seen:          # overlapping exports
                continue
            seen.add(item["id"])
            payload["_id"] = item["id"]
            payload["_ts"] = item["created_at"]
            records.append(payload)
    records.sort(key=lambda r: r["_ts"])
    return records, skipped


# -------------------------------------------------------------------------
# Extraction
# -------------------------------------------------------------------------

def _static(reason):
    """Strip the dynamic '(...)' suffix, as Controller._set_pump does."""
    return (reason or "").split(" (")[0]


def _episodes(records):
    """Group consecutive records with the same static reason and pump state."""
    eps = []
    for r in records:
        key = (_static(r["pump_reason"]), r["pump_on"])
        if eps and eps[-1][0] == key:
            eps[-1][1].append(r)
        else:
            eps.append((key, [r]))
    return eps


def _seconds(a, b):
    """Seconds between two Adafruit ISO timestamps (b - a)."""
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
    return (datetime.strptime(b, fmt) - datetime.strptime(a, fmt)).total_seconds()


def _delta(temps, hot, cold):
    a, b = temps.get(hot), temps.get(cold)
    return None if a is None or b is None else a - b


def _row(decision_rec, exact, decision, start):
    """Gate values from the record decided on; identity from the first record."""
    temps = decision_rec.get("temps", {})
    gate_delta = decision_rec.get("plate_pool_delta")
    if gate_delta is None:                  # pre-1.3.0 payloads
        gate_delta = _delta(temps, "tSolarPlate", "tFlow")
    return {
        "id": start["_id"],
        "date": start["_ts"][:10],      # tests only run 08-18 local, so
        "time": start.get("local_time", ""),  # the UTC date is the local date
        "fw": start.get("fw_version", ""),
        "decision": decision,
        "exact": bool(exact),
        "gate_delta": gate_delta,
        "gate_open": decision_rec.get("test_gate_open"),
        "delta_start": _delta(temps, "tReturn", "tFlow"),
        "delta_peak": None, "outcome": None, "test_s": None, "heat_min": None,
        "tFlow": temps.get("tFlow"),
        "tReturn": temps.get("tReturn"),
        "tSolarPlate": temps.get("tSolarPlate"),
        "tSolarRef": temps.get("tSolarRef"),
        "tAmbient": temps.get("tAmbient"),
    }


def extract(records):
    """Turn a sorted list of debug payloads into test-decision rows."""
    eps = _episodes(records)
    rows = []
    for i, ((reason, _), recs) in enumerate(eps):
        start = recs[0]
        prev = eps[i - 1][1][-1] if i > 0 else None

        if reason == "test skipped":
            rows.append(_row(start, True, "skipped", start))
            continue
        if reason != "periodic test":
            continue

        # The decision loop publishes with pump_runtime_s == 0. If the rate
        # limiter dropped it, the first record we have is ~30 s into the test.
        exact = start.get("pump_runtime_s") == 0
        decided_on = start if exact or prev is None else prev
        gate_open = decided_on.get("test_gate_open")
        row = _row(decided_on, exact, "forced" if gate_open is False else "ran", start)

        peaks = [_delta(r.get("temps", {}), "tReturn", "tFlow") for r in recs]
        peaks = [p for p in peaks if p is not None]
        row["delta_peak"] = max(peaks) if peaks else None

        nxt = eps[i + 1] if i + 1 < len(eps) else None
        if nxt is None:
            rows.append(row)                # outcome filled in by a later export
            continue

        # If the decision record was dropped, the first one we have is already
        # pump_runtime_s into the test.
        test_end = nxt[1][0]["_ts"]
        row["test_s"] = _seconds(start["_ts"], test_end) + (start.get("pump_runtime_s") or 0)
        row["outcome"] = _OUTCOMES.get(nxt[0][0], "other")
        row["heat_min"] = 0
        if row["outcome"] == "heating":
            after = eps[i + 2][1][0]["_ts"] if i + 2 < len(eps) else nxt[1][-1]["_ts"]
            row["heat_min"] = _seconds(test_end, after) / 60
        rows.append(row)
    return rows


# -------------------------------------------------------------------------
# Output
# -------------------------------------------------------------------------

def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return str(v)


def read_csv(path):
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def merge(existing, rows):
    """Upsert new rows into existing ones, keyed on the decision record id."""
    merged = dict(existing)
    for r in rows:
        merged[r["id"]] = {k: _fmt(r[k]) for k in TEST_COLUMNS}
    return sorted(merged.values(), key=lambda r: (r["date"], r["time"], r["id"]))


def daily(rows):
    """Roll the per-test rows up to one line per day."""
    days = {}
    for r in rows:
        d = days.setdefault(r["date"], {c: 0 for c in DAILY_COLUMNS})
        d["date"], d["fw"] = r["date"], r["fw"]
        d[r["decision"]] += 1
        if r["outcome"]:
            d[r["outcome"]] += 1
        d["test_min"] += float(r["test_s"] or 0) / 60
        d["heat_min"] += float(r["heat_min"] or 0)
    for d in days.values():
        d["test_min"] = round(d["test_min"], 1)
        d["heat_min"] = round(d["heat_min"], 1)
    return [days[k] for k in sorted(days)]


def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Reduce an Adafruit IO debug-feed export to one row per test decision.")
    ap.add_argument("exports", nargs="+", help="Adafruit IO debug-feed JSON export(s)")
    ap.add_argument("--out-dir", default="data", help="where tests.csv and daily.csv live")
    args = ap.parse_args(argv)

    records, skipped = load_records(args.exports)
    rows = extract(records)

    os.makedirs(args.out_dir, exist_ok=True)
    tests_path = os.path.join(args.out_dir, "tests.csv")
    existing = read_csv(tests_path)
    merged = merge(existing, rows)
    write_csv(tests_path, TEST_COLUMNS, merged)
    write_csv(os.path.join(args.out_dir, "daily.csv"), DAILY_COLUMNS, daily(merged))

    added = sum(1 for r in rows if r["id"] not in existing)
    inexact = sum(1 for r in rows if not r["exact"])
    span = f"{records[0]['_ts'][:10]} to {records[-1]['_ts'][:10]}" if records else "none"
    print(f"records read:    {len(records)} ({skipped} skipped as not debug payloads)")
    print(f"span:            {span}")
    print(f"test decisions:  {len(rows)} ({added} new, {len(rows) - added} updated)")
    print(f"inexact:         {inexact} (decision record dropped by rate limiter)")
    print(f"{tests_path}: {len(merged)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
