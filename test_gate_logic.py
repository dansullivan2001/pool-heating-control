# test_gate_logic.py
__version__ = "0.1.0"

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


def midday_ts():
    """
    An epoch timestamp that is 12:00 *local* time, so core-hours checks
    (which use time.localtime) pass regardless of the machine's timezone.
    """
    t = time.localtime()
    return time.mktime((t[0], t[1], t[2], 12, 0, 0, t[6], t[7], t[8]))


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
