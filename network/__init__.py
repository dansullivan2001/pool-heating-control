# network.py
__version__ = "0.0.1"

import time
from .wifi import WiFiManager
from .mqtt import MQTTManager
from .feeds import Feeds
import secrets  # holds WIFI_SSID, WIFI_PASSWORD, AIO_USERNAME, AIO_KEY


class Network:
    """Handles combined WiFi + MQTT connectivity."""

    def __init__(self):
        # Setup feeds
        self.feeds = Feeds(secrets.AIO_USERNAME)

        # Setup WiFi manager
        self.wifi = WiFiManager(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)

        # Setup MQTT manager
        self.mqtt = MQTTManager(
            aio_username=secrets.AIO_USERNAME,
            aio_key=secrets.AIO_KEY,
            feeds=self.feeds,
            wifi_manager=self.wifi
        )

    def connect(self):
        """Connect WiFi and MQTT."""
        print("[Network] Connecting WiFi...")
        self.wifi.connect()
        print("[Network] Connecting MQTT...")
        self.mqtt.connect()

    def loop(self):
        """Process WiFi + MQTT events, keep connection alive."""
        # WiFi keepalive (could add reconnect logic here if needed)
        self.wifi.loop()

        # MQTT processing (subscriptions + rate-limited publishes)
        self.mqtt.loop()
