# config.py
__version__ = "0.0.1"

PUMP_TEST_INTERVAL = 3600
PUMP_TEST_DURATION = 30
MAX_ENCLOSURE_TEMP = 50

# GPIO pins
PIN_PUMP = 5
PIN_LED = 6
PIN_WATER_LEVEL = 14
PIN_BUTTON = 10
PIN_TEMPS = 0

OTA_CHECK_INTERVAL = 3600


# ==== Sensor labels ====
rom_to_label = {
    '28d2908700370520': 'tReturn',
#    '28e7688700c21d87': 'tReturnTest',
    '28206f87007e6fc7': 'tAmbient',
    '2874c18700153578': 'tFlow',
#    '2812358700210518': 'tFlowTest',
    '28ee28e31216013e': 'tEnclosure'
}
