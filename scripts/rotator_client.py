import asyncio
import pty
import time
import urllib
from nicegui import run, ui
from nicegui.events import ValueChangeEventArguments
from nicegui.events import KeyEventArguments
from nicegui.events import UploadEventArguments
from chimera.core.proxy import Proxy
from chimera.interfaces.telescope import Telescope
from chimera.util.coord import Coord


def get_dss_image(ra, dec, ftype="gif", ccd_height=3 * 60, ccd_width=30 * 60):
    url = "http://stdatu.stsci.edu/cgi-bin/dss_search?"
    query_args = {
        "r": ra * 15,  # convert RA from hours to degrees
        "d": dec,
        "f": ftype,
        "e": "j2000",
        "c": "gz",
        "fov": "NONE",
    }

    # use POSS2-Red surbey ( -90 < d < -20 ) if below -25 deg declination, else use POSS1-Red (-30 < d < +90)
    # http://www-gsss.stsci.edu/SkySurveys/Surveys.htm
    if dec < -25:
        query_args["v"] = "poss2ukstu_red"
        query_args["h"] = (
            ccd_height / 59.5
        )  # ~1"/pix (~60 pix/arcmin) is the plate scale of DSS POSS2-Red
        query_args["w"] = ccd_width / 59.5
    else:
        query_args["v"] = "poss1_red"
        query_args["h"] = (
            ccd_height / 35.3
        )  # 1.7"/pix (35.3 pix/arcmin) is the plate scale of DSS POSS1-Red
        query_args["w"] = ccd_width / 35.3

    url += urllib.parse.urlencode(query_args)

    return url


class ToggleButton(ui.button):

    def __init__(self, *args, keyboard=None, **kwargs) -> None:
        self._state = False
        self.keyboard = keyboard
        super().__init__(*args, **kwargs)
        self.on("click", self.toggle)

    def toggle(self) -> None:
        """Toggle the button state."""
        self._state = not self._state
        self.update()

    def update(self) -> None:
        # with self.props.suspend_updates():
        if self.keyboard:
            self.keyboard.active = self._state
        self.props(f'color={"green" if self._state else "red"}')
        super().update()


