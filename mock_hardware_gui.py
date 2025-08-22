# mock_hardware_gui.py
__version__ = "0.0.1"
# mock_hardware_gui.py
import tkinter as tk

class MockHardwareGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Mock Pump Controller GUI")

        # store widgets so they aren't GC'ed
        self.labels = {}
        self.sliders = {}

        # Temperature sliders
        self.temp_vars = {}
        for idx, sensor in enumerate(["tFlow", "tReturn", "tAmbient", "tEnclosure"]):
            var = tk.DoubleVar(value=20.0)
            self.temp_vars[sensor] = var

            lbl = tk.Label(root, text=sensor)
            lbl.grid(row=idx, column=0, sticky="w", padx=5, pady=5)
            self.labels[sensor] = lbl

            sld = tk.Scale(root, from_=0, to=50, orient="horizontal",
                           resolution=0.1, variable=var, length=200)
            sld.grid(row=idx, column=1, padx=5, pady=5)
            self.sliders[sensor] = sld

        # Water level switch
        self.level_var = tk.BooleanVar(value=True)
        self.water_checkbox = tk.Checkbutton(
            root, text="Water Present", variable=self.level_var,
            onvalue=True, offvalue=False
        )
        self.water_checkbox.grid(row=len(self.temp_vars), column=0, columnspan=2, sticky="w", padx=5, pady=5)

        # Pump indicator
        self.pump_state = tk.StringVar(value="OFF")
        self.pump_label_text = tk.Label(root, text="Pump State:")
        self.pump_label_text.grid(row=10, column=0, sticky="w", padx=5, pady=5)

        self.pump_label = tk.Label(root, textvariable=self.pump_state, fg="red")
        self.pump_label.grid(row=10, column=1, sticky="w", padx=5, pady=5)
