# main.py

__version__ = "2.0.1"

from network import Network
from sensors import Sensors
from controller.controller import Controller
from config import CONFIG

sensors = Sensors(temp_pin=1, level_pin=14, button_pin=10)
network = Network()
controller = Controller(sensors, network, CONFIG)

while True:
    controller.loop()