class SwopeUI:
    current_pa: str = "0.0º"
    offset_pa: float = 0.0
    current_ra: float = 0.0
    current_dec: float = 0.0
    current_ra_str: str = 0.0
    current_dec_str: str = 0.0
    current_focus: float = 0.0
    target_focus: float = 0.0
    current_rotator: float = 0.0
    last_update: float = 0.0

    def __init__(self):
        self.display_proxy = Proxy("127.0.0.1:6379/Ds9AutoDisplay/display")
        self.display_proxy.update_pa += self.update_pa_offset
        self.rotator_proxy = Proxy("127.0.0.1:6379/FakeRotator/rotator")
        self.rotator_proxy.slew_complete += self.update_rotator
        self.telescope_proxy: Telescope = Proxy("127.0.0.1:6379/FakeTelescope/swope")
        self.focuser_proxy = Proxy("127.0.0.1:6379/SwopeFocuser/focus")
        self.focus_min, self.focus_max = self.focuser_proxy.get_range()

        self.update_rotator()
        self.update_telescope_coordinates()
        self.offset_pa = 0.0
        self.draw()

        ui.timer(2, self.update_proxy_data)

    def handle_key(self, e: KeyEventArguments):
        if e.action.keydown:
            if e.key.arrow_left:
                ui.notify("Moving West")
                self.offset_west_btn()
            elif e.key.arrow_right:
                ui.notify("Moving East")
                self.offset_east_btn()
            elif e.key.arrow_up:
                ui.notify("Moving North")
                self.offset_north_btn()
            elif e.key.arrow_down:
                ui.notify("Moving South")
                self.offset_south_btn()

    # data update methods
    def update_proxy_data(self):
        if time.time() - self.last_update < 1.0:
            return
        self.last_update = time.time()
        self.update_telescope_coordinates()
        self.update_focus()
        self.update_rotator()

    def update_telescope_coordinates(self):
        self.current_ra, self.current_dec = self.telescope_proxy.get_position_ra_dec()
        self.current_ra_str = Coord.from_d(float(self.current_ra)).strfcoord()
        self.current_dec_str = Coord.from_d(float(self.current_dec)).strfcoord()

    def update_focus(self):
        self.current_focus = self.focuser_proxy.get_position()

    def update_rotator(self):
        self.current_rotator = self.rotator_proxy.get_position()
        self.current_pa = f"{self.current_rotator:.3f}º"

    ###

    def show(self, event: ValueChangeEventArguments):
        name = type(event.sender).__name__
        ui.notify(f"{name}: {event.value}")
        pass

    def update_pa_offset(self, pa):
        print("Updating PA offset:", pa)
        self.offset_pa = pa

    def set_focus_btn(self):
        try:
            print(f"Setting focus to {self.target_focus}")
            self.focuser_proxy.move_to(int(self.target_focus))
        except Exception as e:
            ui.notify(f"Error setting focus: {e}")
        self.update_focus()

    def move_btn(self):
        ui.notify(f"Offsetting rotator by {self.offset_pa:.3f}º")
        self.rotator_proxy.move_by(self.offset_pa)
        self.offset_pa = 0.0
        self.update_pa_offset(self.offset_pa)
        self.update_rotator()

    def set_pa_offset(self, event: ValueChangeEventArguments):
        self.offset_pa = float(event.value)

    def get_display_proxy_pa(self, detect_stars=True):
        try:
            self.display_proxy.get_pa(detect_stars=detect_stars)
        except Exception as e:
            ui.notify(f"Error getting PA from DS9: {e}")
            return

        # return self.display_proxy.get_pa(detect_stars=detect_stars)

    async def grab_stars_btn(self):
        ui.notify("Grabbing PA from DS9")
        await run.cpu_bound(self.get_display_proxy_pa, detect_stars=True)
        ui.notify("Finished grabbing PA from DS9")

    async def grab_pixels_btn(self):
        ui.notify("Grabbing PA from DS9 (2 points)")
        await run.cpu_bound(self.get_display_proxy_pa, detect_stars=False)
        ui.notify("Finished grabbing PA from DS9 (2 points)")

    def offset_north_btn(self):
        self.telescope_proxy.move_north(1)
        self.update_telescope_coordinates()

    def offset_south_btn(self):
        self.telescope_proxy.move_south(1)
        self.update_telescope_coordinates()

    def offset_east_btn(self):
        self.telescope_proxy.move_east(1)
        self.update_telescope_coordinates()

    def offset_west_btn(self):
        self.telescope_proxy.move_west(1)
        self.update_telescope_coordinates()

    def update_chart_btn(self):
        self.update_telescope_coordinates()
        self.dss_image = get_dss_image(self.current_ra, self.current_dec)

    async def run_subprocess(self, arg="--help"):
        # button.disable()
        self.terminal.clear()
        args = arg.split()
        process = await asyncio.create_subprocess_exec(
            # 'python3', '-u', '-c',
            # (
            #     'import time\n'
            #     'for i in range(5):\n'
            #     '    print(f"Step {i+1}/5: Processing...")\n'
            #     '    time.sleep(0.5)\n'
            #     'print("\\x1b[32m✓ All steps completed!\\x1b[0m")'
            # ),
            "chimera-sched",
            *args,
            "--config",
            "/Users/william/workspace/chimera/chimera-swope/etc/chimera.config",  # fixme
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def write_to_terminal(stream: asyncio.StreamReader) -> None:
            while chunk := await stream.read(128):
                self.terminal.write(chunk)

        await asyncio.gather(
            write_to_terminal(process.stdout),
            write_to_terminal(process.stderr),
            process.wait(),
        )
        # button.enable()

    async def upload_sched_file(self, e: UploadEventArguments):
        ui.notify(f"Uploaded {e.file.name}")
        await e.file.save(f"/tmp/sched.yaml")  # fixme

    def draw(self):
        self.update_proxy_data()
        keyboard = ui.keyboard(on_key=self.handle_key)

        with ui.tabs().classes("w-full") as tabs:
            ui.tab("Telescope")
            ui.tab("Rotator")
            ui.tab("Henrietta")
            ui.tab("Scheduler")
            ui.tab("Dome")

        with ui.tab_panels(tabs, value="Telescope", animated=False).classes("w-full"):
            with ui.tab_panel("Telescope"):

                with ui.grid(columns=2):
                    with ui.column():
                        ui.input("Telescope RA:").bind_value(
                            self, "current_ra_str"
                        ).props("readonly")
                        ui.input("Telescope Dec:").bind_value(
                            self, "current_dec_str"
                        ).props("readonly")
                    with ui.column():
                        with ui.grid(columns=3):
                            ui.label()
                            ui.button("N", on_click=self.offset_north_btn)
                            ui.label()
                            ui.button("E", on_click=self.offset_east_btn)
                            but = ToggleButton("K", keyboard=keyboard)
                            print("Keyboard active:", keyboard.active)
                            ui.button("W", on_click=self.offset_west_btn)
                            ui.label()
                            ui.button("S", on_click=self.offset_south_btn)
                with ui.row(align_items="center"):
                    self.update_focus()
                    ui.input(
                        "Focus:",
                        validation={
                            "Out of range": lambda v: self.focus_min
                            <= float(v)
                            <= self.focus_max
                        },
                        on_change=lambda e: setattr(self, "target_focus", e.value),
                    ).bind_value(self, "current_focus")
                    ui.button("Set", on_click=self.set_focus_btn)
                    self.update_telescope_coordinates()
                    self.dss_image = get_dss_image(self.current_ra, self.current_dec)
                    print("DSS Image file:", self.dss_image)
                ui.separator()
                # ui.button("Update Chart", on_click=self.update_chart_btn)
            with ui.tab_panel("Rotator"):
                with ui.row():
                    ui.input("Current PA:").bind_value(self, "current_pa").props(
                        "readonly"
                    )
                    ui.input("Offset PA:", on_change=self.set_pa_offset).bind_value(
                        self, "offset_pa"
                    )
                    ui.button("Grab Stars", on_click=self.grab_stars_btn)
                    ui.button("Grab Pixels", on_click=self.grab_pixels_btn)
                with ui.row():
                    ui.button("Move", on_click=self.move_btn)
            # with ui.tab_panel("Henrietta"):
            #                 ui.html(
            #                 f"""

            #                 """)
            #                 ui.add_body_html("""
            # <script src='https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js' charset='utf-8'></script>

            # <script type="text/javascript">
            # var aladin;
            # A.init.then(() => {
            #     aladin = A.aladin('#aladin-lite-div', {fov:1, target: 'M81'});
            # });
            # </script>
            # """)
            #                 ui.html("""
            # <div id="aladin-lite-div" style="width: 800px; height: 600px;"></div>
            # """)

            with ui.tab_panel("Dome"):
                ui.label("Slit:")
                ui.label("Azimuth:")
                ui.label("Wind screen:")

            with ui.tab_panel("Scheduler"):
                with ui.grid(columns=2):
                    ui.upload(
                        on_upload=self.upload_sched_file, auto_upload=True, max_files=1
                    )  # .classes('max-w-full').classes('no-wrap')
                    with ui.button_group():
                        ui.button(
                            "Load file",
                            on_click=lambda: self.run_subprocess(
                                "--new -f /tmp/sched.yaml"
                            ),
                            color="blue",
                        )
                        ui.button(
                            "Start",
                            on_click=lambda: self.run_subprocess("--start"),
                            color="green",
                        )
                        ui.button(
                            "Stop",
                            on_click=lambda: self.run_subprocess("--stop"),
                            color="red",
                        )
                        ui.button(
                            "Monitor",
                            on_click=lambda: self.run_subprocess("--monitor"),
                            color="blue",
                        )

                # ui.button("Stop")
                # self.terminal = ui.xterm({'cols': 120, 'rows': 40, 'convertEol': True})
                # self.terminal.on_bell(lambda: ui.notify('🔔 scheduler 🔔'))


root = SwopeUI()

ui.run(
    root, host="0.0.0.0", native=True, title="Henrietta Swope", dark=True, reload=True
)
