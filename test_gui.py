# test_gui.py
import tkinter as tk
from mock_hardware_gui import MockHardwareGUI

root = tk.Tk()
gui = MockHardwareGUI(root)

# Demo loop: toggle pump state every 2s
def demo_toggle():
    current = gui.level_var.get()
    gui.level_var.set(not current) 
    root.after(2000, demo_toggle)

def demo_print_sensors():
    temps = {name: gui.get_temperature(name) for name in gui.temp_vars}
    water = gui.water_present()
    print("Temperatures:", temps, "| Water present:", water)
    root.after(3000, demo_print_sensors)

demo_toggle()
demo_print_sensors()
root.mainloop()