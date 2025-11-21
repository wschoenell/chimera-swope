# This is an example of an simple instrument.

from chimera.core.chimeraobject import ChimeraObject
from astropy.samp import SAMPIntegratedClient
from astropy.samp import SAMPHubError
from chimera.interfaces.camera import CameraStatus
from chimera.core.event import event

# todo: move to another class
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from photutils.detection import DAOStarFinder
import numpy as np

# todo: move to another class


class Ds9AutoDisplay(ChimeraObject):
    __config__ = {"camera": "127.0.0.1:6379/FakeCamera/fake"}
    # __config__ = {"camera": "/Camera/0"}

    def __init__(self):
        ChimeraObject.__init__(self)
        self.ds9_client = SAMPIntegratedClient()
        self.image_fname = None

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
            self.log.error(
                "Failed to connect to DS9. Is DS9 running with SAMP enabled?"
            )
            return False

    def __start__(self):

        def ds9_clbk(image, status):
            if status != CameraStatus.OK:
                return
            if not self.connect_ds9():
                return

            self.log.info("Sending image to DS9")
            self.image_fname = image.filename
            self.ds9_client.ecall_and_wait("c1", "ds9.set", "10", cmd="frame clear")
            self.ds9_client.ecall_and_wait(
                "c1", "ds9.set", "10", cmd=f"url file://{self.image_fname}"
            )
            self.ds9_client.ecall_and_wait("c1", "ds9.set", "10", cmd="zscale")

        cam = self.get_proxy(self["camera"])
        cam.ping()
        cam.readout_complete += ds9_clbk

    def get_pa(self, detect_stars=True):

        if not self.connect_ds9():
            self.log.error("Cannot get PA: not connected to DS9")
            return
        if self.image_fname is None and detect_stars:
            self.log.info("No image to process")
            return

        pts = []
        for _ in range(2):
            coord = self.ds9_client.ecall_and_wait("c1", "ds9.get", "0", cmd="imexam")
            pts.append([float(f) for f in coord["samp.result"]["value"].split()])

        if not detect_stars:
            (x1, y1), (x2, y2) = pts
            print(f"Points: {pts}")
            self.update_pa(np.atan2(y2 - y1, x2 - x1) * 180 / np.pi)
            return

        data = fits.getdata(self.image_fname)
        _, median, std = sigma_clipped_stats(data, sigma=3.0)
        daofind = DAOStarFinder(fwhm=3.0, threshold=5.0 * std)
        sources = daofind(data - median)

        if sources is None:
            self.log.info("No stars found")
            return

        self.log.info(f"Found {len(sources)} stars")

        for i, pt in enumerate(pts):
            idx = np.argmin(
                (pt[0] - sources["xcentroid"]) ** 2
                + (pt[1] - sources["ycentroid"]) ** 2
            )
            x, y = sources["xcentroid"][idx], sources["ycentroid"][idx]
            self.ds9_client.ecall_and_wait(
                "c1",
                "ds9.set",
                "10",
                cmd=f"region command {{point {x} {y} # color=red}}",
            )
            print(f"Found star at {x},{y}")
            pts[i] = [x, y]

        (x1, y1), (x2, y2) = pts
        self.update_pa(np.atan2(y2 - y1, x2 - x1) * 180 / np.pi)

    def calculate_offsets(self, ra_east, dec_east, ra_west, dec_west):
        # 1 - run astrometry.net on the image to get WCS solution
        # self.image_fname
        # 2 - convert ra/dec to x/y using WCS
        # 3 - calculate PA from x/y
        # 4 - calculate center offset
        pass

    @event
    def update_pa(self, pa):
        pass
