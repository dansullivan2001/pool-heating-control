# test_main_controller_gui.py

import time
import tkinter as tk
from status_led import DesktopStatusLED
from state import state
from sensors.temperature import TemperatureSensor
from sensors.water_level import WaterLevelSensor
from network import Network
from mocks.mock_hardware_gui import MockHardwareGUI
from mocks.mock_hardware import MockDS18X20, MockOneWire, MockPin, gui as mock_gui
from controller.controller import Controller
from config import PIN_TEMPS, PIN_WATER_LEVEL, rom_to_label, CONFIG

# ---------- Setup GUI ----------
root = tk.Tk()
gui = MockHardwareGUI(root)
mock_gui = gui  # assign global for mocks

# LED managed separately by status_led
status_led = DesktopStatusLED("led", state_ref=state)
#status_led.led = MockPin("led", mode=MockPin.OUT, gui=gui)
status_led.led.value = lambda val: gui.set_led_state(bool(val))

# ---------- Patch DS18X20 ----------
class TestMockDS18X20(MockDS18X20):
    def scan(self):
        return gui.fake_roms if gui.use_fake_roms.get() else self.roms

    def read_temp(self, sensor_rom):
        return gui.get_temperature(sensor_rom) if sensor_rom in gui.temp_vars else None

# ---------- Sensors ----------
temperature_sensor = TemperatureSensor(PIN_TEMPS)
water_level_sensor = WaterLevelSensor(PIN_WATER_LEVEL)

temperature_sensor.ds_sensor = TestMockDS18X20(MockOneWire(MockPin(PIN_TEMPS)), gui=gui)
water_level_sensor.pin.gui = gui

# Default fake ROMs
gui.fake_roms = [
    "11111111111111",
    "28206f87007e6fc7",
    "2874c18700153578",
    "28ee28e31216013e",
]

def toggle_fake_roms(*args):
    temperature_sensor.ds_sensor.roms = (
        gui.fake_roms if gui.use_fake_roms.get() else list(rom_to_label.keys())
    )
gui.use_fake_roms.trace_add("write", toggle_fake_roms)

# ---------- Network ----------
network = Network()
network.mqtt.client.loop_start()
gui.wifi = network.wifi
network.wifi.wlan.gui = gui
network.connect()

# ---------- Controller ----------
controller = Controller(
    network=network,
    config={
        "pump_test_interval": CONFIG["pump_test_interval"],
        "min_temp_delta": CONFIG["min_temp_delta"],
        "max_enclosure_temp": CONFIG["max_enclosure_temp"],
        "publish_interval": CONFIG["publish_interval"],
        "manual_override_duration": CONFIG["manual_override_duration"],
    }
)
gui.bind_state(controller.state)


def soft_restart():
    print("💥 Simulated Pico restart triggered")

    # Reset state dict
    for k in state.keys():
        if isinstance(state[k], bool):
            state[k] = False
        elif isinstance(state[k], (int, float)):
            state[k] = 0
        elif isinstance(state[k], list):
            state[k] = []
        elif isinstance(state[k], dict):
            state[k] = {}
        else:
            state[k] = None

    # Reset controller timers
    controller._last_publish = 0
    controller._last_test = time.time()
    controller._manual_override_start = None

    # Reset WiFi + MQTT
    network.wifi.disconnect()
    network.mqtt.disconnect()
    network.mqtt.last_ping = time.time()
    network.connect()

    # Reset GUI indicators
    gui.wifi_var.set(network.wifi.is_connected())
    gui.led_state.set(False)
    gui.pump_state.set("OFF")

def pump_off_hook():
    controller._set_pump(False, reason="watchdog restart")

network.soft_restart_callback = soft_restart
network.pre_restart_hook = pump_off_hook


# ---------- Update loop ----------
def update_loop():

    wifi_up = gui.wifi_connected()
    state["wifi_connected"] = wifi_up

    if not wifi_up and network.mqtt.connected:
        network.mqtt.disconnect()
    else:
        # MQTT housekeeping
        network.mqtt.loop()
        network.mqtt.watchdog()

    # --- Simulated sensor read ---
    temps = {}
    for rom in temperature_sensor.ds_sensor.scan():
        label = rom_to_label.get(rom, rom)
        if gui.disable_sensors.get(rom) and gui.disable_sensors[rom].get():
            temps[label] = None
        else:
            temps[label] = temperature_sensor.ds_sensor.read_temp(rom)

    water_ok = water_level_sensor.read()

    # --- Push into state ---
    state["temps"] = temps
    state["water_level_ok"] = bool(water_ok)
    state["sensors_ok"] = all(v is not None for v in temps.values())
    state["disconnected_sensors"] = [l for l, v in temps.items() if v is None]
    state["mqtt_connected"] = network.mqtt.connected
    state["critical_error"] = state.get("last_error") is not None
    state["wifi_connected"] = gui.wifi_connected()


    # state["manual_override"] = gui.button_pressed()

    # --- Manual override button ---
    if gui.button_pressed():
        if controller.state["manual_override"]:
            # Cancel active override
            controller.state["manual_override"] = False
            controller._manual_override_start = None
            controller._set_pump(False, reason="manual override cancelled by button")
        else:
            # Start a new override
            controller.state["manual_override"] = True
            controller._manual_override_start = time.time()

    # --- Compute time to next periodic test ---
    now = time.time()
    interval = controller.config.get("pump_test_interval", 3600)
    elapsed_since_test = now - controller._last_test
    time_to_next_test = max(0, interval - elapsed_since_test)
    state["time_to_next_test"] = time_to_next_test  # in seconds


    # --- Run controller ---
    controller.loop()

    
    # LED update
    status_led.update()

    # --- Wi-Fi toggle sync ---
    desired_wifi = gui.wifi_var.get()

    if desired_wifi and not gui.wifi_connected():
        gui.wifi.connect()
    elif not desired_wifi and gui.wifi_connected():
        gui.wifi.disconnect()






    # --- Update GUI ---
    gui.update_from_state()

    root.after(500, update_loop)

# ---------- Start ----------
root.after(100, update_loop)
root.mainloop()
