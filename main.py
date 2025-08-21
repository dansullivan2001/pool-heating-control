#import pump_controller
print("hello world")

import network, time, os, machine, urequests #type: ignore
from umqtt.simple import MQTTClient
import config

# ==== Wi-Fi / Adafruit IO ====
SSID = config.WIFI_SSID
PASSWORD = config.WIFI_PASSWORD
AIO_USERNAME = config.AIO_USERNAME
AIO_KEY = config.AIO_KEY
AIO_FEED_OTA_TRIGGER = f"{AIO_USERNAME}/feeds/ota_trigger"

DEFAULT_BRANCH = "main"
LOCAL_FILE = "pump_controller.py"
BACKUP_FILE = "pump_controller_backup.py"

# ==== Wi-Fi Connect ====
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(SSID, PASSWORD)
        for _ in range(10):
            if wlan.isconnected():
                break
            time.sleep(1)
    return wlan

# ==== OTA helpers ====
triggered = False
branch_to_update = DEFAULT_BRANCH
force_apply_flag = False

def sub_cb(topic, msg):
    global triggered, branch_to_update, force_apply_flag
    payload = msg.decode().strip()
    parts = payload.split(":")
    if parts[0] == "1":
        triggered = True
        branch_to_update = parts[1] if len(parts) > 1 else DEFAULT_BRANCH
        if len(parts) > 2 and parts[2].lower() == "force":
            force_apply_flag = True

def reset_feed():
    try:
        client = MQTTClient("pico_ota_reset", "io.adafruit.com",
                            user=AIO_USERNAME, password=AIO_KEY)
        client.connect()
        client.publish(AIO_FEED_OTA_TRIGGER, b"0")
        client.disconnect()
    except Exception as e:
        print("Could not reset OTA feed:", e)

def ota_update(branch=DEFAULT_BRANCH, force_apply=False):
    try:
        url = f"https://raw.githubusercontent.com/dansullivan2001/pool-heating-control/{branch}/pump_controller.py"
        print("Fetching update from:", url)
        r = urequests.get(url)
        if r.status_code != 200:
            print("Update fetch failed:", r.status_code)
            return
        new_code = r.text
        r.close()

        # Extract remote version
        remote_version = None
        for line in new_code.splitlines():
            if line.strip().startswith("__version__"):
                remote_version = line.split("=")[1].strip().strip('"').strip("'")
                break

        # Extract local version
        local_version = None
        try:
            with open(LOCAL_FILE) as f:
                for line in f:
                    if line.strip().startswith("__version__"):
                        local_version = line.split("=")[1].strip().strip('"').strip("'")
                        break
        except:
            pass

        # Skip update if not newer unless forced
        if not force_apply and remote_version and local_version:
            if tuple(map(int, remote_version.split("."))) <= tuple(map(int, local_version.split("."))):
                print("Already up to date. No update applied.")
                reset_feed()
                return

        # Backup and write new file
        if LOCAL_FILE in os.listdir():
            os.rename(LOCAL_FILE, BACKUP_FILE)
        with open(LOCAL_FILE, "w") as f:
            f.write(new_code)

        print("Update applied! Resetting trigger and rebooting...")
        reset_feed()
        machine.reset()

    except Exception as e:
        print("OTA error:", e)

def check_ota_trigger_nonblocking():
    global triggered
    try:
        client = MQTTClient("pico_ota", "io.adafruit.com",
                            user=AIO_USERNAME, password=AIO_KEY)
        client.set_callback(sub_cb)
        client.connect()
        client.subscribe(AIO_FEED_OTA_TRIGGER)
        client.publish(AIO_FEED_OTA_TRIGGER + "/get", b"")
        # Poll a few times quickly
        for _ in range(5):
            client.check_msg()
            if triggered:
                break
            time.sleep(0.1)
        client.disconnect()

        if triggered:
            print("OTA triggered!")
            ota_update(branch=branch_to_update, force_apply=force_apply_flag)
        else:
            print("No OTA trigger")
            reset_feed()
    except Exception as e:
        print("Non-blocking OTA check failed:", e)

# ==== Startup sequence ====
connect_wifi()
check_ota_trigger_nonblocking()  # non-blocking OTA
try:
    import pump_controller
    if BACKUP_FILE in os.listdir():
        os.remove(BACKUP_FILE)  # remove backup if update successful
except Exception as e:
    print("Controller crashed:", e)
    if BACKUP_FILE in os.listdir():
        print("Restoring backup controller...")
        try:
            if LOCAL_FILE in os.listdir():
                os.remove(LOCAL_FILE)
            os.rename(BACKUP_FILE, LOCAL_FILE)
            machine.reset()
        except Exception as e2:
            print("Rollback failed:", e2)
