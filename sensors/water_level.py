# sensors/water_level.py
__version__ = "0.1.1"

import time

try:
    import machine
    Pin = machine.Pin
except ImportError:
    from mocks.mock_hardware import MockPin as Pin


class WaterLevelSensor:
    """
    Capacitive water level sensor with debounce and confirmation delays.

    Two-stage filtering prevents false triggers:
      1. Debounce (debounce_ms):  ignores transitions shorter than this —
         filters electrical noise and switch bounce on the raw signal.
      2. Confirmation delay:      a state change is only accepted as stable
         after the new state has been held for wet_delay or dry_delay ms.
         The dry_delay is intentionally longer than wet_delay so the pump
         is never re-enabled until water presence is well confirmed.

    read() is non-blocking and safe to call every main-loop iteration.
    Returns 1 (wet/water present) or 0 (dry/no water).
    """

    def __init__(self, pin, debounce_ms=50, wet_delay=1000, dry_delay=3000, gui=None):
        """
        Args:
            pin:          GPIO pin number connected to the sensor output.
            debounce_ms:  minimum stable time (ms) before a raw edge is accepted.
            wet_delay:    ms the signal must be HIGH before reporting "wet".
            dry_delay:    ms the signal must be LOW before reporting "dry".
                          Longer than wet_delay for fail-safe behaviour:
                          we're slow to declare water present, fast to declare it gone.
            gui:          optional GUI object for desktop simulation.
        """
        self.pin          = Pin(pin, Pin.IN)
        self.debounce_ms  = debounce_ms
        self.wet_delay    = wet_delay
        self.dry_delay    = dry_delay

        if gui and hasattr(self.pin, "attach_gui"):
            self.pin.attach_gui(gui)

        # Initialise from the actual pin state so we don't start with a stale value
        raw               = self._raw_value()
        self._last_raw    = raw       # last raw sample (for debounce edge detection)
        self._stable      = raw       # last debounce-confirmed state
        self._stable_since = self._now_ms()   # when _stable was last confirmed
        self.stable_state = raw       # output: the delay-filtered stable value

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def read(self):
        """
        Sample the sensor and return the delay-filtered stable state.
        Non-blocking. Returns 1 (wet) or 0 (dry).
        """
        now       = self._now_ms()
        raw       = self._raw_value()

        # --- Stage 1: Debounce ---
        # Accept a raw edge only after it has been stable for debounce_ms.
        if raw != self._last_raw:
            # Edge detected — start / restart the debounce timer
            self._last_raw    = raw
            self._edge_time   = now
        elif raw != self._stable:
            # Same raw value as last sample, but differs from confirmed stable.
            # Check if it has been stable long enough to accept.
            if not hasattr(self, "_edge_time"):
                self._edge_time = now
            if now - self._edge_time >= self.debounce_ms:
                self._stable       = raw
                self._stable_since = now

        # --- Stage 2: Confirmation delay ---
        # Only propagate to output after the confirmed state has been held
        # for the appropriate delay (wet or dry).
        if self._stable != self.stable_state:
            elapsed = now - self._stable_since
            delay   = self.wet_delay if self._stable == 1 else self.dry_delay
            if elapsed >= delay:
                self.stable_state = self._stable

        return self.stable_state

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _raw_value(self):
        """Read the raw pin value, accounting for GUI override in simulation."""
        if hasattr(self.pin, "gui") and self.pin.gui is not None:
            return 1 if self.pin.gui.water_present() else 0
        return 1 - self.pin.value()  # active-low: LOW = water present

    @staticmethod
    def _now_ms():
        if hasattr(time, "ticks_ms"):
            return time.ticks_ms()
        return int(time.time() * 1000)