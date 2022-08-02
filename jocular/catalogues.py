''' Serves stars and DSO catalogues to other components, notably the
    platesolver, annotator, and observing list
'''

import os
import glob
import csv
import json
import math
from copy import deepcopy
import numpy as np
from kivy.app import App
from loguru import logger
from kivy.properties import BooleanProperty

from jocular.component import Component
from jocular.settingsmanager import JSettings


def intstep(d, step):
    return int(np.floor(step * np.floor(d / step)))


class Catalogues(Component, JSettings):

    VS = BooleanProperty(True)
    WDS = BooleanProperty(True)
    SkiffSpectralClasses = BooleanProperty(True)
    milliquas = BooleanProperty(True)
    Hyperleda = BooleanProperty(True)

    tab_name = 'Catalogues'
    configurables = [
        ('VS', {'name': 'annotate variable stars?', 'switch': '',
            'help': 'Switch this off if you end up with crowded annotations'}),
        ('WDS', {'name': 'annotate double stars?', 'switch': ''}),
        ('SkiffSpectralClasses', {'name': 'annotate spectra classes?', 'switch': ''}),
        ('milliquas', {'name': 'annotate quasars?', 'switch': ''}),
        ('Hyperleda', {'name': 'annotate faint galaxies?', 'switch': ''})
        ]

    props = ['Name', 'RA', 'Dec', 'Con', 'OT', 'Mag', 'Diam', 'Other']


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.star_db = None

        ''' load object types and normalise colour values to 0-1 
        '''
        with open(self.app.get_path('object_types.json'), 'r') as f:
            self.object_types = json.load(f)
        for v in self.object_types.values():
            v['col'] = [i/255. for i in v['col']]

        self.dsos = None
        self.on_new_object()


    def get_object_types(self):
        return self.object_types


    def on_new_object(self):
        ''' Every time we get a new object, check for the existence
            of the catalogues. This allows a user to load them without
            restarting Jocular
        '''
        if self.star_db is None:
            path = self.app.get_path('star_db')
            if os.path.exists(path):
                try:
                    self.star_db  = np.load(path)
                    logger.info('loaded platesolving star database')
                except Exception as e:
                    logger.warning(f'cannot load star database from {path}: {e}')


    def has_platesolving_db(self):
        return self.star_db is not None


    def get_star_db(self):
        return self.star_db


    def in_tile(self, tile, ras, decs):
        ''' return indices of coordinates within tile
        '''
        rmin, rmax = tile['min_ra'], tile['max_ra']
        dmin, dmax = tile['min_dec'], tile['max_dec']
        if rmin < rmax:
            return (decs >= dmin) & (decs < dmax) & (ras >= rmin) & (ras < rmax)
        else:
            return (decs >= dmin) & (decs < dmax) & ((ras >= rmin) | (ras < rmax))


    def get_tiles(self, tile, rstep, dstep):
        ''' return database tiles covering region defined in tile
        '''
        rmin, rmax = tile['min_ra'], tile['max_ra']
        dmin, dmax = tile['min_dec'], tile['max_dec']

        dec_tiles = np.arange(intstep(dmin, dstep), intstep(dmax, dstep) + dstep, dstep)
        if rmin < rmax:
            ra_tiles = np.arange(intstep(rmin, rstep), intstep(rmax, rstep) + rstep, rstep)
        else:
            # handle wraparound
            ra_tiles = \
                list(range(intstep(rmin, rstep), 360, rstep)) + \
                list(range(0, intstep(rmax, rstep) + rstep, rstep))
        return ra_tiles, dec_tiles        


    def get_platesolving_stars(self, tile=None):
        # get stars in tile by reading npys that are spaced at 30 x 10 degrees in RA/Dec

        if self.star_db is None or tile is None:
            return

        ra_tiles, dec_tiles = self.get_tiles(tile, 30, 10)
        ras, decs, mags = np.array([]), np.array([]), np.array([])
        for ra in ra_tiles:
            for dec in dec_tiles:
                quad = f'r{ra}_d{dec}_'
                ras = np.append(ras, self.star_db[quad+'ra'])
                decs = np.append(decs, self.star_db[quad+'dec'])
                mags = np.append(mags, self.star_db[quad+'mag']/100.) # mags are ints * 100

        locs = self.in_tile(tile, ras, decs)
        return ras[locs], decs[locs], mags[locs]


    def get_basic_dsos(self):
        if self.dsos is None:
            self.load_basic_dsos()
        return self.dsos


    def load_basic_dsos(self):
        ''' load shipped catalogues, user catalogues, and user objects (i.e. those
            resulting from user observations)
        '''

        shipped = glob.glob(os.path.join(self.app.get_path('dsos'), '*.csv'))
        usercats = glob.glob(os.path.join(self.app.get_path('catalogues'), '*.csv'))
        allcats = [c for c in shipped + usercats if not c.endswith('user_objects.csv')] # legacy

        self.dsos = {}
        for cat in allcats:
            cnt = 0
            try:
                with open(cat, newline='') as f:
                    reader = csv.DictReader(f)
                    for d in reader:
                        d['Name'] = d['Name'].strip()
                        nm = f"{d['Name']}/{d['OT']}".upper()
                        self.dsos[nm] = d
                        self.dsos[nm]['Usr'] = ''
                        cnt += 1
                logger.info(f'loaded {cnt} DSOs from {cat}')
            except Exception as e:
                logger.error(f'problem loading/reading catalogue {cat} ({e})')

        # read user objects or initialise
        try:
            with open(os.path.join(self.app.get_path('catalogues'), 'user_objects.json')) as f:
                user_objects = json.load(f)
            # add to dsos only if not already present, and mark as user objects
            for k, v in user_objects.items():
                ku = k.upper()
                if ku not in self.dsos:
                    self.dsos[ku] = v
                    self.dsos[ku]['Usr'] = 'Y'
        except Exception as e:
            logger.error(f'problem loading/reading user_objects.json ({e})')

        # update user objects (test)
        self.save_user_objects()

        # ensure all fields are present and consistent
        for v in self.dsos.values():
            for col in ['RA', 'Dec', 'Mag', 'Diam']:
                val = v.get(col, '')
                try:
                    v[col] = float(val)
                except:
                    v[col] = math.nan
            for col in ['OT', 'Con']:
                v[col] = v.get(col, '').upper()
            v['Other'] = v.get('Other', '')


    def lookup(self, name, OT=None):
        ''' lookup object details for name
            If name is in form name/OT then return match or None
            If name is in form name (no OT) then return data for all matches
        '''

        name = name.upper()

        if OT is not None and OT and '/' not in name:
            name = f'{name}/{OT}'

        logger.debug(name)
        dsos = self.get_basic_dsos()
        if name in dsos:
            return dsos[name]

        # if just provided with a name and no OT, check if there is a unique match
        if '/' not in name:
            name += '/'
            matches = [n for n in dsos if n.startswith(name)]
            if len(matches) == 1:
                return dsos[matches[0]]

        return None


    def update_user_object(self, props):
        ''' Called from DSO when object is saved and is new or altered
        '''

        name = f"{props['Name']}/{props['OT']}".upper()

        if name in self.dsos and self.dsos[name]['Usr'] != 'Y':
            logger.warning(f'cannot update non-user-defined DSO {name}')
            return

        # update main DSO list
        self.dsos[name] = props.copy()
        self.dsos[name]['Usr'] = 'Y'

        self.save_user_objects()


    def save_user_objects(self):
        fields = ['Name', 'OT', 'Con', 'RA', 'Dec', 'Diam', 'Mag', 'Other']
        udict = {}
        for k, v in self.dsos.items():
            if v['Usr'] == 'Y':
                udict[k] = {k1: v1 for k1, v1 in v.items() if k1 in fields}
        try:
            with open(os.path.join(self.app.get_path('catalogues'), 'user_objects.json'), 'w') as f:
                json.dump(udict, f, indent=1)
        except Exception as e:
            logger.warning(f'Unable to save user_objects.csv ({e})')


    def delete_user_object(self, name):
        ''' Remove user object and save user objects list
        '''

        name = name.upper()
        if name in self.dsos and self.dsos[name]['Usr'] == 'Y':
            del self.dsos[name]
            self.save_user_objects()
       

    def is_excluded(self, catname):
        return hasattr(self, catname) and not getattr(self, catname)


    def get_annotation_dsos(self, tile=None):
        ''' Retrieve all DSOs in the specified tile. Use basic DSOs combined
            with any deeper DSOs available. Return as a dict with dso names as
            keys and values are dicts of object properties

            To do: streamline using in_tile etc so RA wraparound is handled in one place
        '''

        if tile is None:
            return {}

        dsos = self.get_basic_dsos()
        dmin, dmax = tile['min_dec'], tile['max_dec']
        in_dec = {k: v for k, v in dsos.items() 
            if (v['Dec'] >= dmin) & (v['Dec'] < dmax)}
        rmin, rmax = tile['min_ra'], tile['max_ra']
        if rmin < rmax:
            matches = {k: v for k, v in in_dec.items() 
                if (v['RA'] >= rmin) & (v['RA'] < rmax)}
        else:
            # handle RA wrap-around
            matches = {k: v for k, v in in_dec.items() 
                if (v['RA'] >= rmin) | (v['RA'] < rmax)}

        # load any deep catalogues that user has placed in catalogues
        deepcats = glob.glob(os.path.join(self.app.get_path('catalogues'), '*.npz'))
        for cat in deepcats:
            if not self.is_excluded(os.path.basename(cat)[:-4]):
                matches = {**matches, **self.load_deepcat(cat, tile)}

        # return copy in case receiver decides to modify things
        return deepcopy(matches)


    def load_deepcat(self, nm, tile):

        cat = np.load(nm, allow_pickle=True)
        try:
            rstep, dstep = cat['ra_step'][0], cat['dec_step'][0]
        except:
            return {}

        ra_tiles, dec_tiles = self.get_tiles(tile, rstep, dstep)

        # extract objects from all necessary tiles
        cols = cat['columns']
        OT = cat['OT'][0]
        catname = cat['catname'][0]

        matches = {}
        for ra in ra_tiles:
            for dec in dec_tiles:
                subdat = cat[f'r{ra}_d{dec}'][0]
                ras, decs = subdat['RA'], subdat['Dec']
                locs = self.in_tile(tile, ras, decs)
                for l in np.where(locs)[0]:
                    matches[subdat['Name'][l] + '/' + OT] = {c: subdat[c][l] for c in cols}

        # add object type and catalogue
        for k, v in matches.items():
            v['OT'] = OT
            v['Cat'] = catname

        return matches

