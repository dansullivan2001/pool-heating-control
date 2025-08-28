__version__ = "0.0.1"

import time
try:
    import machine
except ImportError:
    from mocks.mock_hardware import MockPin as Pin
    class machine:
        Pin = Pin

class Button:
    def __init__(self, pin, pull_up=True, debounce_ms=50):
        self.pin = machine.Pin(pin, machine.Pin.IN, machine.Pin.PULL_UP if pull_up else None)
        self.debounce_ms = debounce_ms
        self._last_state = self.pin.value()
        self._last_time = time.ticks_ms()

    def is_pressed(self):
        current_state = self.pin.value()
        now = time.ticks_ms()
        if current_state != self._last_state:
            self._last_time = now
            self._last_state = current_state
        elif current_state == 0 and (time.ticks_diff(now, self._last_time) > self.debounce_ms):
            return True
        return False
