''' Manages previous observations and associated observations table.
'''

import os
import shutil
import glob
import json
from loguru import logger

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window

from jocular.component import Component
from jocular.table import Table
from jocular.metadata import get_metadata
from jocular.utils import toast
from jocular.image import Image, fits_in_dir
from jocular.exposurechooser import exp_to_str


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
        ''' Load json file containing observation details. If any problem,
            set observations to empty and continue.
        '''
        obspath = self.app.get_path('previous_observations.json')
        if os.path.exists(obspath):
            try:
                with open(obspath, 'r') as f:
                    self.observations = json.load(f)
                logger.info(f'Loaded {len(self.observations)} observations')
            except Exception as e:
                logger.warning(f'none loaded, rescanning captures ({e})')
                self.observations = {}
        # no obs so rebuild from captures
        # could be slow...
        else:
            self.get_observations_from_captures(detailed=False)


    def save_observations(self):
        try:
            with open(self.app.get_path('previous_observations.json'), 'w') as f:
                json.dump(self.observations, f, indent=1)
            logger.info(f'saved {len(self.observations)}')
        except Exception as e:
            logger.warning(f'cannot save previous observations ({e})')


    def get_observations_from_captures(self, detailed=True):
        ''' look in captures and its subdirectories to build observations structure
        '''
        self.observations = {}
        for sesh in glob.glob(os.path.join(self.app.get_path('captures'), '*')):
            for dso in glob.glob(os.path.join(sesh, '*')):
                if os.path.isdir(dso):
                    self.observations[dso] = get_metadata(dso, simple=True)
                    if detailed:
                        fail = 0
                        filts, expos, shapes = [], [], []
                        for f in fits_in_dir(dso):
                            try:
                                im = Image(f)
                                filts += [im.filter]
                                expos += [im.exposure]
                                shapes += [im.shape_str]
                            except:
                                fail += 1
                        if fail > 0:
                            logger.debug(f'{fail} unreadable FITs for {dso}')

                        # filters
                        filts = set(filts)
                        if {'L', 'R', 'G', 'B'} <= filts:
                            fstr = 'LRGB'
                        elif 'L' in filts:
                            rest = filts - {'L'}
                            fstr = 'L' + ''.join(rest)
                        else:
                            fstr = ''.join(filts)
                        self.observations[dso]['Filts'] = fstr

                        # exposures
                        expos = list(set(expos))
                        if len(expos) == 0:
                            expostr = ''
                        elif len(expos) > 1:
                            expostr = 'mult'
                        elif expos[0] is None:
                            expostr = ''
                        else:
                            expostr = exp_to_str(expos[0])
                        self.observations[dso]['Expo'] = expostr

                        shapes = list(set(shapes))
                        if len(shapes) != 1:
                            logger.debug(f'multiple sub dims for {dso}')
                            shapestr = 'mult'
                        else:
                            shapestr = shapes[0]
                        self.observations[dso]['Size'] = shapestr

        self.save_observations()


    def rebuild_observations(self, *args):
        ''' rebuild observations from scratch
        '''
        try:
            self.get_observations_from_captures(detailed=True)
            Clock.schedule_once(self.rebuild_table, .1)
        except Exception as e:
            logger.exception(e)
           

    def fast_rebuild_observations(self, *args):
        ''' rebuild observations from scratch
        '''
        try:
            self.get_observations_from_captures(detailed=False)
            Clock.schedule_once(self.rebuild_table, .1)
        except Exception as e:
            logger.exception(e)


    def rebuild_table(self, dt=None):
        self.observations_table.data = self.get_observations()         
        self.observations_table.update()
        toast('rebuilt!')


    def build_observations(self):
        # table construction ~150ms

        cols = {
            'Name': {'w': 250, 'align': 'left', 'sort': {'catalog':''}, 'action': self.load_dso},
            'OT': {'w': 40},
            'Con': {'w': 50},
            'Session': {'w': 140, 'sort': {'DateFormat': '%d %b %y %H:%M'}, 'label': 'Date'},
            'N': {'w': 40, 'align': 'right', 'type': int},
            'Expo': {'w': 70, 'sort': {'exposure': ''}},
            'Filts': {'w': 60},
            'Size': {'w': 100},
            'Notes': {'w': 1, 'align': 'left'}
        }

        # set up editable fields
        for c in ['Expo', 'Filts']:
            cols[c]['action'] = self.edit_prop

        return Table(
            size=Window.size,
            data=self.get_observations(),
            name='Observations',
            description='click on DSO name to load',
            cols=cols,
            actions={
                'move to delete dir': self.move_to_delete_folder,
                'rebuild observations': self.rebuild_observations,
                'fast rebuild': self.fast_rebuild_observations},
            on_hide_method=self.app.table_hiding,
            initial_sort_column='Session', 
            reverse_initial_sort=True
            )    


    def edit_prop(self, row, prop, value):
        # placeholder for now
        toast(f'editing prop {prop} {value} (not yet implemented)')


    def show_observations(self, *args):

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

        capdir = self.app.get_path('captures')
        for sesh in glob.glob(os.path.join(capdir, '*')):
            dsos = os.listdir(sesh)
            if len(dsos) == 0 or ('.DS_Store' in dsos and len(dsos) == 1):
                try:
                    shutil.rmtree(sesh)
                    logger.debug(f'removing empty session {sesh}')
                except Exception as e:
                    logger.error(f'problem removing empty session {sesh} ({e})')
            else:
                for dso in dsos:
                    dname = os.path.join(sesh, dso)
                    if os.path.isdir(dname):
                        subs = os.listdir(dname)
                        if len(subs) == 0 or ('.DS_Store' in subs and len(subs) == 1):
                            try:
                                shutil.rmtree(dname)
                                logger.debug(f'removing empty DSO dir {dname}')
                            except Exception as e:
                                logger.error(f'problem removing empty DSO dir {dname} ({e})')


    def move_to_delete_folder(self, *args):
        objio = Component.get('ObjectIO')
        for s in self.observations_table.selected:
            if s in self.observations:
                objio.delete_file(s)
                del self.observations[s]
        logger.info(f'Deleted {len(self.observations_table.selected)} observations')
        self.observations_table.update()
        self.save_observations()


    def update(self, oldpath, newpath):
        ''' We have either an existing observation being saved or a 
            new observation, so read it and generate extra required info to 
            update self.observations
        '''

        # if not yet built, no worries because it will be found when next built
        if not hasattr(self, 'observations'):
            return

        self.observations[newpath] = get_metadata(newpath, simple=True)
        logger.debug(f'new path {newpath} = {self.observations[newpath]}')
        # user has changed directory
        if oldpath != newpath:
            if oldpath in self.observations:
                del self.observations[oldpath]

        # only update if we have already displayed table
        if hasattr(self, 'observations_table'):
            self.observations_table.update()

        self.save_observations()


    def load_dso(self, row, col, value):
        self.observations_table.hide()
        # convert row.key to str (it is numpy.str by default)
        Component.get('ObjectIO').load_previous(path=str(row.key))
