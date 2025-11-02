import jinja2
import os

with open("observing_sequence.j2", "r") as f:
    template_content = f.read()

template = jinja2.Template(template_content)
observation_data = {
    "program_name": "TOI-620 b",
    "pi_name": "Jason Williams",
    "priority": 1,
    "target": {
        "name": "TOI-620 b",
        "ra": "09:28:41.6",
        "dec": "-12:09:55.8",
        # "epoch": "J2000",
        "pa": 45,
        "offsets": {"south": 20, "east": 10},
    },
}

output_content = template.render(observation=observation_data)
output_file = "observing_sequence.yaml"
with open(output_file, "w") as f:
    f.write(output_content)


# henrietta@henrietta-spreadsheets.iam.gserviceaccount.com
# import gspread

# gc = gspread.service_account()
# sh = gc.open("Observation Planning")
# sh.sheet1.get('A1')
# sh.sheet1
# s = sh.sheet1
# s.append_row?
# s.update?
# s.update?
# s.update("test", "A2")
# s.update("A2", "test")
# s.update(["test"], "A2")
# s.update([["test"]], "A2")
# s.update([["test\nxyz"]], "A2")
