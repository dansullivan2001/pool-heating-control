# status_led.py
__version__ = "0.2.0"

import time
import sys
from state import state as shared_state

try:
    from machine import Pin
except ImportError:
    from mocks.mock_hardware import MockPin as Pin


# ---------------------------------------------------------------------------
# Pattern definitions
# Each pattern is a list of (led_value, duration_ms) steps, looped forever.
#   led_value: 1 = on, 0 = off
#
# Priority (highest first) is defined by PRIORITY list below.
# _choose_pattern_name() walks it in order — first match wins.
# ---------------------------------------------------------------------------

PATTERNS = {
    "critical":        [(1, 1000), (0, 1000)],   # slow blink  — unrecoverable error
    "sensor_missing":  [(1, 1500), (0,  100)],   # long on / short off — sensor fault
    "mqtt_offline":    [(1,  250), (0,  250)],   # fast flash  — network issue
    "ok":              [(1,  200), (0, 2000)],   # heartbeat   — all good
}

PRIORITY = ["critical", "sensor_missing", "mqtt_offline", "ok"]


# ---------------------------------------------------------------------------
# Tick helpers
# Centralised here so StatusLED never touches the global time module.
# On MicroPython these delegate to time.ticks_*; on CPython they use
# time.time() arithmetic instead.
# ---------------------------------------------------------------------------

def _ticks_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.time() * 1000)

def _ticks_add(t, delta):
    if hasattr(time, "ticks_add"):
        return time.ticks_add(t, delta)
    return t + delta

def _ticks_diff(a, b):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(a, b)
    return a - b


# ---------------------------------------------------------------------------
# StatusLED
# ---------------------------------------------------------------------------

class StatusLED:
    """
    Non-blocking status LED controller driven by shared state flags.

    Call update() every main-loop iteration. It reads state, selects the
    highest-priority pattern, and advances the blink sequence as needed.
    Never blocks or sleeps.

    Pattern priority (highest first):
      critical         — unrecoverable software error
      sensor_missing   — any sensor disconnected or enclosure sensor absent
      mqtt_offline     — MQTT not connected
      ok               — everything healthy (heartbeat blink)
    """

    def __init__(self, pin_num=25, state_ref=None):
        self.state = state_ref if state_ref is not None else shared_state

        try:
            self.led = Pin(pin_num, Pin.OUT)
        except Exception:
            self.led = Pin(pin_num)   # mock pins may not accept mode arg

        # Start in OK pattern — _choose_pattern_name() will correct this
        # on the first update() call if needed.
        self.pattern_name = "ok"
        self.pattern      = PATTERNS["ok"]
        self.index        = 0
        self.next_ms      = _ticks_add(_ticks_ms(), self.pattern[0][1])
        self._led_set(self.pattern[0][0])

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def update(self):
        """
        Advance the LED state machine. Call every main-loop iteration.
        Non-blocking.
        """
        desired = self._choose_pattern_name()
        if desired != self.pattern_name:
            self._set_pattern(desired)
            return

        now = _ticks_ms()
        if _ticks_diff(now, self.next_ms) >= 0:
            self.index = (self.index + 1) % len(self.pattern)
            val, duration = self.pattern[self.index]
            self._led_set(val)
            self.next_ms = _ticks_add(now, duration)

    def current_pattern(self):
        """Return the name of the currently active pattern (useful for debug/GUI)."""
        return self.pattern_name

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _choose_pattern_name(self):
        """
        Inspect shared state and return the highest-priority pattern name.

        Conditions checked (in priority order):
          critical       — state["critical_error"] is True
          sensor_missing — any sensor missing OR enclosure sensor absent
                           (enclosure_sensor_missing is a distinct safety flag
                            added in state.py v0.1.0)
          mqtt_offline   — MQTT not connected
          ok             — all clear
        """
        s = self.state

        if s.get("critical_error"):
            return "critical"

        # sensor_missing covers both general sensor faults and the specific
        # case where the enclosure temperature sensor is absent (which is a
        # safety stop, not an overtemp condition).
        sensor_fault = (
            not s.get("sensors_ok", True)
            or bool(s.get("disconnected_sensors"))
            or s.get("enclosure_sensor_missing", False)
        )
        if sensor_fault:
            return "sensor_missing"

        if not s.get("mqtt_connected", True):
            return "mqtt_offline"

        return "ok"

    def _set_pattern(self, name):
        self.pattern_name = name
        self.pattern      = PATTERNS[name]
        self.index        = 0
        self.next_ms      = _ticks_add(_ticks_ms(), self.pattern[0][1])
        self._led_set(self.pattern[0][0])

    def _led_set(self, value):
        try:
            self.led.value(value)
        except Exception:
            pass   # silently ignore — mock or disconnected LED


# ---------------------------------------------------------------------------
# DesktopStatusLED
# ---------------------------------------------------------------------------

class DesktopStatusLED(StatusLED):
    """
    StatusLED subclass for desktop/simulation use.

    Does NOT monkey-patch the global time module. Instead, StatusLED now
    uses module-level _ticks_* helpers that handle CPython automatically,
    so no patching is needed at all. This class exists purely as a named
    import target for the test harness.
    """
    pass