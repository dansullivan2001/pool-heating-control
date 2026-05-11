# feeds.py
__version__ = "0.0.1"

import network
import time
import machine
from umqtt.simple import MQTTClient
import secrets
import utils

# --- MQTT client and message queue ---
client = None
pending_messages = []
MQTT_RECONNECT_INTERVAL = 5  # seconds

# --- Wi-Fi tracking ---
wifi_last_connected = time.time()
WIFI_OFFLINE_TIMEOUT = 300  # seconds

# --- MQTT tracking ---
mqtt_last_connected = time.time()
MQTT_OFFLINE_TIMEOUT = 300  # seconds

# --- Wi-Fi functions ---
def is_wifi_connected():
    wlan = network.WLAN(network.STA_IF)
    return wlan.isconnected()

def connect_wifi(max_retries=1):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    retries = 0
    while not wlan.isconnected() and retries < max_retries:
        wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
        time.sleep(1)
        retries += 1
    return wlan.isconnected()

# --- MQTT functions ---
def connect_mqtt():
    global client, mqtt_last_connected
    try:
        client = MQTTClient(secrets.AIO_USER, "io.adafruit.com",
                            user=secrets.AIO_USER, password=secrets.AIO_KEY)
        client.connect()
        mqtt_last_connected = time.time()
        flush_pending_messages()
        utils.log("✅ MQTT connected")
        return True
    except Exception as e:
        client = None
        utils.log(f"⚠️ MQTT connect failed: {e}")
        return False

def publish(topic, msg):
    global pending_messages
    if client is None:
        pending_messages.append((topic, msg))
        reconnect_mqtt()
        return
    try:
        client.publish(topic, msg)
    except Exception:
        pending_messages.append((topic, msg))
        client = None
        reconnect_mqtt()

def flush_pending_messages():
    global pending_messages
    if client is None:
        return
    for t, m in pending_messages[:]:
        try:
            client.publish(t, m)
            pending_messages.remove((t, m))
        except Exception:
            pass

def reconnect_mqtt():
    delay = MQTT_RECONNECT_INTERVAL
    while True:
        if connect_mqtt():
            break
        time.sleep(delay)
        delay = min(delay*2, 60)

# --- Combined Wi-Fi + MQTT watchdog ---
def network_watchdog_check():
    """Non-blocking check for Wi-Fi and MQTT; reboot if offline too long."""
    global wifi_last_connected, mqtt_last_connected

    now = time.time()

    # Wi-Fi check
    if is_wifi_connected():
        wifi_last_connected = now
    else:
        utils.log("⚠️ Wi-Fi disconnected, trying reconnect")
        if connect_wifi(max_retries=1):
            wifi_last_connected = now
            utils.log("✅ Wi-Fi reconnected")

    # MQTT check
    if client is not None:
        mqtt_last_connected = now
    else:
        reconnect_mqtt()

    # Reboot if offline too long
    if now - wifi_last_connected > WIFI_OFFLINE_TIMEOUT or now - mqtt_last_connected > MQTT_OFFLINE_TIMEOUT:
        utils.log("❌ Network offline too long, restarting Pico")
        time.sleep(1)
        machine.reset()
