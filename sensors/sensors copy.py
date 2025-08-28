# sensors.py
__version__ = "0.0.1"

import time
from config import PIN_TEMPS, PIN_WATER_LEVEL
from config import rom_to_label

try:
    import machine, onewire, ds18x20
except ImportError:
    from mocks.mock_hardware import MockPin as Pin
    from mocks.mock_hardware import MockOneWire as OneWire
    from mocks.mock_hardware import MockDS18X20 as DS18X20

    class machine:
        Pin = Pin

    class onewire:
        OneWire = OneWire

    class ds18x20:
        DS18X20 = DS18X20


class SensorManager:
    def __init__(self, temp_pin=PIN_TEMPS, water_pin=PIN_WATER_LEVEL):
        self.ds_pin = machine.Pin(temp_pin)
        self.ds_sensor = ds18x20.DS18X20(onewire.OneWire(self.ds_pin))
        self.roms = self.ds_sensor.scan()
        self.water_pin = machine.Pin(water_pin, machine.Pin.IN)

        print("DEBUG: Found sensors:")
        for rom in self.roms:
            rom_hex = "".join("{:02x}".format(b) for b in rom)
            label = rom_to_label.get(rom_hex, f"unknown_{rom_hex}")
            print(f"  ROM {rom_hex} → {label}")

    def read_temps(self):
        """Read all sensors and return dict {label: temp}"""
        self.ds_sensor.convert_temp()
        time.sleep(0.1)

        temps = {}
        for rom in self.roms:
            rom_hex = "".join("{:02x}".format(b) for b in rom)  # convert bytes -> hex string
            label = rom_to_label.get(rom_hex, f"unknown_{rom_hex}")
            temps[label] = self.ds_sensor.read_temp(rom)

        if hasattr(self.ds_sensor, "advance"):
            self.ds_sensor.advance()  # progress mock simulation

        return temps
