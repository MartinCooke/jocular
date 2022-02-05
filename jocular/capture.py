''' Runs the capture scripts.
'''

import time
import numpy as np
from functools import partial
from scipy.interpolate import interp1d
from loguru import logger

from kivy.app import App
from kivy.properties import NumericProperty, BooleanProperty
from kivy.clock import Clock

from jocular.component import Component
# from jocular.gradient import image_stats
from jocular.utils import toast, percentile_clip

capture_controls = {'devices', 'script_button', 'capturing', 'exposure_button', 'filter_button'}


class Capture(Component):

    capturing = BooleanProperty(False)
    exposure = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.gui = self.app.gui

    def on_new_object(self):
        self.reset()
        self.info('inactive')
        self.gui.enable(['capturing'])

    def on_previous_object(self):
        self.info('inactive')
        self.gui.disable(['capturing'])

    def reset(self, stop_capturing=True):
        logger.debug('stop capturing? {:}'.format(stop_capturing))
        self.series_number = None
        self.fps = 0
        self.last_faf = None
        if stop_capturing:
            self.stop_capture()

    def on_capturing(self, *args):
        # user (pressing camera button) or system changes capture state

        logger.debug('capturing state changed')

        if not self.capturing:
            self.stop_capture()
            return

        if not Component.get('Camera').connected():
            self.stop_capture(message='cannot connect to camera')
            return
            
        if not Component.get('FilterWheel').connected():
            self.stop_capture(message='cannot connect to filterwheel')
            return
            
        self.gui.disable(capture_controls)
        self.gui.disable({'load_previous', 'new_DSO'})
        self.gui.disable({'apply_ROI'})
        self.gui.enable({'capturing'})
        logger.debug('camera connected, starting capture')

        try:
            self.capture()
        except Exception as e:
            self.stop_capture(message=e)

    def stop_capture(self, message=None):
        # stops capture normally or abnormally
        logger.debug('stopping capture')
        Component.get('Camera').stop_capture()
        self.gui.set('capturing', False, update_property=True)
        self.gui.enable(capture_controls)
        self.gui.enable({'new_DSO', 'apply_ROI'})
        if Component.get('Stacker').is_empty():
            self.gui.enable({'load_previous'})
        if message is not None:
            Component.get('CaptureScript').reset_generator()
            logger.error('problem capturing ({:})'.format(message))
            toast('Capture problem: {:}'.format(message))
        self.info('stopped')

    def capture(self, *args):
        # generator yields next command to execute

        # check if user has pressed pause/stop
        if not self.capturing:
            return 

        # get next command from generator
        op = next(Component.get('CaptureScript').generator)

        # logger.debug(op)

        if len(op) == 2:
            op, param = op

        # allow ROI selection during framing captures
        # not yet working on ASI
        # if op == 'expose short':
        #     self.gui.enable({'apply_ROI'})
        # else:
        #     self.gui.disable({'apply_ROI'})

        # change filter
        if op == 'set filter':
            Component.get('FilterWheel').select_filter(name=param, 
                changed_action=self.capture,
                not_changed_action=partial(self.stop_capture, message='FW problem'))

        elif op == 'set exposure':
            self.exposure = param
            self.capture()

        # carry out a normal exposure
        elif op == 'expose long':
            try:
                self.start_capture_time = time.time()
                Component.get('Camera').capture_sub(
                    exposure=self.exposure, 
                    on_capture=self.save_capture,
                    on_failure=self.stop_capture)
                if self.exposure > 2:
                    self.expo = self.exposure
                    self.exposure_start_time = time.time()
                    Clock.schedule_once(self.tick, 0)
                self.info('capturing [{:.1f} fps]'.format(self.fps))
            except Exception as e:
                logger.exception('problem in expose long {:}'.format(e))

        elif op == 'expose short':
            try:
                self.start_capture_time = time.time()
                Component.get('Camera').capture_sub(
                    exposure=self.exposure, 
                    on_capture=self.send_to_display,
                    on_failure=self.stop_capture,
                    is_faf=True)
                self.info('capturing [{:.1f} fps]'.format(self.fps))
            except Exception as e:
                logger.exception('problem in expose short {:}'.format(e))

        elif op == 'expose bias':
            self.start_capture_time = time.time()
            Component.get('Camera').capture_sub(
                on_capture=self.save_capture,
                on_failure=self.stop_capture,
                is_bias=True)
            self.info('capturing bias [{:.1f} fps]'.format(self.fps))

        elif op == 'autoflat':
            auto_expo = self.get_flat_exposure()
            if auto_expo is not None:
                self.exposure = auto_expo
                self.capture()
            else:
                self.stop_capture()
                Component.get('CaptureScript').reset_generator()

    def on_exposure(self, *args):
        Component.get('CaptureScript').exposure_changed(self.exposure)        

    def tick(self, *args):
        ''' count up to exposure time using status info line
        '''
        dur = time.time() - self.exposure_start_time
        if self.capturing:
            self.info('Exposing {:2.0f}s [{:.1f} fps]'.format(dur, self.fps))
            Clock.schedule_once(self.tick, 1)

    def send_to_display(self, *args):
        # send short subs directly to display
        self.fps = 1 / (time.time() - self.start_capture_time)
        try:
            im = Component.get('Camera').get_image()
            # new: store last short sub in case we want to platesolve
            self.last_faf = im
            Component.get('Monochrome').display_sub(im)
            self.capture()
        except Exception as e:
            logger.exception('problem send to display {:}'.format(e))

    def save_capture(self, *args):
        ''' Called via camera when image is ready.
        '''

        self.fps = 1 / (time.time() - self.start_capture_time)

        im = Component.get('Camera').get_image()
        capture_props = Component.get('Camera').get_capture_props()

        if im is None:
            toast('No image to save')
            return

        # image always comes across scaled 0-1 so rescale to 16-bits
        im *= (2**16 - 1)

        if not hasattr(self, 'series_number') or self.series_number is None:
            self.series_number = 1
        else: 
            self.series_number += 1

        capture_props['exposure'] = self.exposure
        capture_props['filter'] = Component.get('FilterWheel').current_filter
        if capture_props['temperature'] is None:
            capture_props['temperature'] = Component.get('Session').temperature
        sub_type = Component.get('CaptureScript').get_sub_type()
        capture_props['sub_type'] = sub_type

        # check why no bias in below (just a naming convention, but still...)
        prefix = sub_type if sub_type in {'flat', 'dark'} else capture_props['filter']
        name = '{:}_{:d}.fit'.format(prefix, self.series_number)
        
        Component.get('ObjectIO').new_sub(
            data=im.astype(np.uint16),
            name=name,
            capture_props=capture_props)

        # ask for next capture immediately
        self.capture()

    def compute_ADU(self, expo):
        ''' Estimate ADU in central part of image given exposure
        '''
        im = Component.get('Camera').capture_sub(exposure=expo, 
            return_image=True,
            on_failure=self.stop_capture)
        return percentile_clip(im.ravel(), perc=75)


    def get_flat_exposure(self):
        ''' make a series of test exposures to get ADU (actually
            normalised to range 0-1) in the middle of the range; note
            that we only test exposures in the range 0.5-2.5s and aim
            for ADU in the range 0.3-0.7
        '''

        logger.info('doing autoflat')

        min_exposure, max_exposure = .5, 2.5
        min_ADU, max_ADU = .3, .7

        expos = np.linspace(min_exposure, max_exposure, 5)
        adus = np.ones(len(expos)) 

        # do shortest first in case no point
        adus[0] = self.compute_ADU(expos[0])
        if adus[0] > max_ADU:
            toast('Too early to collect flats')
            return None

        # do longest in case too late
        adus[-1] = self.compute_ADU(expos[-1])
        if adus[-1] < min_ADU:
            toast('Too late to collect flats')
            return None

        # do remaining ADUs
        adus[1: -1] = [self.compute_ADU(e) for e in expos[1: -1]]

        # interpolate to get things purrrrfect
        f = interp1d(expos, adus)
        adu_target = .7
        xvals = np.linspace(min_exposure, max_exposure, 500)
        best = np.argmin(np.abs(adu_target - f(xvals)))
        best_exposure = xvals[best]
        mesg = 'best exposure for autoflat {:} with ADU {:}'.format(
            best_exposure, f(best_exposure))
        toast(mesg)
        logger.info(mesg)
        return float(best_exposure)
