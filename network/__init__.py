# network.py
__version__ = "0.1.0"

import time
from .wifi import WiFiManager
from .mqtt import MQTTManager
from .feeds import Feeds
from config import CONFIG
import secrets  # holds WIFI_SSID, WIFI_PASSWORD, AIO_USERNAME, AIO_KEY


class Network:
    """Handles combined WiFi + MQTT connectivity."""

    def __init__(self):

        # Store username here so we can use it in publish_state()
        self.aio_username = secrets.AIO_USERNAME
        
        # Setup feeds
        self.feeds = Feeds(self.aio_username)

        # Setup WiFi manager
        self.wifi = WiFiManager(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)

        # Setup MQTT manager
        self.mqtt = MQTTManager(
            aio_username=self.aio_username,
            aio_key=secrets.AIO_KEY,
            feeds=self.feeds,
            wifi_manager=self.wifi,
            watchdog_interval=CONFIG.get("mqtt_watchdog_interval", 60),
            restart_callback=self.restart_system,  # we'll add this
            message_handler=None  # will be set later by controller
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


    def publish_state(self, state):
        """Publish controller state to MQTT (or just print for testing)"""
        if self.mqtt.connected:
            # Example: publish pump state
            pump_topic = f"{self.aio_username}/feeds/pump_state"
            self.mqtt.publish(pump_topic, int(state.get("pump_on", 0)))

            # Example: publish LED state
            led_topic = f"{self.aio_username}/feeds/led_state"
            self.mqtt.publish(led_topic, int(state.get("led_on", 0)))

            # Example: publish temps
            for label, temp in state.get("temps", {}).items():
                topic = f"{self.aio_username}/feeds/{label}"
                if temp is not None:
                    self.mqtt.publish(topic, temp)

            # Example: publish water level
            topic_level = f"{self.aio_username}/feeds/water_level"
            water_level = state.get("water_level")
            if water_level is not None:
                self.mqtt.publish(topic_level, int(water_level))
        else:
            print("❌ MQTT not connected, cannot publish state")

    def restart_system(self):
        """Called by the MQTT watchdog if unresponsive."""
        print("💥 Restart callback triggered")
        # call pre-restart hook if defined
        if hasattr(self, "pre_restart_hook") and callable(self.pre_restart_hook):
            self.pre_restart_hook()
        try:
            import machine
            machine.reset()  # Pico: perform hard reset
        except ImportError:
            # Mac simulation: soft reset handled in test_main_controller_gui
            if hasattr(self, 'soft_restart_callback'):
                self.soft_restart_callback()
