# controller/controller.py
__version__ = "0.4.0"   

import time
from network import mqtt
from state import state

class Controller:
    def __init__(self, network, config, sensors=None):
        """
        Controller handles pump logic, MQTT publishing, and safety checks.
        """
        self.network = network
        self.network.mqtt.message_handler = self.handle_mqtt_message  # set the handler
        self.sensors = sensors or {}
        self.state = state  # shared global state
        self.config = config
        self.mqtt = network.mqtt

        # timing
        self._last_publish = 0
        self._last_test = 0
        self._manual_override_start = None  # track when override began

    def loop(self):
        """
        One controller cycle. Call regularly from test_main_controller_gui.py
        or main.py.
        """
        now = time.time()

        # --- Safety overrides ---
        if not self.state["water_level_ok"]:
            self._set_pump(False, reason="dry run protect")
            self.state["dry_run_protect"] = True
            self.state["manual_override"] = False
            self._manual_override_start = None
            return
        else:
            self.state["dry_run_protect"] = False

        t_enclosure = self.state.get("temps", {}).get("tEnclosure")
        self.state["t_enclosure"] = t_enclosure
        if t_enclosure is None or t_enclosure > self.config["max_enclosure_temp"]:
            self._set_pump(False, reason="enclosure overtemp")
            self.state["overtemp_shutdown"] = True
            self.state["manual_override"] = False
            self._manual_override_start = None
            return
        else:
            self.state["overtemp_shutdown"] = False

        # --- Cancel manual override if button pressed ---
        if self.state["manual_override"] and self.sensors.get("button") and self.sensors["button"].button_pressed():
            self.state["manual_override"] = False
            self._manual_override_start = None
            self._set_pump(False, reason="manual override cancelled by button")


        # --- Manual override timer check ---
        manual_duration = self.config.get("manual_override_duration", 300)
        if self.state["manual_override"]:
            if self._manual_override_start is None:
                self._manual_override_start = now
            elapsed = now - self._manual_override_start
            if elapsed <= manual_duration:
                reason_str = f"manual override ({elapsed:.0f}/{manual_duration}s)"
                self._set_pump(True, reason=reason_str)
                return  # skip automatic control
            else:
                self.state["manual_override"] = False
                self._manual_override_start = None
                reason_str = f"manual override expired ({manual_duration:.0f}s)"
                self._set_pump(False, reason=reason_str)


        
        # --- Automatic control ---
        temps = self.state.get("temps", {})
        flow = temps.get("tFlow")
        ret = temps.get("tReturn")

        auto_wants_pump = self.state["pump_on"] 

        if flow is not None and ret is not None:
            delta = ret - flow
            high_threshold = self.config.get("delta_threshold_high", 0.5)
            low_threshold = self.config.get("delta_threshold_low", 0.1)
            
            if not self.state["pump_on"] and delta >= high_threshold:
                auto_wants_pump = True
                self.state["pump_reason"] = f"solar heating active ({delta:.1f}C)"
            elif self.state["pump_on"] and delta < low_threshold:
                auto_wants_pump = False
                self.state["pump_reason"] = f"insufficient gain ({delta:.1f}C)"
        else:
            auto_wants_pump = False
            self.state["pump_reason"] = "missing temps"

        # --- Periodic test run ---
        test_interval = self.config.get("pump_test_interval", 600)
        test_duration = self.config.get("pump_test_duration", 90)

        # 1. Start the test if it's time
        if (now - self._last_test) >= test_interval:
            self.state["test_running"] = True
            self._last_test = now
            # We don't call _set_pump here anymore, we let the logic below handle it

        # 2. Final Decision Logic (The "Priority Stack")
        if self.state["test_running"]:
            if (now - self._last_test) < test_duration:
                self._set_pump(True, reason="periodic test")
            else:
                self.state["test_running"] = False
                print("🧪 Periodic test finished")
                self._set_pump(auto_wants_pump, reason=self.state["pump_reason"])
        else:
            # No test? Use the automatic logic
            self._set_pump(auto_wants_pump, reason=self.state["pump_reason"])

        # --- Publish state at intervals ---
        if (now - self._last_publish) >= self.config["publish_interval"]:
            self.publish_state()
            self._last_publish = now

    # ---------------- Helpers ----------------

    def _set_pump(self, on: bool, reason=""):
        if self.state["pump_on"] != on or self.state.get("pump_reason") != reason:
            print(f"🔄 Pump {'ON' if on else 'OFF'} ({reason})")
        self.state["pump_on"] = on
        self.state["pump_reason"] = reason  # 👈 add reason into state

    def publish_state(self):
        """Push state + sensors to Adafruit IO."""
        if not self.network or not self.network.mqtt.connected:
            return

        feeds = self.network.feeds

        # --- Basic states ---

        self.mqtt.publish(feeds.manual_override, int(self.state["manual_override"]))
        self.mqtt.publish(feeds.pump_state, int(self.state["pump_on"]))
        self.mqtt.publish(feeds.ota_trigger, "0")  # reset OTA trigger after use

        # --- Sensor values
        for label, value in self.state["temps"].items():
            if value is not None:
                topic = getattr(feeds, label, None)
                if topic:
                    self.mqtt.publish(topic, value)

        # --- Full state dump for debugging ---
        import json
        # Convert the full state dict to a JSON string
        state_json = json.dumps(self.state, indent=2)
        # Publish to a debug feed
        self.mqtt.publish(feeds.debug, state_json)

    def handle_mqtt_message(self, topic, payload):
        feeds = self.network.feeds
        if topic == feeds.manual_override:
            state["manual_override"] = payload == "1"
            state["pump_reason"] = (
                "Manual override (AIO)" if state["manual_override"] else "Manual override released"
            )
        elif topic == feeds.ota_trigger and payload == "1":
            state["ota_pending"] = True
            state["pump_reason"] = "OTA update triggered"