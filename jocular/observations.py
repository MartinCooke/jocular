''' Manages previous observations and associated observations table.
'''

import os
import random
import shutil
import time
import glob
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.logger import Logger

from jocular.component import Component
from jocular.table import Table
from jocular.metadata import get_metadata


def simple_metadata(d):
    return { 
        'Name': d.get('Name', ''),
        'OT': d.get('OT', ''),
        'Con': d.get('Con', ''),
        'Session': d.get('session', ''),
        'N': d.get('nsubs', 0),
        'Notes': d.get('Notes', '')
    }    

class Observations(Component):

    def __init__(self):
        super().__init__()
        self.app = App.get_running_app()
        Clock.schedule_once(self.load_observations, 0)

    def get_observations(self):
        if not hasattr(self, 'observations'):
            self.load_observations()
        return self.observations

    def load_observations(self, dt=None):
        t0 = time.time()
        self.observations = {}
        for sesh in glob.glob(os.path.join(self.app.get_path('captures'), '*')):
            for dso in glob.glob(os.path.join(sesh, '*')):
                if os.path.isdir(dso):
                    self.observations[dso] = simple_metadata(get_metadata(dso))
        self.update_status()
        Logger.info('Observation: Loaded {:} observations in {:}ms'.format(
            len(self.observations), int(1000*(time.time() - t0))))

    def build_observations(self):
        # table construction ~150ms

        if not hasattr(self, 'observations'):
            self.load_observations()

        return Table(
            size=Window.size,
            data=self.observations,
            name='Observations',
            description='click on DSO name to load',
            cols={
                'Name': {'w': 250, 'align': 'left', 'sort': {'catalog':''}, 'action': self.load_dso},
                'OT': {'w': 40},
                'Con': {'w': 50},
                'Session': {'w': 140, 'sort': {'DateFormat': '%d %b %y %H:%M'}},
                'N': {'w': 40, 'type': int},
                'Notes': {'w': 1, 'align': 'left'}
                },
            actions={'move to delete dir': self.move_to_delete_folder},
            on_hide_method=self.app.table_hiding,
            initial_sort_column='Session', 
            initial_sort_direction='reverse'
            )    

    def show_observations(self, *args):
        '''Called from menu to browse DSOs; open on first use'''

        if not hasattr(self, 'observations_table'):
            self.observations_table = self.build_observations()
        self.app.showing = 'observations'

        # redraw on demand as it is expensive
        if self.observations_table not in self.app.gui.children:
            self.app.gui.add_widget(self.observations_table, index=0)

        self.observations_table.show()    

    def on_close(self, *args):
        # clean up empty observation and session directories
        sesh = Component.get('ObjectIO').session_dir
        # remove any empty observations
        for dso in glob.glob(os.path.join(sesh, '*')):
            if os.path.isdir(dso):
                # remove any empty observation directories
                if len(os.listdir(dso)) == 0:
                    try:
                        os.rmdir(dso)
                    except Exception as e:
                        Logger.warn('Observations: cannot remove observation directory {:} ({:})'.format(dso, e))
        # remove empty session dirs
        for sesh in glob.glob(os.path.join(self.app.get_path('captures'), '*')):
            if len(os.listdir(sesh)) == 0:
                try:
                    os.rmdir(sesh)
                except Exception as e:
                    Logger.warn('Observations: cannot remove session directory {:} ({:})'.format(sesh, e))

    def move_to_delete_folder(self, *args):
        for s in self.observations_table.selected:
            if s in self.observations:
                self._delete(s)
                del self.observations[s]
        self.observations_table.update()
        self.update_status()

    def update_status(self):
        if hasattr(self, 'observations'):
            self.info('{:}'.format(len(self.observations)))

    def _delete(self, path):
        try:
            dname = os.path.join(self.app.get_path('deleted'),
                '{:}_{:}_{:d}'.format(os.path.basename(path),
                datetime.now().strftime('%d_%b_%y_%H_%M'),
                random.randint(1,9999)))
            shutil.move(os.path.join(self.app.get_path('captures'), path), dname)
        except Exception as e:
            Logger.error('Observations: deleting observations ({:})'.format(e))
            self.error('problem on delete')

    # needs testing
    def update(self, oldpath, newpath):
        # we have either an existing observation being saved or a new observation
        # so read it and extra required info to update self.observations

        # if not yet built, no worries because it will be found when next built
        if not hasattr(self, 'observations'):
            return

        self.observations[newpath] = simple_metadata(get_metadata(newpath))
        # user has changed directory
        if oldpath != newpath:
            if oldpath in self.observations:
                del self.observations[oldpath]

        # only update if we have already displayed table
        if hasattr(self, 'observations_table'):
            self.observations_table.update()

        self.update_status()

    def load_dso(self, row):
        self.observations_table.hide()
        # convert row.key to str (it is numpy.str by default)
        Component.get('ObjectIO').load_previous(path=str(row.key))
