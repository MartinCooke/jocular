''' Handles LRGB and L+narrowband processing
'''

import json
from functools import partial

import warnings
warnings.simplefilter('ignore')
import numpy as np

from scipy.stats import trimboth
from skimage.color import rgb2lab, lab2rgb
from skimage.transform import resize, rescale
from loguru import logger

from kivy.properties import NumericProperty, StringProperty
from kivy.app import App
from kivy.metrics import dp
from kivy.uix.gridlayout import GridLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label

from jocular.gradient import estimate_gradient, estimate_background
from jocular.component import Component
from jocular.settingsmanager import JSettings
from jocular.widgets.widgets import JMDToggleButton
from jocular.panel import Panel



def bin_image(im, binfac=2, rescale_to_orig=True):
    ''' bin and rescale to original size; 
        in v0.5 added the preserve range option
    '''
    binfac = int(binfac)
    if binfac == 1:
        return im
    if binfac < 1:
        return im
    im2 = rescale(im, 1 / binfac, anti_aliasing=True, mode='constant', 
        preserve_range=True, multichannel=False)
    if rescale_to_orig:
        return resize(im2, im.shape, anti_aliasing=False, mode='constant',
            preserve_range=True)
    return im2


def _percentile_clip(a, perc=80):
    return np.mean(trimboth(np.sort(a, axis=0), (100 - perc)/100, axis=0), axis=0)


def modify_saturation(x, saturation):
    # Shift endpoints of labA or B to increase saturation. A/B values cover the
    # range -127- to 128 so we increase slope and then trim to range.
    # sat=1 corresponds to shift of 100 (that's a lot!)
    if saturation <= 0:
        return x
    k = saturation * 100
    mx = np.mean(x)
    # steepen but preserve mean (perhaps should do this after trimming?)
    x1 = (x - mx) * (255/(255 - 2*k)) + mx 
    x1[x1 < -127] = -127
    x1[x1 > 127] = 127
    return x1


def modify_hue(x, shift):
    # Shift mean of x by given amount
    x = x + shift
    return x


def limitto01(im):
    im[im < 0] = 0
    im[im > 1] = 1
    return im



