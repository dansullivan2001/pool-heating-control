# config.py
__version__ = "0.1.5"

CONFIG = {
    # --- Pump timing ---
    "pump_test_interval":     600,   # seconds between periodic test runs
    "pump_test_duration":      90,   # seconds each test run lasts
    "manual_override_duration": 90,  # seconds a manual boost lasts

    # --- Periodic test irradiance gate ---
    # Before a scheduled test, compare the solar plate against the (stagnant)
    # flow sensor. If the plate isn't meaningfully warmer than the water sitting
    # in the circuit, the test would almost certainly end with the pump switching
    # straight back off, so skip it and save the run. Threshold derived
    # empirically from logged test outcomes.
    # FAIL-SAFE: if either sensor is unavailable the gate is treated as open,
    # i.e. behaviour reverts to the timer-only test schedule.
    "gate_enabled":          True,   # kill switch — False restores timer-only tests
    "gate_threshold":         0.5,   # °C — tSolarPlate must exceed tFlow by this
    "gate_fallback_interval": 3600,  # seconds — force a test after this long regardless

    # --- Solar delta thresholds ---
    # Pump turns ON  when (tReturn - tFlow) >= delta_threshold_high
    # Pump turns OFF when (tReturn - tFlow) <  delta_threshold_low
    # The gap between the two provides hysteresis to prevent rapid cycling.
    "delta_threshold_high":   0.5,
    "delta_threshold_low":    0.1,

    # --- Core operating hours ---
    # Pump will not run automatically outside these hours (24h clock).
    "core_start_hour":          8,
    "core_end_hour":           18,

    # --- Safety ---
    "max_enclosure_temp":      55,   # °C — pump stops above this

    # --- Network ---
    "publish_interval":        30,   # seconds between full state publishes (core hours)
    "publish_interval_off_hours": 300,  # seconds between full state publishes (outside core hours)
    "mqtt_watchdog_interval":  60,   # seconds before MQTT watchdog fires
}

# -------------------------------------------------------------------------
# GPIO pin assignments
# -------------------------------------------------------------------------
PIN_PUMP        = 16
PIN_LED         = "LED"
PIN_WATER_LEVEL = 14
PIN_BUTTON      = 3
PIN_TEMPS       = 0

# -------------------------------------------------------------------------
# DS18x20 ROM → label mapping
# Add a new entry here whenever a sensor is added or replaced.
# Commented-out entries are kept for reference (test sensors etc.)
# -------------------------------------------------------------------------
rom_to_label = {
    "28d2908700370520": "tReturn",
    "28206f87007e6fc7": "tAmbient",
    "2874c18700153578": "tFlow",
    "28ee28e31216013e": "tEnclosure",
    "2812358700210518": "tSolarPlate",
    "28e7688700c21d87": "tSolarRef",
}