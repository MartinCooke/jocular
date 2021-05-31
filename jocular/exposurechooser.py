''' A panel that allows user to choose an exposure preset or to add a new preset
'''

import json
from functools import partial

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout

from jocular.component import Component
from jocular.widgets import Panel, TextInputC, LabelL

def exp_to_str(e):
    if e < 1:
        return '{:.0f} ms'.format(e*1000)
    if e - int(e) < .0001:
        return '{:.0f}s'.format(e)
    return '{:.2f}s'.format(e)

def str_to_exp(s):
    s = str(s)
    s = s.lower().strip()
    try:
        if s.endswith('ms'):
            return float(s[:-2].strip()) / 1000
        if s.endswith('s'):
            return float(s[:-1].strip())
        return float(s)
    except:
        raise Exception


class ExposureChooser(Panel, Component):

    def __init__(self, **args):
        super().__init__(**args)
        self.app = App.get_running_app()
        try:
            with open(self.app.get_path('user_exposures.json'), 'r') as f:
                self.user_expos = json.load(f)
        except:
            self.user_expos = []
        self.build()

    def save(self, dt=None):
        with open(self.app.get_path('user_exposures.json'), 'w') as f:
            json.dump(self.user_expos, f, indent=1)       

    def on_show(self):
        # ensure exposurechooser reflects current state
        e_str = exp_to_str(Component.get('CaptureScript').get_exposure())
        for e, but in self.expo_buttons.items():
            but.state = 'down' if e == e_str else 'normal'

    def build(self, *args):

        self.expos = [
            .001, .002, .003, .005, .01, .02, .05, .1, .2, .5, 
            1, 2, 5, 10, 15, 20, 25, 30, 45, 60
        ]

        self.add_widget(Label(size_hint=(1, 1), text='Select exposure', font_size='24sp'))
        self.expo_buttons = {}
        for e in self.expos + self.user_expos:
            e_str = exp_to_str(e)
            self.expo_buttons[e_str] = ToggleButton(text=e_str, 
                size_hint=(.2, None), group='expos', height=dp(30), 
                on_press=partial(self.exposure_selected, e))

        # short exposures
        self.add_widget(LabelL(text='short', size_hint=(1, 1)))
        gl = GridLayout(size_hint=(1, 2), cols=5, spacing=(dp(5), dp(5)))
        for e in [i for i in self.expos if i < 1]:
            gl.add_widget(self.expo_buttons[exp_to_str(e)])
        self.add_widget(gl)

        # longer exposures
        self.add_widget(LabelL(text='long', size_hint=(1, 1)))
        gl = GridLayout(size_hint=(1, 2), cols=5, spacing=(dp(5), dp(5)))
        for e in [i for i in self.expos if i >= 1]:
            gl.add_widget(self.expo_buttons[exp_to_str(e)])
        self.add_widget(gl)

        # recently used exposure here; limit to 10 most recent, in order
        self.add_widget(LabelL(text='user-defined', size_hint=(1, 1)))
        self.user_gl = GridLayout(size_hint=(1, 2), cols=5, spacing=(dp(5), dp(5)))
        for e in sorted(self.user_expos):
            self.user_gl.add_widget(self.expo_buttons[exp_to_str(e)])
        # add some blank labels
        for e in range(10 - len(self.user_expos)):
            self.user_gl.add_widget(Label(size_hint=(.2, None), height=dp(30)))
        self.add_widget(self.user_gl)

        # exposure box
        bh = BoxLayout(orientation='horizontal', size_hint=(1, 1), padding=(0, 10))
        bh.add_widget(LabelL(text='add new', size_hint=(.2, 1))) 
        bh.add_widget(TextInputC(hint_text='10, 10s, 30ms, 0.3', size_hint=(.4, 1), 
            multiline=False, font_size='16sp',
            on_text_validate=self.custom_exposure_added))
        bh.add_widget(Label(text='10 most recent stored', size_hint=(.4, 1), color=(.5, .5, .5, 1))) 
        self.add_widget(bh)

        self.app.gui.add_widget(self)

    def custom_exposure_added(self, tb):
        try:
            self.exposure = str_to_exp(tb.text)
            if self.exposure not in self.expos + self.user_expos:
                self.user_expos += [self.exposure]
            if len(self.user_expos) > 10:
                self.user_expos = self.user_expos[-10:]
            self.user_gl.clear_widgets()
            for e in sorted(self.user_expos):
                self.user_gl.add_widget(ToggleButton(text=exp_to_str(e), size_hint=(.2, None), 
                    group='expos', height=dp(30),
                    on_press=partial(self.exposure_selected, e)))
            for e in range(11 - len(self.user_expos)):
                self.user_gl.add_widget(Label(size_hint=(.2, None), height=dp(30)))
            self.save()
        except:
            pass

    def exposure_selected(self, expo, *args):
        # set exposure on GUI and on scripts panel
        Component.get('CaptureScript').exposure_changed(expo)
        self.hide()

