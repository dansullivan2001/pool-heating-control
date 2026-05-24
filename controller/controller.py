# controller/controller.py
__version__ = "0.9.6"

import time
import json
from state import state

try:
    import machine
    def _make_pump_pin(pin_num):
        return machine.Pin(pin_num, machine.Pin.OUT)
except ImportError:
    from mocks.mock_hardware import MockPin
    def _make_pump_pin(pin_num):
        return MockPin(pin_num)


class Controller:
    def __init__(self, network, config, sensors=None, pump_pin=None):
        """
        Controller handles pump logic, MQTT publishing, and safety checks.

        Safety chain priority (highest to lowest):
          1. Water level (dry-run protect)
          2. Enclosure temperature (overtemp / sensor missing)
          3. Flow/Return sensors missing
          4. Manual boost (timed)
          5. Core hours / holiday gate
          6. Solar delta automatic control
          7. Periodic test run
        """
        self.network = network
        self.network.mqtt.message_handler = self.handle_mqtt_message
        self.sensors = sensors  # Sensors object (optional, used for local button)
        self.state = state      # shared global state
        self.config = config
        self.mqtt = network.mqtt
        self._pump_pin = pump_pin

        # --- Timing ---
        self._last_publish = 0
        self._manual_override_start = None
        self._test_start_time = None
        self._pump_on_since = None

        # Initialise test timer to now so we don't immediately test on boot
        now = time.time()
        self._last_test = now
        self.state["last_test_ts"] = now
        self.state["time_to_next_test"] = self.config.get("pump_test_interval", 600)

    # -------------------------------------------------------------------------
    # Main loop
    # -------------------------------------------------------------------------

    def loop(self, now_ts=None):
        """
        One controller cycle. Call as frequently as possible from main.py.
        All logic is non-blocking.
        """
        now = now_ts if now_ts is not None else time.time()

        # 1. Read local button (if sensors available)
        self._check_local_button(now)

        # 3. Safety chain — sets safety_stop=True and returns early if unsafe
        safety_stop, enclosure_missing = self._run_safety_chain()
        if safety_stop:
            self._check_publish(now)
            return

        # 4. Core hours / holiday gate + automatic control
        self._run_control_logic(now, enclosure_missing)

        # 5. Periodic publish
        self._check_publish(now)

    # -------------------------------------------------------------------------
    # Step 1: Local button
    # -------------------------------------------------------------------------

    def _check_local_button(self, now):
        """Trigger manual boost from physical button press."""
        if self.sensors is None:
            return
        try:
            if self.sensors.button.is_pressed():
                if not self.state["manual_override"]:
                    print("🔘 Button: Boost Triggered")
                    self.state["manual_override"] = True
                    self.state["manual_disabled"] = False
                    self._manual_override_start = None  # controller sets this on next loop
        except Exception as e:
            print(f"⚠️ Button read error: {e}")

    # -------------------------------------------------------------------------
    # Step 3: Safety chain
    # -------------------------------------------------------------------------

    def _run_safety_chain(self):
        """
        Evaluate all hardware safety conditions in priority order.

        Returns (safety_stop: bool, enclosure_missing: bool).
        safety_stop=True means the pump has been forced off and the caller
        should skip all control logic for this cycle.
        """
        temps = self.state.get("temps", {})
        t_enclosure = temps.get("tEnclosure")
        enclosure_missing = t_enclosure is None
        essential_missing = temps.get("tFlow") is None or temps.get("tReturn") is None

        # --- Priority 1: Water level ---
        if not self.state["water_level_ok"]:
            self._set_pump(False, reason="dry run protect", urgent=True)
            self.state["dry_run_protect"] = True
            self.state["overtemp_shutdown"] = False
            self.state["enclosure_sensor_missing"] = False
            self.state["manual_override"] = False  # safety always wins
            self._manual_override_start = None
            return True, enclosure_missing

        self.state["dry_run_protect"] = False

        # --- Priority 2a: Enclosure sensor missing ---
        if enclosure_missing:
            # Treat a missing enclosure sensor as a safety stop — we can't
            # verify the electronics are safe. Flag it distinctly from overtemp
            # so the LED and MQTT report the right thing.
            self._set_pump(False, reason="enclosure sensor missing", urgent=True)
            self.state["enclosure_sensor_missing"] = True
            self.state["overtemp_shutdown"] = False
            self.state["manual_override"] = False
            self._manual_override_start = None
            return True, True

        self.state["enclosure_sensor_missing"] = False

        # --- Priority 2b: Enclosure overtemp ---
        if t_enclosure > self.config["max_enclosure_temp"]:
            self._set_pump(False, reason="enclosure overtemp", urgent=True)
            self.state["overtemp_shutdown"] = True
            self.state["manual_override"] = False
            self._manual_override_start = None
            return True, False

        self.state["overtemp_shutdown"] = False

        # --- Priority 3: Essential flow/return sensors missing ---
        if essential_missing:
            # Not a hard safety stop (enclosure is fine) but we can't make
            # a sensible heating decision. Stop the pump and flag for LED.
            self._set_pump(False, reason="flow/return sensor missing")
            self.state["dry_run_protect"] = False
            self.state["overtemp_shutdown"] = False
            return True, False

        # All safety checks passed
        return False, False

    # -------------------------------------------------------------------------
    # Step 4: Control logic
    # -------------------------------------------------------------------------

    def _run_control_logic(self, now, enclosure_missing):
        """Solar heating logic, manual boost, and periodic test."""
        current_hour = time.localtime(now)[3]
        start_h = self.config.get("core_start_hour", 9)
        end_h = self.config.get("core_end_hour", 18)
        is_core_hours = start_h <= current_hour < end_h
        is_holiday = self.state.get("manual_disabled", False)

        # Update next-test countdown for GUI / debug.
        # While the pump is already running, freeze the timer — sensors are
        # already circulating so no test is needed until the pump goes idle.
        test_int = self.config.get("pump_test_interval", 600)
        if self.state["pump_on"] and not self.state["test_running"]:
            self._last_test = now
            self.state["last_test_ts"] = now
        self.state["time_to_next_test"] = max(0, test_int - (now - self._last_test))

        # --- Manual boost (works outside core hours, but not during safety stop) ---
        if self.state["manual_override"]:
            if self._manual_override_start is None:
                self._manual_override_start = now
                # Reset test timer so a test doesn't immediately follow a boost
                self._last_test = now
                self.state["last_test_ts"] = now

            elapsed = now - self._manual_override_start
            duration = self.config.get("manual_override_duration", 90)

            if elapsed <= duration:
                self._set_pump(True, reason=f"manual boost ({elapsed:.0f}/{duration}s)")
                return  # skip automatic logic while boosting
            else:
                # Boost expired — fall through to normal logic
                print("⏱️ Manual boost expired")
                self.state["manual_override"] = False
                self._manual_override_start = None

        # --- Night / holiday shutdown ---
        if not is_core_hours or is_holiday:
            self.state["test_running"] = False
            reason = "holiday mode" if is_holiday else f"sleep (hour {current_hour})"
            self._set_pump(False, reason=reason)
            return

        # --- Within core hours: solar delta logic ---
        temps = self.state.get("temps", {})
        flow = temps.get("tFlow")
        ret = temps.get("tReturn")

        # Hysteresis: start from current pump state to avoid rapid cycling
        auto_wants_pump = self.state["pump_on"]
        auto_reason = self.state.get("pump_reason", "")

        if flow is not None and ret is not None:
            delta = ret - flow
            self.state["delta_t_flow_return"] = round(delta, 2)
            high_thresh = self.config.get("delta_threshold_high", 0.5)
            low_thresh = self.config.get("delta_threshold_low", 0.1)

            if not self.state["pump_on"] and delta >= high_thresh:
                auto_wants_pump = True
                auto_reason = f"solar heating ({delta:.1f}C)"
            elif self.state["pump_on"] and delta < low_thresh:
                auto_wants_pump = False
                auto_reason = f"insufficient gain ({delta:.1f}C)"
            elif auto_wants_pump:
                # Pump is on, delta still adequate — keep running
                auto_reason = f"solar heating ({delta:.1f}C)"
            else:
                # Pump is off, delta not yet high enough — keep off
                auto_reason = f"waiting for solar gain ({delta:.1f}C)"
        else:
            self.state["delta_t_flow_return"] = None
            auto_wants_pump = False
            auto_reason = "flow/return sensor missing"

        plate = temps.get("tSolarPlate")
        ref   = temps.get("tSolarRef")
        if plate is not None and ref is not None:
            self.state["delta_irradiance"] = round(plate - ref, 2)
        else:
            self.state["delta_irradiance"] = None

        # --- Periodic test run ---
        # WHY: tFlow and tReturn only reflect actual roof conditions when water
        # is circulating. When the pump is off, both sensors stagnate and the
        # delta reading becomes meaningless. Running the pump briefly every
        # test_int seconds forces circulation so the readings update and the
        # solar delta logic can make a correct heating decision.
        # test_dur must be long enough for readings to stabilise (default 90 s).
        test_dur = self.config.get("pump_test_duration", 90)

        if not self.state["test_running"] and (now - self._last_test) >= test_int:
            print("🧪 Starting periodic test")
            self.state["test_running"] = True
            self._test_start_time = now
            # _last_test is reset when the test *finishes*, not when it starts,
            # so test_int measures the gap between end of one test and start of next.

        if self.state["test_running"]:
            if (now - self._test_start_time) < test_dur:
                self._set_pump(True, reason="periodic test")
            else:
                print("✅ Periodic test finished")
                self.state["test_running"] = False
                self._last_test = now
                self.state["last_test_ts"] = now
                # Immediately re-evaluate solar logic after test ends
                self._set_pump(auto_wants_pump, reason=auto_reason)
        else:
            self._set_pump(auto_wants_pump, reason=auto_reason)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _set_pump(self, on: bool, reason: str = "", urgent: bool = False):
        """
        Update pump state. Publishes immediately on any meaningful change.

        The 'static_reason' comparison strips the dynamic timer portion
        "(elapsed/duration s)" so we don't publish on every loop tick
        during a boost, only when the fundamental reason changes.

        urgent=True bypasses the MQTT rate limiter for safety-critical stops.
        """
        static_reason = reason.split(" (")[0]
        old_static_reason = self.state.get("pump_reason", "").split(" (")[0]

        state_changed = self.state["pump_on"] != on
        reason_changed = static_reason != old_static_reason

        self.state["pump_on"] = on
        self.state["pump_reason"] = reason

        if self._pump_pin is not None:
            self._pump_pin.value(1 if on else 0)

        if state_changed:
            self._pump_on_since = time.time() if on else None

        if state_changed or reason_changed:
            print(f"🔄 Pump {'ON' if on else 'OFF'} — {reason}")
            self.publish_state(force_all=False, urgent=urgent)
            self._last_publish = time.time()

    def _check_publish(self, now):
        """Periodic full-state publish on interval."""
        t = time.localtime()
        start_h = self.config.get("core_start_hour", 8)
        end_h = self.config.get("core_end_hour", 18)
        in_core = start_h <= t[3] < end_h
        interval = self.config["publish_interval"] if in_core else self.config["publish_interval_off_hours"]
        if (now - self._last_publish) >= interval:
            self.publish_state(force_all=True)
            self._last_publish = now

    def publish_state(self, force_all: bool = False, urgent: bool = False):
        """
        Push state to Adafruit IO via MQTT.

        force_all=True: publish all sensor readings (used for periodic updates).
        force_all=False: publish only pump state + debug (used on state change).
        urgent=True: bypasses MQTT rate limiter (used for safety stops).
        """
        if not self.network or not self.network.mqtt.connected:
            return

        feeds = self.network.feeds
        now = time.time()

        # Always publish pump state
        self.mqtt.publish(feeds.pump_state, int(self.state["pump_on"]), urgent=urgent)

        # Sensor readings on periodic publish
        if force_all:
            for label, value in self.state["temps"].items():
                topic = getattr(feeds, label, None)
                if topic is not None and value is not None:
                    self.mqtt.publish(topic, value)
            if self.state["delta_t_flow_return"] is not None:
                self.mqtt.publish(feeds.delta_t_flow_return, self.state["delta_t_flow_return"])
            if self.state["delta_irradiance"] is not None:
                self.mqtt.publish(feeds.delta_irradiance, self.state["delta_irradiance"])

        # Derived fields
        t = time.localtime(now)
        local_time = "{:02d}:{:02d}".format(t[3], t[4])
        start_h = self.config.get("core_start_hour", 9)
        end_h = self.config.get("core_end_hour", 18)
        in_core_hours = start_h <= t[3] < end_h
        pump_runtime_s = (
            int(now - self._pump_on_since)
            if (self.state["pump_on"] and self._pump_on_since is not None)
            else 0
        )

        debug = {
            "fw_version":               self.state["fw_version"],
            "pump_on":                  self.state["pump_on"],
            "pump_reason":              self.state["pump_reason"],
            "pump_runtime_s":           pump_runtime_s,
            "delta_t_flow_return":       self.state["delta_t_flow_return"],
            "delta_irradiance":         self.state["delta_irradiance"],
            "temps":                    self.state["temps"],
            "local_time":               local_time,
            "in_core_hours":            in_core_hours,
            "manual_override":          self.state["manual_override"],
            "manual_disabled":          self.state["manual_disabled"],
            "test_running":             self.state["test_running"],
            "time_to_next_test":        int(self.state["time_to_next_test"]),
            "water_level_ok":           self.state["water_level_ok"],
            "sensors_ok":               self.state["sensors_ok"],
            "disconnected_sensors":     self.state["disconnected_sensors"],
            "dry_run_protect":          self.state["dry_run_protect"],
            "overtemp_shutdown":        self.state["overtemp_shutdown"],
            "enclosure_sensor_missing": self.state["enclosure_sensor_missing"],
            "critical_error":           self.state["critical_error"],
            "last_error":               self.state["last_error"],
        }

        self.mqtt.publish(feeds.debug, json.dumps(debug))

    def handle_mqtt_message(self, topic, payload):
        """
        Handle incoming MQTT commands from Adafruit IO dashboard.

        Mode values:
          0 = Auto (cancel holiday mode; boost timer is unaffected)
          1 = Manual boost (timed, one-shot)
          2 = Holiday mode (system stays off until mode 0 received)
        """
        feeds = self.network.feeds

        if topic == feeds.manual_override:
            try:
                mode = int(payload)

                if mode == 1:
                    # Boost: only trigger if not already boosting (prevents timer reset spam)
                    if not self.state["manual_override"]:
                        print("🚀 MQTT: Boost triggered")
                        self.state["manual_override"] = True
                        self.state["manual_disabled"] = False
                        self._manual_override_start = None  # will be set on next loop
                        # Reset dashboard button back to 0 so it acts as a momentary trigger
                        self.mqtt.publish(feeds.manual_override, "0")

                elif mode == 2:
                    print("🏖️ MQTT: Holiday mode enabled")
                    self.state["manual_disabled"] = True
                    self.state["manual_override"] = False  # cancel any active boost
                    self._manual_override_start = None

                elif mode == 0:
                    # Cancel holiday only. The boost timer manages itself.
                    if self.state["manual_disabled"]:
                        print("🤖 MQTT: Returning to auto from holiday")
                        self.state["manual_disabled"] = False

                self.state["pump_reason"] = f"AIO mode change: {mode}"

            except ValueError:
                print(f"⚠️ MQTT: Unrecognised override payload: '{payload}'")

        elif topic == feeds.ota_trigger and payload == "1":
            print("🔄 MQTT: OTA update requested")
            self.state["ota_pending"] = True
            self.state["pump_reason"] = "OTA pending"