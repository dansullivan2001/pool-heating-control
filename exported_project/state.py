# state.py
__version__ = "0.0.1" 
# Central shared state dictionary for the whole controller

state = {
    # --- Pump control ---
    "pump_on": False,             # current pump state
    "manual_override": False,     # set via Adafruit IO or local button
    "last_pump_run": None,        # timestamp of last test run
    "test_running": False,        # true when periodic test is active
    "pump_reason": "",            # reason for last pump state change

    # --- Sensors ---
    "temps": {},                  # dict of label -> temperature (C)
    "sensors_ok": True,           # flag: all sensors reporting
    "disconnected_sensors": [],   # list of labels/IDs that failed
    "t_enclosure": None,          # cached enclosure temp
    "water_level_ok": True,       # from capacitive sensor

    # --- Network / cloud ---
    "wifi_connected": False,
    "mqtt_connected": False,

    # --- Safety / error handling ---
    "critical_error": False,      # set on unrecoverable error
    "overtemp_shutdown": False,   # enclosure too hot → pump disabled
    "dry_run_protect": False,     # true if pump inhibited by no water

    # --- Debug / diagnostics ---
    "last_error": None,           # string or exception message
}
