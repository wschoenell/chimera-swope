import asyncio
import os
import random
import time
from concurrent.futures.thread import ThreadPoolExecutor

from chimera.core.bus import Bus
from chimera.core.chimera_config import ChimeraConfig
from chimera.core.constants import CHIMERA_CONFIG_DEFAULT_FILENAME, INSTRUMENT_CLASSES
from chimera.core.proxy import Proxy
from chimera.util.coord import Coord
from nicegui import Event, app, run, ui
from nicegui.events import (
    KeyEventArguments,
    UploadEventArguments,
    ValueChangeEventArguments,
)


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


def setup() -> None:
    """Setup function that initializes all state and defines the UI."""

    # State variables
    state = {
        "current_pa": "0.0º",
        "offset_pa": 0.0,
        "current_ra": 0.0,
        "current_dec": 0.0,
        "current_ra_str": "",
        "current_dec_str": "",
        "current_lst_str": "",
        "current_ut_str": "",
        "current_focus": 0.0,
        "target_focus": 0.0,
        "current_rotator": 0.0,
        "last_update": 0.0,
        "message": None,
        "aladin": None,
        "terminal": None,
        "audio": None,
        "focus_min": 0,
        "focus_max": 1,
    }

    tweet = Event[str]()

    # Create bus
    print("Starting bus...")
    pool = ThreadPoolExecutor()
    random_port = random.randint(10000, 60000)
    bus = Bus(f"tcp://127.0.0.1:{random_port}")
    pool.submit(bus.run_forever)

    # Load configuration
    config_path = os.getenv("CHIMERA_CONFIG", CHIMERA_CONFIG_DEFAULT_FILENAME)
    print(f"Loading configuration from: {config_path}")
    cfg = ChimeraConfig.from_file(config_path)

    # Initialize proxy lists for each instrument class
    proxies = {cls.lower(): [] for cls in INSTRUMENT_CLASSES}
    proxies["display"] = []
    proxies["operator"] = []
    proxies["site"] = Proxy(next(iter(cfg.sites.keys())), bus)

    # Connect to instruments from config
    print("Connecting to instruments...")
    for instrument in cfg.instruments.keys():
        try:
            proxy = Proxy(instrument, bus)
            # Try to ping the proxy to see if it's reachable
            try:
                proxy.ping()
                print(f"✓ Connected to {instrument}")

                # Categorize proxy by its features
                categorized = False
                for cls in INSTRUMENT_CLASSES:
                    if proxy.features(cls):
                        proxies[cls.lower()].append(proxy)
                        categorized = True
                        break

                if not categorized:
                    print(
                        f"  Warning: {instrument} does not match any known instrument class"
                    )

            except Exception as e:
                print(f"✗ Could not reach {instrument}: {e}")

        except Exception as e:
            print(f"✗ Could not connect to {instrument}: {e}")

    # # Try to connect to controllers
    # for controller in cfg.controllers.keys():
    #     try:
    #         proxy = Proxy(controller, bus)
    #         try:
    #             proxy.ping()
    #             print(f"✓ Connected to controller {controller}")

    #             # Check if it's a display or operator and add to proxies
    #             if "display" in controller.lower():
    #                 proxies["display"].append(proxy)
    #             elif "operator" in controller.lower():
    #                 proxies["operator"].append(proxy)

    #         except Exception as e:
    #             print(f"✗ Could not reach controller {controller}: {e}")
    #     except Exception as e:
    #         print(f"✗ Could not connect to controller {controller}: {e}")

    # Set focus range if focuser is available
    if proxies["focuser"]:
        try:
            state["focus_min"], state["focus_max"] = proxies["focuser"][0].get_range()
            print(f"Focuser range: {state['focus_min']} - {state['focus_max']}")
        except Exception as e:
            print(f"Could not get focuser range: {e}")

    # Telescope methods
    def tel_slew_complete(ra=None, dec=None, status=None):
        print("Telescope slew complete callback")
        tel_aladin_update(ra, dec)

    def tel_update_coordinates():
        if not proxies["telescope"]:
            return
        state["current_ra"], state["current_dec"] = proxies["telescope"][
            0
        ].get_position_ra_dec()

        # fixme: this should not be necessary: chimera bug
        if not isinstance(state["current_ra"], float):
            state["current_ra"] = float(state["current_ra"].to_d())
        if not isinstance(state["current_dec"], float):
            state["current_dec"] = float(state["current_dec"].to_d())
        # fixme end

        state["current_ra_str"] = Coord.from_d(float(state["current_ra"])).strfcoord()
        state["current_dec_str"] = Coord.from_d(float(state["current_dec"])).strfcoord()

    def site_update_time():
        state["current_ut_str"] = proxies["site"].ut().split(".")[0].replace("T", " ")
        state["current_lst_str"] = proxies["site"].lst()

    def tel_offset_north():
        if not proxies["telescope"]:
            return
        proxies["telescope"][0].move_north(1)
        tel_update_coordinates()

    def tel_offset_south():
        if not proxies["telescope"]:
            return
        proxies["telescope"][0].move_south(1)
        tel_update_coordinates()

    def tel_offset_east():
        if not proxies["telescope"]:
            return
        proxies["telescope"][0].move_east(1)
        tel_update_coordinates()

    def tel_offset_west():
        if not proxies["telescope"]:
            return
        proxies["telescope"][0].move_west(1)
        tel_update_coordinates()

    # Chimera callbacks
    if proxies["telescope"]:
        proxies["telescope"][0].slew_complete += tel_slew_complete

    def update_rotator(*args, **kwargs):
        """Callback for rotator slew complete."""
        pass

    if proxies["rotator"]:
        proxies["rotator"][0].slew_complete += update_rotator

    # Data update methods
    def update_proxy_data():
        if time.time() - state["last_update"] < 1.0:
            return
        state["last_update"] = time.time()
        tel_update_coordinates()
        focuser_update()
        site_update_time()

    def focuser_update():
        if proxies["focuser"]:
            state["current_focus"] = proxies["focuser"][0].get_position()
        if proxies["rotator"]:
            state["current_rotator"] = proxies["rotator"][0].get_position()
            state["current_pa"] = f"{state['current_rotator']:.3f}º"

    def operator_request(type, msg):
        print(f"xxx Operator request: {type} -- {msg}")
        state["message"] = f"Operator request: {type} -- {msg}"
        tweet.emit(state["message"])

    def show(event: ValueChangeEventArguments):
        name = type(event.sender).__name__
        ui.notify(f"{name}: {event.value}")

    def rotator_offset_update(pa):
        print("Updating PA offset:", pa)
        state["offset_pa"] = pa

    def rotator_get_ds9_pa(detect_stars=True):
        """Get PA from DS9 display - can be run in cpu_bound context."""
        if not proxies["display"]:
            try:
                proxy = Proxy("127.0.0.1:6379/Ds9AutoDisplay/display", bus)
                proxy.ping()
                proxies["display"].append(proxy)
            except Exception as e:
                ui.notify(f"Error connecting to DS9: {e}")
                return
        try:
            print(proxies["display"][0].get_pa(detect_stars=detect_stars))
        except Exception as e:
            ui.notify(f"Error getting PA from DS9: {e}")
            return

    # Button handlers
    def focuser_set_btn():
        if not proxies["focuser"]:
            ui.notify("Focuser not connected")
            return
        try:
            print(f"Setting focus to {state['target_focus']}")
            proxies["focuser"][0].move_to(int(state["target_focus"]))
        except Exception as e:
            ui.notify(f"Error setting focus: {e}")
        focuser_update()

    def rotator_move_btn():
        if not proxies["rotator"]:
            ui.notify("Rotator not connected")
            return
        ui.notify(f"Offsetting rotator by {state['offset_pa']:.3f}º")
        proxies["rotator"][0].move_by(state["offset_pa"])
        state["offset_pa"] = 0.0
        rotator_offset_update(state["offset_pa"])

    def rotator_set_offset(event: ValueChangeEventArguments):
        state["offset_pa"] = float(event.value)

    async def rotator_grab_stars_btn():
        ui.notify("Grabbing PA from DS9")
        print("Grabbing PA from DS9")
        await run.cpu_bound(rotator_get_ds9_pa, detect_stars=True)
        ui.notify("Finished grabbing PA from DS9")

    async def rotator_grab_pixels_btn():
        ui.notify("Grabbing PA from DS9 (2 points)")
        await run.cpu_bound(rotator_get_ds9_pa, detect_stars=False)
        ui.notify("Finished grabbing PA from DS9 (2 points)")

    def tel_handle_key_input(e: KeyEventArguments):
        if e.action.keydown:
            if e.key.arrow_left:
                ui.notify("Moving West")
                tel_offset_west()
            elif e.key.arrow_right:
                ui.notify("Moving East")
                tel_offset_east()
            elif e.key.arrow_up:
                ui.notify("Moving North")
                tel_offset_north()
            elif e.key.arrow_down:
                ui.notify("Moving South")
                tel_offset_south()

    async def sched_run_subprocess(arg="--help"):
        state["terminal"].clear()
        args = arg.split()
        process = await asyncio.create_subprocess_exec(
            "chimera-sched",
            *args,
            "--config",
            config_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def sched_write_to_terminal(stream: asyncio.StreamReader) -> None:
            while chunk := await stream.read(128):
                state["terminal"].write(chunk)

        await asyncio.gather(
            sched_write_to_terminal(process.stdout),
            sched_write_to_terminal(process.stderr),
            process.wait(),
        )

    async def sched_upload(e: UploadEventArguments):
        ui.notify(f"Uploaded {e.file.name}")
        await e.file.save("/tmp/sched.yaml")  # fixme

    def tweet_handler(message: str):
        state["audio"].play()
        ui.notify(
            f'A Someone tweeted: "{message}"',
            close_button="Release",
            type="warning",
            spinner=True,
            timeout=0,
        )
        ui.notify(
            f'B Someone tweeted: "{message}"',
            close_button="Release",
            type="warning",
            spinner=True,
            timeout=0,
        )

    def release_operator():
        if proxies["operator"]:
            proxies["operator"][0].release()

    def tel_aladin_show():
        ui.add_body_html(
            "<script src='https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js' charset='utf-8'></script>"
        )
        aladin_div = (
            ui.element("div")
            .props('id="aladin-lite-div"')
            .style("width: 400px; height: 400px;")
        )
        state["aladin"] = aladin_div
        tel_aladin_update()
        ui.button("Update", on_click=tel_aladin_update)
        return aladin_div

    def tel_aladin_update(ra=None, dec=None, draw_footprint=False):
        tel_update_coordinates()
        ra = state["current_ra"] * 15  # convert RA from hours to degrees
        dec = state["current_dec"]

        with state["aladin"]:
            ui.run_javascript(
                f"""
                aladin = A.aladin('#aladin-lite-div', {{
                            fov:0.5, target: '{ra} {dec}', showReticle: false,
                            showFrame: false, showLayersControl: false, showGotoControl: false, showProjectionControl: false
                            }});
            """
            )

            if draw_footprint:
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

    @ui.page("/")
    def page():
        """Main page definition."""
        update_proxy_data()
        keyboard = ui.keyboard(on_key=tel_handle_key_input)

        tweet.subscribe(tweet_handler)

        with ui.tabs().classes("w-full") as tabs:
            if proxies["telescope"]:
                ui.tab("Telescope")
            if proxies["rotator"]:
                ui.tab("Rotator")
            ui.tab("Henrietta")
            ui.tab("Scheduler")
            if proxies["dome"]:
                ui.tab("Dome")
            ui.tab("Settings", label="", icon="settings")

        # Determine first available tab
        first_tab = None
        if proxies["telescope"]:
            first_tab = "Telescope"
        elif proxies["rotator"]:
            first_tab = "Rotator"
        else:
            first_tab = "Henrietta"

        with ui.tab_panels(tabs, value=first_tab, animated=False).classes("w-full"):
            if proxies["telescope"]:
                with ui.tab_panel("Telescope"):
                    with ui.grid(columns=3):
                        with ui.column():
                            ui.input(
                                "Universal Time:", value=state["current_ut_str"]
                            ).bind_value(state, "current_ut_str").props("readonly")
                            ui.input(
                                "Local Sidereal Time:", value=state["current_lst_str"]
                            ).bind_value(state, "current_lst_str").props("readonly")
                            ui.input(
                                "Telescope RA:", value=state["current_ra_str"]
                            ).bind_value(state, "current_ra_str").props("readonly")
                            ui.input(
                                "Telescope Dec:", value=state["current_dec_str"]
                            ).bind_value(state, "current_dec_str").props("readonly")

                            ui.input(
                                "Focus:",
                                value=state["current_focus"],
                                validation={
                                    "Out of range": lambda v: state["focus_min"]
                                    <= float(v)
                                    <= state["focus_max"]
                                },
                                on_change=lambda e: state.update(
                                    {"target_focus": e.value}
                                ),
                            ).bind_value(state, "current_focus")
                            ui.button("Set", on_click=focuser_set_btn)

                        with ui.column():
                            with ui.grid(columns=3):
                                ui.label()
                                ui.button("N", on_click=tel_offset_north)
                                ui.label()
                                ui.button("E", on_click=tel_offset_east)
                                ToggleButton("K", keyboard=keyboard)
                                print("Keyboard active:", keyboard.active)
                                ui.button("W", on_click=tel_offset_west)
                                ui.label()
                                ui.button("S", on_click=tel_offset_south)
                        with ui.column():
                            tel_aladin_show()
                    ui.separator()

            if proxies["rotator"]:
                with ui.tab_panel("Rotator"):
                    with ui.row():
                        ui.input("Current PA:", value=state["current_pa"]).bind_value(
                            state, "current_pa"
                        ).props("readonly")
                        ui.input(
                            "Offset PA:",
                            value=state["offset_pa"],
                            on_change=rotator_set_offset,
                        ).bind_value(state, "offset_pa")
                        ui.button("Grab Stars", on_click=rotator_grab_stars_btn)
                        ui.button("Grab Pixels", on_click=rotator_grab_pixels_btn)
                    with ui.row():
                        ui.button("Move", on_click=rotator_move_btn)

            if proxies["dome"]:
                with ui.tab_panel("Dome"):
                    ui.label("Slit:")
                    ui.label("Azimuth:")
                    ui.label("Wind screen:")

            with ui.tab_panel("Henrietta"):
                ui.label("TODO:  henrietta controls here")

            with ui.tab_panel("Scheduler"):
                with ui.grid(columns=2):
                    ui.upload(on_upload=sched_upload, auto_upload=True, max_files=1)
                    with ui.button_group():
                        ui.button(
                            "Load file",
                            on_click=lambda: sched_run_subprocess(
                                "--new -f /tmp/sched.yaml"
                            ),
                            color="blue",
                        )
                        ui.button(
                            "Start",
                            on_click=lambda: sched_run_subprocess("--start"),
                            color="green",
                        )
                        ui.button(
                            "Stop",
                            on_click=lambda: sched_run_subprocess("--stop"),
                            color="red",
                        )
                        ui.button(
                            "Monitor",
                            on_click=lambda: sched_run_subprocess("--monitor"),
                            color="blue",
                        )
                state["terminal"] = ui.xterm(
                    {"cols": 120, "rows": 40, "convertEol": True}
                )
                state["terminal"].on_bell(lambda: ui.notify("🔔 scheduler 🔔"))

            with ui.tab_panel("Settings"):
                ui.label("Alert Sounds:")
                state["audio"] = ui.audio(
                    "https://cdn.pixabay.com/download/audio/2025/06/11/audio_e064a2fc07.mp3"
                )
                ui.button(
                    on_click=lambda: state["audio"].props("muted"), icon="volume_off"
                ).props("outline")
                ui.button(
                    on_click=lambda: state["audio"].props(remove="muted"),
                    icon="volume_up",
                ).props("outline")

        # ui.separator()
        # ui.button("Release", on_click=release_operator)

        with ui.footer():
            ui.label("This is a label at the bottom of the page.")

    # Start periodic updates
    app.timer(1, update_proxy_data)


# All the setup is only done when the server starts, following the nicegui pattern
app.on_startup(setup)

ui.run(
    host="0.0.0.0",
    # native=True,
    title="Henrietta Swope",
    # fullscreen=True,
    dark=True,
    reload=True,
)
