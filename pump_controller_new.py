from sensors import SensorManager
from debounced_water_level import DebouncedWaterLevel

sensors = SensorManager(pin=1)
water_level = DebouncedWaterLevel(sensors, delay_ms=100, wet_hold=2000, dry_hold=2000)

while True:
    temps = sensors.read_temps()
    level = water_level.update()

    print("Temps:", temps, "Water level:", "Wet" if level else "Dry")
    time.sleep(0.5)
