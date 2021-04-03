''' Manages previous observations and associated observations table.
'''

import os
import random
import shutil
import time
import glob
import json
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.logger import Logger

from jocular.component import Component
from jocular.table import Table
from jocular.metadata import get_metadata


class Observations(Component):

    def __init__(self):
        super().__init__()
        self.app = App.get_running_app()
        Clock.schedule_once(self.load_observations, 0)
        # self.load_observations()

    def get_observations(self):
        if not hasattr(self, 'observations'):
            self.load_observations()
        return self.observations

    def load_observations(self, dt=None):
        ''' Load json file containing observation details. If any problem,
            set observations to empty and continue.
        '''
        try:
            with open(self.app.get_path('previous_observations.json'), 'r') as f:
                self.observations = json.load(f)
            Logger.info('Observations: Loaded {:} observations'.format(
                len(self.observations)))
        except Exception as e:
            Logger.warn('Observations: none loaded ({:})'.format(e))
            self.observations = {}
        self.info('Loaded {:}'.format(len(self.observations)))

    def save_observations(self):
        try:
            with open(self.app.get_path('previous_observations.json'), 'w') as f:
                json.dump(self.observations, f, indent=1)
            Logger.info('Observations: saved {:}'.format(len(self.observations)))
        except Exception as e:
            Logger.warn('Observations: cannot save previous observations ({:})'.format(e))

    def build_observations(self):
        # table construction ~150ms

        return Table(
            size=Window.size,
            data=self.get_observations(),
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
        '''Called from menu to browse DSOs; open on first use
        '''

        if not hasattr(self, 'observations_table'):
            self.observations_table = self.build_observations()
        self.app.showing = 'observations'

        # redraw on demand as it is expensive
        if self.observations_table not in self.app.gui.children:
            self.app.gui.add_widget(self.observations_table, index=0)

        self.observations_table.show()    

    def on_close(self, *args):
        ''' Save observations, clean up any empty observation and session dirs
        '''

        self.save_observations()
        sesh = Component.get('ObjectIO').session_dir
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
        self.save_observations()
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

    def update(self, oldpath, newpath):
        ''' We have either an existing observation being saved or a 
            new observation, so read it and generate extra required info to 
            update self.observations
        '''

        # if not yet built, no worries because it will be found when next built
        if not hasattr(self, 'observations'):
            return

        self.observations[newpath] = get_metadata(newpath, simple=True)
        # user has changed directory
        if oldpath != newpath:
            if oldpath in self.observations:
                del self.observations[oldpath]

        # only update if we have already displayed table
        if hasattr(self, 'observations_table'):
            self.observations_table.update()

        self.save_observations()
        self.info('{:}'.format(len(self.observations)))

    def load_dso(self, row):
        self.observations_table.hide()
        # convert row.key to str (it is numpy.str by default)
        Component.get('ObjectIO').load_previous(path=str(row.key))
