# main.py
__version__ = "0.9.4"

import gc
import time

# -------------------------------------------------------------------------
# Boot: OTA integrity check — must run before any other imports
# so that if a bad update was applied, we restore and reboot before
# anything broken gets imported.
# -------------------------------------------------------------------------
from ota import verify_or_rollback
verify_or_rollback()

# -------------------------------------------------------------------------
# Normal imports (only reached if firmware verified clean)
# -------------------------------------------------------------------------
from net import Network
from sensors import Sensors
from controller.controller import Controller
from config import CONFIG, PIN_TEMPS, PIN_WATER_LEVEL, PIN_BUTTON, PIN_PUMP, PIN_LED
from state import state
from net.ntp import sync_time, is_time_synced
from status_led import StatusLED

# -------------------------------------------------------------------------
# Boot
# -------------------------------------------------------------------------

print(f"🚀 Solar Pool Controller v{__version__} starting...")

# Read the locally-stored manifest to populate fw_version in state.
# OTA writes an updated manifest.json after each successful update, so this
# always reflects the last-applied bundle version.
try:
    import json as _json
    with open("manifest.json") as _f:
        state["fw_version"] = _json.load(_f).get("version", "unknown")
    del _json, _f
except Exception:
    pass  # state["fw_version"] stays "unknown" — non-fatal

# Initialise hardware
import machine
pump_pin = machine.Pin(PIN_PUMP, machine.Pin.OUT)
pump_pin.value(0)  # ensure pump off at boot
sensors = Sensors(temp_pin=PIN_TEMPS, level_pin=PIN_WATER_LEVEL, button_pin=PIN_BUTTON)

# Perform first sensor reads immediately so state is populated before
# the controller's first loop. This ensures we start in a known safe state
# rather than relying on defaults.
try:
    sensors.temperature.read()          # populates state["temps"]
except Exception as e:
    state["last_error"] = str(e)
    print(f"⚠️ Initial temperature read failed: {e}")

try:
    state["water_level_ok"] = bool(sensors.water_level.read())
except Exception as e:
    state["last_error"] = str(e)
    state["water_level_ok"] = False     # fail-safe
    print(f"⚠️ Initial water level read failed: {e}")

# Connect network (blocking on boot is acceptable — we want MQTT before first loop)
network = Network()
network.connect()

# NTP time sync — must happen after WiFi is connected.
# Sets the Pico RTC to UK local time (GMT or BST) so that
# core hours comparisons in the controller are correct.
if sync_time():
    state["time_synced"] = True
    state["last_ntp_sync"] = time.time()
else:
    print("⚠️ NTP sync failed at boot — core hours may be incorrect until sync succeeds")

# Build controller
controller = Controller(network, CONFIG, sensors, pump_pin=pump_pin)
network.pre_restart_hook = lambda: controller._set_pump(False, reason="watchdog restart", urgent=False)

# Status LED
status_led = StatusLED(pin_num=PIN_LED, state_ref=state)

print("✅ Boot complete, entering main loop")

# -------------------------------------------------------------------------
# Main loop
# -------------------------------------------------------------------------

SENSOR_READ_INTERVAL = 2      # seconds between sensor reads
_last_sensor_read    = 0

NTP_SYNC_HOUR        = 3      # resync daily at 03:00 local time
_last_ntp_day        = None   # day-of-year of last successful sync

while True:
    now = time.time()

    # 1. Read sensors on interval (non-blocking between reads)
    if now - _last_sensor_read >= SENSOR_READ_INTERVAL:
        try:
            sensors.temperature.read()   # updates state["temps"] internally
        except Exception as e:
            state["last_error"] = str(e)
            print(f"⚠️ Temperature read error: {e}")

        try:
            state["water_level_ok"] = bool(sensors.water_level.read())
        except Exception as e:
            state["last_error"] = str(e)
            state["water_level_ok"] = False   # fail-safe on error
            print(f"⚠️ Water level read error: {e}")

        _last_sensor_read = now

    # 2. Daily NTP resync at 03:00 local time
    #    Keeps the RTC accurate across DST transitions and long uptimes.
    _today = time.localtime(now)[7]   # day-of-year
    _hour  = time.localtime(now)[3]
    if _hour == NTP_SYNC_HOUR and _last_ntp_day != _today:
        print("🕐 NTP: Daily resync...")
        if sync_time():
            state["time_synced"]    = True
            state["last_ntp_sync"]  = now
            _last_ntp_day           = _today
        else:
            print("⚠️ NTP: Daily resync failed — will retry next minute")

    # 3. Network housekeeping (non-blocking)
    try:
        network.loop()
    except Exception as e:
        state["last_error"] = str(e)
        print(f"⚠️ Network loop error: {e}")

    # 4. OTA check (if requested via MQTT)
    if state.get("ota_pending"):
        state["ota_pending"] = False
        try:
            from ota import check_for_update
            controller._set_pump(False, reason="OTA update starting", urgent=True)
            gc.collect()              # free as much RAM as possible before download
            check_for_update()
            # check_for_update() reboots the Pico if updates were applied.
            # If we reach here, no updates were needed or the check failed safely.
            print("ℹ️ OTA: No updates available")
        except Exception as e:
            state["last_error"] = str(e)
            print(f"⚠️ OTA check failed: {e}")

    # 5. Controller logic
    try:
        controller.loop()
    except Exception as e:
        state["last_error"] = str(e)
        state["critical_error"] = True
        print(f"❌ Controller error: {e}")

    # 6. Status LED
    status_led.update()

    # 7. Memory management
    gc.collect()