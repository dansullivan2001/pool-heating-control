# run_mock_env.py

from mocks import MockEnvironment

# Create the simulated hardware environment
env = MockEnvironment()

# Demo logic: print pump state when you interact
def monitor_pump():
    print("Initial pump state:", env.pump_pin.value())
    env.pump_pin.value(1)  # simulate turning pump on
    print("Pump state after ON:", env.pump_pin.value())
    env.pump_pin.value(0)  # simulate turning pump off
    print("Pump state after OFF:", env.pump_pin.value())
    print("Water level:", "Present" if env.water_level_pin.value() else "Dry")
    for sensor in env.ds18x20.scan():
        temp = env.ds18x20.read_temp(sensor)
        print(f"{sensor}: {temp} °C")

# Optionally, you can set up a repeating check
# Here we just call it once for demo
monitor_pump()

# Start the GUI event loop (blocking)
env.root.mainloop()
