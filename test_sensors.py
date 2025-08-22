import time
from sensors import Sensors
from config import PIN_TEMPS, PIN_WATER_LEVEL

s = Sensors(temp_pin=PIN_TEMPS, level_pin=PIN_WATER_LEVEL)

print("Starting mock sensor test...\n")

for i in range(5):  # 5 steps across scenarios
    temps = s.temperature.read()
    water_level = s.water_level.read()
    print(f"Step {i+1}: Return={temps['28d2908700370520']} °C, "
          f"Flow={temps['2874c18700153578']} °C, "
          f"Water Level={'Wet' if water_level else 'Dry'}")
    time.sleep(0.5)
