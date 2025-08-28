# tests/test_wifi_publish_gui.py
import time
import tkinter as tk
from network import Network
from mocks.mock_hardware import MockHardwareGUI
from mocks import mock_hardware
from config import rom_to_label

# ---------- Setup GUI ----------
root = tk.Tk()
gui = MockHardwareGUI(root)
mock_hardware.gui = gui  # make GUI accessible to mocks

# ---------- Initialize network ----------
network = Network()                 # creates WiFi + MQTT
network.mqtt.client.loop_start()  # ✅ runs MQTT in background thread

gui.wifi = network.wifi
network.wifi.wlan.gui = gui
network.connect()                   # connect WiFi + MQTT

# ---------- Example sensor mocks ----------
# You can add more if needed
mock_temps = {rom: 25.0 for rom in rom_to_label}  # mock temperature readings

# ---------- Update loop ----------
def update_loop():

    # Handle MQTT background tasks
    network.mqtt.loop()        # flush queue, non-blocking
    network.mqtt.watchdog()    # reconnect if needed
    # Poll WiFi status
    print("WiFi connected:", network.wifi.is_connected())

    # Publish mock temperatures
    for rom, value in gui.temp_vars.items():  # temp_vars: mock ROM -> value
        label = rom_to_label.get(rom, rom)  # fallback to ROM if unmapped
        topic = f"{network.mqtt.aio_username}/feeds/{label}"
        network.mqtt.publish(topic, value.get())

    root.after(500, update_loop)  # schedule next update

# Start the periodic update
root.after(100, update_loop)
root.mainloop()
