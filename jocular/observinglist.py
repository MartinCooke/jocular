''' Handles DSO table and observing list management, including alt-az/transit
    computations.
'''

import json
import time
import math
import numpy as np
from datetime import datetime, timedelta
from collections import Counter
from loguru import logger

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.properties import NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.slider import MDSlider
from kivy.uix.label import Label
from kivy.metrics import dp
from kivymd.toast.kivytoast import toast

from jocular.component import Component
from jocular.settingsmanager import Settings
from jocular.RA_and_Dec import RA, Dec
from jocular.table import Table, CButton, TableLabel
from jocular.calcs import local_sidereal_time, sun_altitude

def ToHM(x):
    if math.isnan(x):
        return ''
    h = int(x)
    m = (x - h) * 60
    return '{:2.0f}h{:02.0f}'.format(h, m).strip()

def fmt_diam(d):
    if d < 1:
        # ds = 60
        return '{:4.1f}"'.format(d * 60)
    elif d < 10:
        return "{:4.2f}'".format(d)
    elif d < 100:
        return "{:4.1f}'".format(d)
    else:
        dg = int(d / 60)
        return "{:.0f}\u00b0{:2.0f}'".format(dg, (d - dg) / 60.0)

def quadrant(x):
    # terrestrial direction
    qmap = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    quad = int((x + 22.5) // 45)
    if quad == 8:
        quad = 0
    return qmap[quad]

class ObservingList(Component, Settings):

    tab_name = 'Observatory'

    latitude = NumericProperty(42)
    longitude = NumericProperty(-2)

    configurables = [
        ('latitude', {
            'double_slider_float': (-90, 90),
            'fmt': '{:.2f}\u00b0',
            }),
        ('longitude', {
            'double_slider_float': (-180, 180),
            'fmt': '{:.2f}\u00b0',
            'help': 'Positive for points E of Greenwich, negative W'
            })
    ]

    def __init__(self):
        super().__init__()
        self.app = App.get_running_app()

        # time zone offset
        ts = time.time()
        self.utc_offset = (
            datetime.fromtimestamp(ts) - datetime.utcfromtimestamp(ts)
        ).total_seconds() / 3600.0

        Clock.schedule_once(self.load, 0)

    def on_close(self):
        self.save_observing_list()
        self.save_notes()

    def save_observing_list(self, *args):
        try:
            ol = {v['Name']: v['Added'] for v in self.objects.values() if v['Added'] != ''}
            with open(self.app.get_path('observing_list.json'), 'w') as f:
                json.dump(ol, f, indent=1)
        except Exception as e:
            logger.exception('problem saving ({:})'.format(e))
            toast('problem saving observing list')

    def save_notes(self, *args):
        try:
            ol = {v['Name']: v['Notes'] for v in self.objects.values() if v['Notes'].strip() != ''}
            with open(self.app.get_path('observing_notes.json'), 'w') as f:
                json.dump(ol, f, indent=1)
        except Exception as e:
            logger.exception('problem saving ({:})'.format(e))
            toast('problem saving observing notes')

    def compute_altaz(self, current_hours_offset=0):

        t = datetime.now() + timedelta(seconds=3600 * current_hours_offset)
        rads = math.pi / 180

        if hasattr(self, 'last_time_changed'):
            tdiff = t - self.last_time_changed
            if tdiff.seconds < 5:
                return
        self.last_time_changed = t

        lst = local_sidereal_time(t, self.longitude)
        lat = self.latitude * rads
        ras = np.array([v['RA'] for v in self.objects.values()])
        decs = np.array([v['Dec'] for v in self.objects.values()]) * rads

        sinlat, coslat = np.sin(lat), np.cos(lat)
        H = (-self.utc_offset * 15 + lst - ras) * rads
        sinH, cosH = np.sin(H), np.cos(H)
        az = 180 + (np.arctan2(sinH, cosH * sinlat - np.tan(decs) * coslat) / rads)
        alt = np.arcsin(sinlat * np.sin(decs) + coslat * np.cos(decs) * cosH) / rads

        for v, _alt, _az in zip(self.objects.values(), alt, az):
            v['Az'] = math.nan if math.isnan(_az) else int(_az)
            v['Alt'] = math.nan if math.isnan(_alt) else int(_alt)
            v['Quadrant'] = '' if math.isnan(_az) else quadrant(_az)

    def compute_transits(self):
        # from ch 15 of Meeus

        ras = np.array([v['RA'] for v in self.objects.values()])
        decs = np.array([v['Dec'] for v in self.objects.values()])

        #  apparent sidereal time at Greenwich at 0hUT
        t = datetime.now()
        gst_0 = local_sidereal_time(datetime(t.year, t.month, t.day), 0)

        max_alts = 90 - self.latitude + decs
        max_alts[max_alts > 90] = 180 - max_alts[max_alts > 90]

        # transit time: slight diff from Meeus since longitude negative from W here
        transiting = np.abs(decs) < (90 - self.latitude)
        m0 = (ras - self.longitude - gst_0 + self.utc_offset * 15) / 15
        m0[m0 > 24] = m0[m0 > 24] - 24
        m0[m0 < 0] = m0[m0 < 0] + 24

        # 80 ms or so
        for v, _max_alt, _transits, _m in zip(
            self.objects.values(), max_alts, transiting, m0
        ):
            v['MaxAlt'] = math.nan if math.isnan(_max_alt) else int(_max_alt)
            v['Transit'] = float(_m) if _transits else math.nan

        logger.info('computed transits for {:} objects'.format(len(ras)))


    @logger.catch()
    def load(self, dt):

        # load DSOs
        try:
            self.objects = Component.get('Catalogues').get_basic_dsos()
        except Exception as e:
            logger.exception('problem loading DSOs ({:})'.format(e))
            toast('problem loading DSOs')
            self.objects = {}

        # load observing list (maps names to date added)
        try:
            with open(self.app.get_path('observing_list.json'), 'r') as f:
                observing_list = json.load(f)
        except:
            observing_list = {}
        logger.info('{:} on observing list'.format(len(observing_list)))

        # load observing notes
        try:
            with open(self.app.get_path('observing_notes.json'), 'r') as f:
                observing_notes = json.load(f)
        except:
            observing_notes = {}
        logger.info('{:} observing notes'.format(len(observing_notes)))

        # load previous observations if necc and count previous
        try:
            obs = Component.get('Observations').get_observations()
            previous = dict(Counter([v['Name'].lower() for v in obs.values() if 'Name' in v]))
        except Exception as e:
            logger.warning('problem loading previous DSOs ({:})'.format(e))
            previous = {}
        logger.info('{:} unique previous observations found'.format(len(previous)))

        # augment/combine DSO info
        for v in self.objects.values():
            name = v['Name']
            v['Obs'] = previous.get(name.lower(), 0)
            v['Added'] = observing_list.get(name, '')
            v['List'] = 'Y' if name in observing_list else 'N'
            v['Notes'] = observing_notes.get(name, '')
            v['Other'] = v.get('Other', '')

        try:
            self.compute_transits()
        except Exception as e:
            logger.exception('problem computing transits {:}'.format(e))

    def build(self):

        if not hasattr(self, 'objects'):
            self.load()

        cols = {
            'Name': {'w': 180, 'align': 'left', 'sort': {'catalog': ''}, 'action': self.new_from_list},
            'OT': {'w': 45},
            'Con': {'w': 45},
            'RA': {'w': 80, 'align': 'right', 'type': float, 'val_fn': lambda x: x * 15, 'display_fn': lambda x: str(RA(x))},
            'Dec': {'w': 85, 'align': 'right', 'type': float, 'display_fn': lambda x: str(Dec(x))},
            'Loc': {'w': 40, 'align': 'center', 'field': 'Quadrant'},
            'Az': {'w': 40, 'align': 'center', 'type': int},
            'Alt': {'w': 40, 'align': 'center', 'type': int},
            'Max': {'w': 40, 'align': 'center', 'type': int, 'field': 'MaxAlt'},
            'Transit': {'w': 60, 'align': 'right', 'type': float, 'display_fn': ToHM},
            'Mag': {'w': 50, 'align': 'right', 'type': float},
            'Diam': {'w': 50, 'align': 'right', 'type': float, 'display_fn': fmt_diam},
            'Obs': {'w': 40, 'type': int, 'field': 'Obs'},
            'List': {'w': 35},
            'Added': {'w': 65, 'sort': {'DateFormat': '%d %b'}},
            'Notes': {'w': 100, 'input': True},
            'Other': {'w': 1, 'align': 'left'},
        }

        # time control widget
        ctrl = BoxLayout(orientation='horizontal', size_hint=(1, 1))

        # observing list buttons
        ctrl.add_widget(
            CButton(
                text='add to list', width=dp(100), on_press=self.add_to_observing_list
            )
        )
        ctrl.add_widget(
            CButton(
                text='remove from list',
                width=dp(130),
                on_press=self.remove_from_observing_list,
            )
        )

        ctrl.add_widget(Label(size_hint_x=None, width=dp(40)))

        self.sun_time = TableLabel(text='', markup=True, size_hint_x=None, width=dp(80))

        ctrl.add_widget(self.sun_time)
        self.slider = MDSlider(
            orientation='horizontal',
            min=0,
            max=24,
            value=0,
            size_hint_x=None,
            width=dp(250),
        )
        self.slider.bind(value=self.time_changed)
        self.time_field = TableLabel(
            text=datetime.now().strftime('%d %B %H:%M'), size_hint_x=None, width=dp(160)
        )
        ctrl.add_widget(self.slider)
        ctrl.add_widget(self.time_field)
        self.time_changed(self.time_field, 0)

        logger.info('built')

        return Table(
            size=Window.size,
            data=self.objects,
            name='DSOs',
            cols=cols,
            update_on_show=False,
            controls=ctrl,
            on_hide_method=self.app.table_hiding,
            initial_sort_column='RA',
        )

    def time_changed(self, widgy, value):
        # user moves time slider
        if hasattr(self, 'update_event'):
            self.update_event.cancel()
        t0 = datetime.now() + timedelta(seconds=3600 * value)
        self.time_field.text = t0.strftime('%d %B %H:%M')

        sun_alt = sun_altitude(t0, self.latitude, self.longitude)
        self.sun_time.text = 'sun: {:3.0f}\u00b0'.format(sun_alt)
        try:
            self.compute_altaz(current_hours_offset=self.slider.value)
        except Exception as e:
            logger.exception('problem computing altaz {:}'.format(e))

        if hasattr(self, 'table'):
            # update display since this is fast, but update table (reapply filters) when slider stops
            self.table.update_display()
            self.update_event = Clock.schedule_once(self.table.update, 0.5)

    @logger.catch()
    def show(self, *args):
        '''Called from menu to browse DSOs; open on first use'''
        if not hasattr(self, 'table'):
            self.table = self.build()
        self.app.showing = 'observing list'

        # redraw on demand when required
        if self.table not in self.app.gui.children:
            self.app.gui.add_widget(self.table, index=0)

        self.table.show()
        self.time_changed(self.time_field, 0)

    def new_from_list(self, row, *args):
        # User selects a row in the observing list table
        name = row.fields['Name'].text + '/' + row.fields['OT'].text
        self.table.hide()
        Component.get('DSO').new_DSO_name(self.lookup_name(name))

    def add_to_observing_list(self, *args):
        dn = datetime.now().strftime('%d %b')
        for s in self.table.selected:
            self.objects[s]['Added'] = dn
            self.objects[s]['List'] = 'Y'
        logger.info('added {:} objects'.format(len(self.table.selected)))
        self.update_list()

    def remove_from_observing_list(self, *args):
        for s in self.table.selected:
            self.objects[s]['Added'] = ''
            self.objects[s]['List'] = 'N'
        logger.info('removed {:} objects'.format(len(self.table.selected)))
        self.update_list()

    def new_observation(self):
        OT = Component.get('Metadata').get('OT', '')
        Name = Component.get('Metadata').get('Name', None)
        logger.info('{:}/{:}'.format(Name, OT))
        #  update observed count if DSO is known
        if Name is not None:
            name = '{:}/{:}'.format(Name, OT)
            if name in self.objects:
                self.objects[name]['Obs'] += 1
            if hasattr(self, 'table'):
                self.table.update()

    def update_list(self):
        self.save_observing_list()
        self.table.update()
        self.table.deselect_all()

    @logger.catch()
    def lookup_name(self, name, *args):
        ''' name is of the form name/object type e.g. SHK 10/CG and will exist
            either in self.objects or in catalogue objects (latter case for any
            ojects added during the current session). Called either after looking
            up object types (in dso.py), or when a user clicks on a row in the
            dso table (above)
        '''
        if not hasattr(self, 'objects'):
            self.load()
        nm = name.upper()

        # most of the time the object is already in the table
        if nm in self.objects:
            dso = self.objects[nm]
        else:
            # if not, ought to be in the cataogue object structure
            dso = Component.get('Catalogues').get_basic_dsos().get(nm, {})

        # tidy it up to reduce any None and nan to empties
        for k, v in dso.items():
            if v is None or str(v) == 'nan':
                dso[k] = ''
        return dso

    def lookup_OTs(self, name):
        ''' Find all OTs that have this name; note that keys in objects are stored
            in upper case
        '''
        if not hasattr(self, 'objects'):
            self.load()
        name = name.upper() + '/'
        return [n.split('/')[1] for n in self.objects.keys() if n.startswith(name)]
