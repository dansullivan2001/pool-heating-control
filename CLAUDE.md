# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

MicroPython firmware for a Raspberry Pi Pico W that controls a solar pool heating pump. The controller reads DS18x20 temperature sensors to detect a solar gain differential (tReturn − tFlow) and runs the pump accordingly. All configuration, cloud connectivity (Adafruit IO via MQTT), OTA updates, and safety logic run on the Pico.

The codebase is **dual-platform**: every module that uses MicroPython-specific imports wraps them in `try/except ImportError` and falls back to desktop mocks, enabling the full controller to run on CPython for development and testing without real hardware.

## Running and testing

**Desktop simulation (primary dev workflow):**
```bash
python test_main_controller_gui.py   # Tkinter GUI — simulates all hardware inputs/outputs
```

**Run other test files:**
```bash
source .venv/bin/activate
python -m pytest test_sensors.py test_mock_environment.py -v
```

**Deploy to Pico:** Copy all source files (excluding `mocks/`, `typings/`, `.venv/`, test files) to the Pico filesystem using `mpremote` or Thonny. `main.py` runs automatically on boot.

## Architecture

### Shared state (`state.py`)
A single module-level `state` dict is the sole source of truth at runtime. All keys with safe defaults are declared there — safety-critical booleans default to the restrictive/fail-safe value (`False`). No module writes state outside `state.py`'s declared keys.

### Boot sequence (`main.py`)
1. `ota.verify_or_rollback()` — runs before all other imports; rolls back to `.bak` files and reboots if any critical file is corrupt
2. Sensor initialisation + first reads (so state is populated before the first controller loop)
3. `Network.connect()` — blocking WiFi + MQTT connect
4. NTP sync (sets Pico RTC to UK local time for correct core-hours comparisons)
5. `Controller` construction
6. Main loop: sensor reads every 2 s → `network.loop()` → OTA check (if flagged) → `controller.loop()` → `gc.collect()`

### Controller safety chain (`controller/controller.py`)
`_run_safety_chain()` evaluates conditions in strict priority order. The first failing condition forces the pump off and short-circuits all remaining logic:

1. Water level — dry-run protect (fail-safe: pump off if level sensor absent or low)
2. Enclosure sensor missing — can't verify electronics are safe
3. Enclosure overtemp — `tEnclosure > config["max_enclosure_temp"]`
4. Flow/Return sensors missing — can't compute solar delta

If the chain passes, `_run_control_logic()` runs:
- Manual boost (button or MQTT mode 1) — timed, overrides night/holiday
- Night / holiday gate (outside `core_start_hour`–`core_end_hour`, or `manual_disabled`)
- Solar delta hysteresis: pump ON when `delta >= delta_threshold_high`, OFF when `delta < delta_threshold_low`
- Periodic test run every `pump_test_interval` seconds — forces circulation so stagnant sensor readings refresh

### Network layer (`network/`)
- `Network` aggregates `WiFiManager`, `MQTTManager`, and `Feeds`
- Publishing is done exclusively by `Controller.publish_state()` — the Network layer never publishes on its own
- `MQTTManager.publish()` has a per-topic rate limit (10 s); `urgent=True` bypasses it for safety-critical state changes
- Offline messages are queued (bounded at 20) and flushed on reconnect
- MQTT watchdog triggers `machine.reset()` after a sustained outage (`watchdog_interval × 3` seconds)
- `message_handler` is set on the `MQTTManager` by the Controller after construction — not at `Network.__init__` time

### Sensor layer (`sensors/`)
- `TemperatureSensor` is non-blocking: `read()` starts a DS18x20 conversion on one call and returns results on the next (≥750 ms later), avoiding a blocking 750 ms delay in the main loop
- ROM → label mapping lives in `config.rom_to_label`; adding a sensor = add one entry there
- `WaterLevelSensor` and `Button` are simple digital reads

### OTA (`ota.py`)
Triggered by MQTT → `state["ota_pending"] = True`. Downloads changed files to `.new`, verifies syntax, then atomically renames: existing → `.bak`, `.new` → active. `ota.py` itself is applied last. On next boot `verify_or_rollback()` checks CRITICAL_FILES; if any fail, `.bak` files are restored and the Pico reboots.

**Version tracking:** Every source file has `__version__ = "x.y.z"` at the top. `manifest.json` (hosted at `secrets.OTA_MANIFEST_URL`) lists the expected version for each file. Update both the file's `__version__` and `manifest.json` when making changes intended for OTA deployment.

### Desktop simulation (`test_main_controller_gui.py`, `mocks/`)
`test_main_controller_gui.py` is a full Tkinter harness that mirrors the `main.py` loop at 100 ms ticks. It injects `GUIMockDS18X20` (GUI sliders → temperature readings), a mock water level, and mock WiFi. State flows one-directionally: GUI inputs → shared `state` → controller → GUI outputs. `update_from_state()` never writes to `state`.

### Status LED (`status_led.py`)
Non-blocking pattern player. Priority order: `critical` → `sensor_missing` → `mqtt_offline` → `ok`. `DesktopStatusLED` is used in the simulation harness; `StatusLED` uses `machine.Pin` on the Pico.

## Key configuration

- **`config.py`**: `CONFIG` dict (thresholds, timers, MQTT intervals), GPIO pin assignments, `rom_to_label` sensor map
- **`secrets.py`**: `WIFI_SSID`, `WIFI_PASSWORD`, `AIO_USERNAME`, `AIO_KEY`, `OTA_MANIFEST_URL` — not committed to git
- **`manifest.json`**: OTA manifest — update `base_url` to point to the real GitHub raw URL before deploying OTA

## Dual-platform pattern

Every module that needs MicroPython hardware follows this pattern:

```python
try:
    import machine
    import onewire
    # ... real hardware
except ImportError:
    from mocks.mock_hardware import MockPin as Pin, ...
```

The same pattern applies in `network/mqtt.py` (`umqtt` vs `paho`), `ntp.py` (`ntptime` vs no-op), and `status_led.py` (`machine.Pin` vs `MockPin`). When adding new hardware-dependent code, always follow this pattern to keep the desktop simulation working.
