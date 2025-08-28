# mqtt.py
__version__ = "0.0.1"

import time
import sys
from collections import deque

try:
    import umqtt.simple as mqtt  # MicroPython
except ImportError:
    import paho.mqtt.client as mqtt  # Desktop testing


WATCHDOG_TIMEOUT = 300   # 5 minutes
QUEUE_MAXLEN = 50        # Max queued messages


class MqttManager:
    """Handles Adafruit IO MQTT connectivity with watchdog + queue."""

    def __init__(self, aio_username, aio_key, feeds, wifi_manager=None):
        self.aio_username = aio_username
        self.aio_key = aio_key
        self.feeds = feeds
        self.wifi = wifi_manager

        self.client = None
        self.last_message_time = time.time()
        self.last_connect_attempt = 0
        self.connected = False

        # Queue for offline publishing
        self.queue = deque(maxlen=QUEUE_MAXLEN)

        # Platform detection
        self.is_micropython = "umqtt" in sys.modules

    def connect(self):
        """Connect to Adafruit IO MQTT broker."""
        broker = "io.adafruit.com"
        client_id = f"{self.aio_username}-client"

        if self.is_micropython:
            self.client = mqtt.MQTTClient(
                client_id=client_id,
                server=broker,
                user=self.aio_username,
                password=self.aio_key
            )
            self.client.set_callback(self._on_message)
            self.client.connect()
        else:
            # Desktop testing with paho-mqtt
            self.client = mqtt.Client(client_id=client_id)
            self.client.username_pw_set(self.aio_username, self.aio_key)
            self.client.on_message = self._on_message
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.connect(broker, 1883, 60)
            self.client.loop_start()

        self.connected = True
        self.last_message_time = time.time()
        print("[MQTT] Connected")

    def _on_message(self, topic, msg=None):
        print(f"[MQTT] Message on {topic}: {msg}")
        self.last_message_time = time.time()

    def _on_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] Connected with rc={rc}")
        self.connected = True
        self.last_message_time = time.time()

    def _on_disconnect(self, client, userdata, rc):
        print(f"[MQTT] Disconnected rc={rc}")
        self.connected = False

    def publish(self, feed, value):
        """Publish a message, or queue if disconnected."""
        payload = str(value)
        topic = feed

        if self.connected:
            try:
                if self.is_micropython:
                    self.client.publish(topic, payload)
                else:
                    self.client.publish(topic, payload)
                self.last_message_time = time.time()
                return True
            except Exception as e:
                print(f"[MQTT] Publish error: {e}")
                self.connected = False

        # If here → queue the message
        self.queue.append((topic, payload))
        print(f"[MQTT] Queued message: {topic}={payload}")
        return False

    def loop(self):
        """Non-blocking keepalive, process queue, run watchdog."""
        now = time.time()

        if self.is_micropython:
            try:
                self.client.check_msg()
            except Exception:
                self.connected = False

        # Try reconnect if not connected
        if not self.connected and (now - self.last_connect_attempt > 10):
            self.last_connect_attempt = now
            try:
                print("[MQTT] Attempting reconnect...")
                self.connect()
            except Exception as e:
                print(f"[MQTT] Reconnect failed: {e}")
                self.connected = False

        # Flush queue if connected
        if self.connected and self.queue:
            topic, payload = self.queue.popleft()
            try:
                if self.is_micropython:
                    self.client.publish(topic, payload)
                else:
                    self.client.publish(topic, payload)
                print(f"[MQTT] Flushed queued: {topic}={payload}")
                self.last_message_time = now
            except Exception as e:
                print(f"[MQTT] Flush failed: {e}")
                self.queue.appendleft((topic, payload))
                self.connected = False

        # Watchdog → soft reset after timeout
        if now - self.last_message_time > WATCHDOG_TIMEOUT:
            print("[MQTT] Watchdog triggered: rebooting...")
            if self.is_micropython:
                import machine
                machine.reset()
            else:
                sys.exit(1)  # For Mac testing
