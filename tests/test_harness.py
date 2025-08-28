import time
import mocks.mock_hardware as hw
import pump_controller  # your real controller code

# Test runner
def run_scenario(mode, label):
    print("\n===============================")
    print(f" Running scenario {mode}: {label}")
    print("===============================\n")
    hw.SCENARIO.set_mode(mode)
    # Run controller loop a few times to process sensor data
    for i in range(3):
        print(f"\n--- Step {i+1} ---")
        pump_controller.main_loop_once()  # you'd need to refactor your code so logic fits here
        time.sleep(0.5)

if __name__ == "__main__":
    run_scenario(1, "Return higher than Flow (no heating)")
    run_scenario(2, "Flow higher than Return (heating active)")
    run_scenario(3, "Return starts higher, then falls below Flow (transition)")
