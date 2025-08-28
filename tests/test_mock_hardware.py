# test_mock_hardware.py
__version__ = "0.0.1"

import threading, time
import mocks.mock_hardware as mock_hardware

def poll():
    ds = mock_hardware.MockDS18X20(None)
    while True:
        for s in ds.scan():
            print(f"{s}: {ds.read_temp(s):.2f} °C", end=" | ")
        print("Water:", "Present" if mock_hardware.gui.water_present() else "Dry")
        time.sleep(3)

threading.Thread(target=poll, daemon=True).start()
mock_hardware.root.mainloop()
