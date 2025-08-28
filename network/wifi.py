# wifi.py
__version__ = "0.2.0"

import time
try:
    import network
except ImportError:
    from mocks.mock_hardware import MockWiFi as wlan
else:
    wlan = network.WLAN(network.STA_IF)

class WiFiManager:
    def __init__(self, ssid, password, max_retries=10, retry_delay=2):
        self.ssid = ssid
        self.password = password
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.wlan = network.WLAN(network.STA_IF)

    def connect(self):
        """Connect to WiFi, retrying up to max_retries."""
        self.wlan.active(True)
        if self.wlan.isconnected():
            return True

        print(f"🔌 Connecting to WiFi SSID={self.ssid}...")
        self.wlan.connect(self.ssid, self.password)

        retries = 0
        while not self.wlan.isconnected() and retries < self.max_retries:
            time.sleep(self.retry_delay)
            retries += 1
            print(f"⏳ WiFi retry {retries}/{self.max_retries}...")

        if self.wlan.isconnected():
            print("✅ WiFi connected:", self.wlan.ifconfig())
            return True
        else:
            print("❌ WiFi failed")
            return False

    def is_connected(self):
        return self.wlan.isconnected()

    def disconnect(self):
        self.wlan.disconnect()
        self.wlan.active(False)
        print("🔌 WiFi disconnected")
