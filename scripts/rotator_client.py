import asyncio
import random
import time
from concurrent.futures.thread import ThreadPoolExecutor

from chimera.core.bus import Bus
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

    # Initialize proxies
    proxies = {
        "display": None,
        "rotator": None,
        "telescope": None,
        "focuser": None,
        "operator": None,
        "dome": None,
    }

    # Create bus
    print("Starting bus...")
    pool = ThreadPoolExecutor()
    random_port = random.randint(10000, 60000)
    bus = Bus(f"tcp://127.0.0.1:{random_port}")
    pool.submit(bus.run_forever)

    # Try to connect to each proxy
    try:
        proxies["rotator"] = Proxy("tcp://127.0.0.1:6379/FakeRotator/rotator", bus)
        proxies["rotator"].ping()
    except Exception as e:
        print(f"Could not connect to rotator: {e}")
        proxies["rotator"] = None

    try:
        proxies["telescope"] = Proxy("tcp://127.0.0.1:6379/FakeTelescope/swope", bus)
        proxies["telescope"].ping()
    except Exception as e:
        print(f"Could not connect to telescope: {e}")
        proxies["telescope"] = None

    try:
        proxies["focuser"] = Proxy("tcp://127.0.0.1:6379/SwopeFocuser/focus", bus)
        proxies["focuser"].ping()
        state["focus_min"], state["focus_max"] = proxies["focuser"].get_range()
        print("Focuser range:", state["focus_min"], state["focus_max"])
    except Exception as e:
        print(f"Could not connect to focuser: {e}")
        proxies["focuser"] = None

    # try:
    #     proxies["display"] = Proxy("tcp://127.0.0.1:6379/Ds9AutoDisplay/display", bus)
    #     proxies["display"].update_pa += update_pa_offset
    # except Exception as e:
    #     print(f"Could not connect to display: {e}")

    # try:
    #     proxies["operator"] = Proxy("tcp://127.0.0.1:6379/TelescopeOperator/operator", bus)
    #     proxies["operator"].notify += operator_request
    # except Exception as e:
    #     print(f"Could not connect to operator: {e}")

    # Telescope methods
    def tel_slew_complete(ra=None, dec=None, status=None):
        print("Telescope slew complete callback")
        tel_aladin_update(ra, dec)

    def tel_update_coordinates():
        if not proxies["telescope"]:
            return
        state["current_ra"], state["current_dec"] = proxies[
            "telescope"
        ].get_position_ra_dec()

        # fixme: this should not be necessary: chimera bug
        if not isinstance(state["current_ra"], float):
            state["current_ra"] = float(state["current_ra"].to_d())
        if not isinstance(state["current_dec"], float):
            state["current_dec"] = float(state["current_dec"].to_d())
        # fixme end

        state["current_ra_str"] = Coord.from_d(float(state["current_ra"])).strfcoord()
        state["current_dec_str"] = Coord.from_d(float(state["current_dec"])).strfcoord()

    def tel_offset_north():
        if not proxies["telescope"]:
            return
        proxies["telescope"].move_north(1)
        tel_update_coordinates()

    def tel_offset_south():
        if not proxies["telescope"]:
            return
        proxies["telescope"].move_south(1)
        tel_update_coordinates()

    def tel_offset_east():
        if not proxies["telescope"]:
            return
        proxies["telescope"].move_east(1)
        tel_update_coordinates()

    def tel_offset_west():
        if not proxies["telescope"]:
            return
        proxies["telescope"].move_west(1)
        tel_update_coordinates()

    # Chimera callbacks
    if proxies["telescope"]:
        proxies["telescope"].slew_complete += tel_slew_complete

    def update_rotator(*args, **kwargs):
        """Callback for rotator slew complete."""
        pass

    if proxies["rotator"]:
        proxies["rotator"].slew_complete += update_rotator

    # Data update methods
    def update_proxy_data():
        if time.time() - state["last_update"] < 1.0:
            return
        state["last_update"] = time.time()
        tel_update_coordinates()
        focusser_update()

    def focusser_update():
        if proxies["focuser"]:
            state["current_focus"] = proxies["focuser"].get_position()
        if proxies["rotator"]:
            state["current_rotator"] = proxies["rotator"].get_position()
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
                proxies["display"] = Proxy("127.0.0.1:6379/Ds9AutoDisplay/display", bus)
            except Exception as e:
                ui.notify(f"Error connecting to DS9: {e}")
                return
        try:
            print(proxies["display"].get_pa(detect_stars=detect_stars))
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
            proxies["focuser"].move_to(int(state["target_focus"]))
        except Exception as e:
            ui.notify(f"Error setting focus: {e}")
        focusser_update()

    def rotator_move_btn():
        if not proxies["rotator"]:
            ui.notify("Rotator not connected")
            return
        ui.notify(f"Offsetting rotator by {state['offset_pa']:.3f}º")
        proxies["rotator"].move_by(state["offset_pa"])
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
            "/Users/william/workspace/chimera/chimera-swope/etc/chimera.config",  # fixme
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
            proxies["operator"].release()

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
                                "Telescope RA:", value=state["current_ra_str"]
                            ).bind_value(state, "current_ra_str").props("readonly")
                            ui.input(
                                "Telescope Dec:", value=state["current_dec_str"]
                            ).bind_value(state, "current_dec_str").props("readonly")

                            focusser_update()
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

        ui.separator()
        ui.button("Release", on_click=release_operator)

    # Start periodic updates
    app.timer(2, update_proxy_data)


# All the setup is only done when the server starts, following the nicegui pattern
app.on_startup(setup)

ui.run(
    host="0.0.0.0",
    native=True,
    title="Henrietta Swope",
    fullscreen=True,
    dark=True,
    reload=True,
)
