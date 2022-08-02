''' Represents a sub or a master calibration image; handles all 
    FITs reading/writing plus metadata from FITs header/filename parsing
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

''' map from FITs names (converted to lower case) to Image attributes; 
    (1) can have multiple names mapping to same attribute
    (2) keys must be lower case for lookup, even though UC in FITs
    (3) values must have case as used in Image props and rest of program
    (4) any that are not same in UC must be specified in imagepropmap
'''
fitspropmap = {
        'exptime': 'exposure', 'expo': 'exposure', 'exp': 'exposure',
        'filt': 'filter',
        'roi_x': 'ROI_x', 'roi_y': 'ROI_y', 'roi_w': 'ROI_w', 'roi_h': 'ROI_h',
        'calibrat': 'calibration_method',
        'subtype': 'sub_type', 'imagetyp': 'sub_type',
        'temperat': 'temperature', 'temp': 'temperature', 'ccd-temp': 'temperature',
        'stackcnt': 'nsubs',
        'xpixsz': 'pixel_width', 'ypixsz': 'pixel_height',
        'xbinning': 'binning',
        'ybinning': 'binning',
        'instrume': 'camera'
        }

''' used to map from image prop names to fits name if they are difference; 
    can't use inverse of fitspropmap as it is not unique
'''
imagepropsmap = {
    'calibration_method': 'calibrat',
    'pixel_width': 'xpixsz',
    'pixel_height': 'ypixsz',
    'temperature': 'temperat'
}

fitscomments = {
    'calibration_method': 'calibration method applied to master flats'
}

''' properties we must have (even if None) in each Image instance
    these are overridden by name and FITs properties
'''
default_props = {
    'exposure': None, 
    'sub_type': 'light', 
    'filter': 'L', 
    'temperature': None,
    'gain': None,
    'offset': None,
    'camera': None,
    'binning': 1,
    'ROI_x': None,
    'ROI_y': None,
    'ROI_w': None,
    'ROI_h': None,
    'pixel_width': None,
    'pixel_height': None,
    'calibration_method': 'None',
    'nsubs': None}

# map from possible found filter names to the Jocular scheme
filter_map = {'r': 'R', 'g': 'G', 'b': 'B', 'red': 'R', 'green': 'G', 
    'blue': 'B', 'dark': 'dark',  
    'ha': 'H', 'halpha': 'H', 'h': 'H',
    's': 'S', 'sii': 'S', 's': 'S',
    'oiii': 'O', 'o': 'O',
    'spect': 'spec', 'l': 'L', 'lum': 'L', 'no': 'L', 'none': 'L'}

# this should be moved to a fits module
def update_wcs(im=None, path=None, w=None, h=None, fov_w=None, fov_h=None, ra0=None, dec0=None, north=None):
    ''' add or update FITs at path with WCS keys
        see 
            [1] https://fits.gsfc.nasa.gov/standard40/fits_standard40aa-le.pdf
            [2] https://learn.astropy.org/tutorials/celestial_coords1.html
            [3] https://docs.astropy.org/en/stable/api/astropy.wcs.Wcsprm.html#astropy.wcs.Wcsprm
    '''
    from astropy.wcs import WCS

    # provide rotation matrix
    theta = np.radians(north)
    costheta, sintheta = np.cos(theta), np.sin(theta)

    # NB axis 1 is RA
    wcs_dict = {
        'CTYPE1': 'RA---TAN', # RA to gnomonic
        'CUNIT1': 'deg',      # RA in degrees
        'CDELT1': -fov_w / w, # degrees increment per pixel (neg because RA decreases to R)
        'CRPIX1': w // 2,     # central pixel in x; might need to alter this by 1 
        'CRVAL1': ra0,        # RA value at central pixel
        'NAXIS1': w,          # size of axis 1
        'CTYPE2': 'DEC--TAN', 
        'CUNIT2': 'deg', 
        'CDELT2': fov_h / h, 
        'CRPIX2': h // 2,     # might need to alter this by 1?
        'CRVAL2': dec0,
        'PC1_1':  costheta,   # rotation matrix
        'PC1_2':  -sintheta,  #   cos -sin  ===   PC1_1 PC1_2
        'PC2_1':  sintheta,   #   sin  cos  ===   PC2_1 PC2_2
        'PC2_2':  costheta,   # 
        'NAXIS2': h
    }

    wcs_hdr = WCS(wcs_dict)

    # # to do: update FITs header
    # # to start with, generate a testfits with the image and WCS info
    # # to plot and overlay axes
    from astropy.io import fits
    from datetime import datetime

    hdu = fits.PrimaryHDU(im, header=wcs_hdr.to_header())
    hdr = hdu.header
    hdr['CREATOR'] = ('Jocular')
    date_obs = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
    hdr['DATE-OBS'] = date_obs
    hdu.writeto('platesolved_wcs_' + date_obs + '.fits')


def convert_fits_props(hdr):
    ''' form dict from Image prop to value but don't include unknown FITs props
    '''
    props = {}
    for k, v in hdr.items():
        ktran = fitspropmap.get(k.lower(), k.lower())
        if ktran in default_props:
            props[ktran] = v
    return props


def is_fit(f):
    return f.lower().endswith('.fit') or f.lower().endswith('.fits')



class ImageNotReadyException(Exception):
    pass


def fits_in_dir(path):
    # get all fits in path, returning sorted by modification time
    fits = [f for f in glob.glob(os.path.join(path, '*')) if is_fit(f)]
    fits = {f: os.path.getmtime(f) for f in fits}
    return sorted(fits, key=fits.get)


def save_image(data=None, path=None, capture_props=None):
    ''' saves sub or master to path
        capture_props is a dict to save e.g. gain, offset, expo
    '''

    dupes = [
        ('SUBTYPE', 'IMAGETYP'),
        ('EXPOSURE', 'EXPTIME'), 
        ('CAMERA', 'INSTRUME'), 
        ('NSUBS', 'STACKCNT'),
        ('BINNING', 'XBINNING'),
        ('BINNING', 'YBINNING'),
        ('TEMPERAT', 'CCD-TEMP')
    ]

    exposure = capture_props.get('exposure', None)
    sub_type = capture_props.get('sub_type', 'L')
    filt = capture_props.get('filter', 'L')
    temperature = capture_props.get('temperature', None)
    nsubs = capture_props.get('nsubs', None)

    try:
        hdu = fits.PrimaryHDU(data)
        hdr = hdu.header
        hdr['CREATOR'] = ('Jocular', __version__)
        hdr['DATE-OBS'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
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

        # add any other keys that are not in the header
        # ensuring that any conversions are done
        for k, v in capture_props.items():
            newk = imagepropsmap.get(k.lower(), k).upper()
            if v is not None and newk not in hdr:
                hdr[newk] = (v, fitscomments.get(k, ''))

        # duplicate values for alternative keys
        for key, altkey in dupes:
            if key in hdr:
                hdr[altkey] = hdr[key]

        hdu.writeto(path, overwrite=True)
        logger.info(f'saved {path}')
        for k, v in hdr.items():
            logger.trace(f'{k:9s} = {v}')

    except Exception as e:
        logger.warning(f'unable to save to {path} ({e})')

# def update_fits_header(path, exposure=None, sub_type=None, temperature=None):
#     ''' modify headers; not used currently but will be used when advanced
#         save is re-implemented in ObjectIO
#     '''
#     try:
#         with fits.open(path, mode='update') as hdu:
#             hdr = hdu[0].header
#             if exposure is not None:
#                 hdr['EXPOSURE'] = (exposure, 'seconds')
#             if sub_type is not None:
#                 hdr['SUBTYPE'] = sub_type
#             if temperature is not None:
#                 hdr['TEMPERAT'] = temperature
#             hdu.close()
#     except Exception as e:
#         logger.exception('Unable to read fits header for {:} ({:})'.format(path, e))
#         return


