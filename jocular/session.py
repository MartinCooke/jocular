''' Represents session info
'''

import json
import math
from datetime import datetime
from loguru import logger

from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.clock import Clock
from kivy.lang import Builder
from kivymd.uix.boxlayout import MDBoxLayout

from jocular.component import Component
from jocular.settingsmanager import Settings


Builder.load_string('''

<MyBoxLayout@BoxLayout>:
    size_hint: (1, None)
    # height: '{:}dp'.format(int(app.form_font_size[:-2]) + 20)
    height: '42dp'

<SessionInfo>:
    padding: '10dp'
    adaptive_height: True
    #adaptive_width: True
    pos_hint: {'y': 0, 'x': 0} if root.session.show_session else {'y': 0, 'right': -1000} 
    size_hint: None, None
    orientation: 'vertical'
    spacing: "10dp"

    BoxLayout:
        size_hint: (1, None)
        height: '48dp'

        JTextField:
            width: '180dp'
            height: '32dp'
            #helper_text: ''
            on_focus: root.session.session_changed(self.text) if not self.focus else None
            text: root.session.session

    MyBoxLayout:
        JTextField:
            hint_text: 'transparency'
            width: '220dp'
            #helper_text: 'e.g. high clouds, good'
            on_focus: root.session.transparency_changed(self.text) if not self.focus else None
            text: root.session.transparency


    MyBoxLayout:
        JTextField:
            hint_text: 'seeing'
            width: '240dp'
            #helper_text: 'e.g. poor, excellent'
            on_focus: root.session.seeing_changed(self.text) if not self.focus else None
            text: root.session.seeing

    MyBoxLayout:
        JTextField:
            hint_text: 'temperature'
            #helper_text: 'e.g. 5C or 45F'
            on_focus: root.session.temperature_changed(self.text) if not self.focus else None
            text: root.session.formatted_temperature

        JTextField:
            width: '140dp'
            hint_text: 'brightness'
            #helper_text: 'e.g. 19.23 or 4.5'
            on_focus: root.session.sky_brightness_changed(self.text) if not self.focus else None
            text: root.session.formatted_sky_brightness

    MyBoxLayout:
        JTextField:
            width: '140dp'
            hint_text: 'scope'
            #helper_text: ''
            on_focus: root.session.telescope_changed(self.text) if not self.focus else None
            text: root.session.telescope

        JTextField:
            width: '180dp'
            hint_text: 'camera'
            #helper_text: ''
            on_focus: root.session.camera_changed(self.text) if not self.focus else None
            text: root.session.camera

    BoxLayout:
        size_hint: (1, None)
        height: '72dp'
        JTextField:
            id: _name
            width: '400dp'
            height: '64dp'
            multiline: True
            hint_text: 'session notes'
            #helper_text: ''
            text: root.session.session_notes
            on_focus: root.session.session_notes_changed(self.text) if not self.focus else None

''')


date_time_format = '%d %b %y %H:%M'

def datenow():
    return datetime.now().strftime(date_time_format)

def hours_since_date(mydate):
    return (datetime.now() - datetime.strptime(mydate, date_time_format)).total_seconds()/3600

# from http://unihedron.com/projects/darksky/NELM2BCalc.html
def SQM_to_NELM(sqm):
    return 7.93 - 5 * math.log(10 ** (4.316-(sqm / 5)) + 1)

def NELM_to_SQM(nelm):
    return 21.58 - 5 * math.log(10 ** (1.586 - nelm / 5) - 1)


class SessionInfo(MDBoxLayout):
    def __init__(self, session, **kwargs):
        self.session = session
        super().__init__(**kwargs)


