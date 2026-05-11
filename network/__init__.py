# network/__init__.py
__version__ = "0.2.0"

from .wifi import WiFiManager
from .mqtt import MQTTManager
from .feeds import Feeds
from config import CONFIG
import secrets


class Network:
    """
    Aggregates WiFi, MQTT, and feed definitions into one object.

    Responsibilities:
      - Boot-time connect (blocking, called once from main.py)
      - Per-loop housekeeping via loop() — non-blocking
      - System restart callback for the MQTT watchdog

    Publishing is handled exclusively by Controller.publish_state().
    Network does not publish anything itself.
    """

    def __init__(self):
        self.aio_username = secrets.AIO_USERNAME
        self.feeds        = Feeds(self.aio_username)
        self.wifi         = WiFiManager(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
        self.mqtt         = MQTTManager(
            aio_username      = self.aio_username,
            aio_key           = secrets.AIO_KEY,
            feeds             = self.feeds,
            wifi_manager      = self.wifi,
            watchdog_interval = CONFIG.get("mqtt_watchdog_interval", 60),
            restart_callback  = self.restart_system,
            message_handler   = None,   # set by Controller after construction
        )

    def connect(self):
        """Blocking boot-time connect. Call once from main.py."""
        print("[Network] Connecting WiFi...")
        self.wifi.connect()
        print("[Network] Connecting MQTT...")
        self.mqtt.connect()

    def loop(self):
        """
        Non-blocking per-loop housekeeping.
        Call every main-loop iteration from main.py.
        """
        self.wifi.loop()
        self.mqtt.loop()
        self.mqtt.watchdog()

    def restart_system(self):
        """
        Called by the MQTT watchdog after a sustained outage.
        Turns the pump off before resetting so the pool is left safe.
        """
        print("💥 Network: watchdog restart triggered")

        if hasattr(self, "pre_restart_hook") and callable(self.pre_restart_hook):
            self.pre_restart_hook()

        try:
            import machine
            machine.reset()
        except ImportError:
            # Desktop simulation — soft restart handled by test harness
            if hasattr(self, "soft_restart_callback") and callable(self.soft_restart_callback):
                self.soft_restart_callback()