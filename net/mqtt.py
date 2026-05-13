# network/mqtt.py
__version__ = "0.5.1"

import time
import sys
from state import state

try:
    from umqtt.simple import MQTTClient
    BACKEND = "pico"
except ImportError:
    import paho.mqtt.client as paho
    BACKEND = "desktop"

# On MicroPython there is no stdlib queue — use a simple list instead.
# On desktop use collections.deque for thread safety with paho's background thread.
if BACKEND == "pico":
    class _Queue:
        """Minimal bounded queue for MicroPython."""
        def __init__(self, maxsize=20):
            self._items = []
            self._maxsize = maxsize

        def put(self, item):
            if len(self._items) < self._maxsize:
                self._items.append(item)
            else:
                print("⚠️ MQTT queue full — oldest message dropped")
                self._items.pop(0)
                self._items.append(item)

        def get(self):
            return self._items.pop(0)

        def empty(self):
            return len(self._items) == 0

        def __len__(self):
            return len(self._items)
else:
    import queue as _queue_module
    class _Queue:
        """Thin wrapper around stdlib queue.Queue with a maxsize."""
        def __init__(self, maxsize=20):
            self._q = _queue_module.Queue(maxsize=maxsize)

        def put(self, item):
            if self._q.full():
                print("⚠️ MQTT queue full — oldest message dropped")
                try:
                    self._q.get_nowait()
                except Exception:
                    pass
            try:
                self._q.put_nowait(item)
            except Exception:
                pass

        def get(self):
            return self._q.get_nowait()

        def empty(self):
            return self._q.empty()

        def __len__(self):
            return self._q.qsize()


