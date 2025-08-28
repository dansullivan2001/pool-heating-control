
from sensors.temperature import TemperatureSensor
from sensors.water_level import WaterLevelSensor
from config import PIN_TEMPS, PIN_WATER_LEVEL

temperature_sensor = TemperatureSensor(PIN_TEMPS)
water_level_sensor = WaterLevelSensor(PIN_WATER_LEVEL)

print("Starting mock sensor test...\n")

for i in range(5):  # 5 steps across scenarios
      temps = temperature_sensor.read()
      level = water_level_sensor.read()
      for name, value in temps.items():
            print(f"{name}: {value:.2f} degC", end=" |")
      print(f" Water Level: {'Present' if level else 'Dry'}")
      print()