# network/feeds.py
__version__ = "0.3.0"

class Feeds:
    def __init__(self, username):
        # Define feeds in one place
        self._feeds = {
            "debug": f"{username}/feeds/debug",
            "ota_trigger": f"{username}/feeds/ota_trigger",
            "manual_override": f"{username}/feeds/pump_override",
            "pump_state": f"{username}/feeds/pump_state",
            "ambient_temp": f"{username}/feeds/tAmbient",
            "enclosure_temp": f"{username}/feeds/tEnclosure",
            "flow_temp": f"{username}/feeds/tFlow",
            "return_temp": f"{username}/feeds/tReturn",
  #          "water_level": f"{username}/feeds/water-level",

            
   #         "pump_test_interval": f"{username}/feeds/pump_test_interval",
    #        "pump_test_duration": f"{username}/feeds/pump-test-duration",

        }

    def __getattr__(self, name):
        """Allow dot access: feeds.temperature"""
        if name in self._feeds:
            return self._feeds[name]
        raise AttributeError(f"No feed named {name}")

    def all(self):
        """Return dict of all feeds"""
        return self._feeds.copy()

    def keys(self):
        return list(self._feeds.keys())

    def values(self):
        return list(self._feeds.values())

    def items(self):
        return self._feeds.items()
