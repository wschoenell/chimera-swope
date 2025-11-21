from chimera.interfaces.focuser import FocuserAxis
from chimera.instruments.focuser import FocuserBase
from chimera.interfaces.focuser import InvalidFocusPositionException

from chimera_swope.instruments.swopebase import SwopeBase


class SwopeFocuser(FocuserBase, SwopeBase):
    __config__ = {"tcs_host": "127.0.0.1"}
    __config__["device"] = __config__["tcs_host"]

    def __init__(self):
        FocuserBase.__init__(self)
        SwopeBase.__init__(self)
        self.tcs = None
        self._status = None
        self._last_update = None
        self._update_interval = 1.0  # seconds

    def __start__(self):
        SwopeBase.__start__(self)

    def move_in(self, n, axis=FocuserAxis.Z):
        current_pos = self.get_position(axis)
        return self.move_to(current_pos - n, axis)

    def move_out(self, n, axis=FocuserAxis.Z):
        current_pos = self.get_position(axis)
        return self.move_to(current_pos + n, axis)

    def get_position(self, axis=FocuserAxis.Z):
        return self.status["FocusPos"]

    def move_to(self, position, axis=FocuserAxis.Z):
        limits = self.get_range(axis)
        if position < limits[0] or position > limits[1]:
            raise InvalidFocusPositionException(
                f"Position {position} out of range {limits} for axis {axis}"
            )
        print(f"Moving focuser to position {position}")
        return self.tcs.set_focus(position)

    def get_range(self, axis=FocuserAxis.Z):
        return 20000, 28000

    # def get_temperature(self):
    # def get_metadata(self, request):
