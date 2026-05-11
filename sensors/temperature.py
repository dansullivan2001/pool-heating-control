# sensors/temperature.py
__version__ = "0.1.0"

import time
from state import state
from config import rom_to_label

try:
    import machine
    import onewire
    import ds18x20
    Pin     = machine.Pin
    OneWire = onewire.OneWire
    DS18X20 = ds18x20.DS18X20
except ImportError:
    from mocks.mock_hardware import MockPin as Pin, MockOneWire as OneWire, MockDS18X20 as DS18X20


# DS18x20 requires at least 750 ms conversion time before results can be read.
CONVERSION_MS = 750


class TemperatureSensor:
    """
    Non-blocking DS18x20 temperature sensor manager.

    The DS18x20 read cycle has two phases:
      1. convert_temp() — tells all sensors to start measuring (~750 ms)
      2. read_temp()    — retrieves the result (immediate, after the delay)

    Blocking the main loop for 750 ms on every read is unacceptable on a
    safety controller. Instead, this class splits the cycle across two calls:

      - start_conversion() triggers measurement and records the timestamp.
      - read() checks whether enough time has elapsed, then reads results.
        If called too early it returns the previous readings unchanged.

    Typical usage in the main loop:
        sensor.start_conversion()          # call once to kick off measurement
        # ... do other work for >= 750 ms ...
        readings = sensor.read()           # safe to call after 750 ms

    Or, since main.py reads sensors every SENSOR_READ_INTERVAL seconds
    (>= 750 ms), simply call read() each interval — it calls
    start_conversion() itself if none is pending, then reads on the
    following interval.
    """

    def __init__(self, pin, gui=None):
        self._pin        = Pin(pin)
        self._ow         = OneWire(self._pin)
        self.ds_sensor   = DS18X20(self._ow)

        # Scan once at boot and cache the ROM list.
        # ROMs don't change at runtime (sensors are hardwired).
        self.roms = self.ds_sensor.scan()

        self._conversion_started_ms = None   # None = no conversion pending
        self._last_readings = {}             # cache of last good readings

        if gui and hasattr(self.ds_sensor, "attach_gui"):
            self.ds_sensor.attach_gui(gui)

        self._log_discovered_sensors()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def start_conversion(self):
        """
        Trigger a new temperature measurement on all sensors.
        Non-blocking — returns immediately.
        Call this, then call read() at least 750 ms later.
        """
        try:
            self.ds_sensor.convert_temp()
            self._conversion_started_ms = self._ticks_ms()
        except Exception as e:
            print(f"⚠️ Temperature conversion failed: {e}")
            self._conversion_started_ms = None

    def read(self):
        """
        Read temperature from all known sensors and update shared state.

        If no conversion is pending, starts one and returns the previous
        readings (the results won't be ready until the next call).

        If a conversion is pending but not yet complete, returns the
        previous readings without blocking.

        Returns dict of {label: temp_celsius | None}.
        """
        # No conversion in flight — start one and return cached values.
        if self._conversion_started_ms is None:
            self.start_conversion()
            return dict(self._last_readings)

        # Conversion in flight — check if it's ready yet.
        elapsed = self._ticks_diff_ms(self._ticks_ms(), self._conversion_started_ms)
        if elapsed < CONVERSION_MS:
            return dict(self._last_readings)   # not ready — return previous

        # Ready — read all sensors.
        readings = {}
        disconnected = []

        for rom in self.roms:
            rom_id = self._rom_to_hex(rom)
            label  = rom_to_label.get(rom_id)

            if label is None:
                print(f"⚠️ Unknown ROM {rom_id} — sensor not in config")
                # Include it with a synthetic label so it shows in debug output
                label = f"unknown_{rom_id}"
                disconnected.append(rom_id)

            try:
                temp = self.ds_sensor.read_temp(rom)
            except Exception as e:
                print(f"⚠️ read_temp failed for {label}: {e}")
                temp = None

            if temp is None:
                disconnected.append(rom_id)

            readings[label] = temp

        # Mark conversion cycle as done — next call to read() starts a new one.
        self._conversion_started_ms = None
        self._last_readings = readings

        # Update shared state
        state["temps"].update(readings)
        state["disconnected_sensors"] = disconnected
        state["sensors_ok"] = len(disconnected) == 0

        return readings

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _rom_to_hex(self, rom):
        """Convert a ROM (bytes or str) to a lowercase hex string."""
        if isinstance(rom, (bytes, bytearray)):
            return "".join("{:02x}".format(b) for b in rom)
        return str(rom)

    def _log_discovered_sensors(self):
        print("🌡️  Temperature sensors found:")
        for rom in self.roms:
            rom_id = self._rom_to_hex(rom)
            label  = rom_to_label.get(rom_id, f"unknown_{rom_id}")
            print(f"   ROM {rom_id} → {label}")
        if not self.roms:
            print("   ⚠️ No sensors found on OneWire bus!")

    # -------------------------------------------------------------------------
    # Tick helpers — compatible with both MicroPython and CPython
    # -------------------------------------------------------------------------

    @staticmethod
    def _ticks_ms():
        if hasattr(time, "ticks_ms"):
            return time.ticks_ms()
        return int(time.time() * 1000)

    @staticmethod
    def _ticks_diff_ms(a, b):
        if hasattr(time, "ticks_diff"):
            return time.ticks_diff(a, b)
        return a - b