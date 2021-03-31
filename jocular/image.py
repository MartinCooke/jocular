''' Represents a sub or a master calibration image; handles all 
    FITs reading/writing and metadata from FITs header and/or filename parsing
'''

import os
import time
import glob
from datetime import datetime
from astropy.io import fits
from kivy.logger import Logger


def is_fit(f):
    return f.lower().endswith('.fit') or f.lower().endswith('.fits')

class ImageNotReadyException(Exception):
    pass

def fits_in_dir(path):
    # get all fits in path, returning sorted by modification time
    fits = [f for f in glob.glob(os.path.join(path, '*')) if is_fit(f)]
    fits = {f: os.path.getmtime(f) for f in fits}
    return sorted(fits, key=fits.get)

def save_image(data=None, path=None, exposure=None, filt='L', sub_type='light', 
        nsubs=None, temperature=None):
    # saves sub or master
    try:
        hdu = fits.PrimaryHDU(data)
        hdr = hdu.header
        hdr['CREATOR'] = ('Jocular', 'v0.3')
        if exposure is not None:
            hdr['EXPOSURE'] = (exposure, 'seconds')
        if sub_type in {'master dark', 'master bias'}:
            hdr['FILTER'] = 'dark'
        else:
            hdr['FILTER'] = filt
        hdr['SUBTYPE'] = sub_type
        if temperature is not None:
            hdr['TEMPERAT'] = temperature
        if nsubs is not None:
            hdr['NSUBS'] = nsubs 
        hdu.writeto(path, overwrite=True)
    except Exception as e:
        Logger.warn('Image: unable to save image to {:} ({:})'.format(path, e))

