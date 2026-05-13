# Solar Pool Heating Controller

MicroPython firmware for a Raspberry Pi Pico W that controls a solar pool heating pump. The controller reads DS18x20 temperature sensors, detects a solar gain differential between the flow and return pipes, and runs the pump accordingly. Configuration, cloud connectivity, OTA updates, and safety logic all run on the Pico.

---

## How it works

The pump runs when the difference between the solar panel return temperature and the flow temperature (`tReturn − tFlow`) exceeds a threshold, indicating the panels are hot enough to be worth circulating water through. A hysteresis band prevents rapid on/off cycling. The pump is restricted to configurable core hours (default 08:00–18:00) and can be manually boosted via a physical button or an MQTT command.

### Safety chain

Before any pump decision is made, the following are checked in order. The first failure stops the pump immediately:

1. **Water level** — dry-run protection; pump off if the level sensor is absent or low
2. **Enclosure sensor** — pump off if the electronics temperature sensor is missing
3. **Enclosure overtemp** — pump off if the enclosure exceeds 55 °C
4. **Flow/Return sensors** — pump off if either temperature sensor is missing

### Cloud connectivity

State is published to [Adafruit IO](https://io.adafruit.com) via MQTT every 30 seconds (and immediately on any safety-critical change). The MQTT watchdog triggers a full device restart after a sustained outage, ensuring the Pico recovers from network failures automatically.

### OTA updates

Firmware updates are triggered by an MQTT command. The Pico downloads changed files, verifies syntax, then atomically swaps them in. On the next boot, file integrity is checked and rolled back automatically if any critical file is corrupt.

---

## Hardware

| Component | GPIO Pin |
|---|---|
| DS18x20 temperature sensors (1-Wire bus) | 0 |
| Pump relay | 5 |
| Status LED | 6 |
| Manual boost button | 10 |
| Water level sensor | 14 |

**Sensors (DS18x20 ROM addresses → labels):**

| Label | Purpose |
|---|---|
| `tFlow` | Solar panel flow pipe |
| `tReturn` | Solar panel return pipe |
| `tAmbient` | Ambient air temperature |
| `tEnclosure` | Controller enclosure temperature |

ROM addresses are mapped to labels in `config.py` (`rom_to_label`). Update this dict if a sensor is replaced.

---

## Repository structure

```
main.py                  # Boot sequence and main loop
config.py                # Thresholds, GPIO pins, sensor ROM map
state.py                 # Shared runtime state (single source of truth)
ota.py                   # OTA update and rollback logic
manifest.json            # OTA manifest — lists expected version of each file
secrets.template.py      # Template for secrets.py (see below)
status_led.py            # Non-blocking status LED pattern player
utils.py                 # Shared utilities

controller/
  controller.py          # Safety chain and pump control logic

net/
  __init__.py            # Network aggregator (WiFi + MQTT)
  mqtt.py                # MQTT manager with publish queue and watchdog
  wifi.py                # WiFi manager
  feeds.py               # Adafruit IO feed definitions
  ntp.py                 # NTP time sync (sets RTC to UK local time)

sensors/
  __init__.py            # Sensor aggregator
  temperature.py         # Non-blocking DS18x20 reads
  water_level.py         # Digital water level sensor
  button.py              # Debounced manual boost button

mocks/                   # Desktop mock hardware (used by simulation only)
test_main_controller_gui.py  # Tkinter desktop simulation harness
```

---

## Restoring secrets.py

`secrets.py` is **not committed to the repository** (it is listed in `.gitignore`). It must be created manually on any new machine or after a fresh clone.

**To restore:**

1. Copy the template:
   ```bash
   cp secrets.template.py secrets.py
   ```

2. Open `secrets.py` and fill in your credentials:

   ```python
   WIFI_SSID     = "your_wifi_network_name"
   WIFI_PASSWORD = "your_wifi_password"

   AIO_USERNAME  = "your_adafruit_io_username"
   AIO_KEY       = "your_adafruit_io_key"   # found at io.adafruit.com under My Key

   OTA_MANIFEST_URL = "https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/YOUR_REPO/main/manifest.json"
   ```

3. Deploy `secrets.py` to the Pico manually — it is **never updated via OTA** and must be copied using `mpremote` or Thonny each time.

---

## Deploying to the Pico

Copy all source files to the Pico filesystem. The following should be excluded:

- `mocks/`
- `typings/`
- `.venv/` / `venv/`
- `test_*.py`
- `*.template.py`

Using `mpremote`:
```bash
mpremote connect /dev/tty.usbmodem* cp main.py secrets.py config.py state.py ota.py utils.py status_led.py manifest.json :
mpremote connect /dev/tty.usbmodem* cp -r controller/ net/ sensors/ :
```

`main.py` runs automatically on boot.

---

## Desktop simulation

The full controller logic can be run on a desktop without any hardware using the Tkinter GUI harness:

```bash
python test_main_controller_gui.py
```

This simulates all sensors via sliders, mock WiFi, and a mock MQTT broker. State flows one-directionally: GUI inputs → shared `state` → controller → GUI outputs.

**Running the test suite:**
```bash
source .venv/bin/activate
python -m pytest test_sensors.py test_mock_environment.py -v
```

---

## OTA update workflow

1. Edit source files and increment their `__version__` strings.
2. Update `manifest.json` to match the new versions.
3. Commit and push to the `main` branch (the Pico fetches files directly from GitHub raw URLs).
4. Send the OTA trigger via Adafruit IO — the Pico will download, verify, and apply the update then reboot.
