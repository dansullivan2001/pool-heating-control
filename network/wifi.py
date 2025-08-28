# wifi.py
__version__ = "0.3.0"

import time

try:
    import sys
    if sys.implementation.name == "micropython":
        import network as mp_network
        WiFiBackend = lambda: mp_network.WLAN(mp_network.STA_IF)
    else:
        raise ImportError
except ImportError:
    # Desktop or testing environment
    from mocks.mock_hardware import MockWiFi as WiFiBackend

class WiFiManager:
    def __init__(self, ssid, password, max_retries=10, retry_delay=2):
        self.ssid = ssid
        self.password = password
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.wlan = WiFiBackend()

    def connect(self):
        """Connect to WiFi, retrying up to max_retries."""
        try:
            self.wlan.active(True)
        except AttributeError:
            # MockWiFi has no active()
            pass

        if self.is_connected():
            return True

        print(f"🔌 Connecting to WiFi SSID={self.ssid}...")
        self.wlan.connect(self.ssid, self.password)

        retries = 0
        while not self.is_connected() and retries < self.max_retries:
            time.sleep(self.retry_delay)
            retries += 1
            print(f"⏳ WiFi retry {retries}/{self.max_retries}...")

        if self.is_connected():
            try:
                print("✅ WiFi connected:", self.wlan.ifconfig())
            except AttributeError:
                print("✅ WiFi connected (mock)")
            return True
        else:
            print("❌ WiFi failed")
            return False

    def is_connected(self):
        return getattr(self.wlan, "isconnected", lambda: False)()

    def disconnect(self):
        try:
            self.wlan.disconnect()
            self.wlan.active(False)
        except AttributeError:
            pass
        print("🔌 WiFi disconnected")

    def loop(self):
        """Keep WiFi alive — reconnect if disconnected."""
        if not self.is_connected():
            print("🔄 WiFi dropped, reconnecting...")
            self.connect()
