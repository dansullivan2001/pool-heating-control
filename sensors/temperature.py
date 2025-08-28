# sensors/temperature.py
__version__ = "0.0.1"

import time
from config import rom_to_label

try:
    import machine, onewire, ds18x20
except ImportError:
    from mocks.mock_hardware import MockPin as Pin, MockOneWire as OneWire, MockDS18X20 as DS18X20

class TemperatureSensor:
    def __init__(self, pin, gui=None):
        self.ds_pin = Pin(pin)
        self.ds_sensor = DS18X20(OneWire(self.ds_pin))
        self.roms = self.ds_sensor.scan()

        if gui and hasattr(self.ds_sensor, "attach_gui"):
            self.ds_sensor.attach_gui(gui)

    def read(self):
        self.ds_sensor.convert_temp()
        time.sleep(0.1)
 #       return {rom_to_label.get(rom, rom) : self.ds_sensor.read_temp(rom) for rom in self.roms}
        readings = {}
        for rom in self.ds_sensor.roms:
            label = rom_to_label.get(rom)
            if label is None:
                # ROM not recognized
                print(f"⚠️ Warning: Unknown ROM {rom} detected!")
                label = rom  # fallback so we still return something
            readings[label] = self.ds_sensor.read_temp(rom)
        return readings