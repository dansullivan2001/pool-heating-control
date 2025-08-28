# sensors/water_level.py
__version__ = "0.0.1"

import time

try:
    import machine
except ImportError:
    from mocks.mock_hardware import MockPin as Pin
else:
    Pin = machine.Pin


class WaterLevelSensor:
    def __init__(self, pin, debounce_ms=50, wet_delay=1000, dry_delay=1000, gui=None):
        self.pin = Pin(pin)

        if gui and hasattr(self.pin, "attach_gui"):
            self.pin.attach_gui(gui)

        

        self.last_state = self.pin.value()
        self.stable_state = self.last_state
        self.last_time = time.time() * 1000
        self.state_changed_at = self.last_time
        self.debounce_ms = debounce_ms
        self.wet_delay = wet_delay
        self.dry_delay = dry_delay


    def read(self):
        now = time.time() * 1000
        current_state = self.pin.value()   

        # Get current raw state from pin or GUI
        if hasattr(self.pin, "gui") and self.pin.gui is not None:
            current_state = 1 if self.pin.gui.water_present() else 0
        else:
            current_state = self.pin.value()

        # ---------- Debounce ----------
        if current_state != self.last_state:
            if now - self.last_time > self.debounce_ms:
                self.last_state = current_state
                self.state_changed_at = now
            self.last_time = now
        else:
            self.last_time = now

        # ---------- Wet/Dry delay ----------
        if current_state != self.stable_state:
            elapsed = now - self.state_changed_at
            if (current_state == 1 and elapsed > self.wet_delay) or (current_state == 0 and elapsed > self.dry_delay):
                self.stable_state = current_state

        return self.stable_state