class Image:
    ''' Represents sub or master
    '''

    def __init__(self, path=None, verbose=False, check_image_data=False):
        ''' Generate Image instance from path. Throw ImageNotReadyException 
            in cases where re-reading on next event cycle might be successful.
        '''

        # while testing
        verbose = False

        if path is None:
            return

        if not is_fit(path):
            raise Exception(f'not a fits file {path}')

        try:
            # added in v0.5.6 ignore missing end
            with fits.open(path, ignore_missing_end=True) as hdu1:
                hdu1.verify('silentfix')
                hdr = hdu1[0].header
                # we check that the image is readable if necessary
                if check_image_data:
                    bp = hdr['BITPIX']
                    if bp < 0:
                        self.image = hdu1[0].data
                    else:
                        self.image = hdu1[0].data / 2 ** bp

                    self.minval = np.min(self.image) * 100
                    self.maxval = np.percentile(self.image, 99.99) * 100
                    self.meanval = np.mean(self.image) * 100
                    self.overexp = np.mean(self.image > .99) * 100
                else:
                    self.image = None
                    self.minval, self.maxval, self.meanval, self.overexp = .0, .0, .0, .0

        except Exception as e:
            self.image = None
            raise ImageNotReadyException(f'Cannot read fits header for {path} ({e})')

        if verbose:
            logger.trace('From FITS header')
            for k, v in hdr.items():
                logger.trace(f'{k:9s} = {v}')

        # check for a well-formed image (new in v0.5)
        if self.image is not None:
            shape = self.image.shape
            if len(shape) == 3:
                if shape[0] != 3 and shape[2] != 3:
                    raise Exception(f'3D fits without 3 planes {path}')
            elif len(shape) != 2:
                raise Exception(f'can only handle 2D or 3D fits {path}')

        try:
            self.path = path
            self.create_time = datetime.fromtimestamp(os.path.getmtime(path))
            self.arrival_time = datetime.now()
            self.age = (self.arrival_time - self.create_time).days
            self.created_by_jocular = 'CREATOR' in hdr and hdr['CREATOR'].startswith('Jocular')
            self.shape = hdr['NAXIS1'], hdr['NAXIS2']
            self.shape_str = f'{self.shape[0]}x{self.shape[1]}'
            self.fullname = os.path.basename(path)
            self.name = os.path.splitext(os.path.basename(path).lower())[0]
            self.pp_create_time = self.create_time.strftime('%d %b %y %H:%M:%S')
        except Exception as e:
            logger.exception(e)

        # extract any relevant information from FITs header
        fits_props = convert_fits_props(hdr)

        try:
            # is it a master?
            self.is_master = self.name.startswith('master') or \
                fits_props.get('sub_type', '').lower().startswith('master') # or \
                # fits_props.get('nsubs', 0) > 1

        except Exception as e:
            logger.exception(e)

        # get properties from name
        if self.is_master:
            name_props = self.parse_master(self.name[6:])
        else:
            name_props = self.parse_sub(self.name)

        # form properties by overriding
        props = {**default_props, **name_props, **fits_props}

        # rationalise properties
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

            # filter might be R, r, red, filter: red, red filter, ...
            if type(props['filter']) == str:
                v = props['filter'].lower()
                if v.endswith('filter'):
                    v = v[:-6].strip()
                if v.startswith('filter'):
                    v = v[6:].strip()
                props['filter'] = filter_map.get(v, v)   # untested change in v0.5
            else:
                props['filter'] = 'L'

            # temperature format might be a number, or followed by C
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

        # assign properties to Image instance
        for p in default_props:
            setattr(self, p, props[p])

        self.status = 'select'
        self.aligned = 'no'
        self.arrival_time = int(time.time())
        self.keyframe = False
        self.calibrations = {'dark': False, 'flat': False, 'bias': False}

        self.describe(
            fits_props=fits_props, 
            name_props=name_props, 
            verbose=verbose)


    def describe(self, fits_props=None, name_props=None, verbose=False):
        created_by = 'Jocular' if self.created_by_jocular else 'alien'
        if self.is_master:
            logger.debug(f'{created_by} Master {self.name}')
        else:
            logger.debug(f'{created_by} Sub {self.name}')
        if not verbose:
            return

        # list essential props
        for p in default_props:
            logger.trace(f'{p} = {getattr(self, p)}')

        # some image stats
        im = self.get_image()
        logger.trace(f'min {np.min(im):.4f} max {np.max(im):.4f} mean {np.mean(im):.4f}')

        # may be other props we want to output at some point
        # logger.trace('{:9s} {:14s} ({:} days) {:5s} expo {:} filt {:} gain {:} bin {:} {:} {:}'.format(
        #     self.shape_str, 
        #     self.create_time.strftime('%d %b %y %H:%M'),
        #     self.age,
        #     self.sub_type,
        #     self.exposure,
        #     self.filter,
        #     'no' if self.gain is None else self.gain,
        #     self.binning,
        #     str(self.temperature) + 'C' if self.temperature is not None else '',
        #     str(self.nsubs) + ' subs in master' if self.nsubs is not None else ''))
        # logger.trace('from FITS: {:}'.format(fits_props))
        # logger.trace('from name: {:}'.format(name_props))



    def parse_sub(self, nm):
        # should extend this to support same parsing as calibration masters

        props = {}

        # bug here if user has 3 underscores in name....

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
        # and keys are any of the things in the keymap

        prop_sep = '_'
        key_value_sep = '='
        parts = nm.split(prop_sep)
        props = {'sub_type': parts[0]}
 
        for p in parts[1:]:
            try:
                k, v = p.split(key_value_sep)
                if k.lower() in self.fitspropmap:
                    props[self.self.fitspropmap[k]] = v 
            except:
                pass

        return props

    def get_image(self):
        ''' Changed to represent subs as float32
        '''
        if self.image is None:
            try:
                with fits.open(self.path) as hdu:
                    bp = hdu[0].header['BITPIX']
                    self.image = np.array(hdu[0].data, dtype=np.float32)
                    if bp > 0:
                        self.image /= (2 ** bp)
                    self.minval = np.min(self.image) * 100
                    self.maxval = np.percentile(self.image, 99.99) * 100
                    self.meanval = np.mean(self.image) * 100
                    self.overexp = np.mean(self.image > .99) * 100   
            except Exception as e:
                logger.warning(f'cannot read image data from {self.path} ({e})')
        return self.image


    # def get_cached_image(self):
    #     ''' Images are stored in a temp folder
    #     '''

