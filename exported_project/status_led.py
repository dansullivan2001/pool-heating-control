# status_led.py
import time
import sys
from state import state as shared_state


# try to import real Pin (Pico), otherwise use mock
try:
    from machine import Pin
except Exception:
    # in tests the mock provides MockPin with a compatible API
    from mocks.mock_hardware import MockPin as Pin

# Patterns are a list of (value, duration_ms).
# value: 1 -> LED on, 0 -> LED off
PATTERNS = {
    "ok":           [(1, 1500),  (0, 1500)],   # one short blink every 2s (200ms on)
    "mqtt_offline": [(1, 250),  (0, 250)],    # 0.5s cycle (fast flash)
    "sensor_missing":[(1,100), (0,100)],     # long on, short off
    "critical":     [(1,1000), (0,1000)],     # steady slow blink for critical
}

# Pattern priority - first match wins.
PRIORITY = ["critical", "sensor_missing", "mqtt_offline", "ok"]

class StatusLED:
    def __init__(self, pin_num=25, state_ref=None):
        self.state = state_ref if state_ref is not None else shared_state
        # create pin in a way that's compatible with mock and machine.Pin
        try:
            self.led = Pin(pin_num, Pin.OUT)
        except Exception:
            # mock pins may accept only the pin number
            self.led = Pin(pin_num)

        # start with OK pattern
        self.pattern_name = "ok"
        self.pattern = PATTERNS[self.pattern_name]
        self.index = 0
        self.next_ms = time.ticks_add(time.ticks_ms(), self.pattern[0][1])
        # set initial LED state
        try:
            self.led.value(self.pattern[0][0])
        except Exception:
            pass

    def _choose_pattern_name(self):
        s = self.state
        if s.get("critical_error"):
            return "critical"
        if (not s.get("sensors_ok", True)) or (s.get("disconnected_sensors")):
            return "sensor_missing"
        if not s.get("mqtt_connected", True):
            return "mqtt_offline"
        return "ok"

    def _set_pattern(self, name):
        self.pattern_name = name
        self.pattern = PATTERNS[name]
        self.index = 0
        now = time.ticks_ms()
        self.next_ms = time.ticks_add(now, self.pattern[0][1])
        # immediately apply first state
        try:
            self.led.value(self.pattern[0][0])
        except Exception:
            pass

    def update(self):
        """
        Call this frequently (every loop iteration). Non-blocking.
        Handles switching patterns automatically based on shared state flags.
        """
        # pick desired pattern based on priority
        desired = self._choose_pattern_name()
        if desired != self.pattern_name:
            self._set_pattern(desired)
            return

        # advance pattern when its time is reached
        now = time.ticks_ms()
        if time.ticks_diff(now, self.next_ms) >= 0:
            self.index = (self.index + 1) % len(self.pattern)
            state_val, duration = self.pattern[self.index]
            try:
                self.led.value(state_val)
            except Exception:
                pass
            self.next_ms = time.ticks_add(now, duration)

class DesktopStatusLED(StatusLED):
    def __init__(self, *args, **kwargs):
        import sys
        # override ticks_* if not running on MicroPython
        if sys.implementation.name != "micropython":
            import time
            # monkey-patch time module functions used by StatusLED
            time.ticks_ms   = lambda: int(time.time() * 1000)
            time.ticks_add  = lambda t, d: t + d
            time.ticks_diff = lambda a, b: a - b
        # now call parent init
        super().__init__(*args, **kwargs)

