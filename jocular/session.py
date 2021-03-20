''' Represents session info
'''

import json
from datetime import datetime

from kivy.logger import Logger
from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty, ConfigParserProperty, NumericProperty
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.metrics import dp

from jocular.component import Component
from jocular.widgets import JPopup

Builder.load_string('''

<MyLabel@Label>:
    size_hint: 1, None
    height: dp(24)
    text_size: self.size
    markup: True
    halign: 'left'
    font_size: app.form_font_size

<MyTextInput@TextInput>:
    size_hint: 1, None
    background_color: app.background_color
    foreground_color: app.lowlight_color
    multiline: True
    hint_text_color: app.lowlight_color
    height: dp(28)
    cursor_width: '2sp'
    font_size: app.form_font_size

<ParamValue1@ParamValue>:
    callback: root.parent.edit

<Session>:
    size_hint: None, None
    orientation: 'vertical'
    padding: dp(5), dp(2)
    size: max(dp(250), (app.gui.width - app.gui.height) / 2), app.gui.height / 2
    y: 0
    x: 0 if root.show_session else -self.width

    Button:
        size_hint: 1, 1
        markup: True
        text_size: self.size
        padding: dp(3), dp(1)
        halign: 'left'
        valign: 'bottom'
        font_size: app.info_font_size
        background_color: 0, 0, 0, 0
        color: app.lowlight_color
        height: dp(20)
        text: '[b]Session notes[/b] {:}'.format(root.session_notes)

    ParamValue1:
        param: 'Date'
        value: root.session
    ParamValue1:
        param: 'Temp.'
        value: '' if root.temperature is None else '{:}\N{DEGREE SIGN}C'.format(root.temperature)
    ParamValue1:
        param: 'SQM'
        value: '' if root.SQM is None else '{:.2f} mag/arcsec^2'.format(root.SQM)
    ParamValue1:
        param: 'Seeing'
        value: '{:}'.format(root.seeing if root.seeing else '')
    ParamValue1:
        param: 'Transp.'
        value: '{:}'.format(root.transparency if root.transparency else '')
    ParamValue1:
        param: 'Scope'
        value: root.telescope
    ParamValue1:
        param: 'Camera'
        value: root.camera

<SessionInfo>:
    orientation: 'vertical'
    size_hint: None, None
    size: dp(300), dp(500)
    spacing: dp(5)

    MyLabel:
        text: 'Session notes:'
    MyTextInput:
        id: _notes
        hint_text: 'not specified'
        text: root.session.session_notes
        multiline: True
        size_hint: 1, None
        height: dp(80)
        on_text: root.session.session_notes = self.text

    MyLabel:
        text: 'Seeing:'
    MyTextInput:
        id: _seeing
        hint_text: ' not specified'
        text: root.session.seeing
        on_text: root.session.seeing = self.text

    MyLabel:
        text: 'Transparency:'
    MyTextInput:
        id: _transparency
        hint_text: 'not specified'
        text: root.session.transparency
        on_text: root.session.transparency = self.text

    MyLabel:
        text: 'Temperature {:}\N{DEGREE SIGN}C'.format(_temperature.value) if _temperature.value > -26 else 'Temperature not set'
    Slider:
        size_hint: 1, None
        height: dp(30)
        id: _temperature
        value: root.session.temperature if root.session.temperature is not None else -26
        on_value: root.session.temperature = self.value if self.value > -26 else None
        min: -26
        max: 40
        step: 1

    MyLabel:
        text: 'SQM {:.2f} mag/arcsec^2'.format(_sqm.value) if _sqm.value > 15.9999 else 'SQM not set'
    Slider:
        size_hint: 1, None
        height: dp(24)
        id: _sqm
        value: root.session.SQM if root.session.SQM is not None else 15.9999
        on_value: root.session.SQM = self.value if self.value > 16 else None
        min: 15.9
        max: 22
        step: .01

    MyLabel:
        text: 'Telescope:'
    MyTextInput:
        id: _scope
        hint_text: 'not specified'
        text: root.session.telescope
        on_text: root.session.telescope = self.text

    MyLabel:
        text: 'Camera:'
    MyTextInput:
        id: _camera
        hint_text: 'not specified'
        text: root.session.camera
        on_text: root.session.camera = self.text

    BoxLayout:
        size_hint: 1, None
        height: dp(40)
        Button:
            text: 'Close'
            size_hint: 1, .8
            on_press: root.session.done()

''')

