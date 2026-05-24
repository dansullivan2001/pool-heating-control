# test_main_controller_gui.py
__version__ = "0.2.0"

"""
Desktop simulation harness for the pool controller.

Architecture:
  update_loop() runs every TICK_MS milliseconds via root.after().
  Each tick mirrors exactly what main.py does on the real Pico:

    1. Compute 'now' (real or simulated time)
    2. Sync WiFi state from GUI checkbox
    3. Run MQTT housekeeping
    4. Read sensors → write to shared state
    5. Run controller.loop()
    6. Update status LED
    7. Refresh GUI display

State flow is one-directional:
  GUI inputs → shared state → controller → GUI outputs
  update_from_state() is read-only: it never writes back to state.
"""

import time
import tkinter as tk

from status_led import DesktopStatusLED
from state import state
from sensors.temperature import TemperatureSensor
from sensors.water_level import WaterLevelSensor
from net import Network
from mocks.mock_hardware_gui import MockHardwareGUI
from mocks.mock_hardware import MockDS18X20, MockOneWire, MockPin
from controller.controller import Controller
from config import PIN_TEMPS, PIN_WATER_LEVEL, rom_to_label, CONFIG

# How often the simulation loop ticks (ms).
# Must be well below the shortest LED pattern step (100ms) for smooth animation.
TICK_MS = 100

# -------------------------------------------------------------------------
# GUI setup
# -------------------------------------------------------------------------

root = tk.Tk()
gui  = MockHardwareGUI(root)

# -------------------------------------------------------------------------
# Status LED
# -------------------------------------------------------------------------

status_led = DesktopStatusLED(pin_num=25, state_ref=state)
# Route LED on/off calls through to the GUI canvas
status_led.led.value = lambda val: gui.set_led_state(bool(val))
# Let the GUI query the LED pattern name directly (avoids duplicating logic)
gui.bind_status_led(status_led)

# -------------------------------------------------------------------------
# Mock DS18X20 — GUI-controlled temperatures
# -------------------------------------------------------------------------

class GUIMockDS18X20(MockDS18X20):
    """
    DS18X20 mock that reads temperatures from GUI sliders.
    Sensor disable checkboxes are handled here so the sensor layer
    sees None for disabled sensors (matching real disconnected-sensor behaviour).
    """
    def scan(self):
        return gui.fake_roms if gui.use_fake_roms.get() else self.roms

    def read_temp(self, rom):
        # Delegate to GUI — returns None if sensor is disabled
        return gui.get_temperature(rom)

# -------------------------------------------------------------------------
# Sensors
# -------------------------------------------------------------------------

temperature_sensor  = TemperatureSensor(PIN_TEMPS)
water_level_sensor  = WaterLevelSensor(PIN_WATER_LEVEL)

# Replace the real DS18X20 driver with our GUI-backed mock
temperature_sensor.ds_sensor = GUIMockDS18X20(
    MockOneWire(MockPin(PIN_TEMPS)), gui=gui
)
# Also update the cached ROM list to match the mock
temperature_sensor.roms = temperature_sensor.ds_sensor.scan()

# Route water level reads through the GUI checkbox
water_level_sensor.pin.gui = gui

# Fake ROMs: one unknown (tests the "unknown ROM" warning path) + real sensors
gui.fake_roms = [
    "11111111111111",        # unknown — not in rom_to_label
    "28206f87007e6fc7",      # tAmbient
    "2874c18700153578",      # tFlow
    "28ee28e31216013e",      # tEnclosure
    "PLACEHOLDER_SOLAR_PLATE",  # tSolarPlate — replace with real ROM once wired
    "PLACEHOLDER_SOLAR_REF",    # tSolarRef   — replace with real ROM once wired
]

def _on_fake_roms_toggle(*_):
    """Keep the sensor's cached ROM list in sync with the GUI toggle."""
    temperature_sensor.roms = temperature_sensor.ds_sensor.scan()

gui.use_fake_roms.trace_add("write", _on_fake_roms_toggle)

# -------------------------------------------------------------------------
# Network
# -------------------------------------------------------------------------

network = Network()
gui.wifi = network.wifi
network.wifi.wlan.gui = gui   # MockWiFi reads connected state from GUI
network.connect()
# Isolate GUI simulation from real Adafruit IO — suppress all MQTT I/O
network.mqtt.publish                  = lambda *_a, **_kw: print(f"[MQTT] {_a[0]}: {_a[1]}")
network.mqtt._subscribe_control_feeds = lambda: None
network.mqtt.loop                     = lambda: None
network.mqtt.watchdog                 = lambda: None
network.mqtt.disconnect               = lambda: None
network.mqtt.connected                = True
state["mqtt_connected"]               = True

# -------------------------------------------------------------------------
# Controller
# -------------------------------------------------------------------------

# Pass the full CONFIG — avoids KeyError on direct-access keys like
# config["publish_interval"] and config["max_enclosure_temp"].
controller = Controller(network=network, config=CONFIG)
gui.bind_state(controller.state)

# -------------------------------------------------------------------------
# Simulated restart
# -------------------------------------------------------------------------

