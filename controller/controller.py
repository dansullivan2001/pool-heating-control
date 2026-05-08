# controller/controller.py
__version__ = "0.5.0"   

import time
import json
from state import state

class Controller:
    def __init__(self, network, config, sensors=None):
        """
        Controller handles pump logic, MQTT publishing, and safety checks.
        """
        self.network = network
        self.network.mqtt.message_handler = self.handle_mqtt_message
        self.sensors = sensors or {}
        self.state = state  # shared global state
        self.config = config
        self.mqtt = network.mqtt

        # timing
        self._last_publish = 0
        self._last_test = time.time()
        self.state["last_test_ts"] = self._last_test
        self._last_tick = None
        self._manual_override_start = None
        self._test_start_time = None

    def loop(self, now_ts=None):
        """
        One controller cycle. Optimized with Core Hours gate and Runtime tracking.
        """
        now = now_ts if now_ts is not None else time.time()

        # Track the state before we run any logic
        was_pump_on = self.state.get("pump_on", False)

        # 1. Update Runtime (Calculate seconds since last loop)
        if self._last_tick is None: 
            self._last_tick = now
        
        loop_delta = now - self._last_tick
        self._last_tick = now
        
        if self.state.get("pump_on"):
            self.state["daily_runtime_sec"] = self.state.get("daily_runtime_sec", 0) + loop_delta

        # 2. Critical Safety Overrides (Highest Priority)
        safety_stop = False
        
        # Gather data for checks
        temps = self.state.get("temps", {})
        t_enclosure = temps.get("tEnclosure")
        # Essential sensors for solar logic
        essential_missing = temps.get("tFlow") is None or temps.get("tReturn") is None

        # --- The Unified Safety Chain ---
        if not self.state["water_level_ok"]:
            self._set_pump(False, reason="dry run protect")
            self.state["dry_run_protect"] = True
            self.state["overtemp_shutdown"] = False
            self.state["manual_override"] = False
            safety_stop = True

        elif t_enclosure is None or t_enclosure > self.config["max_enclosure_temp"]: # This shuts the pump off - either it's too hot, or we don't know the temp (None)
            self._set_pump(False, reason="enclosure overtemp")
            self.state["overtemp_shutdown"] = True
            self.state["dry_run_protect"] = False
            self.state["manual_override"] = False
            safety_stop = True

        elif essential_missing:
            # This triggers the 'sensor_missing' LED pattern in status_led.py
            self._set_pump(False, reason="missing sensors")
            # Clear critical flags so they don't override the 'sensor_missing' pattern
            self.state["dry_run_protect"] = False
            self.state["overtemp_shutdown"] = False
            safety_stop = True

        else:
            # System is physically safe
            self.state["dry_run_protect"] = False
            self.state["overtemp_shutdown"] = False
        # 3. Mode & Time Window Checks
        if not safety_stop:
            current_hour = time.localtime(now)[3]

            start_h = self.config.get("core_start_hour", 9)
            end_h = self.config.get("core_end_hour", 18)
            
            is_core_hours = start_h <= current_hour < end_h
            is_holiday = self.state.get("manual_disabled", False)

            # 4. Manual Override Logic (Works even outside core hours)
            if self.state["manual_override"]:
                if self._manual_override_start is None:
                    self._manual_override_start = now
                    self._last_test = now  # Reset test timer when manual override starts
                    self.state["last_test_ts"] = self._last_test

                elapsed = now - self._manual_override_start
                duration = self.config.get("manual_override_duration", 90)
                
                if elapsed <= duration:
                    self._set_pump(True, reason=f"manual boost ({elapsed:.0f}/{duration}s)")
                    # Skip automatic control while in manual boost
                    #self._check_publish(now)
                    #return 
                else:
                    self.state["manual_override"] = False
                    self._manual_override_start = None
                    # Allow to fall through to normal logic

            else:
                # 5. Core Operational Gate
                if is_core_hours and not is_holiday:
                    # --- Automatic Control (Solar Delta) ---
                    temps = self.state.get("temps", {})
                    flow = temps.get("tFlow")
                    ret = temps.get("tReturn")
                    
                    auto_wants_pump = self.state["pump_on"] 

                    if flow is not None and ret is not None:
                        delta = ret - flow
                        high_thresh = self.config.get("delta_threshold_high", 0.5)
                        low_thresh = self.config.get("delta_threshold_low", 0.1)
                        
                        if not self.state["pump_on"] and delta >= high_thresh:
                            auto_wants_pump = True
                            self.state["pump_reason"] = f"solar heating ({delta:.1f}C)"
                        elif self.state["pump_on"] and delta < low_thresh:
                            auto_wants_pump = False
                            self.state["pump_reason"] = f"insufficient gain ({delta:.1f}C)"
                    else:
                        auto_wants_pump = False
                        self.state["pump_reason"] = "missing sensors"

                    # --- Periodic Test Run ---
                    test_int = self.config.get("pump_test_interval", 30)
                    test_dur = self.config.get("pump_test_duration", 10)

                    if (now - self._last_test) >= test_int and not self.state["test_running"]:
                        print("🧪 Starting Periodic Test")
                        self.state["test_running"] = True
                        #self._last_test = now
                        self._test_start_time = now  # Track the start time of the test

                    if self.state["test_running"]:
                        if (now - self._test_start_time) < test_dur:
                            self._set_pump(True, reason="periodic test")
                        else:
                            print("✅ Periodic Test Finished")
                            self.state["test_running"] = False
                            self._last_test = now  # Reset test timer when test finishes
                            self.state["last_test_ts"] = self._last_test
                            # After test ends, we re-evaluate the solar logic immediately
                            self._set_pump(auto_wants_pump, reason=self.state["pump_reason"])
                    else:
                        self._set_pump(auto_wants_pump, reason=self.state["pump_reason"])

                else:
                    # --- SHUTDOWN (Night or Holiday) ---
                    self.state["test_running"] = False
                    reason = "Holiday Mode" if is_holiday else f"Sleep (Hour {current_hour})"
                    self._set_pump(False, reason=reason)

        # 6. Periodic Publish
        self._check_publish(now)

   
    # ---------------- Helpers ----------------

    def _check_publish(self, now):
        if (now - self._last_publish) >= self.config["publish_interval"]:
            self.publish_state(force_all=True)
            self._last_publish = now

    def _set_pump(self, on: bool, reason=""):
        # Create a "Static" version of the reason for comparison
        # This strips out the (1/90s) part so it doesn't trigger MQTT every second
        static_reason = reason.split(' (')[0]
        old_static_reason = self.state.get("pump_reason", "").split(' (')[0]

        # Only publish immediately if the ON/OFF state changed 
        # or the fundamental reason changed
        if self.state["pump_on"] != on or static_reason != old_static_reason:
            
            print(f"🔄 Pump {'ON' if on else 'OFF'} ({reason})")
            
            self.state["pump_on"] = on
            self.state["pump_reason"] = reason

            self.publish_state(force_all=False)
            self._last_publish = time.time()  # Ensure we publish immediately on state change, not waiting for the next interval

        else:
            # If nothing changed, just ensure the values are set
            self.state["pump_on"] = on
            self.state["pump_reason"] = reason


    def publish_state(self, force_all=False):
        """Push consolidated state to Adafruit IO."""
        if not self.network or not self.network.mqtt.connected:
            return

        feeds = self.network.feeds
        self.mqtt.publish(feeds.pump_state, int(self.state["pump_on"]))
        #self.mqtt.publish(feeds.ota_trigger, "0") 

        # Sensor values
        if force_all:
            for label, value in self.state["temps"].items():
                topic = getattr(feeds, label, None)
                if topic is None:
                    print(f"⚠️ No feed for sensor '{label}'")
                elif value is not None:
                    self.mqtt.publish(topic, value)
                
        # Full debug dump (includes daily_runtime_sec)
        self.mqtt.publish(feeds.debug, json.dumps(self.state))

    def handle_mqtt_message(self, topic, payload):
        """
        Advanced Remote Control:
        0 = Auto Mode
        1 = Manual Boost (Timed)
        2 = Holiday Mode (Stay OFF)
        """
        #print(f"📩 MQTT Received: {topic} -> {payload}") # ADD THIS DEBUG LINE
        feeds = self.network.feeds
        if topic == feeds.manual_override:
            try:
                mode = int(payload)
                
                if mode == 1: # --- BOOST TRIGGER ---
                    # Only trigger if not already boosting (prevents timer reset spam)
                    if not self.state["manual_override"]:
                        print("🚀 MQTT: Boost Triggered")
                        self.state["manual_override"] = True
                        self._manual_override_start = None # Controller will set this on next loop
                        self.state["manual_disabled"] = False # Ensure we aren't in holiday mode
                        
                        # RESET THE DASHBOARD BUTTON
                        # This sends a '0' back. The Pico will receive that '0' 
                        # in a moment, but look at the 'mode == 0' logic below...
                        self.mqtt.publish(feeds.manual_override, "0")

                elif mode == 2: # --- HOLIDAY MODE ---
                    print("🏖️ MQTT: Holiday Mode Enabled")
                    self.state["manual_disabled"] = True
                    self.state["manual_override"] = False # Kill boost if holiday is turned on

                elif mode == 0: # --- AUTO / RESET ---
                    # We ONLY turn off manual_disabled (Holiday).
                    # We do NOT force manual_override to False here. 
                    # The Controller's 90s timer is the only thing that should 
                    # turn manual_override off.
                    if self.state["manual_disabled"]:
                        print("🤖 MQTT: Returning to Auto from Holiday")
                        self.state["manual_disabled"] = False
                    
                    # Note: We leave self.state["manual_override"] alone!
                
                self.state["pump_reason"] = f"AIO Mode Change: {mode}"
            except ValueError:
                pass
        
        elif topic == feeds.ota_trigger and payload == "1":
            self.state["ota_pending"] = True
            self.state["pump_reason"] = "OTA triggered"