class MultiSpectral(Panel, Component, JSettings):
    
    save_settings = [
        'saturation', 
        'colour_stretch', 
        'redgreen', 
        'yellowblue',
        'synth_lum_weights'
        ]

    tab_name = 'Colour'

    configurables = [
        ('bin_colour', {
            'name': 'colour binning', 
            'options': ['1x1', '2x2', '3x3', '4x4'],
            'help': 'Binning the colour channels helps reduce colour noise'}),
        ('compensation', {
            'name': 'compensation', 
            'options': ['none', 'subtract background', 'subtract gradients'],
            'help': 'done prior to colour scaling (subtract gradents recommended)'}),
        ('colour_percentile', {
            'name': 'percentile',
            'float': (99.9, 100.0, .001),
            'help': 'values to include when computing max feature value in colour channel (factory: 99.99)'
            }),
        ('synth_lum_weights', {
            'name': 'syn lum weights',
            'options': ['equal', '30/59/11', '21/72/07'],
            'help': 'weighting of RGB to create synthetic luminance'
            }),
        ('r_weight', {
            'name': 'weight for R channel',
            'float': (.8, 1.2, .01),
            'help': 'multiply R channel by this prior to forming LAB colour'
            }),
        ('g_weight', {
            'name': 'weight for G channel',
            'float': (.8, 1.2, .01),
            'help': 'multiply G channel by this prior to forming LAB colour'
            }),
        ('b_weight', {
            'name': 'weight for b channel',
            'float': (.8, 1.2, .01),
            'help': 'multiply B channel by this prior to forming LAB colour'
            }),
        ]

    spectral_mode = StringProperty('mono')
    luminance_mode = StringProperty('L')
    bin_colour = StringProperty('2x2')
    synth_lum_weights = StringProperty('equal')
    compensation = StringProperty('subtract gradients')
    colour_percentile = NumericProperty(99.99)
    saturation = NumericProperty(0)
    colour_stretch = NumericProperty(.5)
    redgreen = NumericProperty(0)
    yellowblue = NumericProperty(0)
    r_weight = NumericProperty(1)
    g_weight = NumericProperty(1)
    b_weight = NumericProperty(1)


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stacker = Component.get('Stacker')
 
        self.app = App.get_running_app()
        try:
            with open(self.app.get_path('multispectral.json'), 'r') as f:
                self.chans = json.load(f)
        except:
            self.chans = {}

        self.lum_chans = ['L', 'synL', 'L+synL', 'H', 'O', 'S']

        self.build()
        self.panel_opacity = 0
        self.set_spectral_mode('mono')

        # these represent what is possible as opposed to what user wants
        self.actual_luminance_mode = 'L'
        self.actual_spectral_mode = 'mono'


    def on_new_object(self):
        self.reset()


    def reset(self):
        # set these to None to force updates in the colour-generation sequence
        self.lum = None
        self.R = None
        self.G = None
        self.B = None
        self.normed_RGB = None
        self.LAB = None          
        self.A_sat = None
        self.B_sat = None
        self.A_hue = None
        self.B_hue = None
        self.RGB = None
        self.layer = None
        self.layer_stretched = None
        self.r_weight = 1
        self.g_weight = 1
        self.b_weight = 1


    def update_info(self):
        if self.actual_luminance_mode:
            self.info(f'{self.actual_luminance_mode}, {self.actual_spectral_mode}')
        else:
            self.info(self.actual_spectral_mode)


    def describe_mode(self):
        if self.actual_spectral_mode == 'mono':
            return 'mono'
        return f'{self.actual_luminance_mode}, {self.actual_spectral_mode}'


    ''' chooser stuff
    '''

    def on_show(self):

        # ensure chooser reflects current state
        filts = self.stacker.get_filters()
        if filts is None:
            filts = {'mono'}

        for c, but in self.chan_buttons.items():
            chan = self.chans[c]
            needs = set(chan['needs'])
            avail = needs <= filts
            but.color = (0, 1, 0, .5) if avail else (1, 0, 0, .3)
            but.disabled = not avail
            but.state = 'down' if c == self.spectral_mode else 'normal'

        for c, but in self.lum_buttons.items():
            if 'L' in c:
                avail = True
            else:
                avail = c in filts
            but.color = (0, 1, 0, .5) if avail else (1, 0, 0, .3)
            but.disabled = not avail
            but.state = 'down' if c == self.luminance_mode else 'normal'


    def _mode_button(self, name):
        return JMDToggleButton(
                text=name, 
                group='channels',
                font_size='16sp',
                #height=dp(12),
                on_press=partial(self.chan_selected, name))


    def _lum_button(self, name):
        return JMDToggleButton(
                text=name, 
                group='lumin',
                font_size='16sp',
                #height=dp(20),
                # width=dp(30),
                #size_hint=(1/9, None),
                on_press=partial(self.lum_selected, name))


    def build(self, *args):

        content = self.contents
        self.chan_buttons = {c: self._mode_button(c) for c in self.chans}
        #anchor_layout = AnchorLayout(anchor_x='center', anchor_y='bottom', size_hint=(1, 1))
        #content.add_widget(anchor_layout)
        #mainbox = BoxLayout(size_hint=(1, None), height=dp(180))

        content.add_widget(Label(text='', size_hint=(1, 1)))

        gl = GridLayout(size_hint=(1, None), cols=6, height=dp(120), spacing=(dp(5), dp(5)))
        for b in self.chan_buttons.values():
            gl.add_widget(b)
        content.add_widget(gl)

        # # spacer
        content.add_widget(Label(text='', size_hint=(1, None), height=dp(15)))

        self.lum_buttons = {c: self._lum_button(c) for c in self.lum_chans}
        bl = GridLayout(size_hint=(1, None), cols=6, height=dp(40), spacing=(dp(5), dp(5)))
        for b in self.lum_buttons.values():
            bl.add_widget(b)
        content.add_widget(bl)

        # anchor_layout.add_widget(mainbox)
        self.app.gui.add_widget(self)


    def chan_selected(self, chan, *args):
        if chan != self.spectral_mode:
            self.set_spectral_mode(chan)
 

    def lum_selected(self, lum, *args):
        if lum != self.luminance_mode:
            self.luminance_mode = lum
            # i.e. do update
            self.set_spectral_mode()


    ''' end of chooser stuff
    '''

    def syn_lum(self, R, G, B):
        if self.synth_lum_weights == 'equal':
            L = (R + G + B) / 3
        elif self.synth_lum_weights == '30/59/11':
            L = .299*R  + .587*G + .114*B
        elif self.synth_lum_weights == '21/72/07':
            L = .2125*R  + .7154*G + .0721*B
        return L / np.percentile(L.ravel(), 99.99)


    def on_saturation(self, *args):
        self.adjust_saturation()


    def on_colour_stretch(self, *args):
        self.adjust_colour_stretch()

    def on_r_weight(self, *args):
        self.create_LAB()

    def on_g_weight(self, *args):
        self.create_LAB()

    def on_b_weight(self, *args):
        self.create_LAB()


    # not currently used
    def on_redgreen(self, *args):
        self.adjust_hue()


    def on_yellowblue(self, *args):
        self.adjust_hue()


    def on_bin_colour(self, *args):
        self.create_LAB()


    def on_subtract_gradients(self, *args):
        self.create_LAB()


    def filters_being_displayed(self):
        ''' return set of filters being used in currently displayed image
        '''
        lum = self.actual_luminance_mode
        spect = self.actual_spectral_mode

        # if mono, we're using all the filters
        if spect == 'mono':
            return {'L', 'R', 'G', 'B', 'H', 'O', 'S'}

        # create set from spect
        f = {s for s in spect.replace('+', '')}

        # check if using 'L'
        if lum in {'L', 'L+synL'}:
            f.add('L')

        # if not using synL, add whatever filter is being used
        elif lum != 'synL':
            f.add(lum)

        return f



    def get_lum_stack(self, R, G, B):
        ''' interpret user's luminance stack preference and record
            what was actually possible in the absence of certain
            channels in the stack
        '''

        if self.luminance_mode == 'L':
            l = self.stacker.get_stack('L')
            if l is None:
                self.actual_luminance_mode = 'synL'
                return self.syn_lum(R, G, B)
            self.actual_luminance_mode = 'L'
            return l

        if self.luminance_mode == 'synL':
            self.actual_luminance_mode = 'synL'
            return self.syn_lum(R, G, B)

        if self.luminance_mode == 'L+synL':
            l = self.stacker.get_stack('L')
            if l is None:
                self.actual_luminance_mode = 'synL'
                return self.syn_lum(R, G, B)
            else:
                self.actual_luminance_mode = 'L+synL'
                return (l + self.syn_lum(R, G, B)) / 2

        # otherwise return channel, or create synthetic lum
        c = self.stacker.get_stack(self.luminance_mode)

        if c is None:
            self.actual_luminance_mode = 'synL'
            return self.syn_lum(R, G, B)

        self.actual_luminance_mode = self.luminance_mode
        return c



    def set_spectral_mode(self, mode=None):
        ''' User selects one of many available spectral
            modes for which there are appropriate
            stacks
        '''

        # might not be updating spectral mode but responding to lum mode change
        if mode is None:
            mode = self.spectral_mode 
        
        self.spectral_mode = mode
        self.actual_spectral_mode = mode

        if not self.stacker.viewing_stack:
            self.app.gui.set('spectral_mode', mode)
            return

        self.reset()
        props = self.chans[mode]

        # get required channels
        stacks = {c: self.stacker.get_stack(c) for c in props['needs']}

        # if any chans not available, do mono
        notavail = np.any([v is None for v in stacks.values()])
        if notavail:
            self.luminance_only()
            self.actual_spectral_mode = 'mono'

        # LRGB-style manipulation
        elif mode in {'RGB', 'HOO', 'SHO', 'HOS'}:
            self.R = stacks[mode[0]]
            self.G = stacks[mode[1]]
            self.B = stacks[mode[2]]
            l = self.get_lum_stack(self.R, self.G, self.B)
            self.lum = Component.get('Monochrome').update_lum(l)
            self.create_LAB()

        # view single filter
        elif mode in {'L', 'H', 'O', 'S', 'R', 'G', 'B'}:
            self.actual_luminance_mode = ''
            Component.get('Monochrome').L_changed(stacks[mode])

        # luminance + narrowband layer
        elif mode.startswith('L+'):
            other = mode[-1]
            L = stacks['L']
            layer = stacks[other]
            self.lum = Component.get('Monochrome').update_lum(L)
            self.layer = layer / np.percentile(layer.ravel(), 99.99)
            self.layer_stretch_changed()
    
        # view in mono
        else:
            self.spectral_mode = 'mono'
            self.luminance_only()

        # update GUI
        self.app.gui.set('spectral_mode', self.spectral_mode)

        self.stacker.update_status()
        self.update_info()


    def stack_changed(self):
        ''' Called by Stacker.stack_changed to handle both mono
            and multispectral cases
        '''

        logger.debug('')

        if self.spectral_mode == 'mono':
            L = self.stacker.get_stack(filt='all')
            Component.get('Monochrome').L_changed(L)
            self.reset()
        else:
            self.set_spectral_mode(self.spectral_mode)         


    ''' these methods are part of the chain of processes used in
        colour manipulation; they generally do some specialised
        computation then call the next process in the chain. Done
        like this for efficiency so only those things that need
        recomputing are
    '''

    def layer_stretch_changed(self):
        if self.layer is not None:
            self.layer_stretched = self.modgamma(self.layer - estimate_gradient(self.layer)[0], 
                g=self.colour_stretch)
            self.layer_sat_changed()


    def layer_sat_changed(self):
        if self.layer_stretched is not None:
            r = 3 * self.saturation * self.layer_stretched + self.lum
            r[r < 0] = 0
            r[r > 1] = 1            
            Component.get('View').display_image(np.stack([r, self.lum, self.lum], axis=-1))


    def luminance_only(self):
        Component.get('Monochrome').L_changed(
            self.stacker.get_stack(filt='all'))


    def luminance_updated(self, lum):
        # called from monochrome if user updates luminance control e.g. white

        self.lum = lum
        # we are in LRGB mode
        if self.LAB is not None:
            self.create_RGB()

        # we are in L+ mode
        elif self.layer is not None:
            self.layer_sat_changed()

        # display as mono
        else:            
            Component.get('View').display_image(lum)


    ''' Colour processes are daisy-chained and intermediate representations cached for speed        
        create_LAB          normed_RGB
        stretch_color       LAB             
        adjust_saturation   A_sat, B_sat
        adjust_hue          A_hue, B_hue
        create_RGB          RGB             <-- entry point for luminosity changes
    '''

    def create_LAB(self):
        # Initial stage of LAB image creation from RGB stacks


        if not self.avail(['R', 'G', 'B']):
            return

        # use lupton 
        # from astropy.visualization import make_lupton_rgb
        # lupton = make_lupton_rgb(self.R, self.G, self.B, Q=10, stretch=0.5)
        # Component.get('View').display_image(lupton / 255)
        # return

        # include color normalisation

        ims = [self.r_weight*self.R, self.g_weight*self.G, self.b_weight*self.B]

        # binning ~ 70 ms
        binfac = int(self.bin_colour[0])
        if binfac > 1:
            ims = [bin_image(im, binfac=binfac) for im in ims]

        # compensation prior to scaling
        if self.compensation == 'subtract gradients':
            ims = [im - estimate_gradient(im) for im in ims]
        elif self.compensation == 'subtract background':
            ims = [im - estimate_background(im)[0] for im in ims]

        ''' the percentile is absolutely critical: setting too low
            leads to saturated stars; too high leads to a washed-out
            colour space
        '''
        # max_pixel_vals = [np.percentile(im.ravel(), 99.99) for im in ims]
        logger.trace('find max')
        if self.colour_percentile > 99.999:
            max_pixel_vals = [np.max(im) for im in ims]
            logger.trace(f'max pixel vals via max {max_pixel_vals}')
        else:
            max_pixel_vals = [np.percentile(im.ravel(), self.colour_percentile) for im in ims]
            logger.trace(f'max pixel vals via percentile {max_pixel_vals}')

        ''' divide all images by the largest of these; this expands the
            colour dynamic range without affected colour ratios; the expanded
            range helps when L is combined
        '''
        ims = [im / max(max_pixel_vals) for im in ims]

        ''' limit image to 0-1 because we are about to stretch
            (while it shouldn't be necessary as we've just divided by
            max feature, there may be some brighter hot pixels 
            above unity)
        '''
        self.normed_RGB = [limitto01(im) for im in ims]

        # rest of process
        self.adjust_colour_stretch()


    def modgamma(self, x, g=.5, a0=.01):
        y = x.copy()
        s = g / (a0 * (g - 1) + a0 ** (1 - g))
        d = (1 / (a0 ** g * (g - 1) + 1)) - 1
        y[x < a0] = x[x < a0] * s
        y[x >= a0] =  (1 + d) * (x[x >= a0] ** g) - d
        return y


    def avail(self, props):
        if type(props) != list:
            props = [props]
        return all([hasattr(self, p) and getattr(self, p) is not None for p in props])


    def adjust_colour_stretch(self, *args):
        # intercept LAB process here if we need to stretch colour

        if self.avail('layer'):
            self.layer_stretch_changed()

        elif self.avail('normed_RGB'):
            # use modified gamma correction here to avoid colour noise
            ims = [self.modgamma(im, g=self.colour_stretch) for im in self.normed_RGB]
            self.LAB = rgb2lab(np.stack(ims, axis=-1))  # 80ms
            self.adjust_saturation()


    def adjust_saturation(self, *args):
        # Modify saturation and call next process
        
        if self.avail('layer'):
            self.layer_sat_changed()

        elif self.avail('LAB'):
            self.A_sat = modify_saturation(self.LAB[:, :, 1], self.saturation)
            self.B_sat = modify_saturation(self.LAB[:, :, 2], self.saturation)
            self.adjust_hue() # next process in hue adjustment


    def adjust_hue(self, *args):
        # Modify hue and generate RGB image
        
        if self.avail('A_sat'):
            self.A_hue = modify_hue(self.A_sat, self.redgreen)
            self.B_hue = modify_hue(self.B_sat, self.yellowblue)
            self.create_RGB()  # next process


    def create_RGB(self):
        ''' Combine L, A and B into RGB image. Called here when previous colour process
        has been applied (hue_changed), or when luminosity component has changed (below)
        '''
        if self.avail(['lum', 'A_hue']):
            self.RGB = lab2rgb(np.stack([ 100 * self.lum, self.A_hue, self.B_hue], axis=-1))
            Component.get('View').display_image(self.RGB)

