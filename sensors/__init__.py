# sensors/__init__.py
__version__ = "0.1.0"

from .temperature import TemperatureSensor
from .water_level import WaterLevelSensor
from .button import Button
from config import rom_to_label


class Sensors:
    """
    Aggregates all physical sensors into one object.

    Passed to Controller so it can poll the button.
    Temperature and water level are read directly by main.py on a timed
    interval and written into shared state before controller.loop() runs.
    """

    def __init__(self, temp_pin, level_pin, button_pin, debug=True):
        self.temperature  = TemperatureSensor(temp_pin)
        self.water_level  = WaterLevelSensor(level_pin)
        self.button       = Button(button_pin)

        if debug:
            self._print_debug()

    def _print_debug(self):
        # Temperature sensors are logged by TemperatureSensor.__init__ itself.
        # Water level and button initial states logged here.
        level = self.water_level.read()
        print(f"💧 Water level sensor initial state: {'Wet' if level else 'Dry'}")

        btn = self.button.is_pressed()
        print(f"🔘 Button initial state: {'Pressed' if btn else 'Released'}")