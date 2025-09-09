# mock_hardware_gui.py
__version__ = "0.0.1"
from config import rom_to_label
from state import state

class MockHardwareGUI:
    def __init__(self, root=None):
        import tkinter as tk
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
        self.fake_roms = []  # set externally if needed
        self.disable_sensors = {rom: tk.BooleanVar(value=False) for rom in rom_to_label}
        self.led_state = tk.BooleanVar(value=False)  # False = off, True = on


        # ---------- Widgets ----------
        self.labels = {}
        self.sliders = {}
        #self.sensor_labels = {} 
        self.disable_checks = {}
        self.button = {}

        # Temperature sliders + disable checkboxes
        temp_frame = tk.LabelFrame(root, text="Temperature Sensors", padx=5, pady=5)
        temp_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)
        for idx, (rom, name) in enumerate(rom_to_label.items()):
            lbl = tk.Label(temp_frame, text=name)
            lbl.grid(row=idx, column=0, sticky="w", padx=5, pady=2)
            self.labels[rom] = lbl

            sld = tk.Scale(temp_frame, from_=0, to=55, orient="horizontal",
                           resolution=0.1, variable=self.temp_vars[rom], length=200)
            sld.grid(row=idx, column=1, padx=5, pady=2)
            self.sliders[rom] = sld

            chk = tk.Checkbutton(temp_frame, text="Disable", variable=self.disable_sensors[rom])
            chk.grid(row=idx, column=2, sticky="w", padx=5, pady=2)
            self.disable_checks[rom] = chk

        # Water level checkbox
        self.water_checkbox = tk.Checkbutton(root, text="Water Present", variable=self.level_var)
        self.water_checkbox.grid(row=1, column=0, sticky="w", padx=10, pady=5)

        # WiFi checkbox
        self.wifi_checkbox = tk.Checkbutton(root, text="WiFi Connected", variable=self.wifi_var, command=self._update_wifi)
        self.wifi_checkbox.grid(row=3, column=0, sticky="w", padx=10, pady=5)

        # Fake ROMs checkbox
        self.fake_roms_checkbox = tk.Checkbutton(root, text="Use Fake ROMs", variable=self.use_fake_roms)
        self.fake_roms_checkbox.grid(row=1, column=1, sticky="w", padx=10, pady=5)

        # Pump indicator
        self.pump_label_text = tk.Label(root, text="Pump State:")
        self.pump_label_text.grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.pump_label = tk.Label(root, textvariable=self.pump_state, fg="red")
        self.pump_label.grid(row=2, column=1, sticky="w", padx=10, pady=5)

        # LED indicator
        self.led_label_text = tk.Label(root, text="Status LED:")
        self.led_label_text.grid(row=4, column=0, sticky="w", padx=10, pady=5)
        # LED indicator as a colored circle
        self.led_canvas = tk.Canvas(root, width=20, height=20, highlightthickness=1, highlightbackground="black")
        self.led_canvas.grid(row=4, column=1, sticky="w", padx=10, pady=5)
        # draw the circle
        self.led_circle = self.led_canvas.create_oval(2, 2, 18, 18, fill="grey")



        # Override Button
        self.button = tk.Checkbutton(root, text="Manual Override", variable=self.button_var)
        self.button.grid(row=3, column=0, columnspan=2, pady=10)  

        # --- State viewer ---
        self.state_text = tk.Text(root, height=15, width=50)
        self.state_text.grid(row=5, column=0, columnspan=2, padx=10, pady=10)

        # --- Time to next test ---
        self.next_test_var = tk.StringVar(value="Next test: --:--")
        self.next_test_label = tk.Label(root, textvariable=self.next_test_var)
        self.next_test_label.grid(row=6, column=0, columnspan=2, pady=5)

    # ---------- Methods ----------
    def get_temperature(self, sensor_rom):
        return self.temp_vars[sensor_rom].get()

    def water_present(self):
        return self.level_var.get()

    def set_pump_state(self, on: bool, reason=""):
        text = "ON" if on else "OFF"
        if reason:
            text += f" ({reason})"
        self.pump_state.set(text)
        print("Pump state set to:", text)


    def _update_wifi(self):
        if self.wifi_var.get():
            self.wifi.connect()
        else:
            self.wifi.disconnect()

    def wifi_connected(self):
        return self.wifi_var.get()
    
    def get_wifi_state(self):
        return self.wifi_var.get()

    # check this with ChatGPT
    def button_pressed(self):
        return self.button_var.get()

    def set_led_state(self, on: bool):
        color = "green" if on else "grey"  # green = LED on, grey = off
        self.led_canvas.itemconfig(self.led_circle, fill=color)
        print("LED state:", "ON" if on else "OFF")

    def bind_state(self, state):
        """Give GUI access to the shared controller state dict"""
        self.state = state

    def update_from_state(self):
        """Refresh GUI widgets based on controller state"""
        if not hasattr(self, "state"):
            return

        # Pump
        pump_on = self.state.get("pump_on", False)
        reason = self.state.get("pump_reason", "")
        self.set_pump_state(pump_on, reason)

        # LED
        #self.set_led_state(self.state.get("led_on", False))

        # Override
        self.button_var.set(self.state.get("override", False))

        # Temps
        temps = self.state.get("temps", {})
        for rom, label in rom_to_label.items():
            if rom in temps and self.labels.get(rom):
                value = temps[rom]
                if value is not None:
                    self.labels[rom].config(text=f"{label}: {value:.1f} °C", fg="black")
                else:
                    self.labels[rom].config(text=f"{label}: ERROR", fg="red")

        t_next = self.state.get("time_to_next_test", None)
        if t_next is not None:
            mins, secs = divmod(int(t_next), 60)
            self.next_test_var.set(f"Next test: {mins:02d}:{secs:02d}")

        # --- State dump ---
        self.state_text.delete("1.0", "end")
        for k, v in self.state.items():
            self.state_text.insert("end", f"{k}: {v}\n")

    def set_wifi_state(self, connected: bool):
        """Update the WiFi checkbox from the mock WiFi object"""
        self.wifi_var.set(connected)