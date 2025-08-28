# feeds.py
__version__ = "0.0.2"

class Feeds:
    """Defines all Adafruit IO feed topics used in the project."""

    _feed_names = {
        # Control feeds
        "pump_override": "pump-override",
        "pump_interval": "pump-interval",
        "pump_duration": "pump-duration",
        "publish_interval": "publish-interval",
        "ota_trigger": "ota-trigger",

        # Sensor feeds
        "temp_flow": "temp-flow",
        "temp_return": "temp-return",
        "temp_ambient": "temp-ambient",
        "temp_enclosure": "temp-enclosure",
        "water_level": "water-level",

        # State feeds
        "pump_state": "pump-state",
        "debug": "debug",
    }

    def __init__(self, aio_username):
        self.base = aio_username
        for attr, name in self._feed_names.items():
            setattr(self, attr, f"{self.base}/feeds/{name}")
