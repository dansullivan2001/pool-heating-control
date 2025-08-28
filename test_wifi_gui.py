# tests/test_wifi_gui.py
import time
import tkinter as tk
from network import WiFiManager
from mocks.mock_hardware import MockHardwareGUI
from mocks import mock_hardware
# ---------- Setup GUI ----------
root = tk.Tk()
gui = MockHardwareGUI(root)
mock_hardware.gui = gui  # make GUI accessible to mocks

wifi = WiFiManager("ssid", "password")
wifi.connect()

def poll():
    while True:
        print("WiFi connected:", wifi.is_connected())
        time.sleep(2)

import threading
threading.Thread(target=poll, daemon=True).start()

# Start GUI (toggle WiFi on/off here)
gui.run()
