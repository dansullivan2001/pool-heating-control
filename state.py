# state.py
__version__ = "0.3.1"
# Central shared state dictionary for the whole controller.
# ALL keys used anywhere in the codebase must be declared here with safe defaults.
# Rule: safety-critical booleans default to the SAFE (restrictive) value.

state = {
    # --- Pump control ---
    "pump_on":              False,  # current pump state
    "pump_reason":          "",     # human-readable reason for current state
    "manual_override":      False,  # timed boost active (button or MQTT mode 1)
    "manual_disabled":      False,  # holiday mode — system stays off (MQTT mode 2)
    "test_running":         False,  # true while periodic test run is active
    "last_pump_run":        None,   # timestamp of last pump activation

    # --- Runtime tracking ---
    "last_test_ts":         None,   # timestamp when last periodic test completed
    "time_to_next_test":    0,      # seconds until next test (computed each loop)

    # --- Computed values ---
    "delta_t":              None,   # tReturn - tFlow (°C), computed each loop

    # --- Sensors ---
    # SAFETY: default False/empty so system starts in a safe inhibited state
    # until real sensor reads populate these values.
    "temps":                {},     # dict of label -> temperature (C)
    "water_level_ok":       False,  # FAIL-SAFE: assume dry until sensor confirms wet
    "sensors_ok":           False,  # FAIL-SAFE: assume sensors missing until confirmed
    "disconnected_sensors": [],     # list of labels/IDs that failed last read

    # --- Network / cloud ---
    "wifi_connected":       False,
    "mqtt_connected":       False,

    # --- Safety flags ---
    # These are set by the controller safety chain each loop.
    "overtemp_shutdown":    False,  # enclosure too hot → pump disabled
    "dry_run_protect":      False,  # pump inhibited due to low water
    "enclosure_sensor_missing": False,  # enclosure sensor absent (distinct from overtemp)
    "critical_error":       False,  # set on unrecoverable error → LED critical pattern

    # --- Time ---
    "time_synced":          False,  # True after first successful NTP sync
    "last_ntp_sync":        None,   # timestamp of last successful NTP sync

    # --- OTA ---
    "ota_pending":          False,  # set True by MQTT to trigger OTA check
    "fw_version":           "unknown",  # manifest "version" field, populated at boot

    # --- Debug / diagnostics ---
    "last_error":           None,   # string or exception message from last crash
}