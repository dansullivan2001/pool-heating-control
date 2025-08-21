# sensors.py
__version__ = "0.0.1"

import machine, onewire, ds18x20, time

def read_temperatures():
    # returns dict: {"tFlow": 20.3, "tReturn": 19.8, ...}
    pass

def read_water_level():
    # debounce + delay handling
    return True  # water present
