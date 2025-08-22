from .temperature import TemperatureSensor
from .water_level import WaterLevelSensor

class Sensors:
    def __init__(self, temp_pin, level_pin):
        self.temperature = TemperatureSensor(temp_pin)
        self.water_level = WaterLevelSensor(level_pin)
