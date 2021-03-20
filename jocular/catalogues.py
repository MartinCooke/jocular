''' Serves stars and catalogues to other components, notably the
    platesolver, annotator, and observing list
'''

import os
import glob
import csv
import json
from copy import deepcopy
import numpy as np
from kivy.app import App
from kivy.logger import Logger
from kivy.properties import ConfigParserProperty

from jocular.component import Component

def intstep(d, step):
    return int(np.floor(step * np.floor(d / step)))

class Catalogues(Component):

    exclude_cats = ConfigParserProperty('VS', 'Catalogues', 'exclude_cats', 'app', val_type=str)

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
            except Exception as e:
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
        ''' We load the shipped and user catalogues at the start once only
        '''

        ''' construct list of .csv files; we load shipped then user cats
            with later loads overwriting earlier loads of duplicate
            objects (thereby supporting user updates)
        '''

        shipped = glob.glob(os.path.join(self.app.get_path('dsos'), '*.csv'))
        usercats = glob.glob(os.path.join(self.app.get_path('catalogues'), '*.csv'))

        self.dsos = {}
        for f in shipped + usercats:
            user_objects = f.endswith('user_objects.csv')
            dupes = 0
            with open(f, newline='') as csvfile:
                reader = csv.reader(csvfile, delimiter=',')
                hdr = next(reader)
                if {'Name', 'RA', 'Dec', 'OT', 'Con'} <= set(hdr):
                    cnames = ['Name', 'RA', 'Dec', 'Con', 'OT', 'Mag', 'Diam', 'Other']
                    cols = {c: (hdr.index(c) if c in hdr else None) for c in cnames}
                    cols = {c: i for c, i in cols.items() if i is not None}
                    for row in reader:
                        try:
                            dd = {c: row[i] for c, i in cols.items()}
                            name = '{:}/{:}'.format(dd['Name'], dd['OT'])
                            if name in self.dsos and not user_objects:
                                dupes += 1
                            else:
                                self.dsos[name] = dd
                        except:
                            if len(row) > 0:
                                Logger.warn('Catalogues: error in catalogue {:}, {:}'
                                    .format(f, row))
                else:
                    Logger.warn('Catalogues: {:} no Name/RA/Dec/OT/Con'.format(f))
            Logger.info('Catalogues: loaded {:} ({:} duplicates)'.format(
                os.path.basename(f), dupes))

        # convert all numeric cols to floats
        for k, v in self.dsos.items():
            for col in ['RA', 'Dec', 'Mag', 'Diam']:
                if col in v:
                    v[col] = float(v[col] if v[col] else 'nan')

        Logger.info('Catalogues: loaded {:} DSOs from {:} catalogues'.format(
            len(self.dsos), len(shipped + usercats)))

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
        excluded = self.exclude_cats.lower().split()
        deepcats = glob.glob(os.path.join(self.app.get_path('catalogues'), '*.npz'))
        for cat in deepcats:
            if os.path.basename(cat)[:-4].lower() not in excluded:
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



