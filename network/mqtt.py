# mqtt.py
__version__ = "0.3.0"

import time
import sys
import queue

try:
    from umqtt.simple import MQTTClient
    BACKEND = "pico"
except ImportError:
    import paho.mqtt.client as paho
    BACKEND = "desktop"


class MQTTManager:
    def __init__(self, aio_username, aio_key, feeds, wifi_manager=None, client_id="pico-client", keepalive=60, watchdog_interval=60):
        self.aio_username = aio_username
        self.aio_key = aio_key
        self.feeds = feeds
        self.wifi_manager = wifi_manager
        self.keepalive = keepalive
        self.watchdog_interval = watchdog_interval
        self.publish_interval = 10
        self._last_publish = {} 

        self.client_id = client_id
        self.server = "io.adafruit.com"
        self.port = 1883
        self.user = aio_username
        self.password = aio_key

        self.client = None
        self.queue = queue.Queue()        # fixed Queue import
        self.connected = False
        self.last_ping = time.time()      # initialize watchdog timestamp

        # Initialize client depending on backend
        if BACKEND == "pico":
            self._init_pico_client()
        else:
            self._init_desktop_client()

    # -------------------------------------------------------------------------
    # Private backend initializers
    # -------------------------------------------------------------------------
    def _init_pico_client(self):
        self.client = MQTTClient(self.client_id, self.server, self.port, self.user, self.password, self.keepalive)

    def _init_desktop_client(self):
        # self.client = paho.Client(client_id=self.client_id, callback_api_version=1)
        self.client = paho.Client(client_id=self.client_id)
        if self.user and self.password:
            self.client.username_pw_set(self.user, self.password)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect



    # -------------------------------------------------------------------------
    # Connection handling
    # -------------------------------------------------------------------------
    def connect(self):
        if BACKEND == "pico":
            try:
                self.client.connect()
                self.connected = True
                print("✅ MQTT connected (pico)")
            except Exception as e:
                print(f"❌ MQTT connect failed: {e}")
                self.connected = False
        else:
            try:
                self.client.connect(self.server, self.port, self.keepalive)
                self.client.loop_start()
                self.connected = True
                print("✅ MQTT connected (desktop)")
            except Exception as e:
                print(f"❌ MQTT connect failed: {e}")
                self.connected = False
        return self.connected

    def disconnect(self):
        if BACKEND == "pico":
            self.client.disconnect()
        else:
            self.client.loop_stop()
            self.client.disconnect()
        self.connected = False
        print("🔌 MQTT disconnected")

    # -------------------------------------------------------------------------
    # Publish with queue + watchdog
    # -------------------------------------------------------------------------
    def publish(self, topic, msg):
        now = time.time()
        last = self._last_publish.get(topic, 0)
        if now - last < self.publish_interval:
            print(f"⏳ MQTT rate limit, skipping publish to {topic}")
            return
        
        if not isinstance(msg, (str, bytes)):
            msg = str(msg)

        if self.connected:
            try:
                if BACKEND == "pico":
                    self.client.publish(topic, msg)
                else:
                    self.client.publish(topic, msg)
                self._last_publish[topic] = now
                self.last_ping = time.time()
                print(f"📤 MQTT publish {topic}: {msg}")
            except Exception as e:
                print(f"⚠️ MQTT publish failed, queued: {e}")
                self.queue.put((topic, msg))
                self.connected = False
        else:
            print("📥 MQTT offline, queued:", topic, msg)
            self.queue.put((topic, msg))

    def flush_queue(self):
        if self.connected:
            while not self.queue.empty():
                topic, msg = self.queue.get()
                try:
                    self.client.publish(topic, msg)
                    print(f"📤 MQTT flush {topic}: {msg}")
                except Exception as e:
                    print(f"⚠️ MQTT flush failed: {e}")
                    self.queue.put((topic, msg))
                    break  # stop, keep remaining messages


    def watchdog(self):
        """Non-blocking watchdog for MQTT connection health."""
        now = time.time()
        if now - self.last_ping > self.watchdog_interval:
            print("🐶 MQTT watchdog triggered - reconnecting")
            self.disconnect()
            self.connect()
            self.flush_queue()

    # -------------------------------------------------------------------------
    # Desktop callbacks
    # -------------------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            print("✅ MQTT desktop connected")
        else:
            print("❌ MQTT desktop failed with rc=", rc)

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        print("🔌 MQTT desktop disconnected rc=", rc)

    def check_connection(self):
        if self.wifi_manager.is_connected() and not self.client.is_connected():
            print("[MQTT] WiFi restored, reconnecting MQTT...")
            self.connect()  # reconnect client


    def loop(self):
        if BACKEND == "desktop" and self.connected:
            self.client.loop(timeout=0.1)  # non-blocking
            # Check connection even if desktop client thinks it's connected
            if self.wifi_manager and self.wifi_manager.is_connected() and not self.connected:
                print("[MQTT] WiFi restored, reconnecting MQTT...")
                self.connect()
                self.flush_queue()
        if BACKEND == "pico":
            self.flush_queue()
            if self.wifi_manager and self.wifi_manager.is_connected() and not self.connected:
                print("[MQTT] WiFi restored, reconnecting MQTT (pico)...")
                self.connect()
                self.flush_queue()
