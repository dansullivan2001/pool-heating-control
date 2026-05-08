# config.py
__version__ = "0.0.1"

CONFIG = {
    "pump_test_interval": 60,
    "pump_test_duration": 30,
    "max_enclosure_temp": 50,
    "ota_check_interval": 3600,
    "min_temp_delta": 0,
    "publish_interval": 30,
    "manual_override_duration": 10,
    "mqtt_watchdog_interval": 10,
}

# GPIO pins
PIN_PUMP = 5
PIN_LED = 6
PIN_WATER_LEVEL = 14
PIN_BUTTON = 10
PIN_TEMPS = 0


# ==== Sensor labels ====
rom_to_label = {
    '28d2908700370520': 'tReturn',
#    '28e7688700c21d87': 'tReturnTest',
    '28206f87007e6fc7': 'tAmbient',
    '2874c18700153578': 'tFlow',
#    '2812358700210518': 'tFlowTest',
    '28ee28e31216013e': 'tEnclosure'
}
