from time import time
from swope.tcs.swope_tcs import SwopeTCS, SwopeDomeShutter, SwopeScreenPos, SwopeFocuser


class SwopeBase:

    def __init__(self):
        self.tcs: SwopeTCS | None = None
        self._status: dict | None = None
        self._last_update: float | None = None
        self._update_interval: float = 1.0  # seconds

    def __start__(self):
        self.tcs = SwopeTCS(self["tcs_host"])

    @property
    def status(self, force=False):
        if (
            not force
            and self._last_update is not None
            and (time() - self._last_update) < self._update_interval
        ):
            return self._status
        self._last_update = time()
        self._status = self.tcs.get_status()
        return self._status
