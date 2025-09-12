# network/feeds.py
__version__ = "0.4.0"

class Feeds:
    def __init__(self, username):
        # Define feeds in one place
        self._feeds = {
            "debug": f"{username}/feeds/debug",
            "ota_trigger": f"{username}/feeds/ota_trigger",
            "manual_override": f"{username}/feeds/pump_override",
            "pump_state": f"{username}/feeds/pump_state",
            "tAmbient": f"{username}/feeds/tAmbient",
            "tEnclosure": f"{username}/feeds/tEnclosure",
            "tFlow": f"{username}/feeds/tFlow",
            "tReturn": f"{username}/feeds/tReturn",
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
