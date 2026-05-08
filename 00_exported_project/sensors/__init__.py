from .temperature import TemperatureSensor
from .water_level import WaterLevelSensor
from .button import Button
from config import rom_to_label

class Sensors:
    def __init__(self, temp_pin, level_pin, button_pin, debug=True):
        # Initialize individual sensors
        self.temperature = TemperatureSensor(temp_pin)
        self.water_level = WaterLevelSensor(level_pin)
        self.button = Button(button_pin)

        # Optionally print debug info
        if debug:
            self.print_debug()

    def print_debug(self):
        # --- Temperature sensors ---
        print("DEBUG: Found temperature sensors:")
        for rom in self.temperature.ds_sensor.roms:
            if isinstance(rom, (bytes, bytearray)):
                rom_hex = "".join("{:02x}".format(b) for b in rom)
            else:
                rom_hex = str(rom)
            label = rom_to_label.get(rom_hex, f"unknown_{rom_hex}")
            print(f"  ROM {rom_hex} → {label}")

        # --- Water level sensor ---
        level_state = self.water_level.read()
        print(f"DEBUG: Water level sensor initial state: {'Wet' if level_state else 'Dry'}")

        # --- Button ---
        button_state = self.button.is_pressed()
        print(f"DEBUG: Button initial state: {'Pressed' if button_state else 'Released'}")