class Session(Component, Settings):

    save_settings = ['show_session']

    session = StringProperty('')
    sky_brightness = NumericProperty(None, allownone=True)
    temperature = NumericProperty(None, allownone=True)
    seeing = StringProperty('')
    transparency = StringProperty('')
    session_notes = StringProperty('')
    telescope = StringProperty('')
    camera = StringProperty('')
    is_new_object = BooleanProperty(False)
    show_session = BooleanProperty(False)
    sky_brightness_units = StringProperty('SQM')
    temperature_units = StringProperty('Centigrade')
    formatted_temperature = StringProperty('')
    formatted_sky_brightness = StringProperty('')
    retain_hours =  NumericProperty(3)

    configurables = [
        ('retain_hours', {'name': 'time to retain session information?', 'float': (0, 48, 1),
            'help': 'Session information persists for some time to handle restarts of the program',
            'fmt': '{:.0f} hours'}),
        ('temperature_units', {
            'name': 'temperature units', 
            'options': ['Centigrade', 'Fahrenheit'],
            'help': 'temperatures are stored internally in degrees C'
            }),
        # ('sky_brightness_units', {
        #     'name': 'sky brightness units', 
        #     'options': ['SQM', 'NELM'],
        #     'help': 'brightness stored internally in SQM'
        #     })
        ]

    # all editable properties
    props = ['sky_brightness', 'temperature', 'seeing', 'transparency', 'session_notes', 
        'telescope', 'camera', 'session']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.session_info = SessionInfo(self)
        self.app.gui.add_widget(self.session_info)

    def describe(self):
        ''' return information for Snapshotter
        '''

        return [
            self.session, 
            self.formatted_sky_brightness,
            self.formatted_temperature,
            'seeing {:}'.format(self.seeing) if self.seeing else None,
            'transp {:}'.format(self.transparency) if self.transparency else None
            ]

    def theme_changed(self, *args):
        self.session_info.theme_changed()

    def temperature_changed(self, temp):
        ''' called when temperature field is altered; parse various formats
            with and without degrees and C or F
        '''
        temp = temp.lower().strip()
        try:
            if len(temp) == 0:
                self.temperature = None
            else:
                units = 'F' if temp.endswith('f') else 'C'
                if temp[-1] in {'f', 'c'}:
                    temp = temp[:-1].strip()
                if temp[-1] == '\N{DEGREE SIGN}':
                    temp = temp[:-1].strip()
                temp = int(temp)
                self.temperature = temp if units == 'C' else (temp - 32) / 1.8
        except Exception as e:
            self.temperature = None
            logger.exception(e)
        self.on_temperature()
        self.check_for_change() 

    def get_temperature(self):
        ''' return string temperature in C or F, or empty string if error
            in conversion or non-existent temperature
        '''
        try:
            temp = int(self.temperature)
        except:
            return ''
        if self.temperature_units == 'Centigrade':
            return '{:.0f}\N{DEGREE SIGN}C'.format(temp)
        return '{:.0f}\N{DEGREE SIGN}F'.format(temp*1.8 + 32)

    @logger.catch()
    def on_temperature(self, *args):
        ''' whenever temperature changes, ensure formatted temperature
            is updated
        '''
        self.formatted_temperature = 'xyz'  # forces an update
        self.formatted_temperature = self.get_temperature()

    def on_temperature_units(self, *args):
        ''' whenever user changes temperature preferences in config screen,
            ensure it is applied immediately
        '''
        self.formatted_temperature = self.get_temperature()

    ''' similar methods for sky brightness
    '''

    def sky_brightness_changed(self, bright):
        bright = bright.lower().strip()
        try:
            if len(bright) == 0:
                self.sky_brightness = None
            else:
                units= 'SQM'
                if bright.endswith('nelm'):
                    units = 'NELM'
                    bright = bright[:-4].strip()
                elif bright.endswith('sqm'):
                    bright = bright[:-3].strip()
                bright = float(bright)
                self.sky_brightness = bright if units == 'SQM' else SQM_to_NELM(bright)
        except Exception as e:
            self.sky_brightness = None
        self.on_sky_brightness()
        self.check_for_change() 

    def get_sky_brightness(self):
        try:
            bright = float(self.sky_brightness)
        except:
            return ''
        if self.sky_brightness_units == 'SQM':
            return '{:.2f} sqm'.format(bright)
        return '{:.1f} nelm'.format(NELM_to_SQM(bright))

    def on_sky_brightness(self, *args):
        self.formatted_sky_brightness = 'xyz'
        self.formatted_sky_brightness = self.get_sky_brightness()

    def on_sky_brightness_units(self, *args):
        self.formatted_sky_brightness = self.get_sky_brightness()

    ''' remaining changes
    '''  

    def session_notes_changed(self, session_notes):
        self.session_notes = session_notes
        self.check_for_change() 

    def seeing_changed(self, seeing):
        self.seeing = seeing
        self.check_for_change() 

    def transparency_changed(self, transparency):
        self.transparency = transparency
        self.check_for_change() 

    def telescope_changed(self, telescope):
        ''' Since we persist this between sessions, ensure we save
            the session on any change; likewise with camera
        '''
        self.telescope = telescope
        self.check_for_change()
        self.save_session()

    def camera_changed(self, camera):
        self.camera = camera
        self.check_for_change()
        self.save_session() 

    def session_changed(self, session):
        self.session = session
        self.check_for_change() 

    @logger.catch()
    def check_for_change(self):
        ''' Check if any property has changed and stack is not empty
            For new objects, don't check if session has changed as clock is
            continually changing! 
        '''
        props = self.props
        if self.is_new_object:
            props = set(props) - {'session'}

        changes = [getattr(self, p) != self.initial_values.get(p, '') for p in props]
        self.changed = 'session props' if any(changes) else ''


    ''' main methods for handling new/previous sessions
    '''

    @logger.catch()
    def on_new_object(self):
        self.is_new_object = True
        self.cancel_session_clock()
        self.load_session()
        self.initial_values = {p: getattr(self, p) for p in self.props}

    @logger.catch()
    def on_previous_object(self):
        ''' apply previous session settings, keeping a record so changes can be monitored
        '''
        self.is_new_object = False
        self.cancel_session_clock()
        settings = Component.get('Metadata').get(self.props)
        self.apply_session_settings(settings)
        self.initial_values = {p: getattr(self, p) for p in self.props}

    def cancel_session_clock(self):
        if hasattr(self, 'session_clock'):
            self.session_clock.cancel()

    def load_session(self):
        ''' Try to get information from last session and apply it, otherwise
            create a new session
        '''
        try:
            with open(self.app.get_path('last_session.json'), 'r') as f:
                session = json.load(f)
            if hours_since_date(session['session']) < self.retain_hours:
                self.apply_session_settings(session)
            else:
                # start fresh session but restore scope/camera details
                self.create_empty_session()
                self.telescope = session.get('telescope', '') 
                self.camera = session.get('camera', '')
        except Exception as e:
            # any problems we just start a fresh session
            logger.debug('problem loading session: recreating {:}'.format(e))
            self.create_empty_session()
            self.save_session()

        # create date and clock to update it
        self.session = datetime.now().strftime(date_time_format)
        self.session_clock = Clock.schedule_interval(self.update_time, 1.0)

    def create_empty_session(self):
        ''' set all properties except session to empty/None
        '''
        self.temperature = None
        self.sky_brightness = None
        for p in set(self.props) - {'session', 'temperature', 'sky_brightness'}:
            setattr(self, p, '')

    def get_session(self):
        # accessor method that strips off seconds if present
        if self.session.count(':') == 2:
            return self.session[:-3]
        else:
            return self.session

    def current_session_info(self):
        session = {}
        for p in self.props:
            v = getattr(self, p)
            if v:
                session[p] = v
        session['session'] = self.get_session()
        return session

    def apply_session_settings(self, settings):
        ''' apply 'settings', by clearing existing settings and
            overriding
        '''
        self.create_empty_session()
        for p in self.props:
            if p in settings:
                setattr(self, p, settings[p])

    @logger.catch()
    def save_session(self):
        logger.debug('saving session')
        with open(self.app.get_path('last_session.json'), 'w') as f:
            json.dump(self.current_session_info(), f, indent=1)    

    @logger.catch()
    def on_save_object(self):

        logger.debug('saving properties to metadata')

        # save properties
        for p in self.props:
            Component.get('Metadata').set(p, getattr(self, p))

        # only update last session if live rather than previous
        if self.is_new_object:
            self.save_session()

    def update_time(self, *args):
        self.session = datetime.now().strftime('%d %b %y %H:%M:%S')
