print("DEBUG: pump_controller.py starting")
__version__ = "1.0.0"

import machine #type: ignore
import onewire, ds18x20 #type: ignore
import time #type: ignore
import ntptime
import network
from umqtt.simple import MQTTClient
import config

# ==== Wi-Fi credentials ====
SSID = config.WIFI_SSID
PASSWORD = config.WIFI_PASSWORD

# ==== Adafruit IO credentials ====
AIO_USERNAME = config.AIO_USERNAME
AIO_KEY = config.AIO_KEY

# ==== Feed names ====
AIO_FEED_PUMP_OVERRIDE      = f"{AIO_USERNAME}/feeds/pump_override"
AIO_FEED_PUMP_STATE         = f"{AIO_USERNAME}/feeds/pump_state"
AIO_FEED_PUBLISH_INTERVAL   = f"{AIO_USERNAME}/feeds/publish_interval"
AIO_FEED_PUMP_INTERVAL      = f"{AIO_USERNAME}/feeds/pump_test_interval"
AIO_FEED_PUMP_DURATION      = f"{AIO_USERNAME}/feeds/pump_test_duration"
AIO_FEED_DELTA_TEMP         = f"{AIO_USERNAME}/feeds/delta_temp"
AIO_FEED_LEVEL_STATE        = f"{AIO_USERNAME}/feeds/level_state"
AIO_FEED_OTA_TRIGGER        = f"{AIO_USERNAME}/feeds/ota_trigger"

# ==== Sensor labels ====
rom_to_label = {
    '28d2908700370520': 'tReturn',
#    '28e7688700c21d87': 'tReturnTest',
    '28206f87007e6fc7': 'tAmbient',
    '2874c18700153578': 'tFlow',
#    '2812358700210518': 'tFlowTest',
    '28ee28e31216013e': 'tEnclosure'
}

# ==== Parameters ====
HIGH_THRESHOLD_DIFF = 1.0   # tReturn must exceed tFlow + this to keep pump running
LOW_THRESHOLD_DIFF  = 0.0   # tReturn must fall below tFlow + this to shut off pump
MAX_ENCLOSURE_TEMP = 50.0   # Max safe enclosure temp in °C (thermal shutoff)

PUBLISH_INTERVAL     = 30     # seconds
PUMP_TEST_INTERVAL   = 1200   # 20 minutes = 1200 seconds between pump tests
PUMP_TEST_DURATION   = 60     # 60 seconds pump test duration
last_publish_time    = 0
last_test_time       = 0

pump_on = False
override_active = False
override_end_time = 0

earliest_test_time = 9      #sets the hour when the test cycles can start
latest_test_time = 18       #sets the hour when the test cycles must stop

first_boot = True

# --- Soft reboot flag ---
reboot_triggered = False
reboot_confirmed = False


# ==== Debounce params for level sensor ====
LEVEL_SENSOR_PIN = 14
level_sensor_pin = machine.Pin(LEVEL_SENSOR_PIN, machine.Pin.IN)
LEVEL_DEBOUNCE_DELAY = 2000  # ms delay to confirm wet/dry
last_level_state = 0
level_state = 0
level_last_change = time.ticks_ms()

