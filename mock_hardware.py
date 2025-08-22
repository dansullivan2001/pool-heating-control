"""
Extended mock_hardware with scripted DS18B20 temperature scenarios.
"""

import time
import random

# ----------------------------
# Scenario engine
# ----------------------------
class TempScenario:
    def __init__(self):
        self.step = 0
        self.mode = 1  # default scenario

    def set_mode(self, mode):
        print(f"[MOCK] Switching to temperature scenario {mode}")
        self.mode = mode
        self.step = 0

    def get_temps(self):
        """Return dict of temps for this step in the current scenario"""
        if self.mode == 1:
            # 1. Return higher than Flow (collectors not heating)
            return {"tReturn": 24.0, "tFlow": 20.0, "tAmbient": 19.5, "tEnclosure": 25.0}
        elif self.mode == 2:
            # 2. Flow higher than Return (collectors heating well)
            return {"tReturn": 20.0, "tFlow": 25.0, "tAmbient": 19.0, "tEnclosure": 26.0}
        elif self.mode == 3:
            # 3. Return starts higher, then falls below Flow
            if self.step < 2:
                temps = {"tReturn": 24.0, "tFlow": 22.0, "tAmbient": 19.0, "tEnclosure": 25.0}
            else:
                temps = {"tReturn": 21.0, "tFlow": 24.0, "tAmbient": 19.0, "tEnclosure": 25.0}
            self.step += 1
            return temps
        else:
            # Default fallback
            return {"tReturn": 22.0, "tFlow": 22.0, "tAmbient": 20.0, "tEnclosure": 25.0}

SCENARIO = TempScenario()

# ----------------------------
# machine mocks (same as before, trimmed here)
# ----------------------------
class MockPin:
    OUT = 0
    IN = 1
    PULL_UP = 2

    def __init__(self, pin, mode=IN, pull=None):
        self.pin = pin
        self.mode = mode
        self.state = 0
        print(f"[MOCK] Pin {pin} initialized (mode={mode})")

    def value(self, v=None):
        if v is None:
            return self.state
        else:
            self.state = v
            print(f"[MOCK] Pin {self.pin} set to {v}")


class Timer:
    PERIODIC = 0
    ONE_SHOT = 1

    def init(self, period, mode, callback):
        print(f"[MOCK] Timer started: {period}ms mode={mode}")
        callback(self)


# ----------------------------
# DS18B20 mock (uses SCENARIO)
# ----------------------------
class MockOneWire:
    def __init__(self, pin):
        print(f"[MOCK] OneWire bus on Pin {pin.pin}")


class MockDS18X20:
    def __init__(self, bus):
        print("[MOCK] DS18X20 initialized")

    def scan(self):
        # return your known ROMs
        return [
            "28d2908700370520",  # tReturn
            "28206f87007e6fc7",  # tAmbient
            "2874c18700153578",  # tFlow
            "28ff951c01150203",  # tEnclosure
        ]

    def convert_temp(self):
        print("[MOCK] DS18B20 converting temps...")

    def read_temp(self, rom):
        temps = SCENARIO.get_temps()
        mapping = {
            "28d2908700370520": "tReturn",
            "28206f87007e6fc7": "tAmbient",
            "2874c18700153578": "tFlow",
            "28ff951c01150203": "tEnclosure",
        }
        name = mapping.get(rom, "unknown")
        temp = temps[name]
        print(f"[MOCK] DS18B20 {name} ({rom}) temp = {temp}")
        return temp


# ----------------------------
# network + MQTT mocks (same as earlier)
# ----------------------------
class WLAN:
    STA_IF = 0
    def __init__(self, mode): self.connected = False
    def active(self, state=None): return True
    def connect(self, ssid, password):
        print(f"[MOCK] WiFi connecting to {ssid}..."); time.sleep(0.2); self.connected = True; print("[MOCK] WiFi connected")
    def isconnected(self): return self.connected
    def ifconfig(self): return ("192.168.1.50","255.255.255.0","192.168.1.1","8.8.8.8")


class MQTTClient:
    def __init__(self, client_id, server, user=None, password=None, keepalive=60):
        self.server = server; self.subscriptions={}; self.incoming=[]
        print(f"[MOCK] MQTTClient created for {server} (user={user})")
    def connect(self): print(f"[MOCK] Connected to MQTT broker {self.server}")
    def publish(self, topic, msg):
        feed = topic.decode() if isinstance(topic,bytes) else topic
        message = msg.decode() if isinstance(msg,bytes) else msg
        print(f"[AIO PUBLISH] Feed='{feed}' Value='{message}'")
    def subscribe(self, topic):
        feed = topic.decode() if isinstance(topic,bytes) else topic
        print(f"[AIO SUBSCRIBE] Feed='{feed}'"); self.subscriptions[feed]=None
    def set_callback(self, cb): self.callback = cb
    def queue_message(self, topic,payload): self.incoming.append((topic,payload))
    def check_msg(self):
        if self.incoming:
            topic,payload=self.incoming.pop(0)
            print(f"[AIO INCOMING] Feed='{topic}' Value='{payload}'")
            if hasattr(self,"callback"): self.callback(topic.encode(), payload.encode())

# ----------------------------
# glue for import compatibility
# ----------------------------
machine = __import__(__name__)
onewire = __import__(__name__)
ds18x20 = __import__(__name__)
network = __import__(__name__)
umqtt = {"simple": __import__(__name__)}
