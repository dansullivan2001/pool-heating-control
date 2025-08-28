# mock_hardware.py
__version__ = "0.0.1"

import tkinter as tk
from mocks.mock_hardware_gui import MockHardwareGUI
from config import rom_to_label

# create GUI window at import time
#root = tk.Tk()
#root.geometry("400x300")
#gui = MockHardwareGUI(root)

gui = None  # to be set externally

class MockPin:
    OUT = "out"
    IN = "in"

    def __init__(self, pin, mode=IN, gui=None):
        self.pin = pin
        self.mode = mode
        self._value = 0
        self.gui = gui

#    def attach_gui(self, gui):
#        self.gui = gui

    def value(self, v=None):
        if v is None:
            if self.pin == "water_level" and self.gui:
                return 1 if self.gui.water_present() else 0
            return self._value
        else:
            self._value = v
            if self.mode == MockPin.OUT and self.pin == "pump" and self.gui:
                gui.set_pump_state(bool(v))

class MockOneWire:
    def __init__(self, pin):
        pass

class MockDS18X20:
    def __init__(self, onewire, roms=None, gui=None):
        """
        :param onewire: ignored, just for interface
        :param roms: optional list of ROMs to simulate
        :param gui: optional GUI instance
        """
        # If roms provided, use them; otherwise use real config ROMs
        if roms is not None:
            self.roms = roms
        else:
            self.roms = list(rom_to_label.keys())  # default to realistic sensors

        self.gui = gui

    def attach_gui(self, gui):
        self.gui = gui
        pass

    def scan(self):
        if self.gui and getattr(self.gui, "use_fake_roms", None):
            return self.gui.fake_roms
        return self.roms

    def convert_temp(self):
        pass

    def read_temp(self, sensor):
        if self.gui:
            return self.gui.get_temperature(sensor)
        return 20.0  # fallback default

# in mocks/mock_hardware.py

class MockWiFi:
    """Simulate WiFi connection state"""
    def __init__(self):
        self.connected = True   # start "online"
        self.gui = None

    def connect(self, ssid=None, password=None):
        print("🔌 [MOCK] WiFi connecting...")
        self.connected = True
        if self.gui:
            self.gui.set_wifi_state(True)
        print("✅ [MOCK] WiFi connected")
        return True

    def disconnect(self):
        print("🔌 [MOCK] WiFi disconnected")
        self.connected = False
        if self.gui:
            self.gui.set_wifi_state(False)

    def is_connected(self):
        if self.gui:
            return self.gui.get_wifi_state()
        return self.connected
    
    # Alias to match WiFiManager expectation
    isconnected = is_connected
