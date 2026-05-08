# main.py

__version__ = "2.0.1"

import gc
from network import Network
from sensors import Sensors
from controller.controller import Controller
from config import CONFIG, PIN_TEMPS, PIN_WATER_LEVEL, PIN_BUTTON

sensors = Sensors(temp_pin=PIN_TEMPS, level_pin=PIN_WATER_LEVEL, button_pin=PIN_BUTTON)
network = Network()
controller = Controller(network, CONFIG, sensors)

while True:
    controller.loop()
    gc.collect()