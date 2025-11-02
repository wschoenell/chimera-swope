from chimera.instruments.rotator import RotatorBase


class SwopeRotator(RotatorBase):
    def __init__(self):
        RotatorBase.__init__(self)
        self._pos = 0.0

    def __start__(self):
        pass

    def get_position(self):
        return self._pos

    def move_to(self, angle):
        self.moving_started()
        self._pos = angle
        self.moving_complete()

    def move_by(self, offset):
        self.moving_started()
        self._pos += offset  # todo: wrap around 360, make sure within limits, use actual hardware
        self.moving_complete()
