''' Runs the capture scripts using generators.
'''

import os
import time
import numpy as np
from scipy.interpolate import interp1d

from kivy.app import App
from kivy.properties import NumericProperty, BooleanProperty
from kivy.clock import Clock
from kivy.logger import Logger

from jocular.component import Component
from jocular.widgets import JPopup
from jocular.image import save_image
from jocular.gradient import image_stats


class Capture(Component):

    capturing = BooleanProperty(False)
    exposure = NumericProperty(0)
    scripts = [s + '_script' for s in {'seq', 'light', 'frame', 'dark', 'flat', 'bias'}]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.gui = self.app.gui

    def on_new_object(self):
        self.reset()

    def reset(self):
        self.series_number = None
        self.stop_capture()
        Component.get('Camera').reset()  # may not be needed as reset is called in Camera.on_new_object
        self.gui.set('capturing', False)
        self.gui.enable(self.scripts + ['exposure_button', 'filter_button'])

    def soft_reset(self):
        # when stack is cleared we dont want full reset
        self.series_number = None

    def on_capturing(self, *args):
        # user (pressing camera button) or system changes capture state

        self.info('capturing' if self.capturing else 'paused')
        current_script = Component.get('CaptureScript').current_script

        if self.capturing:
            # user wants to capture, so check that camera is connected
            if not Component.get('Camera').is_connected():
                Component.get('Camera').connect()
            if not Component.get('Camera').is_connected():
                self.gui.set('capturing', False, update_property=True)
                # JBubble(message='No camera connected').open()
                return

            # force user to pause/stop before changing any capture parameters
            self.gui.disable(self.scripts + ['exposure_button', 'filter_button', 'load_previous', 'new_DSO'])
            # enable current script so user can see what is being captures
            self.gui.enable(['{:}_script'.format(current_script)])
            self.capture()

        else:
            Component.get('Camera').pause()

            # we can always do framing
            self.gui.enable(['frame_script', 'exposure_button', 'filter_button', 'new_DSO'])
            # find out what stack contains
            subs = Component.get('Stacker').subs
            if len(subs) > 0:
                current = subs[0].sub_type
                if current == 'light':
                    self.gui.enable(['light_script', 'seq_script'])
                else:
                    self.gui.enable(['{:}_script'.format(current)])
            else:
                self.gui.enable(self.scripts)                   

    def stop_capture(self, *args):
        # called when problem capturing
        self.gui.set('capturing', False, update_property=True)
        self.gui.enable(self.scripts + ['exposure_button', 'filter_button'])

    def slew(self, *args):
        Logger.info('Capture: slew not implemented yet (but coming soon!)')

    def camera_disconnected(self):
        self.stop_capture()
        self.gui.disable(['capturing'])

    def camera_reconnected(self):
        self.gui.enable(['capturing'])

    def capture(self, *args):
        # generator yields next command to execute

        # check if user has pressed pause/stop
        if not self.capturing:
            return 

        # get next command from generator
        op = next(Component.get('CaptureScript').generator)

        if len(op) == 2:
            op, param = op

        # automatically change filter wheel, or request user to do so
        if op == 'set filter':
            Component.get('FilterWheel').select_filter(name=param, 
                changed_action=self.capture,
                not_changed_action=self.stop_capture)

        elif op == 'set exposure':
            self.exposure = param
            self.capture()

        # carry out a normal exposure
        elif op == 'expose long':
            try:
                self.info('capturing ...')
                Component.get('Camera').capture_sub(
                    exposure=self.exposure, 
                    on_capture=self.save_capture,
                    on_failure=self.stop_capture)
                if self.exposure > 2:
                    self.expo = self.exposure
                    self.exposure_start_time = time.time()
                    Clock.schedule_once(self.tick, 0)
                self.info('capturing')
            except Exception as e:
                Logger.error('Capture: problem in expose long {:}'.format(e))

        elif op == 'expose short':
            # we update info twice to ensure display updates...
            try:
                self.info('shorts ...')
                Component.get('Camera').capture_sub(
                    exposure=self.exposure, 
                    on_capture=self.send_to_display,
                    on_failure=self.stop_capture,
                    internal_timing=self.exposure < 1)
                self.info('shorts')
            except Exception as e:
                Logger.error('Capture: problem in expose short {:}'.format(e))

        elif op == 'expose bias':
            Component.get('Camera').capture_bias(
                on_capture=self.save_capture,
                on_failure=self.stop_capture)
            self.info('capturing bias')

        elif op == 'autoflat':
            auto_expo = self.get_flat_exposure()
            if auto_expo is not None:
                self.exposure = auto_expo
                self.capture()
            else:
                self.stop_capture()
                # self.capturing = False

    def on_exposure(self, *args):
        Component.get('CaptureScript').set_exposure_button(self.exposure)        

    def tick(self, *args):
        remaining = self.expo - (time.time() - self.exposure_start_time)
        if self.capturing and (remaining > -.1):
            self.info('Exposing {:2.0f}s'.format(remaining))
            Clock.schedule_once(self.tick, 1)

    def send_to_display(self, *args):
        # send short subs directly to display
        try:
            Component.get('Monochrome').display_sub(Component.get('Camera').last_capture)
            self.capture()
        except Exception as e:
            Logger.error('Capture: problem send to display {:}'.format(e))

    def save_capture(self, *args):
        ''' Called via camera when image is ready. Image is in camera.last_capture
        '''

        im = Component.get('Camera').last_capture * (2**16 - 1)

        if im is None:
            self.warn('No image')
            return

        sub_type = Component.get('CaptureScript').current_script
        if sub_type == 'seq':
            sub_type = 'light'

        if not hasattr(self, 'series_number') or self.series_number is None:
            self.series_number = 1
        else: 
            self.series_number += 1

        filt = Component.get('FilterWheel').current_filter
        pref = sub_type if sub_type in {'flat', 'dark'} else filt
        name = '{:}_{:d}.fit'.format(pref, self.series_number)

        save_image(data=im.astype(np.uint16),
            path=os.path.join(self.app.get_path('watched'), name),
            exposure=self.exposure,
            filt=filt,
            temperature=Component.get('Session').temperature,
            sub_type=sub_type)

        # ask for next capture immediately
        self.capture()

    def get_flat_exposure(self):
        # make a series of test exposures to get ADU just over half-way (0.5)

        min_exposure, max_exposure = 1, 2.5
        min_ADU, max_ADU = .3, .8

        expos = np.linspace(min_exposure, max_exposure, 5)
        adus = np.ones(len(expos))      # normalised ADUs actually
        for i, expo in enumerate(expos):
            im = Component.get('Camera').capture_sub(exposure=expo, 
                return_image=True,
                internal_timing=True,
                on_failure=self.stop_capture)

            # analyse image
            stats = image_stats(im)
            adus[i] = stats['central 75%']
            Logger.debug('Capture: autoflat exposure {:.1f}s has ADU of {:.2f}'.format(expo, adus[i]))

        # are any within ADU tolerance?
        if np.min(adus) > max_ADU:
            JPopup(title='Too early to collect flats', cancel_label='close').open()
            return None

        if np.max(adus) < min_ADU:
            JPopup(title='Too late to collect flats', cancel_label='close').open()
            return None

        # we are OK, so interpolate to get things purrrrfect
        f = interp1d(expos, adus)
        adu_target = .7
        xvals = np.linspace(min_exposure, max_exposure, 500)
        best = np.argmin(np.abs(adu_target - f(xvals)))
        best_exposure = xvals[best]
        Logger.debug('Capture: best exposure for autoflat {:} with ADU {:}'.format(best_exposure, f(best_exposure)))
        return float(best_exposure)
