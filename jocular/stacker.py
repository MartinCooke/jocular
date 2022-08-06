''' Manages calibration, alignment and stacking of incoming subs
'''

import os
import glob
import math
import numpy as np
from datetime import datetime
from loguru import logger
from astropy.io import fits

from kivy.app import App
from kivy.properties import (BooleanProperty, NumericProperty, ListProperty)
from kivy.clock import Clock
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivy.core.window import Window
from kivy.metrics import dp

from jocular.table import Table
from jocular.component import Component
from jocular.settingsmanager import JSettings
from jocular.utils import s_to_minsec, move_to_dir, purify_name, toast
from jocular.image import Image, fits_in_dir
from jocular.widgets.widgets import JSlider

from kivy.lang import Builder

Builder.load_string(
    '''

<MySpinnerOption@SpinnerOption>:
    size_hint_y: None
    height: "24dp"
    background_color: .1, .1, .1, 1

''')


date_time_format = '%d %b %y %H:%M:%S'


def handleNAN(x):
    if type(x) == str:
        return x
    if x is None:
        return math.nan
    return math.nan if math.isnan(x) else x



class Stacker(Component, JSettings):

    save_settings = ['speed']

    selected_sub = NumericProperty(-1) # index of currently selected sub starts at 0
    viewing_stack = BooleanProperty(False)
    subs = ListProperty([])
    animating = BooleanProperty(False)
    speed = NumericProperty(2)
    confirm_before_deleting_stack = BooleanProperty(True)
    reload_rejected = BooleanProperty(False)

    configurables = [
        ('confirm_before_deleting_stack', {
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
        # self.on_spectral_mode()
        self.sub_colors = {'select': (0, 1, 0, .6), 
            'reject': (.5, .5, .5, .6), 
            'nalign': (1, 0, 0, .6),
            'delete': (.1, .1, .1, .6)}
        # initialise speed from settings
        config = self.app.gui.config
        self.speed = config.get('speed', 2)


    def on_new_object(self):
        self.reset()
        # self.app.gui.enable(['clear_stack'])


    def on_previous_object(self):

        # do the standard resets
        self.reset()

        # don't allow users to clear stack for previous objects
        # self.app.gui.disable(['clear_stack'])

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
                    logger.exception(f'problem moving rejected on load {f} ({e})')

        # now load all (which now will include prev rejects)
        sub_num = 0
        for f in fits_in_dir(cod):
            try:
                im = Image(f)
                im.status = 'reject' if os.path.basename(f) in rejected else 'select'
                if im.exposure is None:
                    im.exposure = exposure
                if im.sub_type is None:
                    im.sub_type=sub_type
                sub_num += 1
                im.stack_num = sub_num
                self.subs.append(im)
            except Exception as e:
                logger.exception(f'problem reading image {f} ({e})')

        # if not self.is_empty():
        #      self.original_exposure = self.subs[0].exposure

        # store rejected to see if anything has changed and needs saving
        self.orig_rejects = {os.path.splitext(r)[0].lower() for r in rejected}

        if self.is_empty():
            return

        self.recompute()

        # get filter/exposure/subtype and send to CaptureScript
        expo = self.get_prop('exposure', average=True)

        if expo is None:
            expo = Component.get('Metadata').get('exposure')

        Component.get('CaptureScript').set_external_details(
            exposure=0 if expo is None else expo, 
            sub_type=self.get_prop('sub_type'), 
            filt=''.join({s.filter for s in self.subs}))


    def reset(self):
        # Called when we have a new object and when user clears stack
        self.subs_table_records = None
        self.stop_load() # new in v0.5
        # self.stack_cache = {}
        self.orig_rejects = set({}) # new
        self.subs.clear()
        self.selected_sub = -1
        self.update_stack_scroller()
        # might add option to allow default to show stack after reset
        # in which case it would be this line instead of the next
        # self.app.gui.set('sub_or_stack', 'stack', update_property=True)
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
        # return info useful to snapshotter and status update

        # viewing single sub
        if len(self.subs) > 0 and not self.viewing_stack:
            s = self.subs[self.selected_sub]
            return {
                'nsubs': 1,
                'total_exposure': s.exposure if s.exposure else 0,
                'sub_exposure': s.exposure if s.exposure else 0,
                'multiple_exposures': False,
                'gain': s.gain if s.gain else 0,
                'dark': 'dark' in s.calibrations,
                'flat': 'flat' in s.calibrations,
                'bias': 'bias' in s.calibrations,
                'filters': f'filter: {s.filter}'}

        # remove any not selected
        subs = [s for s in self.subs[:self.selected_sub+1] if s.status == 'select']
        if len(subs) == 0:
            return None

        # check with multispectral which filters are actually being displayed
        filters_being_displayed = Component.get('MultiSpectral').filters_being_displayed()

        # restrict to these filters
        subs = [s for s in subs if s.filter in filters_being_displayed]

        expos = [s.exposure if s.exposure else 0 for s in subs]
        filts = [s.filter for s in subs]
        fstr = ''

        gains = [s.gain if s.gain else 0 for s in subs]

        # ftypes = Component.get('FilterChooser').get_filter_types()
        ftypes = set(filts)

        for f in ftypes:
            if filts.count(f) > 0:
                fstr += f'{filts.count(f)}{f} '

        return {
            'nsubs': len(subs),
            'total_exposure': sum(expos),
            'gain': np.mean(gains),
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


    def delete_sub_or_stack(self, *args):
        ''' called when user clicks 'trash' icon
        '''
        if self.is_empty():
            return
        #if self.sub_or_stack == 'stack':
        if self.viewing_stack:
            self.delete_stack()
        else:
            self.delete_sub()


    def delete_stack(self, *args):
        ''' Clear existing stack by moving/deleting FITs and resetting
        '''
        if Component.get('ObjectIO').existing_object:
            toast('Cannot delete stack for previous capture')

        elif self.confirm_before_deleting_stack:
            self.dialog = MDDialog(
                auto_dismiss=False,
                text="Are you sure you wish to clear the stack?",
                buttons=[
                    MDFlatButton(text="YES", 
                        text_color=self.app.theme_cls.primary_color,
                        on_press=self._delete_stack),
                    MDFlatButton(
                        text="CANCEL", 
                        text_color=self.app.theme_cls.primary_color,
                        on_press=self._cancel)
                ],
            )
            self.dialog.open()
        else:
            self._delete_stack()


    def _cancel(self, *args):
        self.dialog.dismiss()


    def _delete_stack(self, *args):
        ''' clear stack auxilliary method
        '''
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


    def delete_sub(self):
        ''' delete current sub, except for first (at present)
        '''
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
        ''' animate subs or stack
        '''
        if self.is_empty():
            return
        if self.animating:
            self.play_event = Clock.schedule_interval(self.increment_sub, 1/self.speed)
            # construct slider if we haven't already
            if not hasattr(self, 'speed_slider'):
                self.speed_slider = JSlider(
                    size_hint=(None, None), width=dp(200), height=dp(30), 
                    step=0.2, min=0.3, max=7, value=self.speed)
                self.speed_slider.bind(value=self.speed_changed)
                self.app.gui.add_widget(self.speed_slider)
            self.speed_slider.pos_hint = {'center_x': .5, 'center_y': .90} 

        else:
            # hide scroller and cancel play
            self.speed_slider.pos_hint = {'center_x': 10, 'center_y': .90} 
            if hasattr(self, 'play_event'):
                Clock.unschedule(self.play_event)


    def speed_changed(self, widget, *args):
        self.speed = widget.value


    def on_viewing_stack(self, *args):
        self.on_selected_sub()


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


    def set_to_subs(self):
        # self.app.gui.set('sub_or_stack', 'sub', update_property=True)
        self.app.gui.set('viewing_stack', False, update_property=True)


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
        ''' whenever there are changes to the stack, check whether 
            anything needs saving
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
                self.changed = 'sub select/reject status modified'
            else:
                self.changed = ''

        # live object, stack non-empty, therefore changed
        else:
            self.changed = 'new object'


    def stack_changed(self):
        ''' Called whenever we might need to update the stack 
            e.g. sub added/selected
        '''

        self.check_for_change()

        if self.is_empty() or not self.viewing_stack:
            return

        Component.get('MultiSpectral').stack_changed()

        self.update_status()


    def update_stack_scroller(self, *args):
        # sub_labels is array representing the stack
        # these are sub positions on the screen

        self.update_status()
        gui = self.app.gui.gui
        # can happen
        if not 'sub_0' in gui:
            return
        lab = gui['sub_0']['widget']
        i = self.selected_sub
        if i >= 0:
            lab.text = str(i + 1)
            lab.color = self.sub_colors[self.subs[i].status]
            lab.background_color = Component.get('FilterChooser').filter_properties.get(
                self.subs[i].filter,'?')['bg_color']
        else:
            lab.text = ' '
 

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
            # Component.get('Snapshotter').info('saved animation')
            toast(f'saved animation to {save_path}', duration=2)


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

        if self.viewing_stack:
            self.stack_changed()
        else:
            ss = self.subs[s]
            Component.get('Monochrome').display_sub(
                ss.get_image(), 
                do_gradient=ss.sub_type=='light',
                fwhm=ss.fwhm if hasattr(ss, 'fwhm') else 0)

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
                logger.trace(f'using faf with pixel height {self.pixel_height}')
            except:
                logger.trace('no stack and no short subs either')
                return None

        else:
            ''' we have stacked images
            '''
            if first_sub:
                im = self.subs[0].get_image()
            elif self.viewing_stack:
                im = self.get_stack()
            else:
                im = self.subs[self.selected_sub].get_image()

            # get pixel height from sub; not clear if we should
            # be mult by binning though
            ph = self.subs[0].pixel_height
            self.pixel_height = None if ph is None else ph * self.subs[0].binning

        return Component.get('View').do_flips(im)

               
    def get_pixel_height(self):
        if hasattr(self, 'pixel_height'):
            return self.pixel_height
        return None


    def get_RGB_at_pixel(self, x, y):
        ''' Used for G2V calibration: really need to do a proper stellar centroid
            around this pixel
        '''
        x = int(x)
        y = int(y)
        r, g, b = self.get_stack(filt='R'), self.get_stack(filt='G'), self.get_stack(filt='B')
        if r is None or g is None or b is None:
            return


    def get_centroids_for_platesolving(self):
        try:
            return self.subs[self.selected_sub].centroids
        except:
            logger.warning('no image for platesolving')
            return None


    def get_selected_sub_count(self):
        # used by calibrator
        return len([1 for s in self.subs if s.status == 'select'])


    def get_prop(self, prop=None, unique=True, average=False):
        ''' find value of specified property  (e.g. exposure time) from 
            subs on stack; if unique is set return None if more than one 
            value exists for the property
        '''
        if prop is None:
            return None
        pvals = {getattr(s, prop, None) for s in self.subs}
        if average:
            try:
                return np.mean(list(pvals))
            except:
                return None
        if len(pvals) == 0 or None in pvals:
            return None
        if unique:
            return getattr(self.subs[0], prop) if len(pvals) == 1 else None
        return pvals


    def get_stack(self, filt='all', calibration=False):
        ''' Return stack of selected subs of the specified filter. Caches
            results to prevent expensive recomputes. Does fast stack
            combination for addition or removal of a single sub assuming
            combination method is 'mean'. For calibration, uses all subs.
        '''

        # we have no subs
        if not self.subs:
            return None

        orig_sub_map = {s.name: s for s in self.subs}

        # subs up to current selected sub, except in case of calibration
        if calibration:
            subs = self.subs
        else:
            subs = self.subs[:self.selected_sub+1]

        # if no filter, choose all subs, otherwise restrict
        if filt == 'all':
            stk = [s for s in subs if s.status=='select']
        else:
            stk = [s for s in subs if (s.status=='select') & (s.filter==filt)]

        # none remain
        if not stk:
            return None

        return Component.get('StackCombiner').combine(
            stk, 
            orig_sub_map,
            filt=filt, 
            calibration=calibration)


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
                msg = f'sub dims {width} x {height} incompatible with current stack {self.subs[0].get_image().shape}'
                toast(msg)
                logger.error(msg)
                return

        self.process(sub)
        self.subs.append(sub)
        self.sub_added()

        # Add stack number
        sub.stack_num = len(self.subs)

        if sub.temperature is not None:
            Component.get('Session').temperature = sub.temperature


    def realign(self, *args):
        self.recompute(realign=True)


    def recompute(self, widgy=None, realign=False):
        # initial load, recompute or realign
        Component.get('Aligner').reset()
        Component.get('StackCombiner').reset()
        # self.stack_cache = {}
        initial_filters = {'B', 'H', 'S', 'O'}
        # shuffle-based realign
        if realign:
            np.random.shuffle(self.subs)
            # if we have a B or Ha, keep shuffling until we start with that
            if len([s for s in self.subs if s.filter in initial_filters]) > 0:
                while self.subs[0].filter not in initial_filters:
                    np.random.shuffle(self.subs)

            # Renumber the subs
            for num, sub in enumerate(self.subs):
                sub.stack_num = num + 1

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
        # sub.image = Component.get('BadPixelMap').remove_hotpix(sub.get_image())
        Component.get('BadPixelMap').process_bpm(sub)
        if sub.sub_type == 'light':
            Component.get('Calibrator').calibrate(sub)
            Component.get('Aligner').align(sub)
        elif sub.sub_type == 'flat':
            Component.get('Calibrator').calibrate_flat(sub)


    ''' Below, code for viewing/editing of FITs information in subs
    '''

    def show_subs_table(self, *args):
        ''' Called when user clicks on GUI
        '''

        if self.is_empty():
            return

        # build subs_table_records dict
        self.update_sub_records()

        # build table if necessary
        if not hasattr(self, 'subs_table'):
            self.subs_table = self.build_substable()
        
        self.subs_table.data = self.subs_table_records

        self.app.showing = 'subs'

        # check for redraw
        if self.subs_table not in self.app.gui.children:
            self.app.gui.add_widget(self.subs_table, index=0)

        # ensure that selected set aligns with subs display in GUI
        selected_set = set({s.name for s in self.subs if s.status == 'select'})
        self.subs_table.select(selected_set)
        self.subs_table.update()
        self.subs_table.show()    


    def build_substable(self):
        ''' Contruct table from stack
        '''

        cols={
            'stack_num': {'w': 45, 'label': 'N', 'type':int}, 
            'status': {'w': 65, 'label': 'Status'},
            'aligned': {'w': 70, 'label': 'Aligned'},
            'name': {'w': 200, 'align': 'left', 'label': 'Name', 'action': self.view_single_sub}, 
            'pp_create_time': {'w': 140, 'align': 'left', 'label': 'Date', 'sort': {'DateFormat': date_time_format}}, 
            'exposure': {'w': 60, 'label': 'Expo', 'type': float},
            'temperature': {'w': 60, 'label': 'Temp', 'type': float, 'display_fn': lambda x: f'{x:.1f}'},
            'gain': {'w': 60, 'label': 'Gain', 'type': float, 'display_fn': lambda x: f'{x:.0f}'},
            'offset': {'w': 55, 'label': 'Offset', 'type': float, 'display_fn': lambda x: f'{x:.0f}'},
            'binning': {'w': 40, 'label': 'Bin'},
            'filter': {'w': 40, 'label': 'Filt'},
            'fwhm': {'w': 80, 'label': 'FWHM', 'type': float, 'display_fn': lambda x: f'{x:.1f} px'},
            'minval': {'w': 70, 'label': 'Min', 'type': float, 'display_fn': lambda x: f'{x:.1f}%'},
            'maxval': {'w': 70, 'label': 'Max', 'type': float, 'display_fn': lambda x: f'{x:.1f}%'},
            'meanval': {'w': 70, 'label': 'Mean', 'type': float, 'display_fn': lambda x: f'{x:.1f}%'},
            'overexp': {'w': 70, 'label': 'Over', 'type': float, 'display_fn': lambda x: f'{x:.1f}%'}
            }

        # set up editable fields
        for c in ['exposure', 'temperature', 'gain', 'offset', 'binning', 'filter']:
            cols[c]['action'] = self.edit_prop

        return Table(
            size=Window.size,
            data=self.subs_table_records,
            name='Subs',
            description='Subs',
            cols=cols,
            on_hide_method=self.update_stack_from_table,
            initial_sort_column='stack_num'
            )


    def edit_prop(self, row, prop, value):
        # placeholder for now
        toast(f'editing prop {prop} {value} (not yet implemented)')


    def update_stack_from_table(self, *args):
        ''' change selected status based on checkboxes
        ''' 
        if len(self.subs_table.selected) == 0:
            return

        for sub in self.subs:
            sub.status = 'select' if sub.name in self.subs_table.selected else 'reject'

        self.update_stack_scroller()    # updates colours
        self.stack_changed()


    def update_sub_records(self):
        props = [
            'stack_num', 'meanval', 'minval', 'maxval', 'pp_create_time', 
            'exposure', 'filter', 'name', 'fwhm', 'gain', 'offset', 
            'temperature', 'binning', 'overexp', 'status', 'aligned'
            ]
        self.subs_table_records = {}
        for s in self.subs:
            props = {p: handleNAN(getattr(s, p) if hasattr(s, p) else 0) for p in props}
            self.subs_table_records[s.name] = props



    ''' This is potential machinery for editing; not currently used
    '''


    # def is_valid(self, field, value):
    #     if field == 'sub type':
    #         return value in {'dark', 'light', 'bias', 'flat'}
    #     if field in {'exposure', 'gain', 'offset'}:
    #         try:
    #             float(value)
    #             return True
    #         except Exception as e:
    #             return False
    #     if field == 'temperature':
    #         try:
    #             v = float(value)
    #             return v > -100 and v < 100
    #         except Exception as e:
    #             return False
    #     return False

    # def update_fits_header(self, path, key, value, comment=None):
    #     ''' modify headers
    #     '''
    #     # print('updating fits header', path, key, value)
    #     try:
    #         with fits.open(path, mode='update') as hdu:
    #             hdr = hdu[0].header
    #             if comment is None:
    #                 hdr[key] = value
    #             else:
    #                 hdr[key] = (value, comment)
    #             hdu.close()
    #     except Exception as e:
    #         logger.exception('Unable to update fits header for {:} ({:})'.format(path, e))
    #         return

    # def edit_value(self, *args):

    #     # validate value
    #     value = self.edited_value.text.strip()
    #     field = self.spinner.text

    #     if not self.is_valid(field, value):
    #         self.edited_value.foreground_color = (1, 0, 0, 1)
    #         return
    #     self.edited_value.foreground_color = (1, 1, 1, 1)

    #     # for each sub that is selected
    #     for selected_sub in self.subs_table.selected:
    #         sub = None
    #         for s in self.subs:
    #             if s.name == selected_sub:
    #                 sub = s
    #                 break
    #         if field == 'exposure':
    #             self.update_fits_header(sub.path, 'EXPOSURE', value, 'seconds')
    #             self.update_fits_header(sub.path, 'EXPTIME', value, 'seconds')
    #             self.update_fits_header(sub.path, 'EXPO', value, 'seconds')
    #             self.update_fits_header(sub.path, 'EXP', value, 'seconds')
    #         elif field == 'sub type':
    #             self.update_fits_header(sub.path, 'SUBTYPE', value)
    #             self.update_fits_header(sub.path, 'IMAGETYP', value)
    #         elif field == 'temperature':
    #             self.update_fits_header(sub.path, 'TEMPERAT', value)
    #             self.update_fits_header(sub.path, 'TEMP', value)
    #             self.update_fits_header(sub.path, 'CCD-TEMP', value)


    ''' Table for a single sub.

        might be easier to popup a box on hover or on clicking sub name 
        rather than having its own table; 
        on the other hand, perhaps we can edit properties this way too
    '''

    def build_singlesubtable(self):
        ''' Contruct table from stack
        '''

        self.single_sub = {}

        cols={
            'row': {'w': 80, 'align': 'left', 'label': 'line', 'type': int}, 
            'key': {'w': 120, 'align': 'left', 'label': 'Key'}, 
            'value': {'w': .5, 'align': 'left', 'label': 'Value'}, 
            'comment': {'w': .5, 'align': 'left', 'label': 'Comment'}, 
            }

        return Table(
            size=Window.size,
            data=self.single_sub,
            name='SingleSub',
            description='Single Sub',
            cols=cols,
            actions={},
            on_hide_method=self.app.table_hiding,
            initial_sort_column='row' 
            )


    def view_single_sub(self, row, *args):
        sub_name = str(row.key)
        self.subs_table.hide()
        if not hasattr(self, 'singlesub_table'):
            self.singlesub_table = self.build_singlesubtable()

        # find which sub it is
        sub = None
        for s in self.subs:
            if s.name == sub_name:
                sub = s
                break

        if sub is None:
            logger.warning(f'cannot find sub {sub_name}')
            return

        # load FITs
        try:
            with fits.open(sub.path, ignore_missing_end=True) as hdu1:
                hdu1.verify('silentfix')
                hdr = hdu1[0].header
        except Exception as e:
            logger.warning(f'cannot load FITs {sub.path} ({e})')
            return

        self.single_sub = {}
        lines = hdr.tostring(sep='\\n').split('\\n')
        for i, l in enumerate(lines[:-1]):
            kk = i + 1
            ll = l.split('=')
            if len(ll) == 1:
                ll = ll[0]
                if ll.strip().startswith('COMMENT'):
                    key = 'COMMENT'
                    rest = ll.strip()[8:]
                else:
                    key = ''
                    rest = ll
            elif len(ll) == 2:
                key, rest = ll[0], ll[1]
            else:
                key = ll[0]
                rest = '='.join(ll[1:])

            rr = rest.split('/')
            value = rr[0]
            if len(rr) == 1:
                comment = ''
            elif len(rr) == 2:
                comment = rr[1]
            else:
                comment = '/'.join(rr[1:]) 
            self.single_sub[kk] = {
                'row': kk, 
                'key': key.strip(), 
                'value': handleNAN(value.replace('"','').replace("'",'').strip()), 
                'comment': comment.strip()}

        self.singlesub_table.data = self.single_sub
        self.app.showing = 'singlesub'

        # check for redraw
        if self.singlesub_table not in self.app.gui.children:
            self.app.gui.add_widget(self.singlesub_table, index=0)

        self.singlesub_table.show()    


