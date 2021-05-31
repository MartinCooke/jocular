''' Represents a sub or a master calibration image; handles all 
    FITs reading/writing and metadata from FITs header and filename parsing
'''

import os
import time
import glob
import numpy as np
from datetime import datetime
from astropy.io import fits
from loguru import logger

from jocular import __version__
from jocular.exposurechooser import str_to_exp

def is_fit(f):
    return f.lower().endswith('.fit') or f.lower().endswith('.fits')

class ImageNotReadyException(Exception):
    pass

def fits_in_dir(path):
    # get all fits in path, returning sorted by modification time
    fits = [f for f in glob.glob(os.path.join(path, '*')) if is_fit(f)]
    fits = {f: os.path.getmtime(f) for f in fits}
    return sorted(fits, key=fits.get)

# to do: add creation date
def save_image(data=None, path=None, exposure=None, filt='L', sub_type='light', 
        nsubs=None, temperature=None):
    # saves sub or master
    try:
        hdu = fits.PrimaryHDU(data)
        hdr = hdu.header
        hdr['CREATOR'] = ('Jocular', __version__)
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
        logger.info('saved {:}'.format(path))
        for k, v in hdr.items():
            logger.debug('{:9s} = {:}'.format(k, v))

    except Exception as e:
        logger.warning('unable to save to {:} ({:})'.format(path, e))

def update_fits_header(path, exposure=None, sub_type=None, temperature=None):
    ''' modify headers
    '''
    try:
        with fits.open(path, mode='update') as hdu:
            hdr = hdu[0].header
            if exposure is not None:
                hdr['EXPOSURE'] = (exposure, 'seconds')
            if sub_type is not None:
                hdr['SUBTYPE'] = sub_type
            if temperature is not None:
                hdr['TEMPERAT'] = temperature
            hdu.close()
    except Exception as e:
        logger.exception('Unable to reader fits header for {:} ({:})'.format(path, e))
        return


