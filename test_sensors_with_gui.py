# test_sensors_with_gui.py

import time
import tkinter as tk
from sensors.temperature import TemperatureSensor
from sensors.water_level import WaterLevelSensor
from mocks.mock_hardware_gui import MockHardwareGUI
from mocks.mock_hardware import MockDS18X20, MockOneWire, MockPin
from mocks import mock_hardware
from config import PIN_TEMPS, PIN_WATER_LEVEL
from config import rom_to_label

# ---------- Setup GUI ----------
root = tk.Tk()
gui = MockHardwareGUI(root)
mock_hardware.gui = gui  # make GUI accessible to mocks

# ---------- Patch DS18X20 to use GUI ----------
class TestMockDS18X20(MockDS18X20):
    def scan(self):
        # Use fake ROMs if checkbox is selected
        if gui.use_fake_roms.get():
            return gui.fake_roms
        return self.roms

    def read_temp(self, sensor_rom):
        if sensor_rom in gui.temp_vars:
            return gui.get_temperature(sensor_rom)
        else:
            return None

# ---------- Initialize sensors ----------
temperature_sensor = TemperatureSensor(PIN_TEMPS)
water_level_sensor = WaterLevelSensor(PIN_WATER_LEVEL)

# Attach GUI-aware mocks
temperature_sensor.ds_sensor = TestMockDS18X20(MockOneWire(MockPin(PIN_TEMPS)), gui=gui)

# Attach GUI to water level pin
water_level_sensor.pin.gui = gui

# Inject fake ROMs (can be toggled via checkbox)
gui.fake_roms = ["11111111111111", "28206f87007e6fc7", "2874c18700153578", "28ee28e31216013e"]

# Callback to switch ROMs when checkbox is toggled
def toggle_fake_roms(*args):
    if gui.use_fake_roms.get():
        # Swap in the fake ROMs
        temperature_sensor.ds_sensor.roms = gui.fake_roms
        # Add GUI sliders for the fake ROMs
    
    else:
        # Revert to original ROMs
        temperature_sensor.ds_sensor.roms = list(rom_to_label.keys())
    print("Toggling fake ROMs:", gui.use_fake_roms.get())
    print("Current ROMs:", temperature_sensor.ds_sensor.roms)



gui.use_fake_roms.trace_add("write", toggle_fake_roms)

# ---------- Update loop ----------
def update_loop():
    temps = {}
    for rom in temperature_sensor.ds_sensor.scan():
        label = rom_to_label.get(rom, rom)

        if label and gui.disable_sensors.get(rom) and gui.disable_sensors[rom].get():
            print(f"⚠️ Sensor {label} disabled via GUI.")
            temps[rom] = None
            continue

        temp = temperature_sensor.ds_sensor.read_temp(rom)
        if label is None:
            print(f"⚠️ Warning: Unknown ROM {rom} detected!")
            temp = None
        #else:
        temps[rom] = temp

    level = water_level_sensor.read()

    print("\nSensor readings:")
    for rom, value in temps.items():
        label = rom_to_label.get(rom, rom)
        if rom not in gui.labels:
            print(f"{rom}: (no GUI widget)", end=" | ")
            continue
        lbl_widget = gui.labels[rom]
        if value is None:
            lbl_widget.config(text=f"{label}: ERROR", fg="red")
            print(f"{label}: ERROR (unrecognized ROM)", end=" | ")
        else:
            lbl_widget.config(text=f"{label}: {value:.2f} °C", fg="black")
            print(f"{label}: {value:.2f} °C", end=" | ")
        slider_widget = gui.sliders.get(rom)
        if slider_widget:
            if value is None:
                slider_widget.config(state="disabled")
            else:
                slider_widget.config(state="normal")
    print(f"Water Level: {'Present' if level else 'Dry'}")

    # repeat every 500 ms
    root.after(500, update_loop)

# Start the periodic update
root.after(100, update_loop)
root.mainloop()
