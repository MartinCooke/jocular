''' Serves stars and catalogues to other components, notably the
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
from jocular.settingsmanager import Settings

def intstep(d, step):
    return int(np.floor(step * np.floor(d / step)))

class Catalogues(Component, Settings):

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
            try:
                self.star_db  = np.load(self.app.get_path('star_db'))
            except:
                pass

    def has_platesolving_db(self):
        return self.star_db is not None

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
                quad = 'r{:}_d{:}_'.format(ra, dec)
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
        ''' load shipped catalogues then update/overwrite with any user 
            catalogue items; convert to uppercase name/OT as keys on read-in
            for speed of matching later
        '''

        shipped = glob.glob(os.path.join(self.app.get_path('dsos'), '*.csv'))
        usercats = glob.glob(os.path.join(self.app.get_path('catalogues'), '*.csv'))

        self.dsos = {}
        for objfile in shipped + usercats:
            # handle user objects last as they overwrite everything else
            if not objfile.endswith('user_objects.csv'):
                # form dict from user_objects
                with open(objfile, newline='') as f:
                    reader = csv.DictReader(f)
                    for d in reader:
                        nm = '{:}/{:}'.format(d['Name'], d['OT']).upper()
                        self.dsos[nm] = d

        logger.info('loaded {:} DSOs from {:} catalogues'.format(
            len(self.dsos), len(shipped + usercats)))

        # now read user objects and allow them to overwrite
        obj_file = os.path.join(self.app.get_path('catalogues'), 'user_objects.csv')
        if os.path.exists(obj_file):
            with open(obj_file, newline='') as f:
                reader = csv.DictReader(f)
                for d in reader:
                    nm = '{:}/{:}'.format(d['Name'], d['OT']).upper()
                    self.dsos[nm] = d
            logger.info('loaded user DSOs')

        # add any missing fields
        for v in self.dsos.values():
            for p in self.props:
                if p not in v:
                    v[p] = ''

        # convert all numeric cols to floats & ensure OTs/constellations are uppercase
        for k, v in self.dsos.items():
            for col in ['RA', 'Dec', 'Mag', 'Diam']:
                v[col] = float(v[col] if v[col] else math.nan)
            for col in ['OT', 'Con']:
                v[col] = v[col].upper()


    def update_user_catalogue(self, props):
        ''' Update (or create new entry) for DSO defined by dict
            props
        '''

        logger.debug('props {:}'.format(props))

        # no name or empty name
        if props.get('Name', '').strip == '':
            return

        if 'OT' not in props:
            props['OT'] = ''

        name = '{:}/{:}'.format(props['Name'], props['OT'])

        logger.info('Updating user objects with {:}'.format(name))

        # 


        ''' check if we already have a user_objects files; create if not
            and overwrite props or append if name/OT doesn't exist
        '''
        try:
            obj_file = os.path.join(self.app.get_path('catalogues'), 'user_objects.csv')
            if not os.path.exists(obj_file):
                logger.info('Creating user_objects.csv')
                with open(obj_file, 'w') as f:
                    f.write(','.join(self.props) + '\n')

            # form dict from user_objects
            with open(obj_file, newline='') as f:
                reader = csv.DictReader(f)
                odict = {'{:}/{:}'.format(row['Name'], row['OT']).upper(): row for row in reader}

            # add/update properties
            odict[name.upper()] = props

            # update dsos
            self.dsos[name.upper()] = props  

            # write to csv
            with open(obj_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.props)
                writer.writeheader()
                for v in odict.values():
                    writer.writerow(v)

            logger.info('Updated user objects (currently: {:} entries)'.format(
                len(odict)))

        except Exception as e:
            logger.exception('Problem writing user_objects.csv ({:})'.format(e))


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
                subdat = cat['r{:}_d{:}'.format(ra, dec)][0]
                ras, decs = subdat['RA'], subdat['Dec']
                locs = self.in_tile(tile, ras, decs)
                for l in np.where(locs)[0]:
                    matches[subdat['Name'][l] + '/' + OT] = {c: subdat[c][l] for c in cols}

        # add object type and catalogue
        for k, v in matches.items():
            v['OT'] = OT
            v['Cat'] = catname

        return matches

