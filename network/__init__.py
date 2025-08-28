from .wifi import WiFiManager
from .mqtt import MQTTManager
from .feeds import *

class Network:
    def __init__ (self, wifi_ssid, wifi_password, aio_username, aio_key, feeds):
        self.wifi = WiFiManager(wifi_ssid, wifi_password)
        self.mqtt = MQTTManager(aio_username, aio_key, feeds, self.wifi)

    def connect(self):
        self.wifi.connect()
        self.mqtt.connect()

    def loop(self):
        # called from Main loop
        if not self.wifi.is_connected():
            print("Wifi down, disconnecting MQTT")
            self.mqtt.disconnect()
            self.wifi.connect()
        self.mqtt.check_connection()

    def is_connected(self):
        return self.wifi.is_connected() and self.mqtt.is_connected()
    