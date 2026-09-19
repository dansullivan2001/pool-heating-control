# test_gate_logic.py
__version__ = "0.1.1"

"""
Automated tests for the periodic-test irradiance gate.

Run with:  python -m pytest test_gate_logic.py -v

These drive the real Controller over a fake clock via loop(now_ts=...), which
makes the periodic-test timer fully deterministic — the 60-minute fallback in
particular cannot practically be verified by hand in the GUI harness.

Network and MQTT are stubbed so published payloads can be inspected without
touching Adafruit IO. Everything else is the production code path.
"""

import copy
import json
import time

import pytest

from state import state
from config import CONFIG
from controller.controller import Controller

# Snapshot the declared defaults before any Controller mutates the shared dict.
_PRISTINE_STATE = copy.deepcopy(state)


# -------------------------------------------------------------------------
# Test doubles
# -------------------------------------------------------------------------

class FakeFeeds:
    """Every attribute resolves to a topic named after itself."""
    def __getattr__(self, name):
        return name


class FakeMQTT:
    def __init__(self):
        self.connected = True
        self.message_handler = None
        self.published = []      # list of (topic, payload)

    def publish(self, topic, payload, urgent=False):
        self.published.append((topic, payload))


class FakeNetwork:
    def __init__(self):
        self.mqtt = FakeMQTT()
        self.feeds = FakeFeeds()


# -------------------------------------------------------------------------
# Fixtures and helpers
# -------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_state():
    """Reset the shared state dict around every test."""
    state.clear()
    state.update(copy.deepcopy(_PRISTINE_STATE))
    yield
    state.clear()
    state.update(copy.deepcopy(_PRISTINE_STATE))


def local_ts(hour, minute=0, day_offset=0):
    """
    An epoch timestamp at a given *local* hour, so core-hours checks
    (which use time.localtime) behave the same in any timezone.
    """
    t = time.localtime()
    return time.mktime((t[0], t[1], t[2] + day_offset,
                        hour, minute, 0, t[6], t[7], t[8]))


def midday_ts():
    return local_ts(12)


def make_controller(now, **config_overrides):
    """Build a Controller with its test timer aligned to the fake clock."""
    cfg = dict(CONFIG)
    cfg.update(config_overrides)

    controller = Controller(network=FakeNetwork(), config=cfg)
    # __init__ seeds the timer from the real clock; re-align it to the fake one.
    controller._reset_test_timer(now)
    return controller


def set_temps(flow=20.0, ret=20.0, plate=None, ref=15.0, enclosure=25.0):
    """Populate state["temps"] and satisfy the safety chain."""
    state["temps"] = {
        "tFlow": flow,
        "tReturn": ret,
        "tEnclosure": enclosure,
        "tAmbient": 18.0,
        "tSolarPlate": plate,
        "tSolarRef": ref,
    }
    state["water_level_ok"] = True
    state["sensors_ok"] = True


def skip_records(controller):
    """Debug payloads whose pump_reason records a gate skip."""
    out = []
    for topic, payload in controller.network.mqtt.published:
        if topic != "debug":
            continue
        reason = json.loads(payload).get("pump_reason", "")
        if reason.startswith("test skipped"):
            out.append(reason)
    return out


# -------------------------------------------------------------------------
# Gate helper — unit level
# -------------------------------------------------------------------------

def test_gate_open_when_plate_clears_threshold():
    now = midday_ts()
    c = make_controller(now, gate_threshold=0.5)
    state["plate_pool_delta"] = 0.5          # exactly at threshold — inclusive
    assert c._test_gate_open() == (True, 0.5)


def test_gate_closed_when_plate_below_threshold():
    now = midday_ts()
    c = make_controller(now, gate_threshold=0.5)
    state["plate_pool_delta"] = 0.4
    assert c._test_gate_open() == (False, 0.4)


def test_gate_open_when_signal_unavailable():
    """FAIL-SAFE: a missing tSolarPlate or tFlow must never block a test."""
    now = midday_ts()
    c = make_controller(now)
    state["plate_pool_delta"] = None
    assert c._test_gate_open() == (True, None)


