''' Manages calibration, alignment and stacking of incoming subs
'''

import os
import glob
import numpy as np
from datetime import datetime
from loguru import logger

from kivy.app import App
from kivy.properties import (BooleanProperty, NumericProperty, OptionProperty, 
    StringProperty, ListProperty)
from kivy.clock import Clock
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog

from jocular.component import Component
from jocular.settingsmanager import Settings
from jocular.utils import percentile_clip, s_to_minsec, move_to_dir, purify_name, toast
from jocular.image import Image, fits_in_dir
#from jocular.exposurechooser import exp_to_str

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

class Stacker(Component, Settings):

    save_settings = ['spectral_mode', 'speed']

    selected_sub = NumericProperty(-1) # index of currently selected sub starts at 0
    sub_or_stack = StringProperty('sub')
    L_plus_other = StringProperty('Ha')
    subs = ListProperty([])
    animating = BooleanProperty(False)
    combine = OptionProperty('mean', options=['mean', 'median', '70', '80', '90'])
    speed = NumericProperty(2)
    spectral_mode = OptionProperty('mono', options=['mono', 'LRGB', 'L+'])
    confirm_on_clear_stack = BooleanProperty(False)
    reload_rejected = BooleanProperty(False)

    configurables = [
        ('confirm_on_clear_stack', {
            'name': 'confirm before clearing stack?', 
            'switch': '',
            'help': 'Clearing deletes all the current subs in the stack'}),
        ('reload_rejected', {'name': 'reload rejected subs?', 
            'switch': '',
            'help': 'include subs that were previously marked as rejected'})
        ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.on_spectral_mode()

        self.sub_colors = {'select': (0, 1, 0, .6), 
            'reject': (.5, .5, .5, .6), 
            'nalign': (1, 0, 0, .6),
            'delete': (.1, .1, .1, .6)}

    def on_new_object(self):
        self.reset()
        self.app.gui.enable(['clear_stack'])

    def on_previous_object(self):

        # do the standard resets
        self.reset()

        # don't allow users to clear stack for previous objects
        self.app.gui.disable(['clear_stack'])

        # and all the specific stuff to reload previous
        cod = Component.get('ObjectIO').current_object_dir
        settings = Component.get('Metadata').get({'sub_type', 'rejected', 'exposure'})
        rejected = set(settings.get('rejected', []))
        exposure = settings.get('exposure', None)
        sub_type = settings.get('sub_type', 'light')
        if self.reload_rejected:
            for f in fits_in_dir(os.path.join(cod, 'rejects')):
                try:
                    bn = os.path.basename(f)
                    os.rename(f, os.path.join(cod, bn))
                    rejected.add(bn)
                except Exception as e:
                    logger.exception('problem moving rejected on load {:} ({:})'.format(f, e))

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
                logger.exception('problem reading image {:} ({:})'.format(f, e))

        # if not self.is_empty():
        #      self.original_exposure = self.subs[0].exposure

        # store rejected to see if anything has changed and needs saving
        self.orig_rejects = {os.path.splitext(r)[0].lower() for r in rejected}

        if self.is_empty():
            return

        self.recompute()

        # get filter/exposure/subtype and send to CaptureScript
        expo = self.get_prop('exposure')
        if expo is None:
            expo = Component.get('Metadata').get('exposure')
        Component.get('CaptureScript').set_external_details(
            exposure=0 if expo is None else expo, 
            sub_type=self.get_prop('sub_type'), 
            filt=''.join({s.filter for s in self.subs}))

 
    def reset(self):
        # Called when we have a new object and when user clears stack
        self.stop_load() # new in v0.5
        self.stack_cache = {}
        self.orig_rejects = set({}) # new
        self.subs.clear()
        self.selected_sub = -1
        self.update_stack_scroller()
        self.set_to_subs()
        Component.get('View').reset()  # might not be needed as View also does a reset!
        self.info('reset')

    def on_save_object(self):
        # move rejected subs to 'rejected'; we won't touch non-aligned as they are salvageable often
        cod = Component.get('ObjectIO').current_object_dir
        for s in self.subs:
            if s.status == 'reject':
                move_to_dir(os.path.join(cod, s.fullname), 'rejects')

    def is_empty(self):
        return len(self.subs) == 0

    def update_status(self):
        d = self.describe()
        if d:
            self.info('{:} | {:}x{:} | {:}'.format(
                s_to_minsec(d['total_exposure']), 
                d['nsubs'], 
                s_to_minsec(d['sub_exposure']), 
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
            self.dialog = MDDialog(
                auto_dismiss=False,
                text="Are you sure you wish to clear the stack?",
                buttons=[
                    MDFlatButton(text="YES", 
                        text_color=self.app.theme_cls.primary_color,
                        on_press=self._clear),
                    MDFlatButton(
                        text="CANCEL", 
                        text_color=self.app.theme_cls.primary_color,
                        on_press=self._cancel)
                ],
            )
            self.dialog.open()
        else:
            self._clear()

    def _cancel(self, *args):
        self.dialog.dismiss()

    def _clear(self, *args):
        # clear stack auxilliary method since might come after confirmation
        if hasattr(self, 'dialog'):
            self.dialog.dismiss()
        objio = Component.get('ObjectIO')
        cod = objio.current_object_dir
        for nm in glob.glob(os.path.join(cod, '*.fit*')):
            objio.delete_file(os.path.join(cod, nm))

        # perform necessary resets
        Component.get('Aligner').reset()
        self.reset()
        Component.get('Capture').reset(stop_capturing=False)
        self.check_for_change()

    def delete_sub(self, *args):
        if self.is_empty():
            return
        sub_num = self.selected_sub
        if sub_num == 0:
            toast('Cannot delete first sub')
            return
        objio = Component.get('ObjectIO')
        cod = objio.current_object_dir
        objio.delete_file(os.path.join(cod, self.subs[sub_num].name + '.fit'))        
        del self.subs[sub_num]
        self.selected_sub -= 1
        self.check_for_change()

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


    def check_for_change(self):
        ''' whenever there are changes to the stack, check whether anything needs
            saving
        '''

        # empty stack implies no changed
        if self.is_empty():
            self.changed = ''

        # stack contains calibration subs, so always allow master to be saved
        elif self.subs[0].sub_type in {'flat', 'dark', 'bias'}:
            self.changed = 'potential new master'

        # previous object
        elif Component.get('ObjectIO').existing_object:
            if {s.name.lower() for s in self.subs if s.status == 'reject'} != self.orig_rejects:
                # used to have this too: self.subs[0].exposure != self.original_exposure
                self.changed = 'sub select/reject status modififed'
            else:
                self.changed = ''

        # live object, stack non-empty, therefore changed
        else:
            self.changed = 'new object'


    def on_spectral_mode(self, *args):
        self.stack_changed()
 
    def stack_changed(self):
        ''' Called whenever we might need to update the stack e.g. sub added/selected
        deselected/change in stack view/change in mode
        '''

        self.check_for_change()

        if self.is_empty():
            return

        if self.sub_or_stack == 'sub':
            return

        # see if we can satisfy user's non-mono preferences and if not, drop thru to mono
        # filters = self.get_filters()

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
        # sub_labels is array representing the stack
        # these are sub positions on the screen

        self.update_status()
        gui = self.app.gui.gui
        labs = [gui[n]['widget'] for n in ['sub_m2', 'sub_m1', 'sub_0', 'sub_p1', 'sub_p2']]

        # set background to transparent and text to blank to start with
        for l in labs:
            l.text = ''
            l.background_color[-1] = 0

        # we have some subs
        fw = Component.get('FilterChooser')
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
        # stop existing animation
        if hasattr(self, 'play_event'):
            Clock.unschedule(self.play_event)

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
        self.check_for_change()

    def get_current_displayed_image(self, first_sub=False):
        ''' Called by platesolver to get currently displayed image
             which might be short sub, sub, or stack
        '''
 
        if self.is_empty():
            ''' we have no image on the stack so must be faffing
                and pixel height therefore has to come from camera
            '''
            try:
                im = Component.get('Capture').last_faf
                if im is None:
                    logger.trace('last_faf is None')
                    return None
                self.pixel_height = Component.get('Camera').get_pixel_height()
                logger.trace('using faf with pixel height {:}'.format(self.pixel_height))
            except:
                logger.trace('no stack and no short subs either')
                return None

        else:
            ''' we have stacked images
            '''
            if first_sub:
                logger.trace('using first sub')
                im = self.subs[0].get_image()
            elif self.sub_or_stack == 'sub':
                logger.info('using current sub')
                im = self.subs[self.selected_sub].get_image()
            else:
                logger.info('using current stack')
                im = self.get_stack()

            # get pixel height from sub; not clear if we should
            # be mult by binning though
            ph = self.subs[0].pixel_height
            self.pixel_height = None if ph is None else ph * self.subs[0].binning

        return Component.get('View').do_flips(im)

               

        # if not Component.get('ObjectIO').existing_object and Component.get('CaptureScript').faffing():
        #     # currently using focus/align/frame
        #     logger.info('getting last faf image')
        #     im = Component.get('Capture').last_faf
        # elif self.is_empty():
        #     # try to get FAF if current stack is empty
        #     try:
        #         im = Component.get('Capture').last_faf
        #     except:
        #         print('here')
        #         return None
        # elif first_sub:
        #     if not self.is_empty():
        #         im = self.subs[0].get_image()
        #     else:
        #         return None
        # elif self.sub_or_stack == 'sub':
        #     logger.info('getting current sub')
        #     im = self.subs[self.selected_sub].get_image()
        # else:
        #     logger.info('getting current stack')
        #     im = self.get_stack()
        # if im is None:
        #     return None

        # # if we get to here then we have a sub on the stack
        # # rather than a FAF image, so get pixel height
        # if not self.is_empty():
        #     ph = self.subs[0].pixel_height
        #     self.pixel_height = None if ph is None else ph * self.subs[0].binning

        # return Component.get('View').do_flips(im)

    def get_pixel_height(self):
        if hasattr(self, 'pixel_height'):
            return self.pixel_height
        else:
            return None

    def get_RGB_at_pixel(self, x, y):
        ''' Used for G2V calibration: really need to do a proper stellar centroid
            around this pixel
        '''
        x = int(x)
        y = int(y)
        r, g, b = self.get_stack(filt='R'), self.get_stack(filt='G'), self.get_stack(filt='B')
        if r is None or g is None or b is None:
            # print('G2V needs all of RGB')
            return
        # print('G2V: R {:} G {:} B {:}'.format(r[y, x], g[y, x], b[y, x]))


    def get_centroids_for_platesolving(self):
        try:
            return self.subs[self.selected_sub].centroids
        except:
            logger.warning('no image for platesolving')
            return None

    def get_selected_sub_count(self):
        # used by calibrator
        return len([1 for s in self.subs if s.status == 'select'])


    def get_prop(self, prop=None, unique=True):
        ''' find value of specified property  (e.g. exposure time) from 
            subs on stack; if unique is set return None if more than one 
            value exists for the property
        '''
        if prop is None:
            return None
        pvals = {getattr(s, prop, None) for s in self.subs}
        if len(pvals) == 0 or None in pvals:
            return None
        if unique:
            return getattr(self.subs[0], prop) if len(pvals) == 1 else None
        return pvals


    def get_stack(self, filt='all', calibration=False):
        ''' Return stack of selected subs of the given filter if provided. Normally uses 
        those subs up to the currently selected sub on the display. Responsible for 
        caching results to prevent expensive recomputes. For calibration, uses all subs.
        '''

        # we have no subs
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

        # none remain
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

    @logger.catch()
    def add_sub(self, sub):
        ''' called by ObjectIO.new_sub
        '''

        ''' check if sub is the same dims as existing stack, otherwise don't add; note
            dims are in reverse order to those of the numpy array
        ''' 
        if not self.is_empty():
            width, height = self.subs[0].image.shape
            if sub.shape[1] != width or sub.shape[0] != height:
                msg = 'sub dimensions {:} x {:} incompatible with those of current stack {:}'.format(
                    width, height, self.subs[0].get_image().shape)
                toast(msg)
                logger.error(msg)
                return

        self.process(sub)
        self.subs.append(sub)
        self.sub_added()
        if sub.temperature is not None:
            Component.get('Session').temperature = sub.temperature

    def realign(self, *args):
        self.recompute(realign=True)

    def recompute(self, widgy=None, realign=False):
        # initial load, recompute or realign
        Component.get('Aligner').reset()
        self.stack_cache = {}
        # shuffle-based realign
        if realign:
            np.random.shuffle(self.subs)
            # if we have a B or Ha, keep shuffling until we start with that
            if len([s for s in self.subs if s.filter in {'B', 'Ha'}]) > 0:
                while self.subs[0].filter not in {'B', 'Ha'}:
                    np.random.shuffle(self.subs)
        self.selected_sub = -1
        self.reprocess_event = Clock.schedule_once(self._reprocess_sub, 0)

    def _reprocess_sub(self, dt):
        if self.selected_sub + 1 < len(self.subs):
            self.process(self.subs[self.selected_sub + 1])
            self.selected_sub += 1
            self.reprocess_event = Clock.schedule_once(self._reprocess_sub, 0)
        else:
            self.reprocess_event = None
            self.stack_changed()

    def stop_load(self):
        if hasattr(self, 'reprocess_event') and self.reprocess_event is not None:
            Clock.unschedule(self.reprocess_event)

    def process(self, sub):
        # Process sub on recompute/realign

        sub.image = None  # force reload
        sub.image = Component.get('BadPixelMap').remove_hotpix(sub.get_image())
        if sub.sub_type == 'light':
            #logger.trace('start calib')
            Component.get('Calibrator').calibrate(sub)
            #logger.trace('start aligner')
            Component.get('Aligner').process(sub)
            #logger.trace('end aligner')
        elif sub.sub_type == 'flat':
            Component.get('Calibrator').calibrate_flat(sub)
