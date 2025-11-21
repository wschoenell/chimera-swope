import time
from chimera.instruments.dome import DomeBase
from chimera_swope.instruments.swopebase import SwopeBase
from swope.tcs.swope_tcs import SwopeDomeShutter
from chimera.interfaces.dome import Mode


class SwopeDome(DomeBase, SwopeBase):
    __config__ = {
        "tcs_host": "127.0.0.1",
        "telescope": "/Telescope/0",
        "mode": Mode.Track,
        "model": "LCO Swope Dome",
        "timeout_slit_operation": 600,  # 600s -> 10 minutes
    }

    def __init__(self):
        DomeBase.__init__(self)
        SwopeBase.__init__(self)

    def __start__(self):
        SwopeBase.__start__(self)

    def open_slit(self):
        assert self.tcs.set_dome_shutter(SwopeDomeShutter.OPEN)
        t0 = time.time()
        while not self.is_slit_open():
            if time.time() - t0 > self["timeout_slit_operation"]:
                raise TimeoutError("Slit open operation timed out")
            time.sleep(1)
        self.slit_opened(self.get_az())

    def close_slit(self):
        assert self.tcs.set_dome_shutter(SwopeDomeShutter.CLOSE)
        t0 = time.time()
        while self.is_slit_open():
            if time.time() - t0 > self["timeout_slit_operation"]:
                raise TimeoutError("Slit close operation timed out")
            time.sleep(1)
        self.slit_closed(self.get_az())

    def track(self):
        return self.tcs.set_dome_auto(True)

    def stand(self):
        return self.tcs.set_dome_auto(False)

    def is_tracking(self):
        return self.status["Dome_auto"]

    def get_az(self):
        return self.status["Dome_az"]

    def slew_to_az(self, az):
        print("SwopeDome.slew_to_az not implemented")
        return

    def is_slit_open(self):
        return self.tcs.get_dome_shutter() == SwopeDomeShutter.OPEN

    def is_slewing(self):
        self.tcs.is_dome_moving()

    def is_synced_with_telescope(self):
        return self.tcs.is_dome_in_sync()

    # todo: implement - check for timeouts, errors, etc.
    # def sync_with_telescope(self):
    #     if self._mode != Mode.Track:
    #         raise RuntimeError("Cannot sync dome when not in Track mode")
    #     else:
    #         while not self.is_synced_with_telescope():
    #             time.sleep(1)


#     def sync_with_telescope(self):
#     def is_sync_with_telescope(self):
#     def get_mode(self):
#     def slew_to_az(self, az):
#         TODO: NEXTOBJ implements this
#     def is_slewing(self):
#     def abort_slew(self):
#     def open_slit(self):
#         TODO: SHUTTER implements this
#     def close_slit(self):
#         TODO: SHUTTER implements this
#     def is_slit_open(self):
#     def get_metadata(self, request):
