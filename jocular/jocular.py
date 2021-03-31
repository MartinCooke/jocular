''' Main app, called after some checks by startjocular
'''

import os
import json
import sys
from pathlib import Path

from kivy.app import App
from kivy.logger import Logger
from kivy.properties import (
    ListProperty,
    NumericProperty,
    ConfigParserProperty,
    OptionProperty,
    StringProperty,
)
from kivy.uix.settings import SettingsWithSidebar
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import LabelBase

from jocular import __version__

from jocular.component import Component
from jocular.gui import GUI


class Jocular(App):

    showing = OptionProperty(
        'main', options=['main', 'observing list', 'calibration', 'observations']
    )

    highlight_color = ListProperty([1, 1, 1, 1])
    lowlight_color = ListProperty([0.5, 0.5, 0.5, 1])
    hint_color = ListProperty([0.25, 0.25, 0.25, 1])
    lever_color = ListProperty([0.32, 0.32, 0.32, 1])
    background_color = ListProperty([0.06, 0.06, 0.06, 0])  # was 1 transp
    line_color = ListProperty([0.3, 0.3, 0.3, 1])  # used in Obj and Table only

    data_dir = StringProperty(None)

    # quick way to ensure there is a Startup section
    dummy_startup = ConfigParserProperty('dummy', 'Startup', 'dummy', 'app')

    brightness = NumericProperty(1)
    transparency = NumericProperty(0)

    color_codes = {
        'white': [0.8, 0.8, 0.79, 1],
        'red': [0.74, 0.25, 0.3, 1],
        'blue': [0.57, 0.66, 0.82, 1],
        'green': [0.53, 0.69, 0.29, 1],
        'yellow': [0.94, 0.76, 0.31, 1],
    }

    def get_application_config(self):
        return super(Jocular, self).get_application_config(
            os.path.join(self.data_dir, '%(appname)s.ini')
        )

    def get_path(self, name):
        # centralised way to handle accessing resources Jocular needs

        #  if path, return path to data dir, else return path to resource
        if name in [
            'captures',
            'calibration',
            'snapshots',
            'watched',
            'deleted',
            'exports',
            'catalogues',
        ]:
            path = os.path.join(self.data_dir, name)
            try:
                if not os.path.exists(path):
                    Logger.debug('Jocular: creating path {:} -> {:}'.format(name, path))
                    os.mkdir(path)
                return os.path.join(self.data_dir, name)
            except Exception as e:
                sys.exit('Cannot create path {:} ({:})'.format(path, e))
        elif name == 'dsos':
            return os.path.join(self.directory, 'dsos')
        elif name in [
            'observing_list.json',
            'observing_notes.json',
            'last_session.json',
            'capture_scripts.json',
            'previous_observations.json'
        ]:
            return os.path.join(self.data_dir, name)
        elif name == 'shipped_capture_scripts.json':
            return os.path.join(self.directory, 'resources', 'capture_scripts.json')
        elif name == 'libusb':
            return os.path.join(self.directory, 'resources', 'libusb-1.0.dll')
        elif name == 'star_db':
            return os.path.join(self.data_dir, 'platesolving', 'star_tiles.npz')
        elif name == 'dso_db':
            return os.path.join(self.data_dir, 'platesolving', 'dso_tiles')
        else:
            return os.path.join(self.directory, 'resources', name)

    def on_brightness(self, *args):
        for c in [
            'hint_color',
            'highlight_color',
            'lowlight_color',
            'line_color',
            'lever_color',
        ]:
            getattr(self, c)[-1] = self.brightness

    def build_config(self, config):
        # NB this is called before build

        # get user data directory
        try:
            with open(os.path.join(str(Path.home()), '.jocular'), 'r') as f:
                self.data_dir = f.read().strip()
        except Exception as e:
            Logger.exception('Jocular: problem reading user data dir ({:})'.format(e))
            sys.exit()

        self.use_kivy_settings = False

        try:
            with open(self.get_path('configurables.json'), 'r') as f:
                self.configurables = json.load(f)
        except Exception as e:
            Logger.exception('Jocular: cannot read configurables.json ({:})'.format(e))
            sys.exit()

        #  extract all defaults and delete them so settings panel works
        defaults = {}
        for v in self.configurables.values():
            for l in v:
                if ('section' in l) and ('default' in l):
                    sec = l['section']
                    if sec in defaults:
                        defaults[sec][l['key']] = l['default']
                    else:
                        defaults[sec] = {l['key']: l['default']}
                    del l['default']
                if 'component' in l:
                    del l['component']

        for k, v in defaults.items():
            config.setdefaults(k, v)

    def build_settings(self, settings):
        for panel, subsettings in self.configurables.items():
            settings.add_json_panel(panel, self.config, data=json.dumps(subsettings))

    def on_config_change(self, config, section, key, val):
        self.set_param(section, key, val)

    # initially we will call this with all params to handle settings
    def set_param(self, section, key, val=None):

        if val == None:
            val = self.config.get(section, key)

        if section == 'Font sizes':
            setattr(self, '{:}_font_size'.format(key), '{:}sp'.format(val))

        elif section == 'Colours and graylevels':
            if key in ['lowlight_color', 'lever_color']:
                lg = max(30, min(int(val), 100)) / 100
                setattr(self, key, [lg, lg, lg, 1])
            elif key == 'highlight_color':
                self.highlight_color = self.color_codes.get(val, 'white')

        elif section == 'Geometry':
            Window.size = (
                int(self.config.get(section, 'initial_width')),
                int(self.config.get(section, 'initial_height')),
            )

        elif section == 'Filters':
            Component.get('FilterWheel').update_filter(key, val)

    def build(self):


        self.title = 'Jocular v{:}'.format(__version__)

        LabelBase.register(name='Jocular', fn_regular=self.get_path('jocular4.ttf'))

        self.settings_cls = SettingsWithSidebar

        #  apply settings
        for fs in ['ring', 'info', 'form']:
            self.set_param('Font sizes', fs)

        for fs in ['lowlight_color', 'lever_color', 'highlight_color']:
            self.set_param('Colours and graylevels', fs)

        self.set_param('Geometry', 'initial_width')

        # generate GUI so that it exists before we add components
        self.gui = GUI(self.config)

        # draw GUI
        Clock.schedule_once(self.gui.draw, -1)

        return self.gui

    def on_stop(self):
        Component.close()
        self.gui.on_close()
        self.config.write()

    # reset showing to main when any table is hidden
    def table_hiding(self, *args):
        self.showing = 'main'
