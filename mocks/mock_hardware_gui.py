# mock_hardware_gui.py
__version__ = "0.0.1"
from config import rom_to_label

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
        self.wifi_state = tk.BooleanVar(value=True)
        self.pump_state = tk.StringVar(value="OFF")
        self.use_fake_roms = tk.BooleanVar(value=False)
        self.fake_roms = []  # set externally if needed
        self.disable_sensors = {rom: tk.BooleanVar(value=False) for rom in rom_to_label}

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

            sld = tk.Scale(temp_frame, from_=0, to=50, orient="horizontal",
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
        self.wifi_state = tk.Checkbutton(root, text="WiFi Connected", variable=self.wifi_state, command=self._update_wifi)
        self.wifi_state.grid(row=3, column=0, sticky="w", padx=10, pady=5)

        # Fake ROMs checkbox
        self.fake_roms_checkbox = tk.Checkbutton(root, text="Use Fake ROMs", variable=self.use_fake_roms)
        self.fake_roms_checkbox.grid(row=1, column=1, sticky="w", padx=10, pady=5)

        # Pump indicator
        self.pump_label_text = tk.Label(root, text="Pump State:")
        self.pump_label_text.grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.pump_label = tk.Label(root, textvariable=self.pump_state, fg="red")
        self.pump_label.grid(row=2, column=1, sticky="w", padx=10, pady=5)

        # Override Button
        self.button = tk.Button(root, text="Override Pump")
        self.button.grid(row=3, column=0, columnspan=2, pady=10)  

    # ---------- Methods ----------
    def get_temperature(self, sensor_rom):
        return self.temp_vars[sensor_rom].get()

    def water_present(self):
        return self.level_var.get()

    def set_pump_state(self, on: bool):
        self.pump_state.set("ON" if on else "OFF")
        print("Pump state set to:", "ON" if on else "OFF")

    def _update_wifi(self):
        if self.wifi_state.get():
            mock_wifi.connect()
        else:
            mock_wifi.disconnect()

    def wifi_connected(self):
        return self.wifi_state.get()

    # check this with ChatGPT
    def override(self):
        return self.button.invoke()
