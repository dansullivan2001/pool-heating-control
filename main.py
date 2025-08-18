import network, time, os, machine, urequests
import config
from umqtt.simple import MQTTClient

# ==== Wi-Fi & Adafruit IO ====
SSID = config.WIFI_SSID
PASSWORD = config.WIFI_PASSWORD
AIO_USERNAME = config.AIO_USERNAME
AIO_KEY = config.AIO_KEY

# OTA feed
AIO_FEED_OTA_TRIGGER = f"{AIO_USERNAME}/feeds/ota_trigger"

# GitHub update URL
UPDATE_URL = "https://raw.githubusercontent.com/dansullivan2001/pool-heating-control/main/pump_controller.py"

LOCAL_FILE = "pump_controller.py"
BACKUP_FILE = "pump_controller_backup.py"

# ==== Wi-Fi Connect ====
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("🔌 Connecting to Wi-Fi...")
        wlan.connect(SSID, PASSWORD)
        attempts = 0
        while not wlan.isconnected() and attempts < 20:
            time.sleep(1)
            attempts += 1
    if wlan.isconnected():
        print("✅ Wi-Fi connected:", wlan.ifconfig())
    else:
        print("❌ Wi-Fi failed to connect")
    # Allow network stack to stabilize
    time.sleep(2)
    return wlan

# ==== Version helpers ====
def extract_version(path):
    try:
        with open(path, "r") as f:
            for line in f:
                if line.strip().startswith("__version__"):
                    return line.split("=")[1].strip().strip('"').strip("'")
    except:
        return None
    return None

def version_tuple(v):
    return tuple(int(x) for x in v.split(".") if x.isdigit())

def is_newer(remote, local):
    try:
        return version_tuple(remote) > version_tuple(local)
    except:
        return False

# ==== Reset OTA feed ====
def reset_feed():
    try:
        client = MQTTClient("pico_ota_reset", "io.adafruit.com",
                            user=AIO_USERNAME, password=AIO_KEY)
        client.connect()
        client.publish(AIO_FEED_OTA_TRIGGER, b"0")
        client.disconnect()
        print("📤 OTA feed reset to 0")
    except Exception as e:
        print("❌ Could not reset OTA feed:", e)

# ==== OTA Update ====
def ota_update():
    try:
        r = urequests.get(UPDATE_URL, timeout=10)
        if r.status_code != 200:
            print("❌ Update fetch failed:", r.status_code)
            return
        new_code = r.text
        r.close()

        remote_version = None
        for line in new_code.splitlines():
            if line.strip().startswith("__version__"):
                remote_version = line.split("=")[1].strip().strip('"').strip("'")
                break

        local_version = extract_version(LOCAL_FILE)
        print("📄 Local version:", local_version, "| Remote version:", remote_version)

        if remote_version and local_version and not is_newer(remote_version, local_version):
            print("ℹ️ Already up to date. No update needed.")
            reset_feed()
            return

        # Backup old file
        if LOCAL_FILE in os.listdir():
            os.rename(LOCAL_FILE, BACKUP_FILE)

        # Write new controller
        with open(LOCAL_FILE, "w") as f:
            f.write(new_code)

        print("✅ Update applied. Resetting feed and rebooting...")
        reset_feed()
        time.sleep(1)
        machine.reset()

    except Exception as e:
        print("❌ OTA error:", e)
        # Rollback immediately on OTA fetch error
        if BACKUP_FILE in os.listdir():
            try:
                if LOCAL_FILE in os.listdir():
                    os.remove(LOCAL_FILE)
                os.rename(BACKUP_FILE, LOCAL_FILE)
                print("♻️ Rollback applied after OTA failure")
            except Exception as e2:
                print("❌ Rollback failed:", e2)

# ==== Check OTA trigger feed ====
triggered = False
def sub_cb(topic, msg):
    global triggered
    if msg.decode().strip() == "1":
        triggered = True

def check_ota_trigger(retries=3):
    global triggered
    for attempt in range(retries):
        try:
            client = MQTTClient("pico_ota", "io.adafruit.com",
                                user=AIO_USERNAME, password=AIO_KEY)
            client.set_callback(sub_cb)
            client.connect()
            client.subscribe(AIO_FEED_OTA_TRIGGER)
            print(f"🔎 Checking OTA feed (attempt {attempt+1}/{retries})...")

            # Wait briefly for message to arrive
            for _ in range(30):
                client.check_msg()
                if triggered:
                    break
                time.sleep(0.5)
            client.disconnect()

            if triggered:
                print("🚀 OTA triggered!")
                ota_update()
                break
            else:
                print("ℹ️ No OTA trigger detected.")
                return
        except Exception as e:
            print(f"❌ OTA feed check failed (attempt {attempt+1}):", e)
            time.sleep(1)

# ==== Startup sequence ====
connect_wifi()
check_ota_trigger()

# ==== Run main controller with rollback safety ====
try:
    import pump_controller
    # Cleanup backup if controller runs successfully
    if BACKUP_FILE in os.listdir():
        os.remove(BACKUP_FILE)
except Exception as e:
    print("❌ Controller crashed:", e)
    if BACKUP_FILE in os.listdir():
        print("♻️ Restoring backup controller...")
        try:
            if LOCAL_FILE in os.listdir():
                os.remove(LOCAL_FILE)
            os.rename(BACKUP_FILE, LOCAL_FILE)
            machine.reset()
        except Exception as e2:
            print("❌ Rollback failed:", e2)
# if we reach here, the controller ran without crashing