def test_gate_open_when_disabled_in_config():
    now = midday_ts()
    c = make_controller(now, gate_enabled=False)
    state["plate_pool_delta"] = -10.0        # far below any threshold
    assert c._test_gate_open() == (True, None)


# -------------------------------------------------------------------------
# Gate behaviour through the full control loop
# -------------------------------------------------------------------------

def test_test_runs_when_gate_open():
    now = midday_ts()
    c = make_controller(now)
    set_temps(flow=20.0, ret=20.0, plate=25.0)   # plate_pool_delta = 5.0

    c.loop(now_ts=now)
    assert state["test_running"] is False

    c.loop(now_ts=now + 600)
    assert state["test_running"] is True
    assert state["pump_on"] is True
    assert state["pump_reason"] == "periodic test"
    assert state["test_gate_open"] is True


def test_test_skipped_when_gate_closed():
    now = midday_ts()
    c = make_controller(now)
    set_temps(flow=20.0, ret=20.0, plate=20.2)   # plate_pool_delta = 0.2

    c.loop(now_ts=now)
    c.loop(now_ts=now + 600)

    assert state["test_running"] is False
    assert state["pump_on"] is False
    assert state["test_gate_open"] is False
    assert state["pump_reason"] == "test skipped (gate 0.2C)"
    assert state["plate_pool_delta"] == 0.2


def test_skip_does_not_disturb_pump_or_repeat():
    """The skip changes only the reason string, and is logged once."""
    now = midday_ts()
    c = make_controller(now)
    set_temps(flow=20.0, ret=20.0, plate=20.2)

    for offset in range(0, 1200, 2):             # 10 minutes of 2 s ticks
        c.loop(now_ts=now + offset)

    assert state["test_running"] is False
    assert state["pump_on"] is False
    # Reason reverts to normal auto reason after the one-off skip record.
    assert state["pump_reason"].startswith("waiting for solar gain")
    assert len(skip_records(c)) == 1


def test_gate_reevaluated_every_tick_once_slot_is_due():
    """Sun arriving mid-wait starts a test immediately, not at the next slot."""
    now = midday_ts()
    c = make_controller(now)
    set_temps(flow=20.0, ret=20.0, plate=20.2)   # gate closed

    c.loop(now_ts=now)
    c.loop(now_ts=now + 600)
    assert state["test_running"] is False

    # Plate warms 100 s after the slot came due.
    set_temps(flow=20.0, ret=20.0, plate=21.0)   # plate_pool_delta = 1.0
    c.loop(now_ts=now + 700)

    assert state["test_running"] is True
    assert state["pump_reason"] == "periodic test"


def test_fallback_forces_test_after_interval():
    now = midday_ts()
    c = make_controller(now, gate_fallback_interval=3600)
    set_temps(flow=20.0, ret=20.0, plate=20.2)   # gate stays closed throughout

    for offset in range(0, 3600, 60):
        c.loop(now_ts=now + offset)
    assert state["test_running"] is False, "must not test before the fallback"

    c.loop(now_ts=now + 3600)
    assert state["test_running"] is True
    assert state["pump_on"] is True
    assert state["pump_reason"] == "periodic test"
    assert state["test_gate_open"] is False, "test was forced, not gate-approved"


def test_missing_plate_sensor_falls_back_to_timer_only():
    """FAIL-SAFE end to end: no plate reading => tests run on the timer."""
    now = midday_ts()
    c = make_controller(now)
    set_temps(flow=20.0, ret=20.0, plate=None)

    c.loop(now_ts=now)
    assert state["plate_pool_delta"] is None

    c.loop(now_ts=now + 600)
    assert state["test_running"] is True
    assert state["test_gate_open"] is True


def test_gate_disabled_runs_tests_on_timer():
    now = midday_ts()
    c = make_controller(now, gate_enabled=False)
    set_temps(flow=20.0, ret=20.0, plate=20.0)   # would close an enabled gate

    c.loop(now_ts=now)
    c.loop(now_ts=now + 600)

    assert state["test_running"] is True
    assert state["pump_reason"] == "periodic test"


