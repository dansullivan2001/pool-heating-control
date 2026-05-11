# pump.py
__version__ = "0.0.1"

import machine
from config import PIN_PUMP, PIN_LED

pump_relay = machine.Pin(PIN_PUMP, machine.Pin.OUT)
led = machine.Pin(PIN_LED, machine.Pin.OUT)

def set_pump(on: bool):
    pump_relay.value(1 if on else 0)
    led.value(1 if on else 0)

def get_pump_state():
    return bool(pump_relay.value())
