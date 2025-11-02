import os
from chimera.instruments.camera import CameraBase
from chimera.instruments.filterwheel import FilterWheelBase
from chimera.core.chimeraobject import ChimeraObject
from henrietta.henrietta import Henrietta
from chimera.core.proxy import Proxy
from chimera.controllers.imageserver.imagerequest import ImageRequest
from chimera.interfaces.camera import CameraStatus
from chimera.interfaces.camera import CameraFeature
from astropy.io import fits
import datetime
from chimera.util.image import Image
from chimera.controllers.imageserver.util import get_image_server
from chimera.core.lock import lock


class HenriettaBase(Henrietta, ChimeraObject):
    __config__ = {"henrietta_host": "127.0.0.1", "henrietta_port": 52801}

    def __init__(self):
        ChimeraObject.__init__(self)
        Henrietta.__init__(
            self, ip_address=self["henrietta_host"], port=self["henrietta_port"]
        )
        self.open()


class HenriettaWheel(FilterWheelBase):

    __config__ = {
        "henrietta": "127.0.0.1:6379/HenriettaBase/henrietta",
        "filters_gui": "",
    }

    def __init__(self):
        FilterWheelBase.__init__(self)
        self.henrietta: Henrietta = Proxy(self["henrietta"])

        # Map class names to their corresponding wheel names and methods
        wheel_mapping = {
            "HenriettaSlitWheel": {"wheel_name": "slit", "method": "move_slit"},
            "HenriettaGrismWheel": {"wheel_name": "grism", "method": "move_grism"},
            "HenriettaDiffuserWheel": {
                "wheel_name": "diffuser",
                "method": "move_diffuser",
            },
            "HenriettaFilterWheel": {"wheel_name": "filter", "method": "move_filter"},
            "HenriettaSlideWheel": {"wheel_name": "slide", "method": "move_slide"},
        }

        class_name = self.__class__.__name__
        if class_name in wheel_mapping:
            self.wheel_name = wheel_mapping[class_name]["wheel_name"]
            self.move_method = getattr(
                self.henrietta, wheel_mapping[class_name]["method"]
            )
        else:
            raise ValueError(f"Unknown wheel class: {class_name}")

    def __start__(self):
        if self["filters_gui"] == "":
            self["filters_gui"] = self["filters"]
        return super().__start__()

    def set_filter(self, filter):
        fn = self["filters"].upper().split().index(filter.upper())
        self.move_method(fn)
        return True

    def get_filter(self):
        wheels_data = self.henrietta.get_wheels()
        current_wheel_value = wheels_data[self.wheel_name]
        fn = self["filters_gui"].upper().split().index(current_wheel_value.upper())
        return self["filters"].split()[fn]


class HenriettaSlitWheel(HenriettaWheel):
    pass


class HenriettaGrismWheel(HenriettaWheel):
    pass


class HenriettaDiffuserWheel(HenriettaWheel):
    pass


class HenriettaFilterWheel(HenriettaWheel):
    pass


class HenriettaSlideWheel(HenriettaWheel):
    pass


