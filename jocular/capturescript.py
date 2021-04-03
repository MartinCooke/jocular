''' Handles the GUI elements of getting info about different capture scripts.
    Capturing itself is done with the Capture component
'''

import json
import math
from functools import partial

from kivy.app import App
from kivy.properties import OptionProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty, BooleanProperty
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.metrics import dp

from jocular.component import Component
from jocular.widgets import JPopup

Builder.load_string('''

<MyLabel>:
    size_hint: 1, None
    height: dp(24)
    text_size: self.size
    markup: True
    halign: 'left'

<ExposureToggle>:
    markup: True
    background_color: 0, 0, 0, 0
    color: app.highlight_color if self.state == 'down' else app.lowlight_color
    font_size: '17sp'
    group: 'expos'

<FilterToggle>:
    canvas.before:
        Color:
            rgba: .8, .8, .8, .5
        Ellipse:
            pos: self.pos
            size: self.width, self.height
        Color:
            rgb: self.filter_color
            a: 1 if self.state == 'down' else .3
        Ellipse:
            pos: self.x + 2, self.y + 2
            size: self.width - 5, self.height - 5
    markup: True
    color: (1, 1, 1, 1) if self.state == 'down' else (0, 0, 0, 1)
    background_color: 0, 0, 0, 0
    size: dp(50), dp(50)
    font_size: '18sp' if self.state == 'down' else '16sp'
    size_hint: None, None

<ChooseMultiple>:
    orientation: 'vertical'
    grid: _grid
    size_hint: None, None
    width: dp(240)
    spacing: dp(0), dp(15)
    height: _grid.height + _subs_box.height + _temp_box.height + _confirm_box.height + dp(10)

    BoxLayout:
        id: _grid
        size_hint: 1, None
        height: dp(280)

    BoxLayout:
        id: _subs_box
        size_hint: 1, None
        orientation: 'vertical'
        height: dp(80) if root.show_subs else dp(0)
        opacity: 1 if root.show_subs else 0
        index: 1 if root.show_subs else 100
        disabled: not root.show_subs

        Label:
            color: .5, .5, .5, 1
            font_size: '20sp'
            text: '{:} subs per filter'.format(_nsubs.value)

        Slider:
            size_hint: 1, None
            height: dp(30)
            id: _nsubs
            min: 2
            max: root.max_subs
            value: root.capture.scripts[root.capture.current_script].get('nsubs', 0)
            step: 1

    BoxLayout:
        id: _temp_box
        size_hint: 1, None
        height: dp(80) if root.show_temperature else dp(0)
        opacity: 1 if root.show_temperature else 0
        disabled: not root.show_temperature
        orientation: 'vertical'

        Label:
            text: 'Temperature {:}\N{DEGREE SIGN}C'.format(_temperature.value) if _temperature.value > -26 else 'Temperature not set'
            color: .5, .5, .5, 1
            font_size: '20sp'
        Slider:
            size_hint: 1, None
            height: dp(30)
            id: _temperature
            value: root.session.temperature if root.session.temperature is not None else -26
            on_value: root.session.temperature = self.value if self.value > -26 else None
            min: -26
            max: 40
            step: 1
            
    BoxLayout:
        id: _confirm_box
        size_hint: 1, None
        height: dp(40) # if root.show_confirm else dp(0)
        opacity: 1     # if root.show_confirm else 0

        Button:
            text: 'Done'
            size_hint: .5, .8
            on_press: root.capture.exposure_done() if root.choice_type == 'exposure' else root.capture.filters_done(_nsubs.value)
        Button:
            text: 'Cancel'
            size_hint: .5, .8
            on_press: root.capture.cancel_multiple(root.choice_type)
''')

class FilterToggle(ToggleButton):
    filter_color = ListProperty([1, 1, 1, 1])

class ChooseMultiple(BoxLayout):
    grid = ObjectProperty()
    choice_type = StringProperty('exposure')
    show_temperature = BooleanProperty(False)
    show_subs = BooleanProperty(False)
    subs = NumericProperty(2)
    max_subs = NumericProperty(2)

    def __init__(self, capture=None, session=None, choice_type=None, **kwargs):
        script = capture.current_script
        self.show_temperature = script == 'dark'
        self.max_subs = 20
        self.show_subs = script == 'seq'
        self.capture = capture
        self.session = session
        self.choice_type = choice_type
        super().__init__(**kwargs)

