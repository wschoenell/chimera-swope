from chimera.instruments.camera import CameraBase
from chimera.instruments.filterwheel import FilterWheelBase
from henrietta.swope_ccd import SwopeCCD
from chimera.interfaces.camera import ReadoutMode
from chimera.interfaces.camera import CameraStatus
from chimera.controllers.imageserver.imagerequest import ImageRequest
from chimera_swope.instruments.util import concatenate_quad_arrays
from astropy.io import fits
import datetime as dt
import time
import os


class SwopeCamera(CameraBase, FilterWheelBase):

    __config__ = {
        "swope_ccd_host": "127.0.0.1",
        "swope_ccd_port": 51911,
        "fits_links": ",".join(
            [os.path.expanduser(f"~/ccdc{f}.fits") for f in (1, 2, 3, 4)]
        ),
        "ccd_width": 2056 * 2,
        "ccd_height": 2048 * 2,
        "pixel_size_x": 15.0,
        "pixel_size_y": 15.0,
    }

    def __init__(self):
        CameraBase.__init__(self)

        # Define supported ADCs and binnings
        self._my_adc = 1 << 2
        self._my_readout_mode = 1 << 3

        self._adcs = {"12 bits": self._my_adc}

        self._binnings = {"1x1": self._my_readout_mode}

        self._binning_factors = {"1x1": 1}

        readout_mode = ReadoutMode()
        readout_mode.mode = 0
        readout_mode.gain = 1.0
        readout_mode.width = 1024
        readout_mode.height = 1024
        readout_mode.pixel_width = 9.0
        readout_mode.pixel_height = 9.0

        self._readout_modes = {self._my_readout_mode: readout_mode}
        ###

        self.swope_ccd: SwopeCCD = SwopeCCD(
            host=self["swope_ccd_host"], port=self["swope_ccd_port"]
        )
        self.swope_ccd.open()
        self.__last_frame_start = 0

        self._links = [link.strip() for link in self["fits_links"].split(",")]

    def get_binnings(self):
        return self._binnings

    def get_filter(self):
        return self.swope_ccd.get_wheels()["filter"]

    def get_readout_modes(self):
        return self._readout_modes

    def set_filter(self, filter_name: str):
        self.swope_ccd.move_filter(filter_name)

    def _expose(self, image_request: ImageRequest):
        self.expose_begin(image_request)

        status = CameraStatus.OK

        assert self.swope_ccd.set_exposure_type(image_request["type"])
        assert (
            abs(
                self.swope_ccd.exposure_time(image_request["exptime"])
                - image_request["exptime"]
            )
            < 1e-6
        )
        self.__last_frame_start = dt.datetime.now(dt.UTC)
        assert self.swope_ccd.start_exposure()
        t0 = time.time()
        readout_started = False
        while self.swope_ccd.is_exposing:
            if time.time() - t0 > image_request["exptime"] and not readout_started:
                # exposure complete, start readout - approximate
                readout_started = True
                self.readout_begin(image_request)
            time.sleep(0.1)

        self.expose_complete(image_request, status)

    def _readout(self, image_request: ImageRequest):
        self.readout_begin(image_request)

        array_4, header_4 = fits.getdata(
            os.path.expanduser(self._links[0]), header=True
        )
        array_3, header_3 = fits.getdata(
            os.path.expanduser(self._links[1]), header=True
        )
        array_2, header_2 = fits.getdata(
            os.path.expanduser(self._links[2]), header=True
        )
        array_1, header = fits.getdata(os.path.expanduser(self._links[3]), header=True)

        pix = concatenate_quad_arrays(
            array_4, array_3, array_2, array_1, header=header, trim_data=True
        )

        # remove unwanted keywords from header_1 to save in final FITS
        for kw in [
            "BIASSEC",
            "DATASEC",
            "TRIMSEC",
            "NOVERSCN",
            "NBIASLNS",
            "FILENAME",
            "CHOFFX",
            "CHOFFY",
            "OPAMP",
            "ENOISE",
            "NAXIS",
            "NAXIS1",
            "NAXIS2",
            "EXTEND",
        ]:
            header.pop(kw, None)
            # fixme: ENOISE removed above to match other headers
            # SCALE   =                0.435         / arcsec/pixel
            # EGAIN   =                1.040         / electrons/DU
            # ENOISE  =                3.100         / electrons/read

        for c in header.cards:
            if c not in image_request.headers:
                image_request.headers.append(tuple(c))

        image = self._save_image(
            image_request,
            pix,
            extras={
                "frame_start_time": self.__last_frame_start,
                "frame_temperature": header.get("TEMPCCD", None),
                # "binning_factor": self._binning_factors[binning],
            },
        )

        # [ABORT POINT]
        if self.abort.is_set():
            self.readout_complete(None, CameraStatus.ABORTED)
            return None

        self.readout_complete(image.url(), CameraStatus.OK)
        return image

    def get_physical_size(self):
        return self["ccd_width"], self["ccd_height"]

    def get_pixel_size(self):
        return self["pixel_size_x"], self["pixel_size_y"]