class HenriettaCamera(CameraBase):

    __config__ = {
        "henrietta": "127.0.0.1:6379/HenriettaBase/henrietta",
        "fits_link": os.path.expanduser("~/hen.fits"),
        "ccd_width": 2048,
        "ccd_height": 2048,
        "pixel_size_x": 18.0,
        "pixel_size_y": 18.0,
    }

    def __init__(self):
        CameraBase.__init__(self)
        self.henrietta: Henrietta = Proxy(self["henrietta"])

        # TODO: move this out
        from chimera.interfaces.camera import ReadoutMode

        self._my_readout_mode = 1 << 3
        self._binnings = {"1x1": self._my_readout_mode}
        readout_mode = ReadoutMode()
        readout_mode.mode = 0
        readout_mode.gain = 1.0
        readout_mode.width = 2048
        readout_mode.height = 2048
        readout_mode.pixel_width = 9.0
        readout_mode.pixel_height = 9.0
        self._my_ccd = 1 << 1
        self._readout_modes = {self._my_ccd: {self._my_readout_mode: readout_mode}}

        self.supported_features = {CameraFeature.TEMPERATURE_CONTROL: True}

    def get_current_ccd(self):
        return self._my_ccd

    def get_readout_modes(self):
        return self._readout_modes

    def get_binnings(self):
        return self._binnings

    def is_cooling(self):
        return False

    def get_physical_size(self):
        return (self["ccd_width"], self["ccd_height"])

    def get_pixel_size(self):
        return (self["pixel_size_x"], self["pixel_size_y"])

    def get_temperature(self):
        return 0.0

    def _save_image(self, image_request, image_data, extras=None):

        if extras is not None:
            self.extra_header_info.update(extras)

        image_request.headers += self.get_metadata(image_request)
        img = Image.create(image_data, image_request)

        # register image on ImageServer
        server = get_image_server(self.get_manager())
        proxy = server.register(img)

        # and finally compress the image if asked
        if image_request["compress_format"].lower() != "no":
            img.compress(format=image_request["compress_format"], multiprocess=True)

        return proxy

    def _readout(self, image_request: ImageRequest):
        self.readout_begin(image_request)
        binning = image_request["binning"]

        out_fname = os.path.expanduser(self["fits_link"])

        pix, header = fits.getdata(out_fname, header=True)
        # header.update({
        #         "frame_start_time": self.__last_frame_start,
        #         "frame_temperature": self.get_temperature(),
        #         # "binning_factor": self._binning_factors[binning],
        #     })
        proxy = self._save_image(image_request, pix, extras=header)

        # [ABORT POINT]
        if self.abort.is_set():
            self.readout_complete(None, CameraStatus.ABORTED)
            return None

        self.readout_complete(proxy, CameraStatus.OK)
        return proxy

    def _expose(self, request: ImageRequest):
        self.__last_frame_start = datetime.datetime.now(datetime.timezone.utc)
        status = CameraStatus.OK
        print("Request:", request)
        self.henrietta.expose(request["exptime"])
        request["exptime"] = self.henrietta.exposure_time()
        print("Output saved to: ", os.readlink(self["fits_link"]))
        self.expose_complete(request, status)

    def is_exposing(self):
        return self.henrietta.is_exposing()

    def get_metadata(self, request):
        # Check first if there is metadata from an metadata override method.
        md = self.get_metadata_override(request)
        if md is not None:
            return md
        # If not, just go on with the instrument's default metadata.
        md = [
            ("EXPTIME", float(request["exptime"]), "exposure time in seconds"),
            ("IMAGETYP", request["type"].strip(), "Image type"),
            ("SHUTTER", str(request["shutter"]), "Requested shutter state"),
            ("INSTRUME", str(self["camera_model"]), "Name of instrument"),
            ("CCD", str(self["ccd_model"]), "CCD Model"),
            ("CCD_DIMX", self.get_physical_size()[0], "CCD X Dimension Size"),
            ("CCD_DIMY", self.get_physical_size()[1], "CCD Y Dimension Size"),
            ("CCDPXSZX", self.get_pixel_size()[0], "CCD X Pixel Size [micrometer]"),
            ("CCDPXSZY", self.get_pixel_size()[1], "CCD Y Pixel Size [micrometer]"),
        ]

        # if request["window"] is not None:
        #     md += [("DETSEC", request["window"], "Detector coodinates of the image")]

        # if "frame_temperature" in list(self.extra_header_info.keys()):
        #     md += [
        #         (
        #             "CCD-TEMP",
        #             self.extra_header_info["frame_temperature"],
        #             "CCD Temperature at Exposure Start [deg. C]",
        #         )
        #     ]

        # if "frame_start_time" in list(self.extra_header_info.keys()):
        #     md += [
        #         (
        #             "DATE-OBS",
        #             ImageUtil.format_date(
        #                 self.extra_header_info.get("frame_start_time")
        #             ),
        #             "Date exposure started",
        #         )
        #     ]

        # mode, binning, top, left, width, height = self._get_readout_mode_info(
        #     request["binning"], request["window"]
        # )
        # # Binning keyword: http://iraf.noao.edu/projects/ccdmosaic/imagedef/mosaic/MosaicV1.html
        # #    CCD on-chip summing given as two or four integer numbers.  These define
        # # the summing of CCD pixels in the amplifier readout order.  The first
        # # two numbers give the number of pixels summed in the serial and parallel
        # # directions respectively.  If the first pixel read out consists of fewer
        # # unbinned pixels along either direction the next two numbers give the
        # # number of pixels summed for the first serial and parallel pixels.  From
        # # this it is implicit how many pixels are summed for the last pixels
        # # given the size of the CCD section (CCDSEC).  It is highly recommended
        # # that controllers read out all pixels with the same summing in which
        # # case the size of the CCD section will be the summing factors times the
        # # size of the data section.
        # md += [("CCDSUM", binning.replace("x", " "), "CCD on-chip summing")]

        # focal_length = self["telescope_focal_length"]
        # if (
        #     focal_length is not None
        # ):  # If there is no telescope_focal_length defined, don't store WCS
        #     bin_factor = self.extra_header_info.get("binning_factor", 1.0)
        #     pix_w, pix_h = self.get_pixel_size()
        #     focal_length = self["telescope_focal_length"]

        #     scale_x = bin_factor * (((180 / pi) / focal_length) * (pix_w * 0.001))
        #     scale_y = bin_factor * (((180 / pi) / focal_length) * (pix_h * 0.001))

        #     full_width, full_height = self.get_physical_size()
        #     CRPIX1 = ((int(full_width / 2.0)) - left) - 1
        #     CRPIX2 = ((int(full_height / 2.0)) - top) - 1

        #     # Adding WCS coordinates according to FITS standard.
        #     # Quick sheet: http://www.astro.iag.usp.br/~moser/notes/GAi_FITSimgs.html
        #     # http://adsabs.harvard.edu/abs/2002A%26A...395.1061G
        #     # http://adsabs.harvard.edu/abs/2002A%26A...395.1077C
        #     md += [
        #         ("CRPIX1", CRPIX1, "coordinate system reference pixel"),
        #         ("CRPIX2", CRPIX2, "coordinate system reference pixel"),
        #         (
        #             "CD1_1",
        #             scale_x * cos(self["rotation"] * pi / 180.0),
        #             "transformation matrix element (1,1)",
        #         ),
        #         (
        #             "CD1_2",
        #             -scale_y * sin(self["rotation"] * pi / 180.0),
        #             "transformation matrix element (1,2)",
        #         ),
        #         (
        #             "CD2_1",
        #             scale_x * sin(self["rotation"] * pi / 180.0),
        #             "transformation matrix element (2,1)",
        #         ),
        #         (
        #             "CD2_2",
        #             scale_y * cos(self["rotation"] * pi / 180.0),
        #             "transformation matrix element (2,2)",
        #         ),
        #     ]

        return md
