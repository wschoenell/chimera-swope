from chimera.instruments.lamp import LampBase
from chimera_swope.instruments.swopebase import SwopeBase


class SwopeDomeLamp(LampBase, SwopeBase):
    __config__ = {"tcs_host": "127.0.0.1"}
    
    def __init__(self):
        LampBase.__init__(self)
        SwopeBase.__init__(self)

    def __start__(self):
        SwopeBase.__start__(self)

    def is_switched_on(self):
        self.update_status()
        return self.status["DomeLights"]
    
    def switch_on(self):
        self.tcs.set_domelight(True)

    def switch_off(self):
        self.tcs.set_domelight(False)