class ExposureToggle(ToggleButton):
    pass

def exp_to_str(e):
    if e < .1:
        return '{:.0f} ms'.format(e*1000)
    if e < 1:
        return '{:.2f}s'.format(e)
    if e < 10:
        if abs(int(e) - e) < .0001:
            return '{:.0f}s'.format(e)
        return '{:.2f}s'.format(e)
    return '{:.0f}s'.format(e)

def str_to_exp(s):
    s = s.strip()
    try:
        if s.endswith('ms'):
            return float(s[:-2].strip()) / 1000
        if s.endswith('s'):
            return float(s[:-1].strip())
        return float(s)
    except:
        raise Exception


class CaptureScript(Component):

    current_script = OptionProperty('frame', options=['light', 'frame', 'dark', 'flat', 'seq', 'bias'])    

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        try:
            with open(self.app.get_path('capture_scripts.json'), 'r') as f:
                self.scripts = json.load(f)
        except:
            # no capture scripts in user directory so use shipped version to start with
            with open(self.app.get_path('shipped_capture_scripts.json'), 'r') as f:
                self.scripts = json.load(f)

        self.on_current_script()

    def on_close(self, *args):
        with open(self.app.get_path('capture_scripts.json'), 'w') as f:
            json.dump(self.scripts, f, indent=1)       

    def on_current_script(self, *args):
        script = self.scripts[self.current_script]
        self.set_exposure_button(script['exposure'])
        self.app.gui.set('filter_button', script['filter'][0])
        self.reset_generator()
        self.app.gui.set('show_reticle', False, update_property=True)
        self.app.gui.set('mean', True, update_property=True)
        if self.current_script == 'flat':
            self.app.gui.set('80', True, update_property=True)
        elif self.current_script == 'frame':
            self.app.gui.set('show_reticle', True, update_property=True)

    def set_exposure_button(self, val):
        self.app.gui.set('exposure_button', exp_to_str(val))

    def get_current_exposure(self, sub_type):
        if sub_type in self.scripts:
            return self.scripts[sub_type]['exposure']
        return None

    def show_exposure_panel(self):
        ''' New in v0.4.6: allow user to type exposure as well as presets
        '''

        if self.current_script in {'flat', 'bias'}:
            return

        content = BoxLayout(size_hint=(None, None), size=(dp(240), dp(300)), 
            orientation='vertical',
            spacing=(dp(0), dp(20))
            )

        grid = GridLayout(size_hint=(None, None), size=(dp(240), dp(240)), cols=4,
            spacing=(dp(5), dp(0)))

        tinput = TextInput(
            text=exp_to_str(self.scripts[self.current_script].get('exposure', 0)),
            size_hint=(1, 1),
            height=dp(24),
            multiline=False,
            font_size='19sp',
            hint_text='type exposure or select preset',
            background_color=[.8, .8, .8, 1])
        tinput.valign = 'top'
        tinput.bind(on_text_validate=self.exposure_selected_from_text)
        content.add_widget(tinput)
        content.add_widget(Label(size_hint=(None, None), size=(dp(240), dp(20))))
        content.add_widget(grid)

        script = self.scripts[self.current_script]

        for e in script['expos']:
            grid.add_widget(ExposureToggle(
                text=exp_to_str(e), 
                state='down' if e == script['exposure'] else 'normal',
                on_press=partial(self.exposure_selected, e, tinput)))

        if self.current_script == 'dark':
            panel_content = ChooseMultiple(choice_type='exposure', capture=self, session=Component.get('Session'))
            panel_content.grid.add_widget(content)
            self.popup = JPopup(title='Choose exposure and temperature', content=panel_content)
        else:
            self.popup = JPopup(title='Choose exposure', content=content)

        self.popup.open()


    def exposure_selected_from_text(self, textinput):
        try:
            expo = str_to_exp(textinput.text)
            self.app.gui.set('exposure_button', exp_to_str(expo))
            self.scripts[self.current_script]['exposure'] = expo
            # don't dismiss popup if dark as user has opportunity to select temperature too
            if self.current_script != 'dark':
                self.exposure_done()
        except Exception as e:
            textinput.foreground_color[0] = 1

    def set_external_details(self, exposure=None, sub_type=None, filt=None):
        self.current_script = sub_type
        script = self.scripts[self.current_script]
        if exposure is not None:
            script['exposure'] = exposure
            self.app.gui.set('exposure_button', exp_to_str(exposure))
        if filt is not None:
            self.app.gui.set('filter_button', filt)

    def exposure_selected(self, expo, tinput, expo_toggle=None):
        self.app.gui.set('exposure_button', exp_to_str(expo))
        self.scripts[self.current_script]['exposure'] = expo
        tinput.text = exp_to_str(expo)
        # don't dismiss popup if dark as user has opportunity to select temperature too
        if self.current_script != 'dark':
            self.exposure_done()

    def exposure_done(self, *args):
        # user has provided exposure
        self.reset_generator()
        self.popup.dismiss()
        # tell stack about this setting so that it can propagate to subs where required
        Component.get('Stacker').exposure_provided_manually(self.scripts[self.current_script]['exposure'])

    def filters_done(self, nsubs=None, *args):
        script = self.scripts[self.current_script]
        script['nsubs'] = nsubs
        self.reset_generator()
        self.popup.dismiss()

    def cancel_multiple(self, typ=None, *args):
        self.popup.dismiss()

    def show_filter_panel(self):

        fw = Component.get('FilterWheel')
        non_empties = {f for f in fw.filters if f != 'empty'}

        if len(non_empties) < 2:
            return
        if self.current_script in {'dark', 'bias'}:
            return

        script = self.scripts[self.current_script]

        fw_layout = FloatLayout(size_hint=(None, None), size=(dp(240), dp(240)))
        rads = math.pi / 180
        for ang, f in zip([0, 40, 80, 120, 160, 200, 240, 280, 320], fw.filters):
            fw_layout.add_widget(FilterToggle(text=f, filter_color=fw.get_color(f),
                on_press=partial(self.filter_selected, f),
                state='down' if f in script['filter'] else 'normal',
                pos_hint={
                    'center_x': ( .8 * math.cos(ang * rads) + 1 ) / 2, 
                    'center_y': ( .8 * math.sin(ang * rads) + 1 ) / 2}))

        if self.current_script != 'seq':
            self.popup = JPopup(title='Choose filter', content=fw_layout)
        else:
            content = ChooseMultiple(choice_type='filter', capture=self, session=Component.get('Session'))
            content.grid.add_widget(fw_layout)
            self.popup = JPopup(title='Choose multiple filters', content=content)
        self.popup.open()

    def filter_selected(self, f, filter_toggle):
        if f == '-':
            return
        script = self.scripts[self.current_script]
        if self.current_script != 'seq':
            self.app.gui.set('filter_button', f)
            script['filter'] = [f]
            self.reset_generator()
            self.popup.dismiss()
        else:
            if filter_toggle.state == 'down':
                script['filter'].append(f)
            else:
                script['filter'].remove(f)

    def light_generator(self):
        script = self.scripts['light']
        yield 'set filter', script['filter'][0]
        yield 'set exposure', script['exposure']
        while True:
            yield 'expose long'

    def seq_generator(self):
        script = self.scripts['seq']
        yield 'set exposure', script['exposure']
        while True:
            for f in Component.get('FilterWheel').order_by_transmission(script['filter']):
                yield 'set filter', f
                for i in range(script['nsubs']):
                    yield 'expose long'

    def frame_generator(self):
        yield 'set filter', 'L'
        yield 'set exposure', self.scripts['frame']['exposure']
        while True:
            yield 'expose short'

    def dark_generator(self):
        yield 'set filter', 'dark'
        yield 'set exposure', self.scripts['dark']['exposure']
        while True:
            yield 'expose long'

    def bias_generator(self):
        yield 'set filter', 'dark'
        yield 'set exposure', self.scripts['bias']['exposure']
        while True:
            yield 'expose bias'

    def flat_generator(self):
        yield 'set filter', self.scripts['flat']['filter'][0]
        yield 'autoflat'
        while True:
            yield 'expose long'

    def reset_generator(self):
        self.generator = getattr(self, '{:}_generator'.format(self.current_script))()

