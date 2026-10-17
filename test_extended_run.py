# test_extended_run.py
__version__ = "0.1.0"

"""
Automated tests for the extended run (MQTT mode 3, e.g. end-of-season
chemical dosing).

Run with:  python -m pytest test_extended_run.py -v

Reuses the fake clock, stubbed network and state reset from test_gate_logic.
"""

import json

from state import state
from test_gate_logic import clean_state, make_controller, set_temps, midday_ts, local_ts  # noqa: F401

HOUR = 3600


def send(c, payload):
    c.handle_mqtt_message("manual_override", payload)


def last_debug(c):
    for topic, payload in reversed(c.network.mqtt.published):
        if topic == "debug":
            return json.loads(payload)
    return None


def test_default_run_lasts_one_hour():
    now = midday_ts()
    c = make_controller(now)
    set_temps(flow=20.0, ret=20.0)          # no solar gain — auto would keep it off

    send(c, "3")
    c.loop(now_ts=now)
    assert state["pump_on"] is True
    assert state["pump_reason"] == "extended run (60 min left)"

    c.loop(now_ts=now + HOUR - 1)
    assert state["pump_on"] is True
    assert state["pump_reason"] == "extended run (1 min left)"

    c.loop(now_ts=now + HOUR + 1)
    assert state["extended_run"] is False
    assert state["pump_on"] is False
    assert state["pump_reason"].startswith("insufficient gain")


def test_duration_in_hours_from_payload():
    now = midday_ts()
    c = make_controller(now)
    set_temps()

    send(c, "3:0.5")
    c.loop(now_ts=now)
    c.loop(now_ts=now + 30 * 60 - 1)
    assert state["pump_on"] is True
    c.loop(now_ts=now + 30 * 60 + 1)
    assert state["pump_on"] is False


def test_runs_at_night_and_overrides_holiday():
    now = local_ts(23)
    c = make_controller(now)
    set_temps()
    state["manual_disabled"] = True

    send(c, "3:2")
    assert state["manual_disabled"] is False
    c.loop(now_ts=now)
    assert state["pump_on"] is True
    c.loop(now_ts=now + 2 * HOUR - 1)
    assert state["pump_on"] is True

    c.loop(now_ts=now + 2 * HOUR + 1)
    assert state["pump_on"] is False
    assert state["pump_reason"].startswith("sleep")


def test_mode_zero_cancels_run():
    now = midday_ts()
    c = make_controller(now)
    set_temps()

    send(c, "3:8")
    c.loop(now_ts=now)
    c.loop(now_ts=now + 600)
    assert state["pump_on"] is True

    send(c, "0")
    assert state["extended_run"] is False
    c.loop(now_ts=now + 601)
    assert state["pump_on"] is False


def test_holiday_cancels_run():
    now = midday_ts()
    c = make_controller(now)
    set_temps()

    send(c, "3:8")
    c.loop(now_ts=now)
    send(c, "2")
    c.loop(now_ts=now + 1)
    assert state["extended_run"] is False
    assert state["pump_on"] is False
    assert state["pump_reason"] == "holiday mode"


def test_resending_restarts_with_new_duration():
    now = midday_ts()
    c = make_controller(now)
    set_temps()

    send(c, "3:1")
    c.loop(now_ts=now)
    c.loop(now_ts=now + 1800)
    send(c, "3:2")
    c.loop(now_ts=now + 1801)
    c.loop(now_ts=now + 1801 + 2 * HOUR - 1)
    assert state["pump_on"] is True
    c.loop(now_ts=now + 1801 + 2 * HOUR + 1)
    assert state["pump_on"] is False


def test_safety_stop_cancels_run_for_good():
    now = midday_ts()
    c = make_controller(now)
    set_temps()

    send(c, "3:8")
    c.loop(now_ts=now)
    assert state["pump_on"] is True

    state["water_level_ok"] = False
    c.loop(now_ts=now + 10)
    assert state["pump_on"] is False
    assert state["pump_reason"] == "dry run protect"
    assert state["extended_run"] is False

    # Water restored — the run must not restart by itself.
    state["water_level_ok"] = True
    c.loop(now_ts=now + 20)
    assert state["pump_on"] is False
    assert not state["pump_reason"].startswith("extended run")


def test_overtemp_cancels_run():
    now = midday_ts()
    c = make_controller(now)
    set_temps()

    send(c, "3:8")
    c.loop(now_ts=now)
    state["temps"]["tEnclosure"] = 99.0
    c.loop(now_ts=now + 10)
    assert state["pump_on"] is False
    assert state["extended_run"] is False


def test_missing_flow_return_does_not_stop_run():
    now = midday_ts()
    c = make_controller(now)
    set_temps()

    send(c, "3:8")
    c.loop(now_ts=now)
    state["temps"]["tFlow"] = None
    c.loop(now_ts=now + 10)
    assert state["pump_on"] is True
    assert state["pump_reason"].startswith("extended run")

    # Without a run the sensor loss still stops the pump.
    send(c, "0")
    c.loop(now_ts=now + 20)
    assert state["pump_on"] is False
    assert state["pump_reason"] == "flow/return sensor missing"


def test_no_periodic_test_during_or_straight_after_run():
    now = midday_ts()
    c = make_controller(now)
    set_temps(flow=20.0, ret=20.0, plate=25.0)   # gate wide open

    send(c, "3:2")
    for t in range(0, 2 * HOUR, 60):
        c.loop(now_ts=now + t)
        assert state["test_running"] is False

    end = now + 2 * HOUR + 1
    c.loop(now_ts=end)
    assert state["pump_on"] is False
    c.loop(now_ts=end + 599)
    assert state["test_running"] is False
    c.loop(now_ts=end + 601)
    assert state["test_running"] is True


def test_bad_payloads_are_ignored():
    now = midday_ts()
    c = make_controller(now)
    set_temps()

    for payload in ("3:abc", "3:-1", "3:0", "3:nan", "x"):
        send(c, payload)
        assert state["extended_run"] is False, payload


def test_duration_clamped_to_max():
    now = midday_ts()
    c = make_controller(now, extended_run_max_hours=72)
    set_temps()

    send(c, "3:500")
    c.loop(now_ts=now)
    c.loop(now_ts=now + 72 * HOUR - 1)
    assert state["pump_on"] is True
    c.loop(now_ts=now + 72 * HOUR + 1)
    assert state["pump_on"] is False


def test_no_echo_and_boost_ignored_during_run():
    now = midday_ts()
    c = make_controller(now)
    set_temps()

    send(c, "3:8")
    send(c, "1")
    assert state["manual_override"] is False
    assert ("manual_override", "0") not in c.network.mqtt.published

    c.loop(now_ts=now)
    assert state["pump_reason"].startswith("extended run")


def test_debug_payload_reports_run():
    now = midday_ts()
    c = make_controller(now)
    set_temps()

    send(c, "3:1")
    c.loop(now_ts=now)
    c.publish_state(force_all=False)
    d = last_debug(c)
    assert d["extended_run"] is True
    assert d["extended_run_remaining_s"] == HOUR

    send(c, "0")
    c.loop(now_ts=now + 5)
    c.publish_state(force_all=False)
    d = last_debug(c)
    assert d["extended_run"] is False
    assert d["extended_run_remaining_s"] == 0
