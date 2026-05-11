# network/wifi.py
__version__ = "0.4.0"

import time

try:
    import sys
    if sys.implementation.name == "micropython":
        import network as mp_network
        WiFiBackend = lambda: mp_network.WLAN(mp_network.STA_IF)
    else:
        raise ImportError
except ImportError:
    from mocks.mock_hardware import MockWiFi as WiFiBackend


class WiFiManager:
    """
    Manages WiFi connection with non-blocking reconnect logic.

    connect() is intentionally blocking — it is only called at boot time
    where we accept a delay in order to establish connectivity before
    entering the main loop.

    loop() is non-blocking and safe to call every main-loop iteration.
    It uses a timestamp-based retry so it never sleeps.
    """

    # How long to wait between reconnect attempts in loop() (seconds)
    RECONNECT_INTERVAL = 10

    def __init__(self, ssid, password, max_retries=10, retry_delay=2):
        self.ssid = ssid
        self.password = password
        self.max_retries = max_retries      # used only during boot connect()
        self.retry_delay = retry_delay      # used only during boot connect()
        self.wlan = WiFiBackend()

        self._last_reconnect_attempt = 0    # timestamp of last loop() retry

    # -------------------------------------------------------------------------
    # Boot-time connect (blocking — only call from boot/setup code)
    # -------------------------------------------------------------------------

    def connect(self):
        """
        Blocking connect used at boot. Retries up to max_retries times.
        Do NOT call from the main loop — use loop() there instead.
        """
        try:
            self.wlan.active(True)
        except AttributeError:
            pass  # MockWiFi has no active()

        if self.is_connected():
            return True

        print(f"🔌 Connecting to WiFi SSID={self.ssid}...")
        self.wlan.connect(self.ssid, self.password)

        for attempt in range(1, self.max_retries + 1):
            time.sleep(self.retry_delay)
            if self.is_connected():
                self._print_connected()
                return True
            print(f"⏳ WiFi attempt {attempt}/{self.max_retries}...")

        print("❌ WiFi connect failed after all retries")
        return False

    # -------------------------------------------------------------------------
    # Main-loop keepalive (non-blocking)
    # -------------------------------------------------------------------------

    def loop(self):
        """
        Non-blocking WiFi keepalive. Call every main-loop iteration.
        Attempts reconnect at most once per RECONNECT_INTERVAL seconds
        so it never stalls the safety loop.
        """
        if self.is_connected():
            self._last_reconnect_attempt = 0  # reset so next drop retries quickly
            return

        now = time.time()
        if now - self._last_reconnect_attempt < self.RECONNECT_INTERVAL:
            return  # not time to retry yet

        self._last_reconnect_attempt = now
        print("🔄 WiFi dropped — attempting reconnect...")

        try:
            self.wlan.active(True)
        except AttributeError:
            pass

        try:
            self.wlan.connect(self.ssid, self.password)
        except Exception as e:
            print(f"⚠️ WiFi reconnect error: {e}")
            return

        # Give the radio a moment — one short poll only, then return.
        # Full connection will be confirmed on the next loop() call.
        time.sleep(0.1)
        if self.is_connected():
            self._print_connected()

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def is_connected(self):
        return getattr(self.wlan, "isconnected", lambda: False)()

    def disconnect(self):
        try:
            self.wlan.disconnect()
            self.wlan.active(False)
        except AttributeError:
            pass
        print("🔌 WiFi disconnected")

    def _print_connected(self):
        try:
            print(f"✅ WiFi connected: {self.wlan.ifconfig()}")
        except AttributeError:
            print("✅ WiFi connected (mock)")