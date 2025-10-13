from time import time
from swope.tcs.swope_tcs import SwopeTCS
from chimera.instruments.fan import FanBase


class SwopeFan(FanBase):
    __config__ = {"tcs_host": "127.0.0.1"}

    def __init__(self):
        FanBase.__init__(self)
        self.tcs = None
        self.status = None
        self._last_update = None
        self._update_interval = 1.0  # seconds

    def __start__(self):
        self.tcs = SwopeTCS(self["tcs_host"])

    def update_status(self):
        if self._last_update is not None and (time() - self._last_update) < self._update_interval:
            return
        self._last_update = time()
        self.status = self.tcs.get_status()
        print(f"Updated status: {self.status}")

    # fan control
    def switch_on(self):
        print("Switching on tube fans")
        return self.tcs.set_tubefans(True)

    def switch_off(self):
        print("Switching off tube fans")
        return self.tcs.set_tubefans(False)

    def is_switched_on(self):
        self.update_status()
        return self.status["Tube_Fans"]
