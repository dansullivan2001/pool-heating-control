import time

class DebouncedWaterLevel:
    """
    Debounced water level sensor with wet/dry hold times.

    sensor_mgr: instance of SensorManager with read_level_raw() method
    delay_ms: debounce delay
    wet_hold: minimum time to confirm wet state (ms)
    dry_hold: minimum time to confirm dry state (ms)
    """
    def __init__(self, sensor_mgr, delay_ms=200, wet_hold=2000, dry_hold=2000):
        self.sensor_mgr = sensor_mgr
        self.delay_ms = delay_ms
        self.wet_hold = wet_hold
        self.dry_hold = dry_hold

        self.stable_state = self.sensor_mgr.read_level_raw()
        self.last_change = time.ticks_ms()
        self.state_change_time = time.ticks_ms()

    def update(self):
        """Call this every loop; returns debounced water state (1=wet, 0=dry)"""
        current = self.sensor_mgr.read_level_raw()
        now = time.ticks_ms()

        # Detect change and apply debounce
        if current != self.stable_state:
            if time.ticks_diff(now, self.last_change) > self.delay_ms:
                self.stable_state = current
                self.state_change_time = now
                self.last_change = now
        else:
            self.last_change = now  # reset debounce if reading stable

        # Apply wet/dry hold
        elapsed = time.ticks_diff(now, self.state_change_time)
        if self.stable_state == 1 and elapsed < self.wet_hold:
            return 0  # still holding dry until wet_hold expires
        if self.stable_state == 0 and elapsed < self.dry_hold:
            return 1  # still holding wet until dry_hold expires

        return self.stable_state
