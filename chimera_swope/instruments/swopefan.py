from chimera.instruments.fan import FanBase

from chimera_swope.instruments.swopebase import SwopeBase


class SwopeFan(FanBase, SwopeBase):
    __config__ = {"tcs_host": "127.0.0.1"}

    def __init__(self):
        FanBase.__init__(self)
        SwopeBase.__init__(self)

    def __start__(self):
        SwopeBase.__start__(self)

    # fan control
    def switch_on(self):
        return self.tcs.set_tubefans(True)

    def switch_off(self):
        return self.tcs.set_tubefans(False)

    def is_switched_on(self):
        return self.status["Tube_Fans"]
