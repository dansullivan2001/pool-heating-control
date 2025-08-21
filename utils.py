# utils.py
__version__ = "0.0.1"

debug_buffer = []

def log(msg):
    print(msg)
    debug_buffer.append(msg)

def flush_debug():
    # send buffered messages to Adafruit every X sec
    pass
