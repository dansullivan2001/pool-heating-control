# test_sensors_wifi_gui.py

import time
import tkinter as tk
from status_led import StatusLED
from status_led import DesktopStatusLED
from state import state
from sensors.temperature import TemperatureSensor
from sensors.water_level import WaterLevelSensor
from network import Network
from mocks.mock_hardware_gui import MockHardwareGUI
from mocks.mock_hardware import MockDS18X20, MockOneWire, MockPin
from mocks import mock_hardware
from config import PIN_TEMPS, PIN_WATER_LEVEL, rom_to_label

# ---------- Setup GUI ----------
root = tk.Tk()
gui = MockHardwareGUI(root)
mock_hardware.gui = gui  # make GUI accessible to mocks

# Status LED on pin "led" in GUI
led_pin = "led"  # matches the branch we added in MockPin.value()
mock_hardware.MockPin.OUT  # optional for clarity
status_led = DesktopStatusLED(pin_num=led_pin, state_ref=state)
status_led.led = mock_hardware.MockPin("led", mode=mock_hardware.MockPin.OUT, gui=gui)

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
temperature_sensor.ds_sensor = TestMockDS18X20(
    MockOneWire(MockPin(PIN_TEMPS)), gui=gui
)

# Attach GUI to water level pin
water_level_sensor.pin.gui = gui

# Inject fake ROMs (can be toggled via checkbox)
gui.fake_roms = [
    "11111111111111",
    "28206f87007e6fc7",
    "2874c18700153578",
    "28ee28e31216013e",
]

def toggle_fake_roms(*args):
    if gui.use_fake_roms.get():
        temperature_sensor.ds_sensor.roms = gui.fake_roms
    else:
        temperature_sensor.ds_sensor.roms = list(rom_to_label.keys())
    print("Toggling fake ROMs:", gui.use_fake_roms.get())
    print("Current ROMs:", temperature_sensor.ds_sensor.roms)

gui.use_fake_roms.trace_add("write", toggle_fake_roms)

# ---------- Initialize network ----------
network = Network()                 
network.mqtt.client.loop_start()  # ✅ MQTT background thread

gui.wifi = network.wifi
network.wifi.wlan.gui = gui
network.connect()                   # connect WiFi + MQTT

# ---------- Update loop ----------
def update_loop():

    # Update LED non-blocking
    status_led.update()


    # --- WiFi / MQTT housekeeping ---
    network.mqtt.loop()
    network.mqtt.watchdog()
    print("WiFi connected:", network.wifi.is_connected())

    # --- Read sensors ---
    temps = {}
    for rom in temperature_sensor.ds_sensor.scan():
        label = rom_to_label.get(rom, rom)

        if label and gui.disable_sensors.get(rom) and gui.disable_sensors[rom].get():
            print(f"⚠️ Sensor {label} disabled via GUI.")
            temps[rom] = None
            continue

        temp = temperature_sensor.ds_sensor.read_temp(rom)
        temps[rom] = temp

    level = water_level_sensor.read()

    # --- Update GUI + publish MQTT ---
    print("\nSensor readings:")
    for rom, value in temps.items():
        label = rom_to_label.get(rom, rom)
        lbl_widget = gui.labels.get(rom)

        if value is None:
            if lbl_widget:
                lbl_widget.config(text=f"{label}: ERROR", fg="red")
            print(f"{label}: ERROR", end=" | ")
        else:
            if lbl_widget:
                lbl_widget.config(text=f"{label}: {value:.2f} °C", fg="black")
            print(f"{label}: {value:.2f} °C", end=" | ")

            # publish valid readings
            topic = f"{network.mqtt.aio_username}/feeds/{label}"
            network.mqtt.publish(topic, value)

        slider_widget = gui.sliders.get(rom)
        if slider_widget:
            slider_widget.config(state="normal" if value is not None else "disabled")

    print(f"Water Level: {'Present' if level else 'Dry'}")
    topic_level = f"{network.mqtt.aio_username}/feeds/water_level"
    network.mqtt.publish(topic_level, int(level))

    # Sensors OK / disconnected
    state['sensors_ok'] = all(
        not gui.disable_sensors.get(rom, tk.BooleanVar(value=False)).get() 
        for rom in temperature_sensor.ds_sensor.scan()
    )
    state['disconnected_sensors'] = [
        rom for rom in temperature_sensor.ds_sensor.scan() 
        if gui.disable_sensors.get(rom) and gui.disable_sensors[rom].get()
    ]

    # MQTT status
    state['mqtt_connected'] = network.mqtt.connected

    # Optional: simulate critical error manually
    # state['critical_error'] = True


    # repeat every 500 ms
    root.after(500, update_loop)

# ---------- Start the periodic update ----------
root.after(100, update_loop)
root.mainloop()
