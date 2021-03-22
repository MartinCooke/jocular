''' Handles LRGB and L+narrowband processing
'''

import warnings
warnings.simplefilter('ignore')
import numpy as np
from scipy.stats import trimboth
from skimage.color import rgb2lab, lab2rgb
from skimage.transform import resize, rescale
from kivy.properties import ConfigParserProperty, NumericProperty
from jocular.gradient import estimate_gradient, estimate_background
from jocular.component import Component

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

class MultiSpectral(Component):

    colour_binning = ConfigParserProperty(
        1, 'Colour', 'colour_binning', 'app', val_type=int)
    subtract_colour_gradients = ConfigParserProperty(
        1, 'Colour', 'subtract_colour_gradients', 'app', val_type=int)
    
    saturation = NumericProperty(0)
    colour_stretch = NumericProperty(.5)
    redgreen = NumericProperty(0)
    yellowblue = NumericProperty(0)

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

    def on_saturation(self, *args):
        self.adjust_saturation()

    def on_colour_stretch(self, *args):
        self.adjust_colour_stretch()

    def on_redgreen(self, *args):
        self.adjust_hue()

    def on_yellowblue(self, *args):
        self.adjust_hue()

    def LRGB_changed(self, L=None, R=None, G=None, B=None):

        self.reset()
        # we lack one of RGB, so let Monochrome handle it and call reset
        # so colour components are regenerated next time we have RGB
        if R is None or G is None or B is None:
            self.luminance_only()
        else: 
            # we have RGB; if no L, generate synthetic lum
            if L is None:
                L = .2125*R  + .7154*G + .0721*B
                L = L / np.percentile(L.ravel(), 99.99)
                 
            self.lum = Component.get('Monochrome').update_lum(L)
            self.R = R
            self.G = G
            self.B = B
            self.create_LAB()

    def L_plus_changed(self, L=None, layer=None):

        # if we have no layer, update luminance only
        self.reset() # ensure components get updated
        if layer is None:
            self.luminance_only()
        elif L is not None:
            self.lum = Component.get('Monochrome').update_lum(L)
            self.layer = layer / np.percentile(layer.ravel(), 99.99)
            self.layer_stretch_changed()

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
            Component.get('Stacker').get_stack(filt='all'))

    def luminance_updated(self, lum):
        # called from monochrome if user updates luminance control e.g. white

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

    def on_colour_binning(self, *args):
        self.create_LAB()

    def on_subtract_colour_gradients(self, *args):
        self.create_LAB()

    ''' Colour processes are daisy-chained and intermediate representations cached for speed        
        create_LAB          normed_RGB
        stretch_color       LAB             
        adjust_saturation   A_sat, B_sat
        adjust_hue          A_hue, B_hue
        create_RGB          RGB             <-- entry point for luminosity changes
    '''

    def create_LAB(self):
        # Initial stage of LAB image creation from RGB stacks

        # def bin_image(im, binfac=2):
        #     im2 = rescale(im, 1 / binfac, anti_aliasing=True, mode='constant', multichannel=False)
        #     return resize(im2, im.shape, anti_aliasing=False, mode='constant')

        def _limit(im):
            im[im < 0] = 0
            im[im > 1] = 1
            return im

        if not self.avail(['R', 'G', 'B']):
            return

        ims = [self.R, self.G, self.B]

        # binning ~ 70 ms
        if self.colour_binning:
            ims = [bin_image(im) for im in ims]

        # alternative approach to test
        # might also add option to not subtract anything.... just to test
        if self.subtract_colour_gradients:
            ims = [im - estimate_gradient(im) for im in ims]
        else:
            ims = [im - estimate_background(im)[0] for im in ims]

        # it turns out this value is absolutely critical because setting it too low means that stars get saturated
        # whereas too high, or just using the absolute max leads to a colour space is too compressed (too grey).

        max_pixel_vals = [np.percentile(im.ravel(), 99.99) for im in ims]
        ims = [im / max(max_pixel_vals) for im in ims]

        # now limit image to 0-1 because we are about to stretch
        self.normed_RGB = [_limit(im) for im in ims]

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
        # intercept LAB process here if we need to stretch colour

        if self.avail('layer'):
            self.layer_stretch_changed()

        elif self.avail('normed_RGB'):
            # use modified gamma correction here to avoid colour noise
            ims = [self.modgamma(im, g=self.colour_stretch) for im in self.normed_RGB]
            self.LAB = rgb2lab(np.stack(ims, axis=-1))  # 80ms
            self.adjust_saturation()

    def adjust_saturation(self, *args):
        # Modify saturation and call next process
        
        if self.avail('layer'):
            self.layer_sat_changed()

        elif self.avail('LAB'):
            self.A_sat = modify_saturation(self.LAB[:, :, 1], self.saturation)
            self.B_sat = modify_saturation(self.LAB[:, :, 2], self.saturation)
            self.adjust_hue() # next process in hue adjustment

    def adjust_hue(self, *args):
        # Modify hue and generate RGB image
        
        if self.avail('A_sat'):
            self.A_hue = modify_hue(self.A_sat, self.redgreen)
            self.B_hue = modify_hue(self.B_sat, self.yellowblue)
            self.create_RGB()  # next process

    def create_RGB(self):
        ''' Combine L, A and B into RGB image. Called here when previous colour process
        has been applied (hue_changed), or when luminosity component has changed (below)
        '''
        if self.avail(['lum', 'A_hue']):
            self.RGB = lab2rgb(np.stack([ 100 * self.lum, self.A_hue, self.B_hue], axis=-1))
            Component.get('View').display_image(self.RGB)

