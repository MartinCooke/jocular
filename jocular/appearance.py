""" Appearance (font sizes, colours etc)
"""

from kivy.app import App
from kivy.properties import NumericProperty, StringProperty, BooleanProperty
from jocular.component import Component
from jocular.settingsmanager import JSettings


def sat_to_hue(val):
    hues = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900"]
    return hues[int((len(hues) - 1) * val / 100)]


class Appearance(Component, JSettings):

    highlight_color = StringProperty("BlueGray")
    lowlight_color = NumericProperty(50)
    lever_color = NumericProperty(30)
    hint_color = NumericProperty(25)
    ring_font_size = NumericProperty(14)
    form_font_size = NumericProperty(15)
    transparency = NumericProperty(0)
    colour_saturation = NumericProperty(60)
    show_tooltips = BooleanProperty(False)

    configurables = [
        (
            "highlight_color",
            {
                "name": "highlight colour",
                "options": [
                    "Red",
                    "Pink",
                    "Purple",
                    "DeepPurple",
                    "Indigo",
                    "Blue",
                    "LightBlue",
                    "Cyan",
                    "Teal",
                    "Green",
                    "LightGreen",
                    "Lime",
                    "Yellow",
                    "Amber",
                    "Orange",
                    "DeepOrange",
                    "Brown",
                    "Gray",
                    "BlueGray",
                ],
                "help": "choose a colour for highlights e.g. selected options",
            },
        ),
        (
            "colour_saturation",
            {
                "name": "colour saturation",
                "float": (0, 100, 1),
                "fmt": "{:.0f} percent",
            },
        ),
        (
            "lowlight_color",
            {
                "name": "icon/text grey level",
                "float": (0, 100, 1),
                "fmt": "{:.0f} percent",
                "help": "Gray level for normal text/icons",
            },
        ),
        (
            "lever_color",
            {
                "name": "lever grey level",
                "float": (0, 100, 1),
                "fmt": "{:.0f} percent",
                "help": "Gray level for levers (circular scrollers)",
            },
        ),
        (
            "hint_color",
            {
                "name": "hint text grey level",
                "float": (0, 100, 1),
                "fmt": "{:.0f} percent",
                "help": "Hint text appears above text entry boxes",
            },
        ),
        (
            "transparency",
            {
                "name": "ring transparency",
                "float": (0, 100, 1),
                "fmt": "{:.0f} percent",
                "help": "",
            },
        ),
        (
            "ring_font_size",
            {
                "name": "ring font size",
                "float": (10, 24, 1),
                "help": "Font size for labels used on the ring",
                "fmt": "{:.0f} points",
            },
        ),
        (
            "form_font_size",
            {
                "name": "form font size",
                "float": (10, 24, 1),
                "help": "Font size for form elements eg in DSO entry or session",
                "fmt": "{:.0f} points",
            },
        ),
        (
            "show_tooltips",
            {
                "name": "show tooltips",
                "switch": "",
            },
        ),
    ]


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()


    def on_ring_font_size(self, *args):
        self.app.ring_font_size = f"{self.ring_font_size:.0f}sp"


    def on_form_font_size(self, *args):
        self.app.form_font_size = f"{self.form_font_size:.0f}sp"


    def on_highlight_color(self, *args):
        self.app.theme_cls.accent_palette = self.highlight_color
        self.app.theme_cls.primary_palette = self.highlight_color


    def on_colour_saturation(self, *args):
        self.app.theme_cls.accent_hue = sat_to_hue(self.colour_saturation)
        self.app.theme_cls.primary_hue = sat_to_hue(self.colour_saturation)


    def on_lowlight_color(self, *args):
        lg = max(20, min(int(self.lowlight_color), 100)) / 100
        self.app.lowlight_color = [lg, lg, lg, 1]


    def on_lever_color(self, *args):
        lg = max(20, min(int(self.lever_color), 100)) / 100
        self.app.lever_color = [lg, lg, lg, 1]


    def on_hint_color(self, *args):
        lg = max(0, min(int(self.hint_color), 100)) / 100
        self.app.hint_color = [lg, lg, lg, 1]


    def on_transparency(self, *args):
        self.app.transparency = self.transparency / 100


    def on_show_tooltips(self, *args):
        Component.get('Help').show_tooltips = self.show_tooltips
