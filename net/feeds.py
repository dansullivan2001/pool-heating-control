# network/feeds.py
__version__ = "0.7.0"

class Feeds:
    """
    Single source of truth for all Adafruit IO feed topic strings.

    Feed topics are accessed via dot notation:
        feeds.pump_state   →  "username/feeds/pump_state"

    Adding a new feed: add one entry to self._feeds in __init__.
    """

    def __init__(self, username):
        self._feeds = {
            # --- Inbound (subscribed — controller receives these) ---
            "manual_override":  f"{username}/feeds/pump_override",
            "ota_trigger":      f"{username}/feeds/ota_trigger",

            # --- Outbound (published — controller sends these) ---
            "pump_state":            f"{username}/feeds/pump_state",
            "tAmbient":              f"{username}/feeds/tAmbient",
            "tFlow":                 f"{username}/feeds/tFlow",
            "tReturn":               f"{username}/feeds/tReturn",
            "delta_t_flow_return":   f"{username}/feeds/delta-t-flow-return",
            "delta_irradiance":      f"{username}/feeds/delta-irradiance",
            "debug":                 f"{username}/feeds/debug",
        }

    def control_topics(self):
        """
        Return a list of topic strings that the controller subscribes to
        (i.e. inbound feeds). Used by MQTTManager on connect/reconnect.
        """
        return [
            self._feeds["manual_override"],
            self._feeds["ota_trigger"],
        ]

    def __getattr__(self, name):
        if name in self._feeds:
            return self._feeds[name]
        raise AttributeError(f"No feed named '{name}'")

    def all(self):
        return self._feeds.copy()

    def keys(self):
        return list(self._feeds.keys())

    def values(self):
        return list(self._feeds.values())

    def items(self):
        return self._feeds.items()