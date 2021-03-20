''' Handles calibration library and actual calibration of subs.
'''

import os.path
import shutil
import numpy as np
from datetime import datetime
from scipy.stats import trimboth

from kivy.app import App
from kivy.logger import Logger
from kivy.properties import BooleanProperty, DictProperty, ConfigParserProperty
from kivy.core.window import Window

from jocular.table import Table
from jocular.utils import add_if_not_exists, make_unique_filename
from jocular.component import Component
from jocular.image import Image, save_image, fits_in_dir

date_time_format = '%d %b %y %H:%M'

class Calibrator(Component):

    masters = DictProperty({})
    apply_flat = BooleanProperty(False)
    apply_dark = BooleanProperty(False)
    apply_bias = BooleanProperty(False)
    use_l_filter = ConfigParserProperty(1, 'Flats', 'use_l_filter', 'app', val_type=int)
    temperature_tol = ConfigParserProperty(5, 'Darks', 'temperature_tol', 'app', val_type=float)
    exposure_tol = ConfigParserProperty(5, 'Darks', 'exposure_tol', 'app', val_type=float)
    dark_days_tol = ConfigParserProperty(1, 'Darks', 'dark_days_tol', 'app', val_type=float)
    flat_days_tol = ConfigParserProperty(30, 'Flats', 'flat_days_tol', 'app', val_type=float)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.calibration_dir = self.app.get_path('calibration')
        self.load_masters()

    def new_master_from_watcher(self, m):
        # construct unique/sensible name
        dest = make_unique_filename(os.path.join(self.calibration_dir, m.name))
        try:
            os.rename(m.path, dest)
            m.path = dest
            m.name = os.path.basename(dest)
            self.add_to_library(m)
        except Exception as e:
            Logger.error('Calibrator: cannot move {:} ({:})'.format(m.path, e))

    def load_masters(self):
        # construct metadata by reading and validating FITs in calibration dir
        self.masters = {}
        self.library = {}
        for f in fits_in_dir(self.calibration_dir):
            path = os.path.join(self.calibration_dir, f)
            try:
                s = Image(path)
                if s.is_master:
                    self.add_to_library(s)
            except Exception as e:
                Logger.warn('Calibrator: unable to parse calibration {:} ({:})'.format(f, e))

    def add_to_library(self, m):
        # m is a validated masters, so just pick off required fields
        name = m.name
        self.masters[name] = m
        self.library[name] = {
            'name': name,
            'type': m.sub_type,
            'exposure': str(m.exposure) if m.exposure is not None else '???',
            'temperature': str(m.temperature) if m.temperature is not None else '???',
            'filter': m.filter,
            'created': m.create_time.strftime(date_time_format),
            'shape_str': m.shape_str,
            'age': m.age,
            'nsubs': m.nsubs if m.nsubs is not None else 0
        }


    def save_master(self, sub_type=None, exposure=None, temperature=None, filt=None):
        # Save master from existing stack, applying any required post-processing
        # masters are saved to watched directory so that processing is uniform re external captures

        # generate master from stack
        stacker = Component.get('Stacker')

        # force the use of method that the user has chosen or set up by default for this type of calib
        master = stacker.get_stack(filt, calibration=True)

        # apply bad pixel mapping to calibration frames
        # if dark, find hot pixels in master and remove, otherwise use existing BPM
        # not yet tested
        bpm = Component.get('BadPixelMap')
        if sub_type == 'dark':
            master = bpm.do_bpm(master, bpm.find_hot_pixels(master))
        else:
            master = bpm.do_bpm(master)

        # flats were divided thru by their robust mean to account for level differences 
        # but then scaled to 50% to enable B/W controls; so multiply by 2
        if sub_type == 'flat':
            master = 2 * master

        # save calibration master to Watched so that it is processed in the same way as when user drops master)
        save_image(data=master,
            path=os.path.join(self.app.get_path('watched'), 'master{:}.fit'.format(sub_type)),
            exposure=exposure,
            filt=filt,
            temperature=temperature,
            sub_type='master ' + sub_type,
            nsubs=stacker.get_selected_sub_count())

        # add to notes field of current DSO
        Component.get('Notes').notes = 'exposure {:} filter {:} temperature {:}'.format(exposure, filt, temperature)

    def calibrate(self, sub):
        # Given a light sub, apply calibration. Fails silently if no suitable calibration masters. 

        sub.calibrations = set({})

        if not self.library: 
            return

        # get all masters (check speed, but should be quick)
        dark = self.get_dark(sub)
        flat = self.get_flat(sub)
        bias = self.get_bias(sub)

        # Logger.debug('Calibrator: D {:} F {:} B {:}'.format(dark, flat, bias))

        D = self.get_master(dark)
        # if D is not None:
        #     print('{:} min {:} max {:} median {:} mean {:}'.format(dark, np.min(D), np.max(D), np.median(D), np.mean(D)))
        F = self.get_master(flat)
        # if F is not None:
        #     print('{:} min {:} max {:} median {:} mean {:}'.format(flat, np.min(F), np.max(F), np.median(F), np.mean(F)))
        B = self.get_master(bias)
        # if B is not None:
        #     print('{:} min {:} max {:} median {:} mean {:}'.format(bias, np.min(B), np.max(B), np.median(B), np.mean(B)))

        im = sub.get_image()
        if self.apply_dark and self.apply_flat:
            if dark is not None and flat is not None:
                im = (im - D) / F
                sub.calibrations = {'dark', 'flat'}
            elif dark is not None:
                im = im - D
                sub.calibrations = {'dark'}
            elif flat is not None:
                if bias is not None:
                    sub.calibrations = {'flat', 'bias'}
                    im = (im - B) / F
                else:
                    sub.calibrations = {'flat'}
                    im = im / F # inadvisable, but we allow it

        elif self.apply_dark:
            if dark is not None:
                im = im - D
                sub.calibrations = {'dark'}

        elif self.apply_flat:
            if flat is not None:
                if bias is not None:
                    sub.calibrations = {'flat', 'bias'}
                    im = (im - B) / F
                else:
                    sub.calibrations = {'flat'}
                    im = im / F

        elif self.apply_bias:
            if bias is not None:
                sub.calibrations = {'bias'}
                im = im - B

        # limit
        im[im < 0] = 0
        im[im > 1] = 1

        sub.image = im
        applied = ' '.join(list(sub.calibrations))
        if applied:
            self.info('applied ' + applied)
        else:
            self.info('none')

    def get_dark(self, sub):
        # Find suitable dark for this sub given its parameters

        if sub.exposure is None:
            return None

        # choose darks that are the right shape with exposure within tolerance
        darks = {k: v for k, v in self.masters.items()
                    if  v.shape == sub.shape and 
                        v.sub_type == 'dark' and 
                        v.exposure is not None and 
                        abs(v.exposure - sub.exposure) < self.exposure_tol}

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


    def get_bias(self, sub):
        # get the most recent bias

        bias = {k: v.age for k, v in self.masters.items() 
                if v.shape == sub.shape and v.sub_type == 'bias' }

        return min(bias, key=bias.get) if len(bias) > 0 else None
 
    def get_flat(self, sub):

        # flats of right shape
        flats = {k:v for k, v in self.masters.items() 
            if  v.shape == sub.shape and v.sub_type == 'flat'}

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

        # find any within day tolerance, noting that this compares the date of the flat with
        # the date of the sub (i.e. not necessarily the current date)
        flats = {k: abs(v.create_time - sub.create_time).days for k,v in flats_in_filt.items()}
        flats = {k: v for k, v in flats.items() if v <= self.flat_days_tol}

        # find most recent if there is a choice
        for k in sorted(flats, key=flats.get):
            return k
        return None

    def get_master(self, name):
        if name is None:
            return None
        # Retrieve image (NB loaded on demand, so effectively a cache)
        return self.masters[name].get_master_data()

    def _most_subs(self, cands):
        c = {k: cands[k]['nsubs'] for k in cands.keys()}
        return max(c, key=c.get)

    def calibrate_flat(self, sub):
        ''' Perform calibrations on flat which include subtracting bias if
        available , and rescaling so the mean intensity is .5 (because outlier rejection 
        methods used to combine flat subs work best with normalised frames due to changing 
        light levels; the value of .5 is so that we can use B & W controls; we rescale to 
        a mean of 1 when saving since this is what a good flat needs for dividing)
        '''

        im = sub.get_image()
        #print('before calibration min {:} max {:} median {:}'.format(
        #    np.min(im), np.max(im), np.median(im)))

        # subtract bias if available
        bias = self.get_bias(sub)
        if bias is not None:
            #print('subtracting bias')
            im = im - self.get_master(bias)

        #print('after bias min {:} max {:} median {:}'.format(
        #    np.min(im), np.max(im), np.median(im)))

        # normalise by mean of image in central 3rd zone 
        perc = 75  # retain central 75% of points when computing mean 
        w, h = im.shape
        w1, w2 = int(w / 3), int(2 * w / 3)
        h1, h2 = int(h / 3), int(2 * h / 3)
        imr = im[h1: h2, w1: w2]
        # imr = im[(h // 2 - r):(h // 2 + r), (w // 2 - r):(w // 2 + r)]
        robust_mean = np.mean(trimboth(np.sort(imr.ravel(), axis=0), 
            (100 - perc)/100, axis=0), axis=0)
        #print('robust mean in w {:}-{:}, h {:}-{:} is {:}'.format(
        #    w1, w2, h1, h2, robust_mean))

        sub.image = .5 * im / robust_mean
        #print('after bias min {:} max {:} median {:}'.format(
        #    np.min(sub.image), np.max(sub.image), np.median(sub.image)))


    # calibration table handling ---------------------------------------------------------------------

    def build_calibrations(self):

        return Table(
            size=Window.size,
            data=self.library,
            name='Calibration masters',
            description='Calibration masters',
            cols={
                'Name': {'w': 300, 'align': 'left', 'field': 'name'},
                'Type': {'w': 60, 'field': 'type', 'align': 'left'},
                'Exposure': {'w': 80, 'field': 'exposure'},
                'Temp. C': {'w': 80, 'field': 'temperature', 'type': str},
                'Filter': {'w': 80, 'field': 'filter'},
                'Created': {'w': 180, 'field': 'created', 'sort': {'DateFormat': date_time_format}},
                'Size': {'w': 70, 'field': 'shape_str'},
                'Age': {'w': 50, 'field': 'age', 'type': int},
                'Subs': {'w': 50, 'field': 'nsubs', 'type': int}
                },
            actions={'move to delete dir': self.move_to_delete_folder},
            on_hide_method=self.app.table_hiding
            )

    def show_calibration_table(self, *args):
        '''Called from menu'''

        if not hasattr(self, 'calibration_table'):
            self.calibration_table = self.build_calibrations()
        self.app.showing = 'calibration'

        # check for redraw
        if self.calibration_table not in self.app.gui.children:
            self.app.gui.add_widget(self.calibration_table, index=0)

        self.calibration_table.show()    

    def move_to_delete_folder(self, *args):
        add_if_not_exists('deleted')
        for nm in self.calibration_table.selected:
            if nm in self.library:
                to_path = os.path.join('deleted', nm + datetime.now().strftime('%d_%b_%y_%H_%M_%S'))
                from_path = os.path.join(self.calibration_dir, nm)
                try:
                    shutil.move(from_path, to_path)
                    del self.library[nm]
                    del self.masters[nm]
                except Exception as e:
                    self.error('problem moving master')
                    Logger.error('Calibrator: problem moving master to {:} ({:})'.format(to_path, e))
        self.calibration_table.update()

