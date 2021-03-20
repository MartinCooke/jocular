''' Handles DSO table and observing list management, including alt-az/transit
    computations.
'''

import json
import time
import math
import numpy as np
from datetime import datetime, timedelta
from collections import Counter

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.properties import ConfigParserProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.slider import Slider
from kivy.uix.label import Label
from kivy.metrics import dp
from kivy.logger import Logger

from jocular.component import Component
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


class ObservingList(Component):

    latitude = ConfigParserProperty(
        50, 'Observatory', 'latitude', 'app', val_type=float
    )
    longitude = ConfigParserProperty(
        -2, 'Observatory', 'longitude', 'app', val_type=float
    )

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
            ol = {
                v['Name']: v['Added'] for v in self.objects.values() if v['Added'] != ''
            }
            with open(self.app.get_path('observing_list.json'), 'w') as f:
                json.dump(ol, f, indent=1)
        except Exception as e:
            Logger.error('ObservingList: problem saving observing list ({:})'.format(e))
            self.warn('problem saving list')

    def save_notes(self, *args):
        try:
            ol = {
                v['Name']: v['Notes']
                for v in self.objects.values()
                if v['Notes'].strip() != ''
            }
            with open(self.app.get_path('observing_notes.json'), 'w') as f:
                json.dump(ol, f, indent=1)
        except Exception as e:
            Logger.error(
                'ObservingList: problem saving observing notes ({:})'.format(e)
            )
            self.warn('problem saving notes')

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
            v['Az'] = int(_az)
            v['Alt'] = int(_alt)
            v['Quadrant'] = quadrant(_az)

    def compute_transits(self):
        # from ch 15 of Meeus

        t0 = time.time()

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
            v['MaxAlt'] = int(_max_alt)
            v['Transit'] = float(_m) if _transits else math.nan

        Logger.info(
            'ObservingList: computed transits for {:} objects in {:.0f} ms'.format(
                len(self.objects), 1000 * (time.time() - t0)
            )
        )


    def load(self, dt):

        # DSOs
        try:
            self.objects = Component.get('Catalogues').get_basic_dsos()
        except Exception as e:
            Logger.exception('ObservingList: problem loading DSOs ({:})'.format(e))
            self.warn('problem loading DSOs')
            self.objects = {}

        # load observing list (maps names to date added)
        try:
            with open(self.app.get_path('observing_list.json'), 'r') as f:
                observing_list = json.load(f)
        except:
            observing_list = {}
        Logger.info('ObservingList: {:} on observing list'.format(len(observing_list)))

        # load observing notes
        try:
            with open(self.app.get_path('observing_notes.json'), 'r') as f:
                observing_notes = json.load(f)
        except:
            observing_notes = {}
        Logger.info('ObservingList: {:} observing notes'.format(len(observing_notes)))

        # load previous observations if necc and count previous
        try:
            obs = Component.get('Observations').get_observations()
            previous = dict(
                Counter([v['Name'].lower() for v in obs.values() if 'Name' in v])
            )
        except Exception as e:
            Logger.exception(
                'ObservingList: problem loading previous DSOs ({:})'.format(e)
            )
            previous = {}
        Logger.info(
            'ObservingList: {:} unique previous observations found'.format(
                len(previous)
            )
        )

        # ~ 180 ms
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
            Logger.error('ObservingList: problem computing transits {:}'.format(e))

        self.update_status()

    def build(self):

        if not hasattr(self, 'objects'):
            self.load()

        t0 = time.time()

        cols = {
            'Name': {
                'w': 180,
                'align': 'left',
                'sort': {'catalog': ''},
                'action': self.new_from_list,
            },
            'OT': {'w': 45},
            'Con': {'w': 45},
            'RA': {
                'w': 80,
                'align': 'right',
                'type': float,
                'val_fn': lambda x: x * 15,
                'display_fn': lambda x: str(RA(x)),
            },
            'Dec': {
                'w': 85,
                'align': 'right',
                'type': float,
                'display_fn': lambda x: str(Dec(x)),
            },
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
        self.slider = Slider(
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

        Logger.debug(
            'ObservingList: built in {:.0f} ms'.format(1000 * (time.time() - t0))
        )

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
            Logger.error('ObservingList: problem computing altaz {:}'.format(e))

        if hasattr(self, 'table'):
            # update display since this is fast, but update table (reapply filters) when slider stops
            self.table.update_display()
            self.update_event = Clock.schedule_once(self.table.update, 0.5)

    def show(self, *args):
        '''Called from menu to browse DSOs; open on first use'''
        if not hasattr(self, 'table'):
            self.table = self.build()
        self.app.showing = 'observing list'

        # redraw on demand when required
        if self.table not in self.app.gui.children:
            self.app.gui.add_widget(self.table, index=0)

        self.table.show()
        #  update time
        self.time_changed(self.time_field, 0)
        self.update_status()

    def new_from_list(self, row, *args):
        # User selects a row in the observing list table
        name = row.fields['Name'].text + '/' + row.fields['OT'].text
        self.table.hide()
        Component.get('DSO').on_new_object(self.lookup_name(name))

    def update_status(self):
        if hasattr(self, 'objects') and len(self.objects) > 0:
            self.info(
                '{:} out of {:} dsos'.format(
                    len([1 for v in self.objects.values() if v['List'] == 'Y']),
                    len(self.objects),
                )
            )

    def add_to_observing_list(self, *args):
        dn = datetime.now().strftime('%d %b')
        for s in self.table.selected:
            self.objects[s]['Added'] = dn
            self.objects[s]['List'] = 'Y'
        Logger.info('ObservingList: added {:} objects'.format(len(self.table.selected)))
        self.update_list()

    def remove_from_observing_list(self, *args):
        for s in self.table.selected:
            self.objects[s]['Added'] = ''
            self.objects[s]['List'] = 'N'
        Logger.info(
            'ObservingList: removed {:} objects'.format(len(self.table.selected))
        )
        self.update_list()

    def new_observation(self):
        OT = Component.get('Metadata').get('OT', None)
        Name = Component.get('Metadata').get('Name', None)
        #  update observed count if DSO is known
        if Name is not None and OT is not None:
            name = '{:}/{:}'.format(Name, OT)
            if name in self.objects:
                self.objects[name]['Obs'] += 1
            if hasattr(self, 'table'):
                self.table.update()

    def update_list(self):
        self.save_observing_list()
        self.table.update()
        self.table.deselect_all()
        self.update_status()

    def lookup_name(self, nm, *args):
        if not hasattr(self, 'objects'):
            self.load()

        if nm in self.objects:
            od = self.objects[nm]

        else:  #  search thru names
            d = [dd for dd in self.objects.values() if dd['Name'].lower() == nm.lower()]
            if len(d) == 0:
                return None
            else:
                od = d[0]
        od['RA'] = RA(od['RA'])
        od['Dec'] = Dec(od['Dec'])
        return od

    # called once we are sure we have an objesct
    def lookup_details(self, nm):
        return self.objects.get(nm, {})

    def lookup(self, nm, max_matches=11):
        if not hasattr(self, 'objects'):
            self.load()
        nm = nm.lower()
        matches = [n for n in self.objects.keys() if n.lower().startswith(nm)]
        # reorder so that any exact matches ie starting with nm and slash, are prioritised
        priors = [n for n in matches if n.lower().startswith(nm + '/')]
        nonpriors = [n for n in matches if not n.lower().startswith(nm + '/')]
        all_matches = priors + nonpriors
        return all_matches[:max_matches]

    # def get_objects_in_tile(self, tile):
    #     # return all DSOs from database within specified tile
    #     min_ra, max_ra = tile['min_ra'], tile['max_ra']
    #     min_dec, max_dec = tile['min_dec'], tile['max_dec']

    #     decs = {
    #         k: v
    #         for k, v in self.objects.items()
    #         if (v['Dec'] >= min_dec) & (v['Dec'] <= max_dec)
    #     }

    #     if min_ra < max_ra:
    #         return {
    #             k: v
    #             for k, v in decs.items()
    #             if (v['RA'] >= min_ra) & (v['RA'] <= max_ra)
    #         }

    #     return {
    #         k: v for k, v in decs.items() if (v['RA'] >= min_ra) | (v['RA'] <= max_ra)
    #     }
