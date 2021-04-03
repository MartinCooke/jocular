''' Manages calibration, alignment and stacking of incoming subs
'''

import os
import glob
import numpy as np
from datetime import datetime

from kivy.app import App
from kivy.logger import Logger
from kivy.properties import (BooleanProperty, NumericProperty, OptionProperty, 
    StringProperty, ListProperty, ConfigParserProperty)
from kivy.clock import Clock

from jocular.component import Component
from jocular.utils import percentile_clip, s_to_minsec, move_to_dir, purify_name
from jocular.widgets import JBubble
from jocular.image import Image, fits_in_dir

def combine_stack(stk, method='mean'):
    if len(stk) == 1:
        s = stk[0]
    elif len(stk) == 2:
        s = np.mean(stk, axis=0)
    elif method == 'mean':
        s = np.mean(stk, axis=0)
    elif method == 'median':
        s = np.median(stk, axis=0)
    else: 
        s = percentile_clip(stk, perc=int(method))
    return s

class Stacker(Component):

    selected_sub = NumericProperty(-1) # index of currently selected sub starts at 0
    sub_or_stack = StringProperty('sub')
    L_plus_other = StringProperty('Ha')
    subs = ListProperty([])
    animating = BooleanProperty(False)
    combine = OptionProperty('mean', options=['mean', 'median', '70', '80', '90'])
    speed = NumericProperty(2)
    spectral_mode = OptionProperty('mono', options=['mono', 'LRGB', 'L+'])
    confirm_on_clear_stack = ConfigParserProperty(0, 'Confirmations', 'confirm_on_clear_stack', 'app', val_type=int)
    reload_rejected = ConfigParserProperty(0, 'rejects', 'reload_rejected', 'app', val_type=int)
    use_TOA_for_exposure = ConfigParserProperty(1, 'Exposure', 'use_TOA_for_exposure', 'app', val_type=int)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.on_spectral_mode()

        self.sub_colors = {'select': (0, 1, 0, .6), 
            'reject': (.5, .5, .5, .6), 
            'nalign': (1, 0, 0, .6),
            'delete': (.1, .1, .1, .6)}

    def on_new_object(self):
        ''' Prepare for existing or new object. For existing object, loading takes
        place after all components' on_new_object methods have been called 
        '''

        self.reset()
        self.orig_rejects = set({})
        self.original_exposure = 0
        settings = Component.get('Metadata').get({'sub_type', 'rejected', 'exposure'})
        sub_type = settings.get('sub_type', 'light')
        cod = Component.get('ObjectIO').current_object_dir

        # in pre v3 we used a 'rejected' list to store names of rejects; now we don't
        rejected = set(settings.get('rejected', []))
        exposure = settings.get('exposure', None)
        if cod is not None:
            # move any in rejects if user has requested this
            if self.reload_rejected:
                for f in fits_in_dir(os.path.join(cod, 'rejects')):
                    try:
                        bn = os.path.basename(f)
                        os.rename(f, os.path.join(cod, bn))
                        rejected.add(bn)
                    except Exception as e:
                        Logger.warn('Stacker: problem moving rejected on load {:} ({:})'.format(f, e)) 
            # now load all (which now will include prev rejects)
            for f in fits_in_dir(cod):
                try:
                    im = Image(f)
                    im.status = 'reject' if os.path.basename(f) in rejected else 'select'
                    if im.exposure is None:
                        im.exposure = exposure
                    if im.sub_type is None:
                        im.sub_type=sub_type
                    self.subs.append(im)
                except Exception as e:
                    Logger.warn('Stacker: problem reading image {:} ({:})'.format(f, e))
            # if we have loaded up some calibration subs, ensure that we mark things as changed
            if not self.is_empty():
                self.changed = self.subs[0].sub_type in {'dark', 'bias', 'flat'}
                self.original_exposure = self.subs[0].exposure
            # store rejected to see if anything has changed and needs saving
            self.orig_rejects = rejected
 
    def reset(self):
        # Called when we have a new object and when user clears stack
        self.stack_cache = {}
        self.subs.clear()
        self.selected_sub = -1
        self.update_stack_scroller()
        self.set_to_subs()
        Component.get('View').reset()  # might not be needed as View also does a reset!
        self.info('reset stack')

    def on_save_object(self):
        # move rejected subs to 'rejected'; we won't touch non-aligned as they are salvageable often
        cod = Component.get('ObjectIO').current_object_dir
        for s in self.subs:
            if s.status == 'reject':
                move_to_dir(os.path.join(cod, s.name), 'rejects')

    def is_empty(self):
        return len(self.subs) == 0

    def update_status(self):
        d = self.describe()
        if d:
            self.info('{:} | {:}x{:.0f}s | {:}'.format(
                s_to_minsec(d['total_exposure']), 
                d['nsubs'], 
                d['sub_exposure'], 
                d['filters']))

    def describe(self):
        # return info useful to snapshotter (for the moment)

        if len(self.subs) > 0 and self.sub_or_stack == 'sub':
            s = self.subs[self.selected_sub]
            return {
                'nsubs': 1,
                'total_exposure': s.exposure if s.exposure else 0,
                'sub_exposure': s.exposure if s.exposure else 0,
                'multiple_exposures': False,
                'dark': 'dark' in s.calibrations,
                'flat': 'flat' in s.calibrations,
                'bias': 'bias' in s.calibrations,
                'filters': 'filter: {:}'.format(s.filter)}

        subs = [s for s in self.subs[:self.selected_sub+1] if s.status == 'select']
        if len(subs) == 0:
            return None

        expos = [s.exposure if s.exposure else 0 for s in subs]
        filts = [s.filter for s in subs]
        fstr = ''
        for f in ['L', 'R', 'G',  'B', 'Ha', 'OIII', 'SII']:
            if filts.count(f) > 0:
                fstr += '{:}{:} '.format(filts.count(f), f)

        return {
            'nsubs': len(subs),
            'total_exposure': sum(expos),
            'sub_exposure': max(set(expos), key=expos.count),
            'multiple_exposures': len(set(expos)) > 1,
            'dark': 'dark' in subs[0].calibrations,
            'flat': 'flat' in subs[0].calibrations,
            'bias': 'bias' in subs[0].calibrations,
            'filters': fstr.strip()}

    def get_filters(self):
        if self.is_empty():
            return None
        return {s.filter for s in self.subs[:self.selected_sub+1] if s.status == 'select'}

    def clear(self, *args):
        ''' Clear existing stack by moving/deleting FITs and resetting
        '''

        if len(self.subs) == 0:
            return

        if self.confirm_on_clear_stack:
            JBubble(actions={'Really clear?': self._clear}, loc='mouse').open()
        else:
            self._clear()

    def _clear(self, *args):
        # clear stack auxilliary method since might come after confirmation

        cod = Component.get('ObjectIO').current_object_dir
        for nm in glob.glob(os.path.join(cod, '*.fit*')):
            move_to_dir(os.path.join(cod, nm), 'deleted')

        # perform necessary resets
        Component.get('Aligner').reset()
        self.reset()
        Component.get('Capture').soft_reset()
        self.changed = False # indicate nothing has changed

    def delete_sub(self, *args):
        if self.is_empty():
            return
        sub_num = self.selected_sub
        if sub_num == 0:
            return
        cod = Component.get('ObjectIO').current_object_dir
        move_to_dir(os.path.join(cod, self.subs[sub_num].name), 'deleted')
        del self.subs[sub_num]
        self.selected_sub -= 1

    def on_animating(self, *args):
        if self.is_empty():
             return
        if self.animating:
            self.play_event = Clock.schedule_interval(self.increment_sub, 1/self.speed)
        else:
            if hasattr(self, 'play_event'):
                Clock.unschedule(self.play_event)

    def on_sub_or_stack(self, *args):
        self.on_selected_sub()

    def on_L_plus_other(self, *args):
        self.stack_changed()

    def on_speed(self, *args):
        if self.animating:
            Clock.unschedule(self.play_event)
            self.play_event = Clock.schedule_interval(self.increment_sub, 1/self.speed)

    def first_sub(self, *args):
        self.selected_sub = 0

    def last_sub(self, *args):
        self.selected_sub = len(self.subs) - 1

    def previous_sub(self, *args):
        if self.selected_sub > 0:
            self.selected_sub -= 1

    def next_sub(self, *args):
        if self.selected_sub < len(self.subs) - 1:
            self.selected_sub += 1

    def on_combine(self, *args):
        self.stack_changed()

    def set_to_subs(self):
        self.app.gui.set('sub_or_stack', 'sub', update_property=True)

    def toggle_selected_sub(self, *args):
        # user selects displayed sub icon to toggle its selected status

        if self.is_empty():
            return

        current_sub = self.selected_sub
        sub = self.subs[current_sub]
        if sub.status == 'select':
            sub.status = 'reject'
        elif sub.status == 'reject':
            sub.status = 'select'

        self.update_stack_scroller()    # updates colours
        self.stack_changed()            # will check if sub or stack

        # check if anything has changed
        self.check_for_changes()

    def on_spectral_mode(self, *args):
        self.stack_changed()
 
    def stack_changed(self):
        ''' Called whenever we might need to update the stack e.g. sub added/selected
        deselected/change in stack view/change in mode
        '''

        if self.is_empty():
            return
        if self.sub_or_stack == 'sub':
            return

        # see if we can satisfy user's non-mono preferences and if not, drop thru to mono
        filters = self.get_filters()

        if self.spectral_mode == 'LRGB':
            Component.get('MultiSpectral').LRGB_changed(
                L=self.get_stack('L'), 
                R=self.get_stack('R'), 
                G=self.get_stack('G'), 
                B=self.get_stack('B'))

        elif self.spectral_mode == 'L+':
            Component.get('MultiSpectral').L_plus_changed(
                L=self.get_stack('L'), 
                layer=self.get_stack(self.L_plus_other)) 

        else:
            Component.get('Monochrome').L_changed(self.get_stack(filt='all'))
            Component.get('MultiSpectral').reset()            

        self.update_status()

 
    def update_stack_scroller(self, *args):
        # sub_labels is array representing the stack
        # these are sub positions on the screen

        self.update_status()
        gui = self.app.gui.gui
        labs = [gui[n]['widget'] for n in ['sub_m2', 'sub_m1', 'sub_0', 'sub_p1', 'sub_p2']]

        # set background to transparent and text to blank to start with
        for l in labs:
            l.text = ''
            l.background_color[-1] = 0

        # we have some subs
        fw = Component.get('FilterWheel')
        for i, l in enumerate(labs, start=self.selected_sub - 2):
            # if position is occupied by a sub
            if (i >= 0) and (i < len(self.subs)):
                l.text = str(i + 1)
                l.color = self.sub_colors[self.subs[i].status]
                l.background_color = fw.filter_properties[self.subs[i].filter]['bg_color']

    def increment_sub(self, dt):
        if self.selected_sub == len(self.subs) - 1:
            self.selected_sub = 0
        else:
            self.selected_sub += 1


    def get_screen(self, dt=None):
        im = Component.get('Snapshotter').snap(return_image=True).copy()
        self.ims.append(im.convert('L'))
        if len(self.ims) < len(self.subs):
            self.selected_sub += 1
            Clock.schedule_once(self.get_screen, 0)
        else:
            save_path = '{:} {:}.gif'.format(
                    os.path.join(self.app.get_path('snapshots'), 
                        purify_name(Component.get('DSO').Name)), 
                    datetime.now().strftime('%d%b%y_%H_%M_%S'))
            self.ims[0].save(save_path, 
                save_all=True, 
                append_images=self.ims[1:], 
                optimize=True, 
                # include_color_table=False,
                duration=1000 / self.speed, 
                loop=0)
            Component.get('Snapshotter').info('saved animation')

    def make_animated_gif(self):
        self.ims = []
        self.selected_sub = 0
        Clock.schedule_once(self.get_screen, 0)

    def sub_added(self):
        # called when new sub added to the stack by Watcher
        if self.selected_sub == len(self.subs) - 2:  # was on last sub before new one came in
            self.selected_sub = len(self.subs) - 1
        else:
            self.update_stack_scroller()

    def on_selected_sub(self, *args):
        # This is the key method that dictates whether the display has changed
        # on new sub, change of sub selection etc and hence stack updates

        s = self.selected_sub
        if (s < 0) or (s >= len(self.subs)):
            return

        if self.sub_or_stack == 'sub':
            ss = self.subs[s]
            Component.get('Monochrome').display_sub(ss.get_image(), 
                do_gradient=ss.sub_type=='light')
        else:
            self.stack_changed()

        self.update_stack_scroller()


    def get_image_for_platesolving(self):
        ''' Currently gets displayed image on stack, but what if we 
            are framing etc?
        '''
        try:
            if self.sub_or_stack == 'sub':
                im = self.subs[self.selected_sub].get_image()
            else:
                im = self.get_stack()
            return Component.get('View').do_flips(im)
        except Exception as e:
            Logger.warning('Stacker: no image for platesolving')
            return None

    def get_selected_sub_count(self):
        # used by calibrator
        return len([1 for s in self.subs if s.status == 'select'])

    def get_stack(self, filt='all', calibration=False):
        ''' Return stack of selected subs of the given filter if provided. Normally uses 
        those subs up to the currently selected sub on the display. Responsible for 
        caching results to prevent expensive recomputes. For calibration, uses all subs.
        '''

        # we have no subs
        if not self.subs:
            return None

        # subs up to current selected sub, except in case of calibration
        if calibration:
            subs = self.subs
        else:
            subs = self.subs[:self.selected_sub+1]

        # if no filter, choose all subs, otherwise restrict
        if filt == 'all':
            stk = [s for s in subs if (s.status=='select')]
        else:
            stk = [s for s in subs if (s.status=='select') & (s.filter==filt)]

        # none remain
        if not stk:
            return None

        # if calibrating, use user-selected method, otherwise use mean for non-L channels
        if calibration or filt in ['L', 'all']:
            method = self.combine
        else:
            method = 'mean'

        sub_names = set([s.name for s in stk])

        # check if we already have this in the cache
        if filt in self.stack_cache:
            cached = self.stack_cache[filt]
            if (cached['method'] == method) and (cached['sub_names'] == sub_names):
                return cached['stack']

        # if not, we need to update
        stacked = combine_stack(np.stack([s.get_image() for s in stk], axis=0), method=method)

        # cache results
        self.stack_cache[filt] = {
            'stack': stacked, 
            'method': method,
            'sub_names': sub_names
            }

        return stacked

    def add_sub(self, sub):
        # for sub coming from Watcher

        ''' if exposure is estimated, then find estimate. Rules, in priority order:
            (1) if the user has provided a manual estimate via GUI, then always use that.
            (2) if the user allows TOA differences and there are enough subs, use that.
                and propogate estimate to rest of stack so it is continually updated
            (3) otherwise for now use value for this sub type from GUI, even if user
                hasn't altered it; note that it is still not a manual estimate to
                give a chance for re-estimation using TOA later
        '''

        if sub.exposure_is_an_estimate:
            # if first sub used manual estimate, use that estimate
            if len(self.subs) > 0 and self.subs[0].exposure_is_manual_estimate:
                sub.exposure = self.subs[0].exposure
                sub.exposure_is_manual_estimate = True
            # if user wishes to to TOA for exposure, try to use that
            elif self.use_TOA_for_exposure and len(self.subs) > 3:
                dTOA = int(np.mean(np.diff([s.arrival_time for s in self.subs])))
                sub.exposure = dTOA
                # propagate it to all subs
                for s in self.subs:
                    s.exposure = dTOA
                    s.exposure_is_manual_estimate = False
            # otherwise use current exposure indicated for this sub type
            else:
                sub.exposure = Component.get('CaptureScript').get_current_exposure(sub.sub_type)
                sub.exposure_is_manual_estimate = False

            # tell interface
            Component.get('CaptureScript').set_external_details(sub_type=sub.sub_type, exposure=sub.exposure)


        self.process(sub)
        self.subs.append(sub)
        self.sub_added()

        self.changed = not self.is_empty()

    def exposure_provided_manually(self, exposure_estimate):
        # called by CaptureScript when user changes exposure using GUI
        # natively captured subs won't be estimated, so won't get updated
        for s in self.subs:
            if s.exposure_is_an_estimate:
                s.exposure = exposure_estimate
                s.exposure_is_manual_estimate = True
        # check if exposure has changed but only when we are not capturing natively
        if not self.is_empty() and self.subs[0].exposure_is_an_estimate:
            self.check_for_changes()

    def check_for_changes(self):
        # for light subs only, denote a change if any change in select/reject
        # for calibration frames self.changed is always True (so we can save master)
        if self.subs[0].sub_type == 'light':
            self.changed = {s.name for s in self.subs if s.status == 'reject'} != self.orig_rejects or \
                self.subs[0].exposure != self.original_exposure

    def realign(self, *args):
        self.recompute(realign=True)

    def recompute(self, widgy=None, realign=False):
        # initial load, recompute or realign
        Component.get('Aligner').reset()
        self.stack_cache = {}
        # shuffle-baased realign
        if realign:
            np.random.shuffle(self.subs)
            # if we have a B or Ha, keep shuffling until we start with that
            if len([s for s in self.subs if s.filter in {'B', 'Ha'}]) > 0:
                while self.subs[0].filter not in {'B', 'Ha'}:
                    np.random.shuffle(self.subs)
        self.selected_sub = -1
        Clock.schedule_once(self._reprocess_sub, 0)

    def _reprocess_sub(self, dt):
        if self.selected_sub + 1 < len(self.subs):
            self.process(self.subs[self.selected_sub + 1])
            self.selected_sub += 1
            Clock.schedule_once(self._reprocess_sub, 0)
        else:
            self.stack_changed()

    def process(self, sub):
        # Process sub on recompute/realign

        sub.image = None  # force reload
        Component.get('BadPixelMap').process_bpm(sub)
        if sub.sub_type == 'light':
            Component.get('Calibrator').calibrate(sub)
            Component.get('Aligner').process(sub)
        elif sub.sub_type == 'flat':
            Component.get('Calibrator').calibrate_flat(sub)

