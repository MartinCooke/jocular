''' Handles capture script menu and script generators.

    Important. Capture scripts are only altered by the user and
    are not changed in response to either new subs coming from
    the watcher, or from previous captures. Thus any subs with
    strange exposures, for example, don't change the capture
    script values. On the other hand, the GUI components for
    exposure, filter and script *are* updated to reflect the 
    most recent sub regardless of where it originates.
'''

import json
from loguru import logger

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import OptionProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDTextButton

from jocular.component import Component
from jocular.exposurechooser import exp_to_str

faf_scripts = ['align', 'focus', 'frame']
light_scripts = ['light', 'seq']
calibration_scripts = ['dark', 'bias', 'autoflat', 'flat']
all_scripts = faf_scripts + light_scripts + calibration_scripts


class CaptureScript(Component):

    current_script = OptionProperty('align', options=all_scripts)
    capture_controls = {'devices', 'script_button', 'exposure_button', 'filter_button'}

    def __init__(self, **args):
        super().__init__(**args)
        self.app = App.get_running_app()
        try:
            with open(self.app.get_path('capture_scripts.json'), 'r') as f:
                self.scripts = json.load(f)
        except:
            # any problem loading => set up afresh
            self.scripts = {}
            for s in all_scripts:
                self.scripts[s] = {
                    'exposure': .1 if s in faf_scripts else 1, 
                    'filter': ['dark' if s in {'bias', 'dark'} else 'L']
                    }
            self.scripts['bias']['exposure'] = .001
            self.scripts['seq']['nsubs'] = 4
            self.scripts['seq']['filter'] = ['B', 'G', 'R', 'L']
            self.save()

        self.chooser = MDBoxLayout(
            orientation='vertical',
            size_hint=(None, None),
            size=(dp(100), dp(240)),
            pos_hint={'center_x': 10, 'center_y': .5})

        self.app.gui.add_widget(self.chooser)

        self.script_buttons = {}
        for s in all_scripts:
            if s in faf_scripts:
                col = .75, .65, .65, 1
            elif s in light_scripts:
                col = .75, .75, .65, 1
            else:
                col = .65, .75, .65, 1
            but = self.script_buttons[s] = MDTextButton(
                text=s, 
                custom_color=col, 
                font_size='18sp',
                on_press=self.script_chosen)
            self.chooser.add_widget(but)

        # initialise via current script once dependencies have been built
        Clock.schedule_once(self.on_current_script, 0)


    def show_menu(self, *args):
        ''' display choice of next script, taking into account what is
            compatible with current subs or not
        '''

        if Component.get('Stacker').is_empty():
            for v in self.script_buttons.values():
                v.disabled = False

        else:
            if self.current_script in calibration_scripts:
                for k in light_scripts + calibration_scripts:
                    self.script_buttons[k].disabled = True
                self.script_buttons[self.current_script].disabled = False

            elif self.current_script in light_scripts:
                for k in calibration_scripts:
                    self.script_buttons[k].disabled = True
       
        self.chooser.pos_hint = {'right': .95, 'center_y': .5}

    def script_chosen(self, item):
        ''' user has selected script, so update and close menu
        '''
        self.current_script = item.text
        self.chooser.pos_hint = {'center_x': 10, 'center_y': .5}

    def save(self, *args):
        ''' save capture scripts
        '''
        try:
            with open(self.app.get_path('capture_scripts.json'), 'w') as f:
                json.dump(self.scripts, f, indent=1)
        except Exception as e:
            logger.exception('Unable to save capture_scripts.json ({:})'.format(e))

    def on_new_object(self, *args):
        ''' default to framing at start
        '''
        self.app.gui.enable(self.capture_controls)
        self.current_script = 'frame'
        self.on_current_script()

    def on_previous_object(self, *args):
        ''' don't allow user to perform captures when loading previous object
        '''
        self.app.gui.disable(self.capture_controls)

    def on_current_script(self, *args):
        ''' carry out any special actions when certain scripts are selected
        '''
        logger.debug('Changed script to {:}'.format(self.current_script))
        self.app.gui.set('script_button', self.current_script)
        self.update()
        if self.current_script == 'align':
            Component.get('View').fit_to_window(zero_orientation=False)
        self.app.gui.set('show_reticle', self.current_script == 'align', update_property=True)
        self.app.gui.set('80' if self.current_script == 'flat' else 'mean' , 
            True, update_property=True)

    def filterwheel_changed(self):
        ''' when filterwheel changes we need to change the available
            filters in the capture scripts and therefore update the scripts
        '''        
        state = Component.get('FilterWheel').get_state()
        filts = list(state['filtermap'].keys())
        logger.debug('filters available in new filterwheel {:}'.format(filts))
        default = ['L'] if 'L' in filts else [f for f in filts if f != '-']
        logger.debug('Default filter is {:}'.format(default))
        if len(default) == 0:
            default = 'L'
        for k, v in self.scripts.items():
            v['filter'] = [f for f in v['filter'] if f in filts]
            if len(v['filter']) == 0:
                v['filter'] = default if k not in {'dark', 'bias'} else ['dark']
        logger.debug('scripts changed to accommodate new filterwheel')
        self.update()

    def update(self):
        ''' update panel, gui elements and save capture script details
        ''' 
        script = self.scripts[self.current_script]
        self.app.gui.set('exposure_button', exp_to_str(script['exposure']))
        self.app.gui.set('filter_button', ''.join(script['filter']))
        self.save()
        self.reset_generator()

    def get_exposure(self):
        ''' called by ExposureChooser, and also by Watcher to get 
            exposure in case user wishes to override
        '''
        return self.scripts[self.current_script]['exposure']

    def get_sub_type(self):
        ''' called by Watcher and Capture
        '''
        if self.current_script in {'seq', 'light'}:
            return 'light'
        if self.current_script in {'flat', 'autoflat'}:
            return 'flat'
        return self.current_script

    def get_filters(self):
        ''' called by FilterChooser
        '''
        return self.scripts[self.current_script]['filter']

    def get_nsubs(self):
        ''' called by FilterChooser
        '''
        return self.scripts[self.current_script].get('nsubs', 1)

    def exposure_changed(self, exposure):
        ''' called by exposure chooser
        '''
        self.scripts[self.current_script]['exposure'] = exposure
        self.update()

    def filter_changed(self, filt, nsubs=None):
        ''' called by filter chooser
        '''
        self.scripts[self.current_script]['filter'] = filt
        if nsubs is not None:
            self.scripts['seq']['nsubs'] = nsubs
        self.update()

    def set_external_details(self, exposure=None, sub_type=None, filt=None):
        ''' Set the details on the interface regardless of what the scripts say. Used
            for previous captures and watched captures.
        '''
        if type(filt) == list:
            filt = ''.join(filt)
        self.app.gui.set('exposure_button', '?' if exposure is None else exp_to_str(exposure))
        self.app.gui.set('filter_button', '?' if filt is None else filt)
        self.app.gui.set('script_button', '?' if sub_type is None else sub_type)


    ''' define scripts using generators
    '''

    def reset_generator(self):
        logger.debug('reset {:} generator'.format(self.current_script))
        self.generator = getattr(self, '{:}_generator'.format(self.current_script))()

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
            for f in Component.get('FilterChooser').order_by_transmission(script['filter']):
                yield 'set filter', f
                for i in range(script['nsubs']):
                    yield 'expose long'

    def frame_generator(self):
        script = self.scripts['frame']
        yield 'set filter', script['filter'][0]
        yield 'set exposure', script['exposure']
        while True:
            yield 'expose short'

    def focus_generator(self):
        script = self.scripts['focus']
        yield 'set filter', script['filter'][0]
        yield 'set exposure', script['exposure']
        while True:
            yield 'expose short'

    def align_generator(self):
        script = self.scripts['align']
        yield 'set filter', script['filter'][0]
        yield 'set exposure', script['exposure']
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

    def autoflat_generator(self):
        yield 'set filter', self.scripts['autoflat']['filter'][0]
        yield 'autoflat'
        while True:
            yield 'expose long'

    def flat_generator(self):
        script = self.scripts['flat']
        yield 'set filter', script['filter'][0]
        yield 'set exposure', script['exposure']
        while True:
            yield 'expose long'

