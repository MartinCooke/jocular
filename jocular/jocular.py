''' Main app. Mainly used for marshalling resource provision.
'''

import os
import json
import sys
import platform

from kivymd.app import MDApp
from kivy.metrics import dp
from kivy.config import Config
from loguru import logger

from kivy.properties import ListProperty, NumericProperty, OptionProperty, StringProperty
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import LabelBase

from jocular import __version__
from jocular.component import Component
from jocular.gui import GUI

from jocular.utils import get_datadir, start_logging

from jocular.appearance import sat_to_hue

class Jocular(MDApp):

    showing = OptionProperty(
        'main', options=['main', 'observing list', 'calibration', 'observations']
    )

    lowlight_color = ListProperty([0.5, 0.5, 0.5, 1])
    hint_color = ListProperty([0.25, 0.25, 0.25, 1])
    lever_color = ListProperty([0.32, 0.32, 0.32, 1])
    background_color = ListProperty([0.06, 0.06, 0.06, 0])  # was 1 transp
    line_color = ListProperty([0.3, 0.3, 0.3, 1])  # used in Obj and Table only

    ring_font_size = StringProperty('14sp')
    # info_font_size = StringProperty('14sp')
    form_font_size = StringProperty('15sp')

    tooltip_delay = NumericProperty(2)

    data_dir = StringProperty(None)

    subdirs = {'captures', 'calibration', 'snapshots', 'deleted', 
        'exports', 'catalogues', 'settings', 'logs'}

    brightness = NumericProperty(1)
    transparency = NumericProperty(0)

    def get_dir_in_datadir(self, name):
        path = os.path.join(self.data_dir, name)
        try:
            if not os.path.exists(path):
                logger.debug('Creating path {:}'.format(path))
                os.mkdir(path)
            return os.path.join(self.data_dir, name)
        except Exception as e:
            logger.exception('Cannot create path {:} ({:})'.format(path, e))
            sys.exit('Cannot create subdirectory of Jocular data directory')

    def get_path(self, name):
        ''' centralised way to access resources
        '''

        # if path, return path to data dir, else return path to resource
        if name in self.subdirs:
            return self.get_dir_in_datadir(name)

        # jocular's own resources
        elif name == 'dsos':
            return os.path.join(self.directory, 'dsos')

        # example captures
        elif name == 'example_captures':
            return os.path.join(self.directory, 'example_captures')

        elif name in {'configurables.json', 'gui.json', 'object_types.json'}:
            return os.path.join(self.directory, 'resources', name)

        # jocular settings
        elif name.endswith('.json'):
            return os.path.join(self.get_dir_in_datadir('settings'), name)

        # specific files
        elif name == 'libusb':
            return os.path.join(self.directory, 'resources', 'libusb-1.0.dll')
        elif name == 'star_db':
            return os.path.join(self.data_dir, 'platesolving', 'star_tiles.npz')
        elif name == 'dso_db':
            return os.path.join(self.data_dir, 'platesolving', 'dso_tiles')
        elif name == 'ASI':
            # NB these need keeping up to date so perhaps better externalised
            if sys.platform.startswith('linux'):
                asi = os.path.join('linux', 'libASICamera2.so.1.21')
                # asi = 'libASICamera2.so.1.18'
            elif sys.platform.startswith('darwin'):
                asi = os.path.join('mac', 'libASICamera2.dylib.1.21')
            else:
                # detect if 32 or 64 bit windows
                bits, _ = platform.architecture()
                if bits.startswith('64'):
                    asi = os.path.join('win64', 'ASICamera2.dll')
                else:
                    asi = os.path.join('win32', 'ASICamera2.dll')
            return os.path.abspath(os.path.join(self.directory, 'resources', asi))

        # everything else is in jocular's own resources
        else:
            return os.path.join(self.directory, 'resources', name)

    def on_brightness(self, *args):
        for c in ['hint_color', 'lowlight_color', 'line_color', 'lever_color']:
            getattr(self, c)[-1] = self.brightness

    @logger.catch()
    def build(self):

        self.data_dir = get_datadir()
        if self.data_dir is not None:
            start_logging(self.get_path('logs'))

        self.title = 'Jocular v{:}'.format(__version__)
        self.theme_cls.theme_style = "Dark"     

        LabelBase.register(name='Jocular', fn_regular=self.get_path('jocular4.ttf'))

        try:
            with open(self.get_path('Appearance.json'), 'r') as f:
                settings = json.load(f)
        except:
            # set up initial values for settings
            settings = {'highlight_color': 'BlueGray',  'colour_saturation': 56}

        # apply settings      
        for p, v in settings.items():
            if p == 'highlight_color':
                self.theme_cls.accent_palette = v
                self.theme_cls.primary_palette = v
            elif p.endswith('_color'):
                lg = v / 100
                setattr(self, p, [lg, lg, lg, 1])
            elif p.endswith('font_size'):
                setattr(self, p, '{:}sp'.format(v))
            elif p == 'transparency':
                self.transparency = int(v) / 100
            elif p == 'colour_saturation':
                self.theme_cls.accent_hue = sat_to_hue(v)
            elif p == 'tooltip_delay':
                self.tooltip_delay = v

        self.gui = GUI()

        # draw GUI
        Clock.schedule_once(self.gui.draw, -1)

        return self.gui


    @logger.catch()
    def on_stop(self, exception=None):
        if exception is None:
            logger.info('normal close down')
        else:
            logger.exception('root exception: {:}'.format(exception))
        # save width and height
        Config.set('graphics', 'width', str(int(Window.width / dp(1))))
        Config.set('graphics', 'height', str(int(Window.height /dp(1))))
        Config.write()
        Component.close()
        self.gui.on_close()
        logger.info('finished close down')

    # reset showing to main when any table is hidden
    def table_hiding(self, *args):
        self.showing = 'main'


def startjocular():

    # remove possibility of exiting with escape key
    Config.set('kivy', 'log_level', 'error')
    Config.set('kivy', 'exit_on_escape', '0')
    Config.write()

    # start app
    try:
        joc = Jocular()
        joc.run()
    except Exception as e:
        ''' any uncaught problems lead to a normal closedown to ensure 
            devices are disconnected, etc.
        '''
        joc.on_stop(exception=e)
        sys.exit('Jocular failed with error {:}'.format(e))