# ==== Manual override button ====
BUTTON_PIN = 3
button = machine.Pin(BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
last_button_state = 1
last_debounce_time = 0
BUTTON_DEBOUNCE_DELAY = 200  # ms

# ==== DS18B20 setup ====
ds_pin = machine.Pin(0)
ds_sensor = ds18x20.DS18X20(onewire.OneWire(ds_pin))
roms = ds_sensor.scan()
print("Found sensors:", [r.hex() for r in roms])

# ==== Pump output and LED ====
relay = machine.Pin(16, machine.Pin.OUT)
led = machine.Pin("LED", machine.Pin.OUT)

def sync_time(max_attempts=3):
    """
    Sync Pico RTC with NTP, applying UK DST offset.
    Retries up to max_attempts if sync fails.
    """
    def uk_dst_offset(utc_tm):
        """
        Returns offset in seconds for UK DST.
        utc_tm: tuple from time.localtime() in UTC
        """
        year = utc_tm[0]
        # Last Sunday in March
        march_last_sunday = max([d for d in range(31, 24, -1)
                                 if time.localtime(time.mktime((year,3,d,2,0,0,0,0)))[6] == 6])
        # Last Sunday in October
        oct_last_sunday = max([d for d in range(31, 24, -1)
                               if time.localtime(time.mktime((year,10,d,2,0,0,0,0)))[6] == 6])
        month, mday = utc_tm[1], utc_tm[2]
        # UTC+1 if in DST period
        if (month > 3 and month < 10) or (month == 3 and mday >= march_last_sunday) or (month == 10 and mday < oct_last_sunday):
            return 3600
        return 0

    for attempt in range(1, max_attempts+1):
        try:
            print(f"Syncing time with NTP (attempt {attempt})...")
            ntptime.settime()  # sets RTC to UTC
            utc_now = time.localtime()

            offset = uk_dst_offset(utc_now)
            local_epoch = time.mktime(utc_now) + offset
            tm = time.localtime(local_epoch)

            # Write corrected local time to RTC
            machine.RTC().datetime((
                tm[0], tm[1], tm[2], tm[6]+1, tm[3], tm[4], tm[5], 0
            ))

            print("✅ NTP sync successful (local time):", time.localtime())
            return True

        except Exception as e:
            print(f"⚠️ NTP sync failed (attempt {attempt}/{max_attempts}):", e)
            time.sleep(1)

    print("⚠️ Using Pico system time (unsynced)")
    return False

# 
# def last_sunday(year, month):
#     """Return the date of the last Sunday of a given month/year."""
#     # Start from the last day of the month
#     for day in range(31, 0, -1):
#         try:
#             tm = time.localtime(time.mktime((year, month, day, 0, 0, 0, 0, 0)))
#             if tm[6] == 6:  # Sunday
#                 return day
#         except:
#             continue
#     return None
# 
# def uk_dst_offset(now=None):
#     """Return timezone offset in seconds for UK (GMT/BST)."""
#     if now is None:
#         now = time.localtime()
#     year = now[0]
# 
#     # DST starts last Sunday in March, 01:00 UTC
#     dst_start = (year, 3, last_sunday(year, 3), 1, 0, 0, 0, 0)
#     # DST ends last Sunday in October, 01:00 UTC
#     dst_end = (year, 10, last_sunday(year, 10), 1, 0, 0, 0, 0)
# 
#     now_epoch = time.mktime(now)
#     start_epoch = time.mktime(dst_start)
#     end_epoch = time.mktime(dst_end)
# 
#     if start_epoch <= now_epoch < end_epoch:
#         return 3600  # BST
#     else:
#         return 0  # GMT
# 
# def sync_time():
#     try:
#         print("Syncing time with NTP...")
#         ntptime.settime()  # sets RTC to UTC
#         utc_now = time.localtime()
# 
#         # Determine DST offset
#         offset = uk_dst_offset(utc_now)
# 
#         # Apply offset
#         local_epoch = time.mktime(utc_now) + offset
#         tm = time.localtime(local_epoch)
# 
#         # Write corrected local time to RTC
#         machine.RTC().datetime((
#             tm[0], tm[1], tm[2], tm[6]+1, tm[3], tm[4], tm[5], 0
#         ))
# 
#         print("NTP sync successful (local time):", time.localtime())
#         return True
#     except Exception as e:
#         print("NTP sync failed:", e)
#         return False
#     


# ==== Wi-Fi Connect with retries ====
def connect_wifi(max_attempts=10):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to Wi-Fi...")
        wlan.connect(SSID, PASSWORD)
        attempts = 0
        while not wlan.isconnected() and attempts < max_attempts:
            time.sleep(1)
            attempts += 1
    if wlan.isconnected():
        print("✅ Wi-Fi connected:", wlan.ifconfig())
        time.sleep(2)  # allow network stack to settle
    else:
        print("⚠️ Wi-Fi connection failed after retries")
    return wlan.isconnected()

# ==== Wi-Fi connection ====
# wlan = network.WLAN(network.STA_IF)
# wlan.active(True)
# wlan.connect(SSID, PASSWORD)
# while not wlan.isconnected():
#     time.sleep(1)
# print("✅ Wi-Fi connected:", wlan.ifconfig())

# sync_time()


# ==== MQTT Connect with retries ====
def connect_mqtt(max_attempts=3):
    global client
    client = MQTTClient("pico", "io.adafruit.com", user=AIO_USERNAME, password=AIO_KEY, port=1883)
    for attempt in range(max_attempts):
        try:
            client.connect()
            print("✅ MQTT connected")
            return client
        except OSError as e:
            print(f"⚠️ MQTT connect failed (attempt {attempt+1}/{max_attempts}):", e)
            time.sleep(2)
    print("⚠️ MQTT connection failed, proceeding without it")
    return None

# ==== MQTT setup ====
# client = MQTTClient("pico", "io.adafruit.com", user=AIO_USERNAME, password=AIO_KEY, port=1883)


# ==== Startup sequence ====
if connect_wifi():
    sync_time()


    wlan = network.WLAN(network.STA_IF)
    print(wlan.ifconfig())

import usocket as socket

s = socket.socket()
s.settimeout(5)  # 5-second timeout
try:
    s.connect(("1.1.1.1", 80))
    print("Internet access: OK")
except OSError as e:
    print("Internet access failed:", e)
finally:
    s.close()


import urequests

try:
    r = urequests.get("http://example.com")
    print("Internet OK, status:", r.status_code)
    r.close()
except Exception as e:
    print("Internet check failed:", e)
    
mqtt_client = connect_mqtt()


def publish_pump_state(state):
    try:
        client.publish(AIO_FEED_PUMP_STATE, state)
        print(f"📤 Published pump state: {state}")
    except Exception as e:
        print("❌ MQTT publish pump_state failed:", e)

def publish_level_state(state):
    try:
        client.publish(AIO_FEED_LEVEL_STATE, state)
        print(f"📤 Published water level: {state}")
    except Exception as e:
        print("❌ MQTT publish level_state failed:", e)

# ==== Reset feed to "0" ====
########## to be moved to main wrapper ###########
def reset_OTA_trigger_feed():
    try:
        client.publish(AIO_FEED_OTA_TRIGGER, b"0")
        print("📤 Reset OTA Trigger Feed")
    except Exception as e:
        print("❌ Could not reset OTA feed:", e)
#############################

def log_debug(msg):
    try:
        client.publish(f"{AIO_USERNAME}/feeds/debug", msg)
    except Exception as e:
        # Don't crash if WiFi/MQTT isn't ready
        pass

def message_callback(topic, msg):
    global override_active, override_end_time, pump_on, reboot_triggered
    global PUBLISH_INTERVAL, PUMP_TEST_INTERVAL, PUMP_TEST_DURATION

    topic_str = topic.decode()
    msg_str = msg.decode().strip()
    print("📩 Received:", topic_str, msg_str)
    
    # 🔍 Debug line goes here
    print("DEBUG topic:", repr(topic_str), "message:", repr(msg_str))

    if topic_str == AIO_FEED_PUMP_OVERRIDE:
        if msg_str == "NONE":
            return
        if msg_str.upper().startswith("ON"):
            parts = msg_str.split(":")
            duration = 20
            if len(parts) == 2:
                try:
                    duration = int(parts[1])
                except:
                    print("⚠️ Invalid override duration")
            if not level_state:  # Only allow override if water level is wet
                override_active = True
                override_end_time = time.time() + duration
                relay.value(1)
                led.value(1)
                pump_on = True
                publish_pump_state("ON")
                print(f"🚨 Manual pump ON for {duration}s (override)")
            else:
                print("⛔ Override pump ON blocked due to low water level")
        elif msg_str.upper().startswith("OFF"):
            override_active = False
            relay.value(0)
            led.value(0)
            pump_on = False
            publish_pump_state("OFF")
            print("🚨 Manual pump OFF (override)")
        client.publish(AIO_FEED_PUMP_OVERRIDE, "NONE")

    elif topic_str == AIO_FEED_PUBLISH_INTERVAL:
        try:
            PUBLISH_INTERVAL = max(5, min(int(msg_str), 3600))
            print(f"⏱️ Set publish interval: {PUBLISH_INTERVAL}s")
        except:
            print("⚠️ Invalid publish interval")

    elif topic_str == AIO_FEED_PUMP_INTERVAL:
        try:
            PUMP_TEST_INTERVAL = max(60, min(int(msg_str), 3600))
            print(f"🔁 Pump test interval: {PUMP_TEST_INTERVAL}s")
        except:
            print("⚠️ Invalid pump test interval")

    elif topic_str == AIO_FEED_PUMP_DURATION:
        try:
            PUMP_TEST_DURATION = max(5, min(int(msg_str), 600))
            print(f"🕒 Pump test duration: {PUMP_TEST_DURATION}s")
        except:
            print("⚠️ Invalid pump test duration")

    elif topic_str == AIO_FEED_OTA_TRIGGER:
        if msg_str == "1":
            print("Soft reboot requested via feed.")
            reboot_triggered = True
            reboot_confirmed = False
        elif msg_str == "0":
            if reboot_triggered:
                print("✅ OTA trigger feed reset confirmed!")
                reboot_confirmed = True

# --- MQTT setup ---            
client.set_callback(message_callback)
client.connect()
for feed in [AIO_FEED_PUMP_OVERRIDE, AIO_FEED_PUBLISH_INTERVAL, AIO_FEED_PUMP_INTERVAL, AIO_FEED_PUMP_DURATION, AIO_FEED_OTA_TRIGGER]:
    client.subscribe(feed)
print("✅ Subscribed to Adafruit IO feeds")
log_debug("MQTT Connected")

publish_pump_state("OFF")

def debounce_level_sensor():
    global last_level_state, level_state, level_last_change
    reading = level_sensor_pin.value()
    now = time.ticks_ms()
    if reading != last_level_state:
        level_last_change = now
        last_level_state = reading
    else:
        if time.ticks_diff(now, level_last_change) > LEVEL_DEBOUNCE_DELAY:
            if level_state != reading:
                level_state = reading
                state_str = "WET" if not level_state else "DRY"
                print(f"💧 Water level sensor state: {state_str}")
                publish_level_state(state_str)

def check_button():
    global last_button_state, last_debounce_time, override_active, override_end_time, pump_on
    reading = button.value()
    now = time.ticks_ms()
    if reading != last_button_state:
        last_debounce_time = now
    if (time.ticks_diff(now, last_debounce_time) > BUTTON_DEBOUNCE_DELAY) and (reading == 0):
        # Toggle override, but only if water level is wet
        if not level_state:
            override_active = not override_active
            if override_active:
                override_end_time = time.time() + 20  # 20s override default
                relay.value(1)
                led.value(1)
                pump_on = True
                publish_pump_state("ON")
                print("🖲️ Manual override button pressed: Pump ON")
            else:
                relay.value(0)
                led.value(0)
                pump_on = False
                publish_pump_state("OFF")
                print("🖲️ Manual override button pressed: Pump OFF")
        else:
            print("⛔ Manual override blocked due to low water level")
        time.sleep_ms(300)  # small delay to avoid repeat toggles
    last_button_state = reading

def read_temperatures():
    temps = {}
    try:
        ds_sensor.convert_temp()
        time.sleep_ms(750)
        for rom in roms:
            temp = ds_sensor.read_temp(rom)
            rom_hex = rom.hex()
            label = rom_to_label.get(rom_hex)
            if label:
                temps[label] = temp
                print(f"🌡 {label}: {temp:.2f} °C")
            else:
                print(f"⚠️ Unknown sensor {rom_hex}")
    except Exception as e:
        print("❌ Error reading temperatures:", e)
    return temps

def safe_to_run_pump(temps):
    # Pump must NOT run if enclosure sensor missing or enclosure temp too high
    enclosure_temp = temps.get('tEnclosure', None)
    if enclosure_temp is None:
        print("⛔ Enclosure temp sensor missing. Pump blocked for safety.")
        return False
    if enclosure_temp > MAX_ENCLOSURE_TEMP:
        print(f"⛔ Enclosure temp too high ({enclosure_temp:.1f} °C). Pump blocked for safety.")
        return False
    return True

def sensors_ok_for_test(temps):
    # Both flow and return sensors must be present for test cycles
    return ('tFlow' in temps) and ('tReturn' in temps)

def set_pump(state):
    global pump_on
    pump_on = state
    relay.value(1 if state else 0)
    led.value(1 if state else 0)
    publish_pump_state("ON" if state else "OFF")
    print(f"🚿 Pump {'ON' if state else 'OFF'}")

# ==== Time Window Helper ====
# Adjust this offset for your local timezone (e.g. UK summer = +1, UK winter = 0)
UTC_OFFSET_HOURS = 1  # UK BST right now

def within_time_window(start_hour=9, end_hour=17):
    """
    Returns True if local time is within the allowed range.
    start_hour and end_hour are in local time (24h format).
    """
    t = time.localtime()
    current_hour = t[3]
    return start_hour <= current_hour < end_hour


def is_time_synced():
    """
    Returns True if the Pico's RTC time has been set to a date after 2023.
    This is a simple way to check if NTP has run successfully.
    """
    year = time.localtime()[0]
    return year >= 2023


# ==== Main Loop ====
while True:
    try:
        client.check_msg()
    except OSError as e:
        print("❌ MQTT error:", e)
        try:
            client.connect()
            for feed in [AIO_FEED_PUMP_OVERRIDE, AIO_FEED_PUBLISH_INTERVAL, AIO_FEED_PUMP_INTERVAL, AIO_FEED_PUMP_DURATION, AIO_FEED_OTA_TRIGGER]:
                client.subscribe(feed)
            print("🔄 Reconnected to MQTT")
            log_debug("Reconnected to MQTT")
        except Exception as e:
            print("❌ Reconnect failed:", e)
            time.sleep(5)

    # Check time has synced
    if not is_time_synced():
        print("Waiting for NTP time sync")
        continue


    now = time.time()


    if now - last_publish_time >= PUBLISH_INTERVAL:
        log_debug("Updated Main loop running")

    # ==== Soft Reboot (compatible with main.py OTA) ====
    if reboot_triggered and not reboot_confirmed:
        print("Turning off pump before soft reboot...")
        set_pump(False)
        time.sleep(0.5)

        # Wait a few seconds to ensure everything is off
        print("✅ Pump safely turned off, waiting to reboot...")

        # Optional: brief delay to let MQTT messages propagate
        time.sleep(2)

        print("Soft rebooting now!")
        machine.reset()

#     if reboot_triggered and not reboot_confirmed:
#         print("Turning off pump before soft reboot...")
#         set_pump(False)
#         time.sleep(0.5)
# 
#         try:
#             client.publish(AIO_FEED_OTA_TRIGGER, b"0")
#             print("Sent reset request to OTA trigger feed")
#         except Exception as e:
#             print("⚠️ Failed to reset OTA trigger feed:", e)
# 
#         # wait until feed confirmed reset, with timeout
#         start_wait = time.time()
#         while not reboot_confirmed and time.time() - start_wait < 10:
#             try:
#                 client.check_msg()  # process incoming MQTT messages
#             except OSError:
#                 pass
#             time.sleep(0.5)
# 
#         if reboot_confirmed:
#             log_debug("Soft rebooting")
#             time.sleep(1)
#             print("Soft rebooting now!")
#             machine.reset()
#         else:
#             print("⚠️ OTA feed reset not confirmed - skipping reboot for now")


#        time.sleep(0.5)  # ensure pump off
#       reset_OTA_trigger_feed()
#        time.sleep(1)
#        log_debug("Soft rebooting")
#        time.sleep(1)
#        print("Soft rebooting now!")
#        machine.reset()



    debounce_level_sensor()
    check_button()
    temps = read_temperatures()


    # Read water level (LOW = water present)
    water_present = (level_sensor_pin.value() == 0)

    # ======= SAFETY CHECKS =======
    
    if not is_time_synced():
        print("⚠️ Time not synced, attempting NTP sync...")
        if sync_time():
            print("✅ Time synced successfully")
        else:
            print("❌ Time sync failed, will retry in 10s")
            log_debug("Time sync failed, will retry in 10s")
            time.sleep(10)
            continue
    
    if not water_present:
        if pump_on:
            print("⛔ Water level low, turning pump OFF immediately")
            set_pump(False)
        continue  # skip rest of loop

    if not safe_to_run_pump(temps):
        if pump_on:
            print("⛔ Thermal safety triggered, turning pump OFF")
            set_pump(False)
        continue

    if not sensors_ok_for_test(temps):
        print("⚠️ Required sensors missing, skipping all pump logic")
        continue
    # ============================
    


    if override_active and now > override_end_time:
        override_active = False
        set_pump(False)
        print("🕒 Override expired")






    if now - last_publish_time >= PUBLISH_INTERVAL:
        last_publish_time = now
        for label, temp in temps.items():
            topic = f"{AIO_USERNAME}/feeds/{label}"
            try:
                client.publish(topic, str(temp))
                print(f"📤 Published {label}: {temp:.2f} °C")
            except Exception as e:
                print("❌ Publish error:", e)
        # Publish delta temp if both sensors present
        if 'tFlow' in temps and 'tReturn' in temps:
            delta = temps['tReturn'] - temps['tFlow']
            try:
                client.publish(AIO_FEED_DELTA_TEMP, str(delta))
                print(f"📤 Published delta_temp: {delta:.2f} °C")
            except Exception as e:
                print("❌ Publish error delta_temp:", e)


    # Immediately turn pump OFF if water is NOT present
    if not water_present and pump_on:
        print("⛔ Water level low, turning pump OFF immediately")
        set_pump(False)

    # Determine if pump should run
    if override_active:
        # Override only runs pump if water level wet and thermal safe
        if water_present and safe_to_run_pump(temps):
            if not pump_on:
                set_pump(True)
            print("🔒 Override active - pump forced ON")
        else:
            if pump_on:
                set_pump(False)
            print("⛔ Override blocked due to water level or thermal safety")
        time.sleep(5)
        continue

    # No override - automatic control

    t = time.localtime()
    print("DEBUG test conditions:",
          within_time_window(earliest_test_time, latest_test_time),
          sensors_ok_for_test(temps),
          water_present,
          now - last_test_time >= PUMP_TEST_INTERVAL,
          now - last_test_time,
          PUMP_TEST_INTERVAL - (now - last_test_time),
          f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}")
    log_debug(f"DEBUG test conditions: "
          f"sensors_ok={sensors_ok_for_test(temps)} "
          f"water_present={water_present} "
          f"time_ok={now - last_test_time >= PUMP_TEST_INTERVAL} "
          f"within time window={within_time_window(earliest_test_time, latest_test_time)} "
          f"now={now} last={last_test_time} "
          f"time to next test={PUMP_TEST_INTERVAL - (now - last_test_time)} "
          f"current local time={t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}")
    

    # Skip test cycle if flow or return missing

    if first_boot:
        print("🚿 First boot test run...")
        set_pump(True)
        time.sleep(5)
        set_pump(False)
        last_test_time = time.time()
        first_boot = False
    else:
        if within_time_window(earliest_test_time, latest_test_time):
            if sensors_ok_for_test(temps):
                if water_present:
                    if now - last_test_time >= PUMP_TEST_INTERVAL:
                        print("🧪 Starting pump test cycle...")
                        set_pump(True)
                        test_start = time.time()
                        while time.time() - test_start < PUMP_TEST_DURATION and water_present:
                            # Read water level (LOW = water present)
                            water_present = (level_sensor_pin.value() == 0)
                            try:
                                client.check_msg()
                            except OSError:
                                pass
                            temps = read_temperatures()
                            if 'tFlow' in temps and 'tReturn' in temps:
                                delta = temps['tReturn'] - temps['tFlow']
                                print(f"ΔT during test: {delta:.2f} °C")
                                if delta > HIGH_THRESHOLD_DIFF:
                                    print("✅ Solar heating effective, keeping pump ON")
                                    break
                            time.sleep(2)
                        else:
                            print("⛔ Solar ineffective, turning pump OFF")
                            set_pump(False)
                        last_test_time = time.time()
                else:
                    print("💧 Water level low")
            else:
                print("⚠️ Flow or Return sensor missing - skipping test cycle")
        else:
            print("Skipping test - outside allowed hours")

    # Hysteresis control
    if pump_on and sensors_ok_for_test(temps):
        delta = temps['tReturn'] - temps['tFlow']
        if delta < LOW_THRESHOLD_DIFF:
            print(f"🛑 ΔT = {delta:.2f} °C below threshold, turning pump OFF")
            set_pump(False)
            log_debug(f"ΔT = {delta:.2f} °C below threshold, turning pump OFF")

    # If pump is off and delta high, turn on pump (only if sensors ok and thermal safe)
    if (not pump_on) and sensors_ok_for_test(temps) and safe_to_run_pump(temps) and water_present:
        delta = temps['tReturn'] - temps['tFlow']
        if delta > HIGH_THRESHOLD_DIFF:
            print(f"⚡ ΔT = {delta:.2f} °C above threshold, turning pump ON")
            set_pump(True)

    time.sleep(5)
