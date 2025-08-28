# mqtt.py
__version__ = "0.2.0"

import time
from umqtt.simple import MQTTClient

class MQTTManager:
    def __init__(self, client_id, username, key, server="io.adafruit.com", port=1883, reconnect_delay=5):
        self.client_id = client_id
        self.username = username
        self.key = key
        self.server = server
        self.port = port
        self.reconnect_delay = reconnect_delay
        self.client = None
        self.subscriptions = []
        self.on_message = None

    def _new_client(self):
        client = MQTTClient(
            self.client_id,
            self.server,
            self.port,
            self.username,
            self.key,
        )
        if self.on_message:
            client.set_callback(self.on_message)
        return client

    def connect(self):
        """Connect to MQTT broker."""
        try:
            print(f"🔌 Connecting to MQTT {self.server}:{self.port} as {self.username}...")
            self.client = self._new_client()
            self.client.connect()
            print("✅ MQTT connected")
            self._resubscribe()
            return True
        except Exception as e:
            print("❌ MQTT connect failed:", e)
            self.client = None
            return False

    # ...need to check this with ChatGPT
    def is_connected(self):
        return self.connected

    def disconnect(self):
        if self.client:
            try:
                self.client.disconnect()
                print("🔌 MQTT disconnected")
            except:
                pass
            self.client = None

    def publish(self, feed, message, retain=False):
        if not self.client:
            return
        try:
            topic = f"{self.username}/feeds/{feed}"
            print(f"📤 MQTT publish {topic} = {message}")
            self.client.publish(topic, str(message), retain=retain)
        except Exception as e:
            print("❌ MQTT publish failed:", e)
            self._reconnect()

    def subscribe(self, feed):
        """Subscribe to a feed and remember it for auto-resubscribe."""
        if feed not in self.subscriptions:
            self.subscriptions.append(feed)
        if self.client:
            try:
                topic = f"{self.username}/feeds/{feed}"
                self.client.subscribe(topic)
                print(f"📥 Subscribed to {topic}")
            except Exception as e:
                print("❌ MQTT subscribe failed:", e)
                self._reconnect()

    def _resubscribe(self):
        """Re-subscribe to all remembered feeds."""
        if self.client:
            for feed in self.subscriptions:
                topic = f"{self.username}/feeds/{feed}"
                try:
                    self.client.subscribe(topic)
                    print(f"🔄 Resubscribed {topic}")
                except Exception as e:
                    print("❌ Resubscribe failed:", e)

    def _reconnect(self):
        """Try reconnecting until successful."""
        self.disconnect()
        while not self.connect():
            print(f"⏳ Retry in {self.reconnect_delay}s...")
            time.sleep(self.reconnect_delay)

    def check_msg(self):
        """Check for new MQTT messages, auto-reconnect if needed."""
        if not self.client:
            self._reconnect()
        try:
            self.client.check_msg()
        except Exception as e:
            print("❌ MQTT check_msg failed:", e)
            self._reconnect()
