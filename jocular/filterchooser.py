''' Allows user to select one or more filters to apply
'''

import math
import numpy as np
from functools import partial
from loguru import logger

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.lang import Builder
from kivy.properties import ListProperty

from jocular.component import Component
from jocular.widgets import Panel, LabelR

Builder.load_string('''

<FilterToggle>:
    canvas.before:
        Color:
            rgba: .15, .15, .15, 1
        Ellipse:
            pos: self.pos
            size: self.width, self.height
        Color:
            rgb: self.filter_color
            a: .7 if self.state == 'down' else .2
        Ellipse:
            pos: self.x + 2, self.y + 2
            size: self.width - 5, self.height - 5
    markup: True
    color: (.8, .8, .8, 1) if self.state == 'down' else (0, 0, 0, 1)
    disabled: self.text == '-'
    background_color: 0, 0, 0, 0
    size: dp(70), dp(70)
    font_size: '24sp' if self.state == 'down' else '18sp'
    size_hint: None, None
''')

class FilterToggle(ToggleButton):
  filter_color = ListProperty([1, 1, 1, 1])

class FilterChooser(Panel, Component):

    filter_properties = {
        "L": {"color": (0.8, 0.8, 0.8), "bg_color": (0.1, 0.1, 0.1, 0.3)},
        "R": {"color": (1, 0, 0), "bg_color": (1, 0, 0, 0.6)},
        "G": {"color": (0, 1, 0), "bg_color": (0, 1, 0, 0.5)},
        "B": {"color": (0, 0, 1), "bg_color": (0, 0, 1, 0.5)},
        "dark": {"color": (0.2, 0.2, 0.2), "bg_color": (0, 0, 0, 0)},
        "Ha": {"color": (0.8, 0.3, 0.3), "bg_color": (1, 0.6, 0.6, 0.5)},
        "OIII": {"color": (0.2, 0.6, 0.8), "bg_color": (0, 0, 0, 0)},
        "SII": {"color": (0.1, 0.8, 0.4), "bg_color": (0, 0, 0, 0)},
        "spec": {"color": (0.7, 0.6, 0.2), "bg_color": (0, 0, 0, 0)},
        "-": {"color": (0.15, 0.15, 0.15), "bg_color": (0, 0, 0, 0)},
    }

    def __init__(self, **args):
        super().__init__(**args)
        self.app = App.get_running_app()
        self.nsubs = 4
        self.build()

    def on_show(self):
        # ensure filterchooser reflects current filterwheel device
        state = Component.get('FilterWheel').get_state()
        logger.debug('state from FW {:}'.format(state))
        logger.debug('previous state {:}'.format(self.state))
        if state['filtermap'] != self.state['filtermap']:
            logger.debug('rebuilding FilterChooser')
            # need to rebuild
            self.state = state
            self.clear_widgets()
            self.build_fw()
        self.update_panel()

    def build(self, dt=None):
        self.state = Component.get('FilterWheel').get_state()
        if len(self.state['filtermap']) > 0:
            self.build_fw()
        self.app.gui.add_widget(self)

    def build_fw(self, dt=None):
        ''' Generate filterwheel selection widget
        '''

        self.title = Label(size_hint=(1, 1), font_size='24sp')
        self.add_widget(self.title)
        pos2filter = {int(p):f for f, p in self.state['filtermap'].items()}
        n_positions = 9
        angs = np.linspace(0, 2*math.pi, n_positions + 1) # [:-1]
        fw_layout = FloatLayout(size_hint=(None, None), size=(dp(300), dp(300)))
        self.buts = {}
        for i in range(n_positions):
            pos_hint={ 
                'center_x': ( .8 * math.cos(angs[i]) + 1 ) / 2, 
                'center_y': ( .8 * math.sin(angs[i]) + 1 ) / 2
                }
            pos = i + 1
            if pos in pos2filter:
                f = pos2filter[pos]
                b = self.buts[f] = FilterToggle(
                        text=f, filter_color=self.filter_properties[f]['color'], 
                        on_press=partial(self.filter_selected, f),
                        pos_hint=pos_hint)
            else:
                b = FilterToggle(text='-', filter_color=(0, 0, 0, 1), 
                        pos_hint=pos_hint, disabled=True)
            fw_layout.add_widget(Label(text=str(i+1),
                pos_hint={ 
                'center_x': ( .48 * math.cos(angs[i]) + 1 ) / 2, 
                'center_y': ( .48 * math.sin(angs[i]) + 1 ) / 2
                }))
            fw_layout.add_widget(b)

        bh = BoxLayout(padding=(10, 10), size_hint=(1, 6))
        bh.add_widget(Label(size_hint=(1, 1)))        
        bh.add_widget(fw_layout)
        bh.add_widget(Label(size_hint=(1, 1)))        
        self.add_widget(bh)

        bh = self.nsubs_box = BoxLayout(padding=(10, 10), size_hint=(1, 1))
        self.nsubs_label = LabelR(text='subs/filter', size_hint=(.3, 1))
        bh.add_widget(self.nsubs_label)
        self.nsubs_slider = Slider(min=1, max=12, value=4, step=1, size_hint=(.5, 1))
        self.nsubs_slider.bind(value=self.nsubs_changed)
        bh.add_widget(self.nsubs_slider)
        bh.add_widget(Button(text='done', size_hint=(.2, 1), on_press=self.done))
        self.add_widget(bh)

    def done(self, *args):
        filts = [f for f, b in self.buts.items() if b.state == 'down']
        if len(filts) > 0:
            Component.get('CaptureScript').filter_changed(filts, nsubs=self.nsubs)
        self.hide()

    def filter_selected(self, filt, but):
        # set exposure on GUI and on scripts panel
        if Component.get('CaptureScript').current_script == 'seq':
            logger.debug('toggled filter {:}'.format(filt))
        else:
            logger.debug('selected filter {:}'.format(filt))
            Component.get('CaptureScript').filter_changed([filt])
            self.hide()

    def update_panel(self):
        filters = Component.get('CaptureScript').get_filters()
        for f, but in self.buts.items():
            but.state = 'down' if f in filters else 'normal'
        nsubs = Component.get('CaptureScript').get_nsubs()
        if nsubs > 1:
            self.nsubs_slider.value = nsubs
            self.nsubs_label.text = '{:} subs/filter'.format(nsubs)
            self.nsubs = nsubs
            self.title.text = 'Select filters'
            self.nsubs_box.disabled = False
        else:
            self.title.text = 'Select a filter'
            self.nsubs_box.disabled = True

    def nsubs_changed(self, slider, nsubs):
        self.nsubs_label.text = '{:} subs/filter'.format(nsubs)
        self.nsubs = nsubs

    def order_by_transmission(self, filts):
        if type(filts) != list:
            filts = [filts]
        t_order = ['SII', 'OIII', 'Ha', 'B', 'G', 'R', 'L']
        return [f for f in t_order if f in filts]