def test_one_skip_record_per_stagnation_period():
    """
    A second skip is logged only after an intervening test, not per slot.
    Drives a full cycle: skip -> fallback test -> test ends cold -> skip again.
    """
    now = midday_ts()
    c = make_controller(now, gate_fallback_interval=3600, pump_test_duration=90)
    set_temps(flow=20.0, ret=20.0, plate=20.2)

    # First stagnation period: slot due at +600, gate closed, skips until +3600.
    for offset in range(0, 3600, 30):
        c.loop(now_ts=now + offset)
    assert len(skip_records(c)) == 1

    # Fallback test runs and ends with no solar gain, so the pump goes off again.
    c.loop(now_ts=now + 3600)
    assert state["test_running"] is True
    c.loop(now_ts=now + 3600 + 90)
    assert state["test_running"] is False
    assert state["pump_on"] is False

    # Second stagnation period: next slot 600 s after the test ended.
    for offset in range(3690, 4400, 30):
        c.loop(now_ts=now + offset)
    assert len(skip_records(c)) == 2


def test_gate_does_not_block_heating_once_delta_is_good():
    """
    The gate only ever delays a *test*. If the solar delta itself clears the
    high threshold, normal heating starts regardless of the gate.
    """
    now = midday_ts()
    c = make_controller(now)
    # Gate closed (plate barely above flow) but a real solar gain is present.
    set_temps(flow=20.0, ret=21.0, plate=20.2)

    c.loop(now_ts=now)

    assert state["pump_on"] is True
    assert state["pump_reason"].startswith("solar heating")


# -------------------------------------------------------------------------
# Overnight behaviour
# -------------------------------------------------------------------------

def test_solar_delta_is_logged_outside_core_hours():
    """
    delta_t_flow_return is computed every loop, not only inside core hours,
    so overnight debug payloads carry it instead of a stale None.
    """
    night = local_ts(22, 58)
    c = make_controller(night)
    set_temps(flow=18.75, ret=19.3125, plate=15.1875, ref=16.25, enclosure=19.0)

    c.loop(now_ts=night)

    assert state["pump_reason"].startswith("sleep")     # confirm it is night
    assert state["delta_t_flow_return"] == 0.56
    assert state["plate_pool_delta"] == -3.56
    assert state["delta_irradiance"] == -1.06
    assert state["pump_on"] is False


def test_solar_delta_cleared_when_sensor_lost():
    now = midday_ts()
    c = make_controller(now)
    set_temps(flow=20.0, ret=20.5, plate=25.0)
    c.loop(now_ts=now)
    assert state["delta_t_flow_return"] == 0.5

    state["temps"]["tReturn"] = None
    c.loop(now_ts=now + 2)
    assert state["delta_t_flow_return"] is None


def test_no_ungated_test_on_first_tick_of_core_hours():
    """
    The test timer is held at 'now' overnight, so the gate fallback starts
    counting from the start of core hours. A cold panel at 08:00 must be
    gated, not forced through by a fallback carried over from last night.
    """
    night = local_ts(22, 58)
    c = make_controller(night, gate_fallback_interval=3600)
    # Cold panel, and no stagnant solar delta, so the gate is the only thing
    # deciding whether the pump runs.
    set_temps(flow=18.75, ret=18.75, plate=15.1875, ref=16.25, enclosure=19.0)

    n = night
    while n < local_ts(7, 59, day_offset=1):
        c.loop(now_ts=n)
        n += 300

    # First tick of core hours.
    c.loop(now_ts=local_ts(8, 0, day_offset=1))
    assert state["test_running"] is False, "gate must not be bypassed at 08:00"
    assert state["pump_on"] is False

    # Still gated ten minutes later, when the slot actually comes due.
    c.loop(now_ts=local_ts(8, 10, day_offset=1))
    assert state["test_running"] is False
    assert state["test_gate_open"] is False
    assert state["pump_reason"].startswith("test skipped")

    # And the fallback now runs from the start of core hours, not from
    # last night — so it forces a test at 09:00, an hour into the day.
    c.loop(now_ts=local_ts(9, 0, day_offset=1))
    assert state["test_running"] is True
    assert state["pump_reason"] == "periodic test"


