''' A panel that allows user to choose an exposure preset or to add a new preset
'''

import json
from functools import partial
from loguru import logger

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout

from jocular.component import Component
from jocular.widgets import Panel, TextInputC, JMDToggleButton

def exp_to_str(e):
    if e < .001:
        return '{:.0f} µs'.format(e*1e6)
    if e < 1:
        return '{:.0f} ms'.format(e*1000)
    if e - int(e) < .0001:
        return '{:.0f}s'.format(e)
    return '{:.2f}s'.format(e)

def str_to_exp(s):
    s = str(s)
    s = s.lower().strip()
    if len(s) == 0:
        raise Exception
    try:
        if s.endswith('µs') or s.endswith('us'):
            return float(s[:-2].strip()) / 1e6
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

    def _button(self, name, expo):
        return JMDToggleButton(
                text=name, 
                size_hint=(.2, None),
                group='expos',
                font_size='18sp',
                height=dp(24),
                on_press=partial(self.exposure_selected, expo))

    def build(self, *args):

        self.expos = [
            .001, .002, .003, .005, .01, .02, .05, .1, .2, .5, 
            1, 2, 5, 10, 15, 20, 25, 30, 45, 60
        ]

        content = self.contents
        self.title_label = Label(text='Select exposure', font_size='24sp')
        self.header.add_widget(self.title_label)

        self.expo_buttons = {}
        for e in self.expos + self.user_expos:
            e_str = exp_to_str(e)
            self.expo_buttons[e_str] = self._button(e_str, e)

        # spacer
        content.add_widget(Label(text='', size_hint=(1, 1)))

        # short exposures
        content.add_widget(Label(
            text='short', 
            size_hint=(1, None), 
            font_size='20sp',
            height=dp(30)))
        gl = GridLayout(
            size_hint=(1, None), 
            cols=5,
            height=dp(120),
            spacing=(dp(5), dp(5)))
        for e in [i for i in self.expos if i < 1]:
            gl.add_widget(self.expo_buttons[exp_to_str(e)])
        content.add_widget(gl)

        # longer exposures
        content.add_widget(Label(
            text='long', 
            size_hint=(1, None), 
            font_size='20sp',
            height=dp(30)))
        gl = GridLayout(
            size_hint=(1, None), 
            cols=5,
            height=dp(120),
            spacing=(dp(5), dp(5)))
        for e in [i for i in self.expos if i >= 1]:
            gl.add_widget(self.expo_buttons[exp_to_str(e)])
        content.add_widget(gl)

        # recently used exposure here; limit to 10 most recent, in order
        content.add_widget(Label(
            text='user-defined', 
            size_hint=(1, None), 
            font_size='20sp',
            height=dp(30)))
        self.user_gl = GridLayout(
            size_hint=(1, None), 
            cols=5,
            height=dp(120),
            spacing=(dp(5), dp(5)))
        for e in sorted(self.user_expos):
            self.user_gl.add_widget(self.expo_buttons[exp_to_str(e)])
        # add some blank labels
        for e in range(10 - len(self.user_expos)):
            self.user_gl.add_widget(Label(size_hint=(.2, None), height=dp(28)))
        content.add_widget(self.user_gl)

        # exposure box
        bv = BoxLayout(
            orientation='vertical',
            size_hint=(1, None),
            height=dp(90))
        bv.add_widget(Label(
            text='add new exposure', 
            size_hint=(1, None),
            font_size='20sp',
            height=dp(32)))
        self.user_exposure_box = TextInputC(
            hint_text='0.3, 10, 10s, 30ms, 50us', 
            size_hint=(.65, None), 
            multiline=False,
            height=dp(30),
            pos_hint={'center_x': .5},
            font_size='20sp',
            on_text_validate=self.custom_exposure_added)
        bv.add_widget(self.user_exposure_box)
        content.add_widget(bv)

        content.add_widget(Label(text='', size_hint=(1, 1)))

        self.app.gui.add_widget(self)

    @logger.catch()
    def custom_exposure_added(self, tb):
        try:
            self.exposure = str_to_exp(self.user_exposure_box.text)
            if self.exposure not in self.expos + self.user_expos:
                self.user_expos += [self.exposure]
            if len(self.user_expos) > 10:
                self.user_expos = self.user_expos[-10:]
            self.user_gl.clear_widgets()
            for e in sorted(self.user_expos):
                self.user_gl.add_widget(self._button(exp_to_str(e), e))
            for e in range(11 - len(self.user_expos)):
                self.user_gl.add_widget(Label(size_hint=(.2, None), height=dp(30)))
            self.user_exposure_box.text = ''
            self.save()
        except Exception as e:
            pass

    def exposure_selected(self, expo, *args):
        # set exposure on GUI and on scripts panel
        Component.get('CaptureScript').exposure_changed(expo)
        # self.hide()

