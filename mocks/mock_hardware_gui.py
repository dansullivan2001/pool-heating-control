# mock_hardware_gui.py
__version__ = "0.0.2"

import tkinter as tk
from config import rom_to_label

class MockHardwareGUI:
    def __init__(self, root=None):
        if root is None:
            root = tk.Tk()
        self.root = root
        self.root.title("Mock Pump Controller GUI")

        # ---------- Variables ----------
        self.temp_vars = {rom: tk.DoubleVar(value=20.0) for rom in rom_to_label}
        self.level_var = tk.BooleanVar(value=True)
        self.wifi_var = tk.BooleanVar(value=True)
        self.button_var = tk.BooleanVar(value=False)
        self.pump_state = tk.StringVar(value="OFF")
        self.use_fake_roms = tk.BooleanVar(value=False)
        self.disable_sensors = {rom: tk.BooleanVar(value=False) for rom in rom_to_label}
        self.time_mode = tk.StringVar(value="auto") # Options: auto, day, night
        self.next_test_var = tk.StringVar(value="Next test: --:--")

        # ---------- Layout: Sensor Inputs ----------
        temp_frame = tk.LabelFrame(root, text="Temperature Sensors", padx=10, pady=5)
        temp_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)
        
        for idx, (rom, name) in enumerate(rom_to_label.items()):
            tk.Label(temp_frame, text=name).grid(row=idx, column=0, sticky="w")
            
            tk.Scale(temp_frame, from_=0, to=60, orient="horizontal", resolution=0.1, 
                     variable=self.temp_vars[rom], length=180).grid(row=idx, column=1, padx=5)
            
            tk.Checkbutton(temp_frame, text="Disable", 
                           variable=self.disable_sensors[rom]).grid(row=idx, column=2, sticky="w")

        # ---------- Layout: System Simulation Controls ----------
        sim_frame = tk.LabelFrame(root, text="Hardware Simulation", padx=10, pady=5)
        sim_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)

        tk.Checkbutton(sim_frame, text="Water Present", variable=self.level_var).grid(row=0, column=0, sticky="w")
        tk.Checkbutton(sim_frame, text="Use Fake ROMs", variable=self.use_fake_roms).grid(row=0, column=1, sticky="w")
        tk.Checkbutton(sim_frame, text="WiFi Connected", variable=self.wifi_var).grid(row=1, column=0, sticky="w")
        tk.Checkbutton(sim_frame, text="Manual Override", variable=self.button_var).grid(row=1, column=1, sticky="w")

        # ---------- Layout: Status Outputs ----------
        status_frame = tk.LabelFrame(root, text="System Status", padx=10, pady=5)
        status_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)

        tk.Label(status_frame, text="Pump State:").grid(row=0, column=0, sticky="w")
        self.pump_label = tk.Label(status_frame, textvariable=self.pump_state, fg="red", font=('Helvetica', 10, 'bold'))
        self.pump_label.grid(row=0, column=1, sticky="w")

        tk.Label(status_frame, text="Status LED:").grid(row=1, column=0, sticky="w")
        self.led_canvas = tk.Canvas(status_frame, width=20, height=20, highlightthickness=0)
        self.led_canvas.grid(row=1, column=1, sticky="w", pady=2)
        self.led_circle = self.led_canvas.create_oval(2, 2, 18, 18, fill="grey")

        tk.Label(status_frame, textvariable=self.next_test_var).grid(row=2, column=0, columnspan=2, sticky="w")

        # ---------- Layout: Time Simulation Mode ----------
        time_frame = tk.LabelFrame(root, text="Time Simulation Mode", padx=10, pady=5)
        time_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)

        tk.Radiobutton(time_frame, text="Real Time (Auto)", variable=self.time_mode, value="auto").grid(row=0, column=0)
        tk.Radiobutton(time_frame, text="Force Day (12:00)", variable=self.time_mode, value="day").grid(row=0, column=1)
        tk.Radiobutton(time_frame, text="Force Night (23:00)", variable=self.time_mode, value="night").grid(row=0, column=2)

        # ---------- Layout: Debug State View ----------
        self.state_text = tk.Text(root, height=20, width=55, font=('Courier', 11))
        self.state_text.grid(row=4, column=0, columnspan=2, padx=10, pady=10)

    # ---------- Logic Methods ----------
    def get_temperature(self, sensor_rom):
        return self.temp_vars[sensor_rom].get()

    def water_present(self):
        return self.level_var.get()

    def button_pressed(self):
        return self.button_var.get()

    def wifi_connected(self):
        return self.wifi_var.get()
    
    def get_wifi_state(self):
        """Used by mock_hardware.py to prevent AttributeErrors."""
        return self.wifi_var.get()

    def set_pump_state(self, on: bool, reason=""):
        color = "green" if on else "red"
        text = "ON" if on else "OFF"
        if reason:
            text += f" ({reason})"
        self.pump_state.set(text)
        self.pump_label.config(fg=color)

    def set_led_state(self, on: bool):
        color = "green" if on else "grey"
        self.led_canvas.itemconfig(self.led_circle, fill=color)

    def bind_state(self, state):
        self.state = state

    def update_from_state(self):
        """Refresh GUI widgets based on controller state"""
        if not hasattr(self, "state"):
            return

        # 1. Sync GUI Checkboxes TO State (Fixes Water/WiFi errors)
        self.state["water_level_ok"] = self.level_var.get()
        self.state["wifi_connected"] = self.wifi_var.get()

        # 2. Update Pump Text
        pump_on = self.state.get("pump_on", False)
        reason = self.state.get("pump_reason", "")
        self.set_pump_state(pump_on, reason)

        # 3. Update LED Visual (The part you are replacing)
        #led_status = self.state.get("led_on", False)
        #self.set_led_state(led_status)

        # 4. Update Manual Override Checkbox
        self.button_var.set(self.state.get("manual_override", False))

        # 5. Update Next Test Timer Label
        t_next = self.state.get("time_to_next_test", 0)
        mins, secs = divmod(int(t_next), 60)
        self.next_test_var.set(f"Next test: {mins:02d}:{secs:02d}")

        # --- ADDED: LED DEBUG CALCULATOR ---
        # We replicate the StatusLED logic here to see what it SHOULD be doing
        s = self.state
        if s.get("critical_error"):
            target_pattern = "CRITICAL (1s on, 1s off)"
        elif not s.get("sensors_ok", True) or s.get("disconnected_sensors"):
            target_pattern = "SENSOR_MISSING (1.5s on, 0.1s off)"
        elif not s.get("mqtt_connected", True):
            target_pattern = "MQTT_OFFLINE (Rapid Flash - 0.25s on, 0.25s off)"
        else:
            target_pattern = "OK (Heartbeat - 0.2s on, 2s off)"

        # 6. Refresh State Dump Text
        self.state_text.delete("1.0", "end")
        self.state_text.insert("end", f"=== LED DEBUG ===\n")
        self.state_text.insert("end", f"Target Pattern: {target_pattern}\n")
        self.state_text.insert("end", f"Critical Flag: {s.get('critical_error')}\n")
        self.state_text.insert("end", f"Sensors OK:    {s.get('sensors_ok')}\n")
        self.state_text.insert("end", f"MQTT Conn:     {s.get('mqtt_connected')}\n")
        self.state_text.insert("end", f"-----------------\n\n")
        for k in sorted(self.state.keys()):
            self.state_text.insert("end", f"{k}: {self.state[k]}\n")

    def set_wifi_state(self, connected: bool):
        self.wifi_var.set(connected)