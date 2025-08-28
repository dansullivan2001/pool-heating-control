# tests/test_wifi.py
import time

try:
    from wifi import WiFiManager
except ImportError:
    # Running on Mac, use mock
    class WiFiManager:
        def __init__(self, ssid, password, max_retries=3, retry_delay=1):
            self.ssid = ssid
            self.password = password
            self.connected = False

        def connect(self):
            print(f"🔌 [MOCK] Connecting to {self.ssid}...")
            time.sleep(1)
            self.connected = True
            print("✅ [MOCK] WiFi connected")
            return True

        def is_connected(self):
            return self.connected

        def disconnect(self):
            self.connected = False
            print("🔌 [MOCK] WiFi disconnected")

# ---- Run test
wifi = WiFiManager("testSSID", "testPASS")
wifi.connect()
print("WiFi status:", wifi.is_connected())
wifi.disconnect()
