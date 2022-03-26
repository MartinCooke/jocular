''' Handles calibration library and calibration of subs.
'''

import os.path
import numpy as np
# from scipy.stats import trimboth
from loguru import logger

from kivy.app import App
from kivy.properties import (
    BooleanProperty, DictProperty, 
    NumericProperty, StringProperty
    )
from kivy.core.window import Window

from jocular.table import Table
from jocular.utils import make_unique_filename, toast, percentile_clip
from jocular.component import Component
from jocular.settingsmanager import Settings
from jocular.image import Image, save_image, fits_in_dir
from jocular.exposurechooser import exp_to_str
from jocular.gradient import estimate_background

date_time_format = '%d %b %y %H:%M'

def none_to_empty(x):
    return '' if x is None else x

def subregion(m, s):
    ''' Return x and y limits of master (m) that correspond 
        to sub (s), or None if not possible to use this master
    '''

    if m is None:
        return None

    ''' if camera is unknown or different for master and sub,
        only allow subregion processing if the shape is identical
    '''

    if (m.camera is None) or (s.camera is None) or (m.camera != s.camera):
        if (m.shape[0] != s.shape[0]) or (m.shape[1] != s.shape[1]):
            return None

    # extract region covered by m and s
    mx = 0 if m.ROI_x is None else m.ROI_x
    my = 0 if m.ROI_y is None else m.ROI_y
    sx = 0 if s.ROI_x is None else s.ROI_x
    sy = 0 if s.ROI_y is None else s.ROI_y
    mw = m.shape[0] if m.ROI_w is None else m.ROI_w
    mh = m.shape[1] if m.ROI_h is None else m.ROI_h
    sw = s.shape[0] if s.ROI_w is None else s.ROI_w
    sh = s.shape[1] if s.ROI_h is None else s.ROI_h

    # forms subregion bounds
    x0 = sx - mx
    x1 = x0 + sw
    y0 = sy - my
    y1 = y0 + sh

    # if s fits within m, return bounds
    if x0 >= 0 and y0 >= 0 and x1 <= mw and y1 <= mh:
        return (x0, x1, y0, y1)

    return None