def _soft_restart():
    """
    Simulate a Pico hard reset in the desktop environment.
    Resets state to safe defaults, restarts network, resets controller timers.
    """
    print("💥 Simulated Pico restart")

    # Reset state to safe defaults (mirrors state.py initial values)
    safe_defaults = {
        bool:       False,
        int:        0,
        float:      0.0,
        list:       [],
        dict:       {},
    }
    for k in list(state.keys()):
        v = state[k]
        state[k] = safe_defaults.get(type(v), None)

    # Fail-safe defaults that must be False, not 0
    state["water_level_ok"] = False
    state["sensors_ok"]     = False

    # Reset controller internals
    now = time.time()
    controller._last_publish          = 0
    controller._last_test             = now
    controller._last_tick             = None
    controller._manual_override_start = None
    controller._test_start_time       = None
    state["last_test_ts"]             = now

    # Reconnect network
    network.wifi.disconnect()
    network.mqtt.disconnect()
    network.mqtt.last_ping = now
    network.connect()

    # Sync GUI
    gui.wifi_var.set(network.wifi.is_connected())
    gui.button_var.set(False)

def _pump_off_before_restart():
    controller._set_pump(False, reason="watchdog restart")

network.soft_restart_callback = _soft_restart
network.pre_restart_hook      = _pump_off_before_restart

# -------------------------------------------------------------------------
# Main simulation loop
# -------------------------------------------------------------------------

# Time-mode state: track a fixed offset so simulated 'now' advances at
# real speed from the moment the mode was set.  Recomputed on mode change.
_time_offset    = 0.0    # seconds to add to time.time() to get simulated now
_prev_time_mode = "auto"


def update_loop():
    global _time_offset, _prev_time_mode

    # 1. Compute 'now' — single value used by all subsystems this tick
    #
    # When a time mode is selected we compute a fixed offset so that
    # time.localtime(now)[3] equals the target hour at the moment of
    # switch, and then 'now' advances at real speed from there.
    # This keeps elapsed-time calculations (test timer, publish timer)
    # correct relative to the controller's internal timestamps.
    mode = gui.time_mode.get()

    if mode != _prev_time_mode:
        real_now = time.time()
        if mode in ("day", "night"):
            target_hour = 12 if mode == "day" else 23
            lt = time.localtime(real_now)
            real_secs = lt[3] * 3600 + lt[4] * 60 + lt[5]
            _time_offset = target_hour * 3600 - real_secs
        else:
            _time_offset = 0.0
        _prev_time_mode = mode

        # Reset the controller's test timer to the new simulated 'now' so
        # the countdown starts from zero rather than showing a huge value.
        now = real_now + _time_offset
        controller._last_test             = now
        controller.state["last_test_ts"]  = now
        controller.state["time_to_next_test"] = controller.config.get("pump_test_interval", 600)

    now = time.time() + _time_offset

    # 2. WiFi sync — GUI checkbox drives the mock WiFi state
    desired_wifi = gui.wifi_var.get()
    currently_up = gui.wifi_connected()
    if desired_wifi and not currently_up:
        network.wifi.connect()
    elif not desired_wifi and currently_up:
        network.wifi.disconnect()

    wifi_up = gui.wifi_connected()
    state["wifi_connected"] = wifi_up

    # 3. MQTT housekeeping
    if not wifi_up and network.mqtt.connected:
        network.mqtt.disconnect()
    elif wifi_up:
        network.mqtt.loop()
        network.mqtt.watchdog()

    state["mqtt_connected"] = network.mqtt.connected

    # 4. Sensor reads → shared state
    #    Temperature: use the non-blocking two-phase API.
    #    The mock's convert_temp() is a no-op so read() returns immediately.
    readings = temperature_sensor.read()
    state["temps"]                = readings
    state["sensors_ok"]           = all(v is not None for v in readings.values())
    state["disconnected_sensors"] = [l for l, v in readings.items() if v is None]

    state["water_level_ok"] = bool(water_level_sensor.read())

    # 5. Manual boost button — only trigger on a fresh press (rising edge).
    #    Let the controller's timer be the sole mechanism for ending a boost.
    gui_button_active = gui.button_pressed()
    if gui_button_active and not state.get("manual_override"):
        print("🔘 GUI: Manual boost triggered")
        state["manual_override"]          = True
        state["manual_disabled"]          = False
        controller._manual_override_start = None   # controller sets on next loop

    # 6. Controller logic
    try:
        controller.loop(now_ts=now)
    except Exception as e:
        state["last_error"]    = str(e)
        state["critical_error"] = True
        print(f"❌ Controller error: {e}")

    # 7. critical_error: set if controller flagged an error this loop.
    #    Safety flags (overtemp, dry_run) are NOT treated as critical_error
    #    here — they have their own LED patterns and are normal operating
    #    conditions, not software faults.
    if state.get("last_error"):
        state["critical_error"] = True

    # 8. Status LED
    status_led.update()

    # 9. GUI refresh (read-only from state — no state writes here)
    gui.update_from_state()

    root.after(TICK_MS, update_loop)


# -------------------------------------------------------------------------
# Start
# -------------------------------------------------------------------------

root.after(100, update_loop)
root.mainloop()