# sensors/temperature.py
__version__ = "0.0.1"

import time
# sensors/temperature.py
try:
    import machine, onewire, ds18x20
except ImportError:
    from mock_hardware import MockPin as Pin, MockOneWire as OneWire, MockDS18X20 as DS18X20

class TemperatureSensor:
    def __init__(self, pin):
        self.ds_pin = Pin(pin)
        self.ds_sensor = DS18X20(OneWire(self.ds_pin))
        self.roms = self.ds_sensor.scan()

    def read(self):
        self.ds_sensor.convert_temp()
        time.sleep(0.1)
        return {rom: self.ds_sensor.read_temp(rom) for rom in self.roms}
