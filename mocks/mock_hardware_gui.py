# mocks/mock_hardware_gui.py
__version__ = "0.1.0"

import tkinter as tk
from config import rom_to_label


class MockHardwareGUI:
    """
    Tkinter GUI for desktop simulation of the pool controller hardware.

    Responsibilities (view layer only):
      - Present sliders/checkboxes representing physical hardware inputs
      - Display system status outputs (pump, LED, timers)
      - Provide read methods that the test harness queries each loop

    This class does NOT write to shared state directly. All state writes
    are the responsibility of update_loop() in the test harness.
    The one exception is set_wifi_state() / set_led_state() which are
    called by the network/LED layers to reflect their own status.
    """

    def __init__(self, root=None):
        if root is None:
            root = tk.Tk()
        self.root = root
        self.root.title("Pool Controller Simulator")

        # ----------------------------------------------------------------
        # Tk Variables (inputs from user / outputs to display)
        # ----------------------------------------------------------------
        self.temp_vars      = {rom: tk.DoubleVar(value=20.0) for rom in rom_to_label}
        self.disable_sensors = {rom: tk.BooleanVar(value=False) for rom in rom_to_label}
        self.level_var      = tk.BooleanVar(value=True)
        self.wifi_var       = tk.BooleanVar(value=True)
        self.button_var     = tk.BooleanVar(value=False)
        self.use_fake_roms  = tk.BooleanVar(value=False)
        self.time_mode      = tk.StringVar(value="auto")   # auto | day | night
        self.pump_state     = tk.StringVar(value="OFF")
        self.next_test_var  = tk.StringVar(value="Next test: --:--")
        self.led_pattern_var = tk.StringVar(value="ok")

        self._build_ui()

    # ----------------------------------------------------------------
    # UI construction
    # ----------------------------------------------------------------

    def _build_ui(self):
        root = self.root

        # --- Temperature sensors ---
        temp_frame = tk.LabelFrame(root, text="Temperature Sensors", padx=10, pady=5)
        temp_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)

        for idx, (rom, name) in enumerate(rom_to_label.items()):
            tk.Label(temp_frame, text=name).grid(row=idx, column=0, sticky="w")
            tk.Scale(
                temp_frame, from_=0, to=60, orient="horizontal",
                resolution=0.1, variable=self.temp_vars[rom], length=180
            ).grid(row=idx, column=1, padx=5)
            tk.Checkbutton(
                temp_frame, text="Disable", variable=self.disable_sensors[rom]
            ).grid(row=idx, column=2, sticky="w")

        # --- Hardware simulation controls ---
        sim_frame = tk.LabelFrame(root, text="Hardware Simulation", padx=10, pady=5)
        sim_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)

        tk.Checkbutton(sim_frame, text="Water Present",   variable=self.level_var ).grid(row=0, column=0, sticky="w")
        tk.Checkbutton(sim_frame, text="Use Fake ROMs",   variable=self.use_fake_roms).grid(row=0, column=1, sticky="w")
        tk.Checkbutton(sim_frame, text="WiFi Connected",  variable=self.wifi_var  ).grid(row=1, column=0, sticky="w")
        tk.Checkbutton(sim_frame, text="Manual Boost",    variable=self.button_var).grid(row=1, column=1, sticky="w")

        # --- Status outputs ---
        status_frame = tk.LabelFrame(root, text="System Status", padx=10, pady=5)
        status_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)

        tk.Label(status_frame, text="Pump:").grid(row=0, column=0, sticky="w")
        self.pump_label = tk.Label(
            status_frame, textvariable=self.pump_state,
            fg="red", font=("Helvetica", 10, "bold")
        )
        self.pump_label.grid(row=0, column=1, sticky="w")

        tk.Label(status_frame, text="LED pattern:").grid(row=1, column=0, sticky="w")
        self.led_pattern_label = tk.Label(
            status_frame, textvariable=self.led_pattern_var, fg="blue"
        )
        self.led_pattern_label.grid(row=1, column=1, sticky="w")

        tk.Label(status_frame, text="LED:").grid(row=2, column=0, sticky="w")
        self.led_canvas = tk.Canvas(status_frame, width=20, height=20, highlightthickness=0)
        self.led_canvas.grid(row=2, column=1, sticky="w", pady=2)
        self.led_circle = self.led_canvas.create_oval(2, 2, 18, 18, fill="grey")

        tk.Label(status_frame, textvariable=self.next_test_var).grid(
            row=3, column=0, columnspan=2, sticky="w"
        )

        # --- Time simulation ---
        time_frame = tk.LabelFrame(root, text="Time Simulation", padx=10, pady=5)
        time_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)

        tk.Radiobutton(time_frame, text="Real time",       variable=self.time_mode, value="auto" ).grid(row=0, column=0)
        tk.Radiobutton(time_frame, text="Force day (12:00)", variable=self.time_mode, value="day"  ).grid(row=0, column=1)
        tk.Radiobutton(time_frame, text="Force night (23:00)", variable=self.time_mode, value="night").grid(row=0, column=2)

        # --- State dump ---
        self.state_text = tk.Text(root, height=22, width=55, font=("Courier", 10))
        self.state_text.grid(row=4, column=0, columnspan=2, padx=10, pady=10)

    # ----------------------------------------------------------------
    # Hardware input accessors (read by test harness each loop)
    # ----------------------------------------------------------------

    def get_temperature(self, sensor_rom):
        """Return slider value for a given ROM. Returns None if sensor disabled."""
        if self.disable_sensors.get(sensor_rom) and self.disable_sensors[sensor_rom].get():
            return None
        var = self.temp_vars.get(sensor_rom)
        return var.get() if var is not None else None

    def water_present(self):
        return self.level_var.get()

    def button_pressed(self):
        """True while the Manual Boost checkbox is ticked."""
        return self.button_var.get()

    def wifi_connected(self):
        return self.wifi_var.get()

    def get_wifi_state(self):
        """Alias used by MockWiFi."""
        return self.wifi_var.get()

    # ----------------------------------------------------------------
    # Output setters (called by LED / network layers)
    # ----------------------------------------------------------------

    def set_led_state(self, on: bool):
        color = "green" if on else "grey"
        self.led_canvas.itemconfig(self.led_circle, fill=color)

    def set_pump_state(self, on: bool, reason: str = ""):
        color = "green" if on else "red"
        text  = "ON" if on else "OFF"
        if reason:
            text += f"  ({reason})"
        self.pump_state.set(text)
        self.pump_label.config(fg=color)

    def set_wifi_state(self, connected: bool):
        self.wifi_var.set(connected)

    # ----------------------------------------------------------------
    # State binding and display refresh
    # ----------------------------------------------------------------

    def bind_state(self, state):
        """Call once after controller is created to bind the shared state dict."""
        self._state = state

    def bind_status_led(self, status_led):
        """
        Bind the StatusLED instance so we can call current_pattern() directly
        instead of duplicating the pattern-selection logic here.
        """
        self._status_led = status_led

    def update_from_state(self):
        """
        Refresh all GUI output widgets from shared state.
        Read-only: does NOT write back to state.
        Called by the test harness after controller.loop().
        """
        if not hasattr(self, "_state"):
            return

        s = self._state

        # Pump display
        self.set_pump_state(s.get("pump_on", False), s.get("pump_reason", ""))

        # Manual override checkbox — reflects controller state, not user input
        # (so it unchecks itself when boost timer expires)
        self.button_var.set(s.get("manual_override", False))

        # Next test countdown
        t_next = s.get("time_to_next_test", 0)
        mins, secs = divmod(int(max(t_next, 0)), 60)
        self.next_test_var.set(f"Next test: {mins:02d}:{secs:02d}")

        # LED pattern name — use StatusLED directly if bound, else read from state
        if hasattr(self, "_status_led"):
            pattern = self._status_led.current_pattern()
        else:
            pattern = s.get("led_pattern", "unknown")
        self.led_pattern_var.set(pattern)

        # State dump
        self.state_text.delete("1.0", "end")
        self.state_text.insert("end", f"LED pattern: {pattern}\n")
        self.state_text.insert("end", "-" * 35 + "\n")
        for k in sorted(s.keys()):
            self.state_text.insert("end", f"{k}: {s[k]}\n")