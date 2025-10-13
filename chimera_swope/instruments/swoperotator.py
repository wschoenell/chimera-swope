from chimera.instruments.rotator import RotatorBase

class SwopeRotator(RotatorBase):
    def __init__(self):
        RotatorBase.__init__(self)

    def __start__(self):
        pass

    def get_position(self):
        return 0.0
    
    def move_to(self, angle):
        self.moving_started()
        self.moving_complete()
        return True
    
    def move_by(self, offset):
        self.moving_started()
        self.moving_complete()
        return True
    
    

