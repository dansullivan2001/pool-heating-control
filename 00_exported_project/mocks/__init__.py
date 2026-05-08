import config
import tkinter as tk
from .mock_hardware import MockPin as Pin, MockOneWire as OneWire, MockDS18X20 as DS18X20
from .mock_hardware_gui import MockHardwareGUI
# from .test_gui import TestGUI

class MockEnvironment:
    def __init__(self, gui):
        # create a single Tk root
        self.gui = gui
        self.gui = MockHardwareGUI(self.gui)

        # map real GPIO numbers to mock strings
        gpio_to_mock = {
            config.PIN_PUMP: "pump",
            config.PIN_WATER_LEVEL: "water_level",
            config.PIN_TEMPS: "temp",
            config.PIN_BUTTON: "button"
        }

        # create fake pins
        self.pump_pin = Pin(gpio_to_mock[config.PIN_PUMP], Pin.OUT, gui=self.gui)
        self.water_level_pin = Pin(gpio_to_mock[config.PIN_WATER_LEVEL], Pin.IN, gui=self.gui)
        self.temp_pin = Pin(gpio_to_mock[config.PIN_TEMPS], Pin.IN, gui=self.gui)
        self.button_pin = Pin(gpio_to_mock[config.PIN_BUTTON], Pin.IN, gui=self.gui)

        # fake OneWire and DS18X20
        self.onewire = OneWire(gpio_to_mock[config.PIN_TEMPS])
        self.ds18x20 = DS18X20(self.onewire)