class MQTTManager:
    """
    Manages MQTT connection for both Pico (umqtt) and desktop (paho).

    Key design principles:
    - connect() is blocking (boot only).
    - loop() and watchdog() are non-blocking (call every main-loop iteration).
    - publish() has a per-topic rate limit to avoid flooding Adafruit IO,
      but urgent=True bypasses the limit for safety-critical messages.
    - Outgoing messages are queued when offline and flushed on reconnect.
    - Watchdog triggers a system restart only after a sustained outage
      (watchdog_interval * WATCHDOG_MULTIPLIER seconds).
    """

    # Watchdog must miss this many intervals before triggering a restart.
    # Prevents spurious reboots from brief network blips.
    WATCHDOG_MULTIPLIER = 3

    # Default per-topic rate limit (seconds). Prevents flooding Adafruit IO.
    # Overridden per-publish with urgent=True for safety-critical messages.
    RATE_LIMIT_SEC = 10

    # Maximum messages held in the offline queue.
    QUEUE_MAXSIZE = 20

    def __init__(
        self,
        aio_username,
        aio_key,
        feeds,
        wifi_manager=None,
        client_id="pico-pool",
        keepalive=60,
        watchdog_interval=60,
        restart_callback=None,
        message_handler=None,
    ):
        self.aio_username = aio_username
        self.aio_key = aio_key
        self.feeds = feeds
        self.wifi_manager = wifi_manager
        self.keepalive = keepalive
        self.watchdog_interval = watchdog_interval
        self.message_handler = message_handler
        self.restart_callback = restart_callback or (lambda: None)

        self.server = "io.adafruit.com"
        self.port = 1883
        self.client_id = client_id

        self.client = None
        self.connected = False
        self.last_ping = time.time()        # updated on every successful publish
        self._last_publish = {}             # topic -> timestamp of last publish
        self._reconnect_attempt = 0         # timestamp of last reconnect try
        self._reconnect_interval = 15       # seconds between non-boot reconnect attempts

        self.queue = _Queue(maxsize=self.QUEUE_MAXSIZE)

        if BACKEND == "pico":
            self._init_pico_client()
        else:
            self._init_desktop_client()

    # -------------------------------------------------------------------------
    # Backend initialisation
    # -------------------------------------------------------------------------

    def _init_pico_client(self):
        self.client = MQTTClient(
            self.client_id, self.server, self.port,
            self.aio_username, self.aio_key, self.keepalive
        )
        self.client.set_callback(self._on_message_pico)

    def _init_desktop_client(self):
        # paho v2 requires CallbackAPIVersion.VERSION1 to use the v1-compatible
        # callback signatures (on_connect(client, userdata, flags, rc), etc.).
        # Without it, paho v2 calls v2 signatures and the parameter counts
        # mismatch, causing MQTT_ERR_PROTOCOL (rc=2) in the disconnect callback.
        try:
            from paho.mqtt.enums import CallbackAPIVersion
            self.client = paho.Client(
                callback_api_version=CallbackAPIVersion.VERSION1,
                client_id=self.client_id,
            )
        except (ImportError, TypeError):
            # paho < 2.0 does not have CallbackAPIVersion
            self.client = paho.Client(client_id=self.client_id)
        if self.aio_username and self.aio_key:
            self.client.username_pw_set(self.aio_username, self.aio_key)
        self.client.on_connect    = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message    = self._on_message_desktop
        self._ever_connected = False

    # -------------------------------------------------------------------------
    # Connection (blocking — boot only)
    # -------------------------------------------------------------------------

    def connect(self):
        """
        Blocking connect. Only call at boot or from watchdog reconnect logic.
        Returns True on success.
        """
        if BACKEND == "pico":
            return self._connect_pico()
        else:
            return self._connect_desktop()

    def _connect_pico(self):
        try:
            self.client.connect()
            self.connected = True
            state["mqtt_connected"] = True
            self.last_ping = time.time()
            self._subscribe_control_feeds()
            self.flush_queue()
            print("✅ MQTT connected (pico)")
            return True
        except Exception as e:
            print(f"❌ MQTT connect failed (pico): {e}")
            self.connected = False
            state["mqtt_connected"] = False
            return False

    def _connect_desktop(self):
        # Desktop uses manual loop() calls from _loop_desktop rather than
        # loop_start()'s background thread. This means any paho internal
        # exception (e.g. struct.error in _handle_suback) is caught by
        # _loop_desktop's except handler instead of crashing an unjoined thread.
        try:
            if self._ever_connected:
                self.client.reconnect()
            else:
                self.client.connect(self.server, self.port, self.keepalive)
                self._ever_connected = True
            # Stamp the attempt time so _try_reconnect's interval guard fires
            # immediately, preventing a second connect() before _on_connect runs.
            # (paho connect() is async — connected stays False until the callback.)
            self._reconnect_attempt = time.time()
            # connected flag is set in _on_connect callback
            print("✅ MQTT connecting (desktop)...")
            return True
        except Exception as e:
            print(f"❌ MQTT connect failed (desktop): {e}")
            self.connected = False
            state["mqtt_connected"] = False
            return False

    def disconnect(self):
        try:
            self.client.disconnect()
        except Exception:
            pass
        self.connected = False
        state["mqtt_connected"] = False
        print("🔌 MQTT disconnected")

    def _subscribe_control_feeds(self):
        """Subscribe to all inbound control topics."""
        for topic in (self.feeds.manual_override, self.feeds.ota_trigger):
            self.subscribe(topic)

    # -------------------------------------------------------------------------
    # Publish
    # -------------------------------------------------------------------------

    def publish(self, topic, msg, urgent=False):
        """
        Publish a message to a topic.

        urgent=True bypasses the per-topic rate limit. Use for safety-critical
        state changes (pump off due to dry-run, overtemp, etc.) so they are
        never silently dropped.

        When offline, messages are held in a bounded queue and flushed on
        the next successful reconnect.
        """
        if not isinstance(msg, (str, bytes)):
            msg = str(msg)

        now = time.time()

        # Rate limiting (skipped for urgent messages)
        if not urgent:
            last = self._last_publish.get(topic, 0)
            if now - last < self.RATE_LIMIT_SEC:
                return   # silently skip — not an error

        if self.connected:
            try:
                self.client.publish(topic, msg)
                self._last_publish[topic] = now
                self.last_ping = now
                print(f"📤 {'🚨 ' if urgent else ''}MQTT → {topic}: {msg}")
            except Exception as e:
                print(f"⚠️ MQTT publish failed: {e} — queuing")
                self.connected = False
                state["mqtt_connected"] = False
                self.queue.put((topic, msg))
        else:
            print(f"📥 MQTT offline — queuing {topic}")
            self.queue.put((topic, msg))

    def flush_queue(self):
        """
        Attempt to deliver all queued messages. Stops on first failure
        so the queue order is preserved.
        """
        if not self.connected:
            return

        while not self.queue.empty():
            topic, msg = self.queue.get()
            try:
                self.client.publish(topic, msg)
                print(f"📤 MQTT flush → {topic}: {msg}")
            except Exception as e:
                print(f"⚠️ MQTT flush failed: {e} — re-queuing")
                self.queue.put((topic, msg))
                self.connected = False
                state["mqtt_connected"] = False
                break

    def subscribe(self, topic):
        try:
            self.client.subscribe(topic)
            print(f"📡 Subscribed: {topic}")
        except Exception as e:
            print(f"⚠️ Subscribe failed for {topic}: {e}")

    # -------------------------------------------------------------------------
    # Main-loop processing (non-blocking)
    # -------------------------------------------------------------------------

    def loop(self):
        """
        Non-blocking loop maintenance. Call every main-loop iteration.
        Handles incoming messages and attempts reconnect if needed.
        """
        if BACKEND == "pico":
            self._loop_pico()
        else:
            self._loop_desktop()

        # Attempt reconnect if disconnected (non-blocking — rate limited)
        if not self.connected:
            self._try_reconnect()

    def _loop_pico(self):
        if not self.connected:
            return
        try:
            self.client.check_msg()   # process any waiting inbound messages
        except Exception as e:
            print(f"⚠️ MQTT check_msg failed: {e}")
            self.connected = False
            state["mqtt_connected"] = False
            return
        self.flush_queue()

    def _loop_desktop(self):
        if not self._ever_connected:
            return
        try:
            self.client.loop(timeout=0.05)
        except Exception as e:
            print(f"⚠️ MQTT desktop loop error: {e}")
            self.connected = False
            state["mqtt_connected"] = False

    def _try_reconnect(self):
        """
        Attempt a single non-blocking reconnect if the interval has elapsed.
        WiFi must be up before we attempt MQTT reconnect.
        """
        if self.wifi_manager and not self.wifi_manager.is_connected():
            return  # wait for WiFi to come back first

        now = time.time()
        if now - self._reconnect_attempt < self._reconnect_interval:
            return  # not time yet

        self._reconnect_attempt = now
        print("🔄 MQTT reconnecting...")
        if self.connect():
            print("✅ MQTT reconnected")

    # -------------------------------------------------------------------------
    # Watchdog (non-blocking)
    # -------------------------------------------------------------------------

    def watchdog(self):
        """
        Non-blocking watchdog. Call every main-loop iteration.
        Triggers a system restart only after a sustained outage of
        watchdog_interval * WATCHDOG_MULTIPLIER seconds.
        """
        if self.connected:
            return  # all good

        now = time.time()
        outage_duration = now - self.last_ping
        threshold = self.watchdog_interval * self.WATCHDOG_MULTIPLIER

        if outage_duration > threshold:
            print(f"⚠️ MQTT unresponsive for {outage_duration:.0f}s — triggering restart")
            self.last_ping = now   # prevent repeated triggers during restart sequence
            self.restart_callback()

    # -------------------------------------------------------------------------
    # Message callbacks
    # -------------------------------------------------------------------------

    def _on_message_pico(self, topic, payload):
        """
        umqtt callback signature: callback(topic_bytes, payload_bytes).
        Named explicitly to avoid the confusing parameter-reuse of the old code.
        """
        topic_str   = topic.decode()   if isinstance(topic,   bytes) else topic
        payload_str = payload.decode() if isinstance(payload, bytes) else str(payload)
        print(f"📩 MQTT ← {topic_str}: {payload_str}")
        if self.message_handler:
            self.message_handler(topic_str, payload_str)

    def _on_message_desktop(self, client, userdata, msg):
        """paho callback signature: callback(client, userdata, message)."""
        payload_str = msg.payload.decode() if isinstance(msg.payload, bytes) else str(msg.payload)
        print(f"📩 MQTT ← {msg.topic}: {payload_str}")
        if self.message_handler:
            self.message_handler(msg.topic, payload_str)


    def _on_connect(self, client, userdata, flags, rc):
        """paho connect callback."""
        if rc == 0:
            self.connected = True
            state["mqtt_connected"] = True
            self.last_ping = time.time()
            print("✅ MQTT connected (desktop)")
            self._subscribe_control_feeds()
            self.flush_queue()
        else:
            self.connected = False
            state["mqtt_connected"] = False
            print(f"❌ MQTT connect failed (desktop) rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        """paho disconnect callback."""
        self.connected = False
        state["mqtt_connected"] = False
        print(f"🔌 MQTT disconnected (desktop) rc={rc}")