class Image:

    # map from likely FITS header names to Image attribute names
    hmap = {
        'exposure': 'exposure', 'exptime': 'exposure', 'expo': 'exposure', 'exp': 'exposure',
        'filter': 'filter', 'filt': 'filter',
        'subtype': 'sub_type', 'sub_type': 'sub_type', 'imagetyp': 'sub_type',
        'temperat': 'temperature', 'temp': 'temperature',
        'nsubs': 'nsubs'}

    # map from possible found filter names to the Jocular scheme
    filter_map = {'r': 'R', 'g': 'G', 'b': 'B', 'red': 'R', 'green': 'G', 'blue': 'B', 'dark': 'dark',  
        'ha': 'Ha', 'halpha': 'Ha', 'sii': 'SII', 'oiii': 'OIII', 'spect': 'spec', 'l': 'L', 'lum': 'L'}


    def __init__(self, path=None, verbose=False, check_image_data=False):
        ''' Generate Image instance from path. Throw ImageNotReadyException in cases where re-reading
            on next event cycle might be successful.
        '''

        if path is None:
            return

        if not is_fit(path):
            raise Exception('not a fits file {:}'.format(path))

        try:
            with fits.open(path) as hdu1:
                hdu1.verify('silentfix')
                hdr = hdu1[0].header
                # we check that the image is readable if necessary
                if check_image_data:
                    self.image = hdu1[0].data
                else:
                    self.image = None
        except Exception:
            self.image = None
            raise ImageNotReadyException('Cannot read fits header for {:}'.format(path))

        if int(hdr['NAXIS']) != 2:
            raise Exception('FITS does not contain 2D data')

        # extract any relevant information from FITs header

        fits_props = {}
        for k, v in hdr.items():
            if k.lower() in self.hmap:
                fits_props[self.hmap[k.lower()]] = v

        self.created_by_jocular = 'CREATOR' in hdr and hdr['CREATOR'].startswith('Jocular')

        self.shape = hdr['NAXIS1'], hdr['NAXIS2']
        self.shape_str = '{:}x{:}'.format(self.shape[0], self.shape[1])

        self.name = os.path.basename(path)
        self.path = path

        self.create_time = datetime.fromtimestamp(os.path.getmtime(path))
        self.arrival_time = datetime.now()
        self.age = (self.arrival_time - self.create_time).days

        # get info from filename
        name = os.path.splitext(self.name.lower())[0]

        # is it a master? check FITs subtype or name
        self.is_master = fits_props.get('sub_type', '').lower().startswith('master') or name.startswith('master')
        #self.is_master = name.startswith('masterflat') or name.startswith('masterdark') or name.startswith('masterbias')
        filename_props = self.parse_master(name[6:]) if self.is_master else self.parse_sub(name)

        # fits properties override filename properties
        props = {**filename_props, **fits_props}


        #----------- validate and normalise property values

        # sub type
        st = props.get('sub_type', '').lower()
        if st.startswith('master'):  # change 'master ' to 'master'
            st = st[6:].strip()
        if st[:4] in {'bias', 'dark', 'flat'}:
            props['sub_type'] = st[:4]
        else:
            props['sub_type'] = 'light'

        # exposure can be a number, or can a string be expressed in s or ms
        if 'exposure' in props and type(props['exposure']) == str:
            v = props['exposure'].lower()
            try:
                if v.endswith('ms'):
                    props['exposure'] = float(v[:-2]) / 1000
                elif v.endswith('s'):
                    props['exposure'] = float(v[-1])
                else:
                    props['exposure'] = float(v)
            except:
                del props['exposure']  # invalid exposure so remove it

        # filter might be R, r, red, filter: red, red filter, ...
        if 'filter' in props:
            v = props['filter'].lower()
            if v.endswith('filter'):
                v = v[:-6].strip()
            if v.startswith('filter'):
                v = v[6:].strip()
            if v in self.filter_map:
                props['filter'] = self.filter_map[v]
            else:
                del props['filter']

        # temperature format might be a number, or followed by C
        if 'temperature' in props and type(props['temperature']) == str:
            v = props['temperature'].lower()
            if v.endswith('c'):
                v = v[:-1].strip()
            try:
                props['temperature'] = float(v)
            except:
                del props['temperature']

        # number of subs
        if 'nsubs' in props and type(props['nsubs']) == str:
            v = props['nsubs']
            try:
                props['nsubs'] = int(v)
            except:
                del props['nsubs']

        # now assign relevant properties (and some defaults) to Sub
        self.exposure = props.get('exposure', None)

        # record the fact that exposure is purely an estimate (will allow user to later change it)
        self.exposure_is_an_estimate = self.exposure == None
        # record whether exposure has been estimated by user (using capture GUI)
        self.exposure_is_manual_estimate = False

        self.filter = props.get('filter', 'L')
        self.temperature = props.get('temperature', None)
        self.nsubs = props.get('nsubs', None)
        self.sub_type = props['sub_type']

        self.status = 'select'
        self.arrival_time = int(time.time())
        self.keyframe = False
        self.calibrations = {'dark': False, 'flat': False, 'bias': False}

        # force reload; is this necessary?
        # self.image = None

        # if verbose:
        #     self.describe()
        # self.describe()

    def describe(self):
        # for debugging
        if self.is_master:
            Logger.info('Image: Master {:}'.format(self.name))
        else:
            Logger.info('Image: Sub {:}'.format(self.name))
        Logger.info('Image:    {:9s} {:14s} ({:} days) {:5s} {:}s {:} {:} {:} {:}'.format(
            self.shape_str, 
            self.create_time.strftime('%d %b %y %H:%M'),
            self.age,
            self.sub_type,
            self.exposure if self.exposure else '?',
            '(est.)' if self.exposure_is_an_estimate else '',
            self.filter + ' filter' if self.filter else '',
            str(self.temperature) + 'C' if self.temperature else '',
            str(self.nsubs) + ' subs in master' if self.nsubs else ''
            ))


    def parse_sub(self, nm):
        # should extend this to support same parsing as calibration masters

        props = {}

        # pre v3 Jocular convention first
        try:
            [sub_type, filt, expo, subnum] = nm.split('_')
            props = {'sub_type': sub_type, 'filter': filt, 'exposure': int(expo[:-2]) / 1000.0}
        except:
            # parse name in one of 2 SLL formats
            nm = nm.lower()
            if nm.startswith('image_sll.'):
                nm = nm[10:]
            elif nm.startswith('image__'):
                nm = nm[7:]
            elif nm.startswith('image_'):
                nm = nm[6:]

            if nm.startswith('red') or nm.endswith('_red'):
                props['filter'] = 'R'
            elif nm.startswith('green') or nm.endswith('_green'):
                props['filter'] = 'G'
            elif nm.startswith('blue') or nm.endswith('_blue'):
                props['filter'] = 'B'
            elif nm.startswith('ha') or nm.endswith('_ha'):
                props['filter'] = 'Ha'
            elif nm[:4] in ['flat', 'dark', 'bias']:
                props['sub_type'] = nm[:4]

        return props

    def parse_master(self, nm):
        # nm  of form <type>_<key>=<value> where keys can come in any order
        # and keys are any of the things in the keymap

        prop_sep = '_'
        key_value_sep = '='
        parts = nm.split(prop_sep)
        props = {'sub_type': parts[0]}
 
        for p in parts[1:]:
            try:
                k, v = p.split(key_value_sep)
                if k in self.hmap:
                    props[self.hmap[k]] = v 
            except:
                pass

        return props

    def get_image(self):
        if self.image is None:
            try:
                with fits.open(self.path) as hdu:
                    bp = hdu[0].header['BITPIX']
                    if bp < 0:
                        self.image = hdu[0].data
                    else:
                        self.image = hdu[0].data / 2 ** bp
            except Exception as e:
                Logger.error('Image: cannot read image data from {:} ({:})'.format(self.path, e))
        return self.image

    def get_master_data(self):
        # we don't rescale masters (at least not Jocular ones; not sure about the rest)
        if self.image is None:
            try:
                with fits.open(self.path) as hdu:
                    self.image = hdu[0].data
                # if it seems to be unscaled, scale it
                # if np.max(self.image) > 10:
                #     self.image /= 2 ** np.abs(hdu[0].header['BITPIX'])
            except Exception as e:
                Logger.error('Image: cannot read image data from {:} ({:})'.format(self.path, e))
        return self.image