class Calibrator(Component, Settings):

    save_settings = ['apply_dark', 'apply_flat']

    masters = DictProperty({})
    apply_flat = BooleanProperty(False)
    apply_dark = BooleanProperty(False)

    use_l_filter = BooleanProperty(True)
    remove_hot_pixels = BooleanProperty(True)
    fd_exposure_tol = NumericProperty(.1)
    exposure_tol = NumericProperty(5)
    temperature_tol = NumericProperty(5)
    dark_days_tol = NumericProperty(1)
    flat_calibration = StringProperty('bias')

    tab_name = 'Calibration'

    configurables = [
        ('flat_calibration', {
            'name': 'flat calibration method', 
            'options': ['bias', 'flat-dark', 'constant'],
            'help': 'how to calibrate flat subs when generating a master flat'
            }),
        ('fd_exposure_tol', {
            'name': 'flat-dark exposure tol', 
            'float': (0, 2, .1),
            'fmt': '{:.1f} seconds',
            'help': 'If using flat-darks, how close must exposure be (seconds)'
            }),
        ('use_l_filter', {
            'name': 'use L flat?', 
            'switch': '',
            'help': 'If there is no flat for the given filter, use a L flat if it exists'
            }),
        ('exposure_tol', {
            'name': 'exposure tolerance', 
            'float': (0, 30, 1), 
            'fmt': '{:.0f} seconds',
            'help': 'When selecting a dark, select those within this exposure tolerance'
            }),
        ('temperature_tol', {
            'name': 'temperature tolerance', 
            'float': (0, 40, 1),
            'fmt': '{:.0f} degrees',
            'help': 'When selecting a dark, restrict to those within this temperature tolerance'
            }),
        ('dark_days_tol', {
            'name': 'dark age tolerance', 'float': (0, 300, 1),
            'fmt': '{:.0f} days',
            'help': 'Maximum age of darks to use if no temperature was specified'
            }),
        ('remove_hot_pixels', {
            'name': 'remove hot pixels?', 
            'switch': '',
            'help': 'Note that this is only done when creating calibration masters'
            })
    ]


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.calibration_dir = self.app.get_path('calibration')

        self.masters = {}   # map from name to FITs Image instance
        self.library = {}   # map from name to calibration table info
 
        ''' construct above dicts from calibration FITs in calibration directory
        '''
        for f in fits_in_dir(self.calibration_dir):
            path = os.path.join(self.calibration_dir, f)
            try:
                s = Image(path)
                if s.is_master:
                    self.add_to_library(s)
            except Exception as e:
                logger.warning('Calibrator: unable to parse calibration {:} ({:})'.format(f, e))


    def on_new_object(self, *args):
        n_masters = len(self.library)
        if n_masters > 0:
            self.info('{:d} masters'.format(n_masters))
        else:
            self.info('no masters')

    def add_to_library(self, m):
        ''' called on initialisation and when we save a new master
        '''

        # keys are full names so they can be reliably deleted
        self.masters[m.fullname] = m
        self.library[m.fullname] = {
            'name': m.name,
            'camera': none_to_empty(m.camera),
            'type': m.sub_type,
            'exposure': exp_to_str(m.exposure) if m.exposure is not None else '',
            'temperature': str(m.temperature) if m.temperature is not None else '',
            'gain': none_to_empty(m.gain),
            'offset': none_to_empty(m.offset),
            'bin': none_to_empty(m.binning),
            'calibration_method': none_to_empty(m.calibration_method),
            #'ROI': none_to_empty(m.ROI),
            'filter': m.filter,
            'created': m.create_time.strftime(date_time_format),
            'shape_str': m.shape_str,
            'age': m.age,
            'nsubs': m.nsubs if m.nsubs is not None else 0
        }


    def create_master(self, capture_props=None):
        ''' Called by ObjectIO to save an existing stack capture by 
            Jocular as a calibration master
        '''

        if 'filter' not in capture_props:
            toast('Cannot create master: unknown filter', 5)
            return

        stacker = Component.get('Stacker')
        sub_type = capture_props['sub_type']

        if sub_type == 'flat' and capture_props['calibration_method'] == 'None':
            toast('Cannot create master flat: flat is uncalibrated', 5)
            return

        ''' Get hold of master from stacker, forcing the use of stack
            combination method that the user has chosen
        '''
        master = stacker.get_stack(capture_props['filter'], calibration=True)
        capture_props['nsubs'] = stacker.get_selected_sub_count()

        ''' Remove hot pixels from calibration frame
        '''

        # possibly shouldn't do this for dark/bias frames
        if sub_type == 'flat':
            master = Component.get('BadPixelMap').remove_hotpix(
                master, 
                apply_BPM=self.remove_hot_pixels)

        ''' Flats were divided thru by their robust mean to account for 
            level differences but then scaled to 50% to enable B/W controls; 
            Here, normalise to unity based on central region
        '''
        if sub_type == 'flat':
            w, h = master.shape
            w1, w2 = int(w / 3), int(2 * w / 3)
            h1, h2 = int(h / 3), int(2 * h / 3)
            imr = master[h1: h2, w1: w2]
            robust_mean = percentile_clip(imr.ravel(), perc=75)
            master = master / robust_mean

        self.save_master(data=master, capture_props=capture_props)


    def save_master(self, data=None, capture_props=None):
        ''' Save master and add to library to make it available immediately. Called both by
            create_master above and by the Watched camera for any alien master subs. The difference is
            that create_master above does BPM/flat handling etc so only applies to natively-captured
            calibration masters.
        '''

        name = 'master{:}.fit'.format(capture_props['sub_type'])
        path = make_unique_filename(os.path.join(self.calibration_dir, name))
        save_image(data=data, path=path, capture_props=capture_props)
        self.add_to_library(Image(path))

        # add to notes field of current DSO
        notes = 'Exposure {:}\n'.format(exp_to_str(capture_props.get('exposure', 0)))
        notes += '\n'.join(['{:} {:}'.format(k, v) for k, v in capture_props.items() 
            if k in {'filter', 'temperature', 'gain', 'offset', 'camera', 
                'binning', 'calibration_method'}])
        Component.get('Notes').notes = notes

        logger.info('new master {:}'.format(capture_props))


    def calibrate(self, sub):
        ''' Given a light sub, apply calibration. Fails silently if no suitable 
            calibration masters. Note that all flat masters are assumed to be
            calibrated (ie bias or flat-dark has been subtracted)
        '''

        sub.calibrations = set({})

        if len(self.library) == 0:
            self.info('no masters')
            return

        if not (self.apply_dark or self.apply_flat):
            self.info('none')
            return

        # get all masters anyway (~1ms)
        dark = self.get_dark(sub)
        flat = self.get_flat(sub)
        bias = self.get_bias(sub)
        
        logger.debug('D {:} F {:} B {:}'.format(dark, flat, bias))

        D = self.get_master(dark)
        F = self.get_master(flat)
        B = self.get_master(bias)

        im = sub.get_image()

        # to apply dark we just need a dark
        if self.apply_dark and dark is not None:
            dx0, dx1, dy0, dy1 = subregion(self.masters[dark], sub)
            logger.trace('Dark subregion {:} {:} {:} {:}'.format(
                dx0, dx1, dy0, dy1))
            im = im - D[dy0: dy1, dx0: dx1]
            sub.calibrations = {'dark'}

        # to apply flat we need a flat and either a bias or a dark
        if self.apply_flat and flat is not None:
            fx0, fx1, fy0, fy1 = subregion(self.masters[flat], sub)
            if 'dark' in sub.calibrations:
                im = im / F[fy0: fy1, fx0: fx1]
                sub.calibrations = {'dark', 'flat'}
            elif bias is not None:
                bx0, bx1, by0, by1 = subregion(self.masters[bias], sub)
                im = (im - B[by0: by1, bx0: bx1]) / F[fy0: fy1, fx0: fx1]
                sub.calibrations = {'bias', 'flat'}
            # else:
            #     # manufacture a constant dark using background
            #     mean_back, std_back = estimate_background(im)
            #     offset = mean_back - 5 * std_back
            #     im = ((im - offset) / F)  + offset
            #     sub.calibrations = {'syn-dark', 'flat'}

        # restore background to avoid clipping in next step 
        if 'bias' in sub.calibrations:
            im = im + np.mean(B)
        elif 'dark' in sub.calibrations:
            im = im + np.mean(D)

        # limit
        im[im < 0] = 0
        im[im > 1] = 1

        sub.image = im
        applied = ' '.join(list(sub.calibrations))
        if applied:
            self.info(applied)
        else:
            self.info('none suitable')


    def get_dark(self, sub, exposure_tol=None):
        ''' find darks with same camera, gain, offset, binning, shape, and
            with an exposure that is within tolerance
            NB for backwards compat, don't enforce camera if sub doesn't have one
        '''

        if sub.exposure is None:
            return None

        if exposure_tol is None:
            exposure_tol = self.exposure_tol

        darks = {k: v for k, v in self.masters.items()
                    if v.sub_type == 'dark' and
                        v.binning == sub.binning and
                        subregion(v, sub) is not None and
                        v.gain == (sub.gain if v.gain is not None else v.gain) and
                        v.offset == (sub.offset if v.offset is not None else v.offset) and
                        v.camera == (sub.camera if v.camera is not None else v.camera) and
                        v.exposure is not None and
                        abs(v.exposure - sub.exposure) <= self.exposure_tol
                }
                    
        temperature = Component.get('Session').temperature

        if temperature is not None:
            # we know temperature, select those with temperatures and within tolerance
            darks = [k for k, v in darks.items() if 
                v.temperature is not None and abs(v.temperature - temperature) < self.temperature_tol]
        else:
            # find those within date tolerance (set to 1 to get darks in current session)
            darks = [k for k, v in darks.items() if v.age < self.dark_days_tol]

        # if we have darks, return name of first one
        return darks[0] if len(darks) > 0 else None


    def get_flatdark(self, sub):
        ''' simply a dark within flat-dark exposure tolerance
        '''
        darks = self.get_dark(sub, exposure_tol=self.fd_exposure_tol)
        if len(darks) == 0:
            logger.debug('no matching flatdark')
            return None

        # find the one with the closest exposure
        for k in sorted(darks, key=darks.get):
            logger.debug('matching flatdark {:}'.format(k))
            return k


    def get_bias(self, sub):
        ''' find bias with same camera, gain, offset, binning, and shape
            NB for backwards compat, don't enforce camera if sub doesn't have one
        '''

        bias = {k: v.age for k, v in self.masters.items()
                    if v.sub_type == 'bias' and
                        v.binning == sub.binning and 
                        subregion(v, sub) is not None and
                        v.gain == (sub.gain if v.gain is not None else v.gain) and
                        v.offset == (sub.offset if v.offset is not None else v.offset) and
                        v.camera == (sub.camera if v.camera is not None else v.camera)
                }

        return min(bias, key=bias.get) if len(bias) > 0 else None
 

    def get_flat(self, sub):
        ''' find flat with same camera, binning, and shape
            NB for backwards compat, don't enforce props if sub doesn't have them
        '''

        flats = {k: v for k, v in self.masters.items()
                    if v.sub_type == 'flat' and
                        v.binning == sub.binning and 
                        subregion(v, sub) is not None and
                        v.camera == (sub.camera if v.camera is not None else v.camera)
                }

        # flat in required filter
        if sub.filter is not None:
            flats_in_filt = {k: v for k, v in flats.items() if v.filter is not None and v.filter == sub.filter}
        else:
            flats_in_filt = {} 

        # if we have none and can use L filter, use these
        if (len(flats_in_filt) == 0) and self.use_l_filter:
            flats_in_filt = {k:v for k, v in flats.items() if v.filter == 'L'}

        # do we have any now? if not, return
        if len(flats_in_filt) == 0:
            return None

        # map from flat to difference between sub create time and master create time
        flats = {k: abs(v.create_time - sub.create_time).days for k,v in flats_in_filt.items()}

        # find closest in date
        for k in sorted(flats, key=flats.get):
            return k


    def get_master(self, name):
        if name is None:
            return None
        # Retrieve image (NB loaded on demand, so effectively a cache)
        return self.masters[name].get_image()

    def _most_subs(self, cands):
        c = {k: cands[k]['nsubs'] for k in cands.keys()}
        return max(c, key=c.get)

    def calibrate_flat(self, sub):
        ''' Perform calibrations on flat which include subtracting 
        bias/flat-dark/constant if possible, then rescaling so the 
        mean intensity is .5 (because outlier rejection methods used 
        to combine flat subs work best with normalised 
        frames due to changing light levels; the value of .5 is so that we can 
        use B & W controls; then normalise by robust mean of central region so that
        when in use this region is unaffected.

        Called by Stacker when flats are added to the stack
        '''

        im = sub.get_image()
        sub.calibration_method = 'None'

        # calibrate using selected method
        if self.flat_calibration == 'flat-dark':
            # look for suitable masters within exposure tolerance
            # if none found, look for bias
            flatdark = self.get_flatdark(sub)
            if flatdark is not None:
                im = im - self.get_master(flatdark)
                sub.calibration_method = 'flat-dark'
            
        elif self.flat_calibration == 'bias':
            bias = self.get_bias(sub)
            if bias is not None:
                im = im - self.get_master(bias)
                sub.calibration_method = 'bias'

        elif self.flat_calibration == 'constant':
            # estimate background and subtract 5 sds to get potential lower bound
            bias = self.get_bias(sub)
            if bias is not None:
                mean_back, std_back = estimate_background(self.get_master(bias))
                im = im - (mean_back - 5 * std_back)
                sub.calibration_method = 'constant'

        # normalise by mean of image in central zone 
        w, h = im.shape
        w1, w2 = int(w / 3), int(2 * w / 3)
        h1, h2 = int(h / 3), int(2 * h / 3)
        imr = im[h1: h2, w1: w2]
        robust_mean = percentile_clip(imr.ravel(), perc=75)
        sub.image = .5 * im / robust_mean


    
    def build_calibrations(self):
        ''' Contruct table from library
        '''

        return Table(
            size=Window.size,
            data=self.library,
            name='Calibration masters',
            description='Calibration masters',
            cols={
                'Name': {'w': 120, 'align': 'left', 'field': 'name', 
                'action': self.show_calibration_frame},
                'Camera': {'w': 140, 'align': 'left', 'field': 'camera', 'type': str},
                'Type': {'w': 60, 'field': 'type', 'align': 'left'},
                'Exposure': {'w': 80, 'field': 'exposure'},
                'Temp. C': {'w': 80, 'field': 'temperature', 'type': str},
                'Gain': {'w': 50, 'field': 'gain', 'type': int},
                'Offset': {'w': 60, 'field': 'offset', 'type': int},
                #'ROI': {'w': 80, 'field': 'ROI', 'type': str},
                'Bin': {'w': 45, 'field': 'bin', 'type': int},
                'Calib': {'w': 120, 'field': 'calibration_method', 'type': str},
                'Filter': {'w': 80, 'field': 'filter'},
                'Created': {'w': 120, 'field': 'created', 'sort': {'DateFormat': date_time_format}},
                'Size': {'w': 110, 'field': 'shape_str'},
                'Age': {'w': 50, 'field': 'age', 'type': int},
                'Subs': {'w': 50, 'field': 'nsubs', 'type': int}
                },
            actions={'move to delete dir': self.move_to_delete_folder},
            on_hide_method=self.app.table_hiding
            )

    def show_calibration_table(self, *args):
        ''' Called when user clicks 'library' on GUI
        '''

        if not hasattr(self, 'calibration_table'):
            self.calibration_table = self.build_calibrations()
        self.app.showing = 'calibration'

        # check for redraw
        if self.calibration_table not in self.app.gui.children:
            self.app.gui.add_widget(self.calibration_table, index=0)

        self.calibration_table.show()    

    def show_calibration_frame(self, row):
        self.calibration_table.hide()
        # convert row.key to str (it is numpy.str by default)
        # get image from path
        try:
            path = os.path.join(self.calibration_dir, str(row.key))
            im = Image(path)
            if im.sub_type == 'flat':
                im.image /= 2
            Component.get('Monochrome').display_sub(im.image)
        except Exception as e:
            logger.error('{:}'.format(e))


    def move_to_delete_folder(self, *args):
        objio = Component.get('ObjectIO')
        for nm in self.calibration_table.selected:
            if nm in self.library:
                objio.delete_file(os.path.join(self.calibration_dir, nm))
                del self.library[nm]
                del self.masters[nm]
        logger.info('deleted {:} calibration masters'.format(len(self.calibration_table.selected)))
        self.calibration_table.update()
