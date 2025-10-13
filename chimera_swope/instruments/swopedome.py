from chimera.instruments.dome import DomeBase
from chimera_swope.instruments.swopebase import SwopeBase
from swope.tcs.swope_tcs import SwopeDomeShutter

class SwopeDome(DomeBase, SwopeBase):
    __config__ = {"tcs_host": "127.0.0.1"}

    def __init__(self):
        DomeBase.__init__(self)
        SwopeBase.__init__(self)

    def __start__(self):
        SwopeBase.__start__(self)

    def open_shutter(self):
        return self.tcs.set_dome_shutter(SwopeDomeShutter.OPEN)
    
    def close_shutter(self):
        return self.tcs.set_dome_shutter(SwopeDomeShutter.CLOSE)

    def track(self):
        return self.tcs.set_dome_auto(True)
    
    def stand(self):
        return self.tcs.set_dome_auto(False)
    
    def is_tracking(self):
        self.update_status()
        return self.status["Dome_auto"]
    
    def get_az(self):
        self.update_status()
        return self.status["Dome_az"]
    
    def is_slit_open(self):
        return None
        raise NotImplementedError
    
    def is_slewing(self):
        return None
        raise NotImplementedError
    
        


    # def is_shutter_open(self):
    #     self.update_status()
    #     return self.status["Dome_Shutter"] == SwopeDomeShutter.OPEN
    


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