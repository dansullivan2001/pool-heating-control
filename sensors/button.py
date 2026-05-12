# sensors/button.py
__version__ = "0.1.0"

import time

try:
    import machine
    Pin = machine.Pin
except ImportError:
    from mocks.mock_hardware import MockPin as Pin
    class machine:
        Pin = Pin


class Button:
    """
    Debounced momentary push button with edge detection.

    is_pressed() returns True exactly once per physical press — on the
    falling edge (button down) after the debounce period has elapsed.
    It will not return True again until the button is released and
    pressed again.

    Wired with PULL_UP (default): pin reads 1 at rest, 0 when pressed.
    """

    def __init__(self, pin, pull_up=True, debounce_ms=50):
        self.pin          = machine.Pin(
                                pin,
                                machine.Pin.IN,
                                machine.Pin.PULL_UP if pull_up else None
                            )
        self.debounce_ms  = debounce_ms

        # Initialise from actual pin state to avoid a spurious press on boot
        self._last_raw    = self.pin.value()   # last sampled pin value
        self._stable      = self._last_raw     # debounce-confirmed state
        self._edge_time   = self._ticks_ms()   # when the last raw edge was seen
        self._reported    = True               # True = press already reported (or not pressed)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def is_pressed(self):
        """
        Returns True once per physical button press (falling edge, debounced).
        Safe to call every main-loop iteration — non-blocking.
        """
        now = self._ticks_ms()
        raw = self.pin.value()

        # Detect raw edge
        if raw != self._last_raw:
            self._last_raw  = raw
            self._edge_time = now
            # Edge resets the reported flag — we haven't reported this transition yet
            self._reported  = False

        # Only evaluate after debounce period
        if self._ticks_diff(now, self._edge_time) < self.debounce_ms:
            return False

        # Update stable state
        self._stable = raw

        # Report a press exactly once per falling edge (pull-up: pressed = 0)
        if self._stable == 0 and not self._reported:
            self._reported = True
            return True

        return False

    # -------------------------------------------------------------------------
    # Tick helpers — compatible with MicroPython and CPython
    # -------------------------------------------------------------------------

    @staticmethod
    def _ticks_ms():
        if hasattr(time, "ticks_ms"):
            return time.ticks_ms()
        return int(time.time() * 1000)

    @staticmethod
    def _ticks_diff(a, b):
        if hasattr(time, "ticks_diff"):
            return time.ticks_diff(a, b)
        return a - b