class Image:

    # map from various FITS header names to Image attribute names
    hmap = {
        'exposure': 'exposure', 'exptime': 'exposure', 'expo': 'exposure', 'exp': 'exposure',
        'filter': 'filter', 'filt': 'filter',
        'subtype': 'sub_type', 'sub_type': 'sub_type', 'imagetyp': 'sub_type',
        'temperat': 'temperature', 'temp': 'temperature', 'ccd-temp': 'temperature',
        'nsubs': 'nsubs', 'stackcnt': 'nsubs'}

    # map from possible found filter names to the Jocular scheme
    filter_map = {'r': 'R', 'g': 'G', 'b': 'B', 'red': 'R', 'green': 'G', 
        'blue': 'B', 'dark': 'dark',  
        'ha': 'Ha', 'halpha': 'Ha', 'sii': 'SII', 'oiii': 'OIII',
        'spect': 'spec', 'l': 'L', 'lum': 'L', 'no': 'L', 'none': 'L'}


    def __init__(self, path=None, verbose=False, check_image_data=False):
        ''' Generate Image instance from path. Throw ImageNotReadyException 
            in cases where re-reading on next event cycle might be successful.
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
                    bp = hdr['BITPIX']
                    if bp < 0:
                        self.image = hdu1[0].data
                    else:
                        self.image = hdu1[0].data / 2 ** bp
                else:
                    self.image = None
        except Exception:
            self.image = None
            raise ImageNotReadyException('Cannot read fits header for {:}'.format(path))

        # check for a well-formed image (new in v0.5)
        if self.image is not None:
            shape = self.image.shape
            if len(shape) == 3:
                if shape[0] != 3 and shape[2] != 3:
                    raise Exception('3D fits without 3 planes {:}'.format(path))
            elif len(shape) != 2:
                raise Exception('can only handle 2D or 3D fits {:}'.format(path))

        try:

            self.path = path
            self.create_time = datetime.fromtimestamp(os.path.getmtime(path))
            self.arrival_time = datetime.now()
            self.age = (self.arrival_time - self.create_time).days
            self.created_by_jocular = 'CREATOR' in hdr and hdr['CREATOR'].startswith('Jocular')
            self.shape = hdr['NAXIS1'], hdr['NAXIS2']
            self.shape_str = '{:}x{:}'.format(self.shape[0], self.shape[1])
            self.fullname = os.path.basename(path)
            self.name = os.path.splitext(os.path.basename(path).lower())[0]

        except Exception as e:
            logger.exception(e)

        # default values (these will get overriden if they exist in name or FITs)
        default_props = {
            'exposure': None, 
            'sub_type': 'light', 
            'filter': 'L', 
            'temperature': None,
            'nsubs': None}

        # extract any relevant information from FITs header
        fits_props = {}
        for k, v in hdr.items():
            if k.lower() in self.hmap:
                fits_props[self.hmap[k.lower()]] = v

        try:
            # is it a master?
            self.is_master = self.name.startswith('master') or \
                fits_props.get('sub_type', '').lower().startswith('master') or \
                fits_props.get('nsubs', 0) > 1

        except Exception as e:
            logger.exception(e)

        # get properties from name
        if self.is_master:
            name_props = self.parse_master(self.name[6:])
        else:
            name_props = self.parse_sub(self.name)

        # form properties by overriding
        props = {**default_props, **name_props, **fits_props}

        # rationalise properties as well as possible

        try:
            if props['exposure'] is not None:
                try:
                    props['exposure'] = str_to_exp(props['exposure'])
                except:
                    props['exposure'] = None

            st = props['sub_type'].lower()
            if st.startswith('master'):  # change 'master ' to 'master'
                st = st[6:].strip()
            if st[:4] in {'bias', 'dark', 'flat'}:
                props['sub_type'] = st[:4]
            else:
                props['sub_type'] = 'light'

            # filter might be R, r, red, filter: red, red filter, ...
            v = props['filter'].lower()
            if v.endswith('filter'):
                v = v[:-6].strip()
            if v.startswith('filter'):
                v = v[6:].strip()
            props['filter'] = self.filter_map.get(v, v)   # untested change in v0.5

            # temperature format might be a number, or followed by C
            if props['temperature'] is not None:
                v = str(props['temperature']).lower()
                if v.endswith('c'):
                    v = v[:-1].strip()
                try:
                    props['temperature'] = float(v)
                except:
                    props['temperature'] = None

            # number of subs
            if props['nsubs'] is not None:
                try:
                    props['nsubs'] = int(props['nsubs'])
                except:
                    props['nsubs'] = None

        except Exception as e:
            logger.exception(e)

        # now assign relevant properties (and some defaults) to Sub
        self.exposure = props['exposure']
        self.filter = props['filter']
        self.temperature = props['temperature']
        self.nsubs = props['nsubs']
        self.sub_type = props['sub_type']

        self.status = 'select'
        self.arrival_time = int(time.time())
        self.keyframe = False
        self.calibrations = {'dark': False, 'flat': False, 'bias': False}

        if verbose:
            self.describe(fits_props=fits_props, name_props=name_props)

    def describe(self, fits_props=None, name_props=None):
        # for debugging
        created_by = 'Jocular' if self.created_by_jocular else 'alien'
        if self.is_master:
            logger.debug('{:} Master {:}'.format(created_by, self.name))
        else:
            logger.debug('{:} Sub {:}'.format(created_by, self.name))
        im = self.get_image()
        logger.debug('{:9s} {:14s} ({:} days) {:5s} expo {:} filt {:} {:} {:}'.format(
            self.shape_str, 
            self.create_time.strftime('%d %b %y %H:%M'),
            self.age,
            self.sub_type,
            self.exposure,
            self.filter,
            str(self.temperature) + 'C' if self.temperature is not None else '',
            str(self.nsubs) + ' subs in master' if self.nsubs is not None else ''))
        logger.debug('from FITS: {:}'.format(fits_props))
        logger.debug('from name: {:}'.format(name_props))
        logger.debug('min {:.4f} max {:.4f} mean {:.4f}'.format(
            np.min(im), np.max(im), np.mean(im)))


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
                logger.warning('cannot read image data from {:} ({:})'.format(self.path, e))
        return self.image

