from nicegui import run, ui
from nicegui.events import ValueChangeEventArguments
from chimera.core.proxy import Proxy


class RotatorClient:

    def show(self, event: ValueChangeEventArguments):
        name = type(event.sender).__name__
        ui.notify(f"{name}: {event.value}")
        pass
        

    def update_pa_offset(self, pa):
        self.offset_pa = pa

    def update_rotator_pa(self, angle):
        self.current_pa = f"{angle:.2f}º"

    def move_btn(self):
        ui.notify(f"Offsetting rotator by {self.offset_pa:.2f}º")
        self.rotator_proxy.move_by(self.offset_pa)
        self.offset_pa = 0.0
        self.update_pa_offset(self.offset_pa)

    def set_pa_offset(self, event: ValueChangeEventArguments):
        self.offset_pa = float(event.value)

    async def grab_stars_btn(self):
        ui.notify("Grabbing PA from DS9")
        await run.cpu_bound(self.display_proxy.get_pa(detect_stars=True))
        ui.notify("Finished grabbing PA from DS9")
        
    async def grab_pixels_btn(self):
        ui.notify("Grabbing PA from DS9 (2 points)")
        await run.cpu_bound(self.display_proxy.get_pa(detect_stars=False))
        ui.notify("Finished grabbing PA from DS9 (2 points)")


    def __init__(self):
        self.display_proxy = Proxy("127.0.0.1:6379/Ds9AutoDisplay/display")
        self.display_proxy.update_pa += self.update_pa_offset
        self.rotator_proxy = Proxy("127.0.0.1:6379/FakeRotator/rotator")
        self.rotator_proxy.slew_complete += self.update_rotator_pa

        self.update_rotator_pa(self.rotator_proxy.get_position())
        self.offset_pa = 0.0
        self.draw()

    def draw(self):

        with ui.row():
            ui.input("Current PA:").bind_value(self, "current_pa").props("readonly")
            ui.input("Offset PA:", on_change=self.set_pa_offset).bind_value(self, "offset_pa").props("type=number")
            ui.button("Grab Stars", on_click=self.grab_stars_btn)
            ui.button("Grab Pixels", on_click=self.grab_pixels_btn)
        with ui.row():
            ui.button("Move", on_click=self.move_btn)

        with ui.footer(value=False) as footer:
            ui.label('Footer')
        # with ui.row():
        #     ui.checkbox("Checkbox", on_change=self.show)
        #     ui.switch("Switch", on_change=self.show)
        #     ui.radio(["A", "B", "C"], value="A", on_change=self.show).props("inline")
        # with ui.row():
        #     ui.input("Text input", on_change=self.show)
        #     ui.select(["One", "Two"], value="One", on_change=self.show)


r = RotatorClient()

ui.run(native=True, title="Rotator Client", dark=True, reload=True)
