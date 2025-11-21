import asyncio
import copy
import random
import time
import urllib
from nicegui import Event, run, ui, app
from nicegui.events import ValueChangeEventArguments
from nicegui.events import KeyEventArguments
from nicegui.events import UploadEventArguments
from chimera.core.proxy import Proxy
from chimera.interfaces.telescope import Telescope
from chimera.util.coord import Coord
from chimera.core.bus import Bus

from concurrent.futures.thread import ThreadPoolExecutor

print("Starting rotator client...")


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


class UiData:
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

    tweet = Event[str]()

    def __init__(self):
        global bus
        # self.display_proxy = Proxy("tcp://127.0.0.1:6379/Ds9AutoDisplay/display", bus)
        # self.display_proxy.update_pa += self.update_pa_offset
        self.rotator_proxy = Proxy("tcp://127.0.0.1:6379/FakeRotator/rotator", bus)
        self.rotator_proxy.slew_complete += self.update_rotator
        self.telescope_proxy: Telescope = Proxy(
            "tcp://127.0.0.1:6379/FakeTelescope/swope", bus
        )
        self.telescope_proxy.ping()
        self.telescope_proxy.slew_complete += self.tel_slew_complete
        self.focuser_proxy = Proxy("tcp://127.0.0.1:6379/SwopeFocuser/focus", bus)
        self.focuser_proxy = Proxy("tcp://127.0.0.1:6379/SwopeFocuser/focus", bus)
        self.focuser_proxy = Proxy("tcp://127.0.0.1:6379/SwopeFocuser/focus", bus)
        self.focuser_proxy.ping()
        self.focus_min, self.focus_max = self.focuser_proxy.get_range()
        print("Focuser range:", self.focus_min, self.focus_max)

        # self.operator_proxy = Proxy("tcp://127.0.0.1:6379/TelescopeOperator/operator", bus)
        # self.operator_proxy.notify += self.operator_request

        self.message = None

        self.offset_pa = 0.0
        app.timer(2, self.update_proxy_data)
        # app.add_static_files("/docs", "docs")  # for aladin

        self.aladin = None

        self.focus_min = 0
        self.focus_max = 1

    # # from CLI
    # def _start_system(self, options: optparse.Values):
    #     self.config = ChimeraConfig.from_file(options.config)
    #     random_port = random.randint(10000, 60000)
    #     self.bus = Bus(f"tcp://{self.config.host}:{random_port}")
    # # from CLI end

    # chimera callbacks
    def tel_slew_complete(self, ra=None, dec=None, status=None):
        print("Telescope slew complete callback")
        self.update_aladin(ra, dec)

    #

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

        # fixme: this should not be necessary: chimera bug
        if not isinstance(self.current_ra, float):
            self.current_ra = float(self.current_ra.to_d())
        if not isinstance(self.current_dec, float):
            self.current_dec = float(self.current_dec.to_d())
        # fixme end

        self.current_ra_str = Coord.from_d(float(self.current_ra)).strfcoord()
        self.current_dec_str = Coord.from_d(float(self.current_dec)).strfcoord()

    def update_focus(self):
        self.current_focus = 12000  # self.focuser_proxy.get_position()

    def update_rotator(self):
        self.current_rotator = self.rotator_proxy.get_position()
        self.current_pa = f"{self.current_rotator:.3f}º"

    def operator_request(self, type, msg):
        print(f"xxx Operator request: {type} -- {msg}")
        self.message = f"Operator request: {type} -- {msg}"
        self.tweet.emit(self.message)

    ###

    def show(self, event: ValueChangeEventArguments):
        name = type(event.sender).__name__
        ui.notify(f"{name}: {event.value}")

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

    @staticmethod
    def get_display_proxy_pa(detect_stars=True):
        try:
            display_proxy = Proxy("127.0.0.1:6379/Ds9AutoDisplay/display")
            print(display_proxy.get_pa(detect_stars=detect_stars))
        except Exception as e:
            ui.notify(f"Error getting PA from DS9: {e}")
            return

        # return self.display_proxy.get_pa(detect_stars=detect_stars)

    async def grab_stars_btn(self):
        ui.notify("Grabbing PA from DS9")
        print("Grabbing PA from DS9")
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

    def tweet_handler(self, message: str):
        self.audio.play()
        ui.notify(
            f'A Someone tweeted: "{message}"',
            close_button="Release",
            type="warning",
            spinner=True,
            timeout=0,
        )  # , on_close=self.release_operator)
        ui.notify(
            f'B Someone tweeted: "{message}"',
            close_button="Release",
            type="warning",
            spinner=True,
            timeout=0,
        )  # , on_close=self.release_operator)

    def release_operator(self):
        self.operator_proxy.release()

    def root(self):
        self.update_proxy_data()
        keyboard = ui.keyboard(on_key=self.handle_key)

        self.tweet.subscribe(self.tweet_handler)
        # ui.label().bind_text(self, "message")
        # ui.notify().bind_text(self, "message")

        with ui.tabs().classes("w-full") as tabs:
            ui.tab("Telescope")
            ui.tab("Rotator")
            ui.tab("Henrietta")
            ui.tab("Scheduler")
            ui.tab("Dome")
            ui.tab("Settings", label="", icon="settings")

        with ui.tab_panels(tabs, value="Telescope", animated=False).classes("w-full"):
            with ui.tab_panel("Telescope"):

                with ui.grid(columns=3):
                    with ui.column():
                        ui.input("Telescope RA:").bind_value(
                            self, "current_ra_str"
                        ).props("readonly")
                        ui.input("Telescope Dec:").bind_value(
                            self, "current_dec_str"
                        ).props("readonly")

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
                    with ui.column():
                        self.show_aladin()
                # with ui.row(align_items="center"):
                ui.separator()
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
            with ui.tab_panel("Henrietta"):
                ui.label("TODO:  henrietta controls here")

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
                self.terminal = ui.xterm({"cols": 120, "rows": 40, "convertEol": True})
                self.terminal.on_bell(lambda: ui.notify("🔔 scheduler 🔔"))

            with ui.tab_panel("Settings"):
                ui.label("Alert Sounds:")
                # self.audio = ui.audio('https://cdn.pixabay.com/download/audio/2022/02/22/audio_d1718ab41b.mp3')
                self.audio = ui.audio(
                    "https://cdn.pixabay.com/download/audio/2025/06/11/audio_e064a2fc07.mp3"
                )  # ?filename=airbus-cabin-pa-beep-tone-passenger-announcement-chime-358248.mp3
                ui.button(
                    on_click=lambda: self.audio.props("muted"), icon="volume_off"
                ).props("outline")
                ui.button(
                    on_click=lambda: self.audio.props(remove="muted"), icon="volume_up"
                ).props("outline")
                # todo: audio volume control button toggle mute/unmute

        ui.separator()
        ui.button("Release", on_click=self.release_operator)

    def show_aladin(self):
        ui.add_body_html(
            "<script src='https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js' charset='utf-8'></script>"
        )
        # ui.add_body_html("<div id='aladin-lite-div' style='width: 400px; height: 400px;'></div>")
        with (
            ui.element("div")
            .props('id="aladin-lite-div"')
            .style("width: 400px; height: 400px;") as self.aladin
        ):
            self.update_aladin()
        ui.button("Update", on_click=self.update_aladin)

    def update_aladin(self, ra=None, dec=None, draw_footprint=False):
        self.update_telescope_coordinates()
        # if ra is None or dec is None:
        #     print("current ra, dec:", self.current_ra, self.current_dec)
        ra = self.current_ra * 15  # convert RA from hours to degrees
        dec = self.current_dec

        with self.aladin:
            ui.run_javascript(
                f"""
                aladin = A.aladin('#aladin-lite-div', {{
                            fov:0.5, target: '{ra} {dec}', showReticle: false,
                            showFrame: false, showLayersControl: false, showGotoControl: false, showProjectionControl: false
                            }});
            """
            )

            if draw_footprint:
                # ccd_dims = 4096 * 0.435 / 3600, 4112 * 0.435 / 3600 # degrees
                ccd_dims = 4096 * 0.435 / 3600, 4096 * 0.435 / 3600  # degrees
                ccd_footprint = [
                    [ra - ccd_dims[0] / 2, dec - ccd_dims[1] / 2],
                    [ra + ccd_dims[0] / 2, dec - ccd_dims[1] / 2],
                    [ra + ccd_dims[0] / 2, dec + ccd_dims[1] / 2],
                    [ra - ccd_dims[0] / 2, dec + ccd_dims[1] / 2],
                ]
                print("CCD footprint:", ccd_footprint)
                ui.run_javascript(
                    f"""
                    var overlay = A.graphicOverlay({{color: '#ee2345', lineWidth: 3}});
                    aladin.addOverlay(overlay);
                    overlay.add(A.polygon({ccd_footprint}));                            
                """
                )


def start_bus():
    global bus
    print("Starting bus...")
    pool = ThreadPoolExecutor()
    random_port = random.randint(10000, 60000)
    bus = Bus(f"tcp://127.0.0.1:{random_port}")
    pool.submit(bus.run_forever)


def on_startup():
    global data
    start_bus()


app.on_startup(on_startup)

data = UiData()
ui.run(
    data.root,
    host="0.0.0.0",
    native=True,
    title="Henrietta Swope",
    fullscreen=True,
    dark=True,
    reload=False,
)
