# mock_hardware.py
__version__ = "0.0.1"

import tkinter as tk
from mock_hardware_gui import MockHardwareGUI

# create GUI window at import time
root = tk.Tk()
root.geometry("400x300")
gui = MockHardwareGUI(root)

class MockPin:
    OUT = "out"
    IN = "in"

    def __init__(self, pin, mode=IN):
        self.pin = pin
        self.mode = mode
        self._value = 0

    def value(self, v=None):
        if v is None:
            if self.pin == "water_level":
                return 1 if gui.water_present() else 0
            return self._value
        else:
            self._value = v
            if self.mode == MockPin.OUT and self.pin == "pump":
                gui.set_pump_state(bool(v))

class MockOneWire:
    def __init__(self, pin):
        pass

class MockDS18X20:
    def __init__(self, onewire):
        pass

    def scan(self):
        return ["tFlow", "tReturn", "tAmbient", "tEnclosure"]

    def convert_temp(self):
        pass

    def read_temp(self, sensor):
        return gui.get_temperature(sensor)
