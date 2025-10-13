# This is an example of an simple instrument.

from chimera.core.chimeraobject import ChimeraObject
from chimera.core.proxy import Proxy
from astropy.samp import SAMPIntegratedClient
from astropy.samp import SAMPHubError
from chimera.interfaces.camera import CameraStatus
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from photutils.detection import DAOStarFinder
import numpy as np


class Ds9AcquisitionDisplay(ChimeraObject):
    __config__ = {"camera": "127.0.0.1:6379/FakeCamera/fake"}

    def __init__(self):
        ChimeraObject.__init__(self)
        self.ds9_client = SAMPIntegratedClient()

    def connect_ds9(self):
        # Try pinging DS9 first
        try:
            if self.ds9_client.client is not None and self.ds9_client.ping() == "OK":
                return True
        except ConnectionRefusedError:
            pass
        # Connect to DS9 via SAMP
        try:
            self.ds9_client.connect()
            self.log.info("Connected to DS9 via SAMP")
            return True
        except (ConnectionRefusedError, SAMPHubError):
            self.log.error("Failed to connect to DS9. Is DS9 running with SAMP enabled?")
            return False

    def __start__(self):

        def ds99_clbk(image, status):
            print('ds9_clbk called')
            if status != CameraStatus.OK:
                return
            self.last_image_fname = image.filename

        cam = Proxy(self["camera"])
        cam.readout_complete += ds99_clbk

    # def do_something(self, arg):
    #     self.log.warning("Hi, I'm doing something.")
    #     self.log.warning("My arg=%s" % arg)
    #     self.log.warning("My param1=%s" % self["param1"])
