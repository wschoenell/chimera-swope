import time

from chimera.instruments.telescope import TelescopeBase
from chimera.interfaces.telescope import TelescopeStatus

from chimera_swope.instruments.swopebase import SwopeBase


class SwopeTelescope(TelescopeBase, SwopeBase):
    __config__ = {
        "tcs_host": "127.0.0.1",
        "model": "Henrietta Swope Telescope",
        "optics": ["Ritchey-Chretien f/7"],
        "mount": "Boller and Chivens",
        "aperture": 1000.0,  # mm
        "focal_length": 7000.0,  # mm unit (ex., 0.5 for a half length focal reducer)
        "focal_reduction": 1.0,
    }

    def __init__(self):
        TelescopeBase.__init__(self)
        SwopeBase.__init__(self)

    def __start__(self):
        SwopeBase.__start__(self)

    def get_alt(self):
        return self.status["Alt"]

    def get_az(self):
        return self.status["Azi"]

    def get_ra(self):
        return self.status["RA_ICRS"] / 15.0

    def get_dec(self):
        return self.status["Dec_ICRS"]

    def get_position_ra_dec(self):
        return self.get_ra(), self.get_dec()

    def get_position_alt_az(self):
        return self.get_alt(), self.get_az()

    def is_tracking(self):
        return self.status["Tracking"]

    def is_slewing(self):
        return self.status["Slewing"]

    def start_tracking(self):
        ret = self.tcs.set_track(True)
        if ret:
            self.tracking_started()
        return ret

    def stop_tracking(self):
        ret = self.tcs.set_track(False)
        if ret:
            self.tracking_stopped()
        return ret

    def set_offset(self, ha: float, dec: float):
        self.slew_begin(self.get_ra() + ha, self.get_dec() + dec, 2000)
        self.tcs.set_offset(ha, dec)
        self.get_status(force=True)
        while self.is_slewing():
            time.sleep(0.01)
        self.slew_complete(self.get_ra(), self.get_dec(), TelescopeStatus.OK)

    def move_east(self, offset, rate=None):
        self.set_offset(offset, 0)

    def move_west(self, offset, rate=None):
        self.set_offset(-offset, 0)

    def move_north(self, offset, rate=None):
        self.set_offset(0, offset)

    def move_south(self, offset, rate=None):
        self.set_offset(0, -offset)

    def slew_to_ra_dec(self, ra: float, dec: float, epoch=None):
        self.slew_begin(ra, dec, epoch)
        self.tcs.set_nextobj(15 * ra, dec, 2000.0)
        time.sleep(2)  # wait for TCS to process
        self.tcs.set_slew()
        time.sleep(1)  # wait for slew to start
        self.get_status(force=True)
        while self.is_slewing():
            time.sleep(0.01)
        self.slew_complete(self.get_ra(), self.get_dec(), TelescopeStatus.OK)

    def _get_site(self):
        # FIXME: create the proxy directly and cache it
        return self.get_proxy("/Site/0")

    def slew_to_alt_az(self, alt: float, az: float):
        self._validate_alt_az(alt, az)
        ra, dec = self._get_site().alt_az_to_ra_dec(alt, az)
        self.slew_to_ra_dec(ra, dec, epoch=2000)
        self.stop_tracking()

    def abort_slew(self):
        self.tcs.set_slew_stop()

    # TD def get_target_ra_dec(self):
    # TD def get_target_alt_az(self):
    # TD def sync_ra_dec(self, ra, dec, epoch=2000): -> CSET?
    #           sync_complete(self, ra: float, dec: float)

    def sync_ra_dec(self, ra: float, dec: float, epoch=2000):
        return self.tcs.set_cset()

    def park(self):
        self.tcs.set_poweron(False)
        self.park_complete()

    def unpark(self):
        self.tcs.set_poweron(True)
        self.get_status(force=True)
        while not self.is_parked():
            time.sleep(0.1)

    def is_parked(self):
        return self.status["Init_done"]

    # N def open_cover(self):
    # N def close_cover(self):
    # N def is_cover_open(self):
    # N def set_pier_side(self, side):
    # N def get_pier_side(self):
