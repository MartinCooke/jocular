''' watcher.py Watches for any data coming in
'''

import os

from kivy.logger import Logger
from kivy.app import App
from kivy.clock import Clock

from jocular.component import Component
from jocular.utils import move_to_dir
from jocular.image import Image, ImageNotReadyException, is_fit

class Watcher(Component):

    def __init__(self):
        super(Watcher, self).__init__()
        self.watched_dir = App.get_running_app().get_path('watched')
        self.watching_event = Clock.schedule_interval(self.watch, .3)

    def on_new_object(self):
        self.flush()

    def on_close(self):
        self.watching_event.cancel()
        self.flush()    # user has had enough so move any FITs to delete


    def flush(self):
        # move any FITs that are not masters to a 'unused' folder in watcher
        # (masters are saved immediately before new object, so risk they are not spotted in time!)
        for f in os.listdir(self.watched_dir):
            if is_fit(f):
                if not f.startswith('master'):
                    move_to_dir(os.path.join(self.watched_dir, f), 'unused')

    def watch(self, dt):
        '''Watcher handles two types of event:

            1.  Users drop individual subs (manually or via a capture program); if
                validated these are passed to ObjectIO
            2.  Users drop master calibration frames; if validated, passed to Calibrator
                to become part of the library and become available for immediate use

            Validated files are removed from 'watched'. If not validated, files are
            either left to be re-handled on the next event cycle, or moved to 'invalid'.
            Non-fits files are moved to 'ignored'
         '''

        for f in os.listdir(self.watched_dir):
            path = os.path.join(os.path.join(self.watched_dir, f))
            if is_fit(f):
                try:
                    s = Image(path)
                    if s.is_master:
                        Component.get('Calibrator').new_master_from_watcher(s)
                    else:
                        Component.get('ObjectIO').new_sub_from_watcher(s)
                except ImageNotReadyException as e:
                    # give it another chance on next event cycle
                    Logger.debug('Watcher: image not ready {:} ({:})'.format(f, e))
                except Exception as e:
                    # irrecoverable, so move to invalid, adding timestamp
                    Logger.debug('Watcher: invalid FITs {:} ({:})'.format(f, e))
                    move_to_dir(path, 'invalid')
            elif not os.path.isdir(path):
                move_to_dir(path, 'ignored')