class SessionInfo(BoxLayout):
    def __init__(self, session, **kwargs):
        self.session = session
        super().__init__(**kwargs)

date_time_format = '%d %b %y %H:%M'

def datenow():
    return datetime.now().strftime(date_time_format)

def hours_since_date(mydate):
    return (datetime.now() - datetime.strptime(mydate, date_time_format)).total_seconds()/3600

class Session(BoxLayout, Component):

    session = StringProperty('')
    SQM = NumericProperty(None, allownone=True)
    temperature = NumericProperty(None, allownone=True)
    seeing = StringProperty('')
    transparency = StringProperty('')
    session_notes = StringProperty('')
    telescope = StringProperty('')
    camera = StringProperty('')

    retain_hours =  ConfigParserProperty(3, 'Session', 'retain_hours', 'app', val_type=float)
    is_new_object = BooleanProperty(False)
    show_session = BooleanProperty(False)

    props = ['SQM', 'temperature', 'seeing', 'transparency', 'session_notes', 
        'telescope', 'camera', 'session']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.app.gui.add_widget(self, index=2) 

    def on_new_object(self):
        self.is_new_object = not Component.get('ObjectIO').existing_object
        # move this to see if I can cancel session clock more reliably
        if hasattr(self, 'session_clock'):
            self.session_clock.cancel()
        if self.is_new_object:
            self.load_session()
        else:
            settings = Component.get('Metadata').get(self.props)
            self.apply_settings(settings)

    def load_session(self):
        try:
            with open(self.app.get_path('last_session.json'), 'r') as f:
                session = json.load(f)
            if hours_since_date(session['session']) < self.retain_hours:
                self.apply_settings(session)
            else:
                # start fresh session but restore scope/camera details
                self.create_new_session()
                self.telescope = session.get('telescope', '') 
                self.camera = session.get('camera', '')
        except Exception as e:
            # any problems we just start a fresh session
            Logger.debug('Session: problem loading session data, so recreating {:}'.format(e))
            self.create_new_session()

        # create date and clock to update it
        self.session = datetime.now().strftime(date_time_format)
        self.session_clock = Clock.schedule_interval(self.update_time, 1.0)

    def create_new_session(self):
        self.SQM = None
        self.temperature = None
        self.seeing = ''
        self.transparency = ''
        self.session_notes = ''
        self.telescope = ''
        self.camera = ''

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

    def apply_settings(self, settings):
        self.create_new_session()
        for p in self.props:
            if p in settings:
                setattr(self, p, settings[p])

    def save_session(self):
        Logger.debug('Session: saving session')
        with open(self.app.get_path('last_session.json'), 'w') as f:
            json.dump(self.current_session_info(), f, indent=1)    

    def on_save_object(self):

        # save properties
        for p in ['SQM', 'temperature', 'seeing', 'transparency', 'session_notes', 'telescope', 'camera']:
            Component.get('Metadata').set(p, getattr(self, p))

        # only update last session if live rather than previous
        if self.is_new_object:
            self.save_session()

    def update_time(self, *args):
        self.session = datetime.now().strftime('%d %b %y %H:%M:%S')

    def edit(self, *args):
        content = SessionInfo(self)
        self.popup = JPopup(title='Session information', content=content, posn='bottom-left')
        self.popup.open()

    def done(self, *args):
        self.popup.dismiss()
        self.changed = not Component.get('Stacker').is_empty() and (
            self.temperature != Component.get('Metadata').get('temperature', default=None) or \
            self.SQM != Component.get('Metadata').get('SQM', default=None) or \
            self.seeing.strip() != Component.get('Metadata').get('seeing', default='') or \
            self.transparency.strip() != Component.get('Metadata').get('transparency', default='') or \
            self.telescope.strip() != Component.get('Metadata').get('telescope', default='') or \
            self.camera.strip() != Component.get('Metadata').get('camera', default='')
            )
        if self.is_new_object:
            self.save_session()

    def on_touch_down(self, touch):
        # print(' TD in Session')
        if self.collide_point(*touch.pos) and touch.pos[0] < dp(100) and self.app.showing == 'main':
            return super().on_touch_down(touch)
        return False