def test_stagnant_overnight_delta_still_starts_heating_at_core_hours():
    """
    Documents pre-existing behaviour the gate deliberately does NOT change.

    tFlow/tReturn stagnate overnight. If that stagnant delta happens to clear
    delta_threshold_high, the pump starts on the first tick of core hours as
    ordinary heating — the gate governs periodic tests only, never heating.
    The pump then circulates, the readings refresh, and the decision corrects
    itself. These are the real sensor values logged on 2026-09-18 at 22:58.
    """
    night = local_ts(22, 58)
    c = make_controller(night)
    set_temps(flow=18.75, ret=19.3125, plate=15.1875, ref=16.25, enclosure=19.0)

    n = night
    while n < local_ts(7, 59, day_offset=1):
        c.loop(now_ts=n)
        n += 300
    assert state["pump_on"] is False, "no heating overnight"

    c.loop(now_ts=local_ts(8, 0, day_offset=1))
    assert state["pump_on"] is True
    assert state["pump_reason"].startswith("solar heating")
    assert state["test_running"] is False, "heating, not a periodic test"

    # Once circulating, a real (low) delta stops it again.
    state["temps"]["tReturn"] = 18.8125           # delta now 0.06 < 0.1
    c.loop(now_ts=local_ts(8, 2, day_offset=1))
    assert state["pump_on"] is False
    assert state["pump_reason"].startswith("insufficient gain")


def test_holiday_mode_also_holds_the_test_timer():
    now = midday_ts()
    c = make_controller(now)
    set_temps(flow=20.0, ret=20.0, plate=25.0)   # gate wide open
    state["manual_disabled"] = True

    c.loop(now_ts=now)
    c.loop(now_ts=now + 600)
    assert state["test_running"] is False
    assert state["pump_reason"] == "holiday mode"

    # Coming off holiday, the first test is a full interval away.
    state["manual_disabled"] = False
    c.loop(now_ts=now + 602)
    assert state["test_running"] is False
    c.loop(now_ts=now + 602 + 600)
    assert state["test_running"] is True


def test_safety_chain_still_wins_over_gate():
    """Low water stops the pump whatever the gate says."""
    now = midday_ts()
    c = make_controller(now)
    set_temps(flow=20.0, ret=20.0, plate=25.0)   # gate wide open
    state["water_level_ok"] = False

    c.loop(now_ts=now + 600)

    assert state["pump_on"] is False
    assert state["pump_reason"] == "dry run protect"
    assert state["test_running"] is False


# -------------------------------------------------------------------------
# Injected-clock consistency
# -------------------------------------------------------------------------

def test_injected_clock_is_used_for_publish_bookkeeping():
    """
    Every timestamp the controller stamps must come from the clock passed to
    loop(), not from time.time().

    _set_pump used to stamp _last_publish with the real clock while
    _check_publish compared it against the injected 'now'. Whenever the two
    disagreed — the GUI harness's day/night time offset, or the fake clock
    these tests drive — the gap instantly exceeded publish_interval and every
    reason change was followed by a spurious second full publish carrying the
    same pump_reason. On the Pico both clocks are the same value, so this never
    showed up in production, only in simulation.
    """
    now = midday_ts()
    c = make_controller(now, publish_interval=30)
    set_temps(flow=20.0, ret=20.0, plate=20.2)

    c.loop(now_ts=now)

    # Stamped from the injected clock, so _check_publish sees no elapsed time.
    assert c._last_publish == now
    debug_before = [p for t, p in c.network.mqtt.published if t == "debug"]

    # A reason change publishes exactly once, not twice.
    c.loop(now_ts=now + 1)
    debug_after = [p for t, p in c.network.mqtt.published if t == "debug"]
    assert len(debug_after) - len(debug_before) <= 1


def test_published_local_time_follows_injected_clock():
    """
    The debug payload's local_time and in_core_hours must describe the clock
    the decision was made on. publish_state() read time.time() directly, so in
    the GUI harness's night mode it reported the real hour while the controller
    was deciding on the simulated one.
    """
    now = local_ts(23)                      # simulated night
    c = make_controller(now)
    set_temps(flow=20.0, ret=20.0, plate=20.2)

    c.loop(now_ts=now)
    c.publish_state(force_all=True)

    debug = json.loads([p for t, p in c.network.mqtt.published if t == "debug"][-1])
    assert debug["local_time"] == "23:00"
    assert debug["in_core_hours"] is False
    assert debug["pump_reason"] == "sleep (hour 23)"
