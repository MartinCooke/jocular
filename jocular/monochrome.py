''' Luminance channel manipulations, including B & W, stretch etc
'''

import math
import numpy as np

from skimage.transform import resize, rescale, downscale_local_mean
from skimage import filters
from skimage.morphology import disk

from astropy.stats import SigmaClip
from photutils.background import Background2D, MedianBackground

from kivy.app import App
from kivy.properties import BooleanProperty, NumericProperty, StringProperty

from jocular.settingsmanager import JSettings
from jocular.gradient import estimate_gradient, estimate_background, image_stats
from jocular.component import Component


def TNR(im, ksize=20, method='gaussian', param=1, binfac=1):
    ''' Tony's Noise Reduction
    '''
 
    ksize = int(ksize)
    if binfac > 1:
        im2 = downscale_local_mean(im, (binfac, binfac))
    else:
        im2 = im.copy()
    if method == 'gaussian':
        bkg = filters.gaussian(im2, ksize / binfac)
    elif method == 'median':
        neighbourhood = disk(radius=ksize / binfac)
        bkg = filters.rank.median(im2, neighbourhood) / 255.
    if binfac > 1:
        h, w = im.shape
        bh, bw = bkg.shape
        # use fast upsizing if result is a multiple
        if bh * binfac == h and bw * binfac == w:
            bkg = rescale(bkg, (binfac, binfac))
        else:
            bkg = resize(bkg, im.shape)

    return ((im - bkg) / (1 + np.exp(param) * np.exp(-27 * im))) + bkg


def unsharp_masking(im, radius=5, amount=1):
    return filters.unsharp_mask(im, radius=radius, amount=amount)


def fractional_bin(im, binfac=1, original_size=True):
    ''' Experimental binning with non-integer factor (binfac)
        By default, binned image is resized to original size
    '''
    if binfac < 1:
        return im

    if binfac > 3:
        binfac = 3

    binned = rescale(im, 1 / binfac, anti_aliasing=True, mode='constant', multichannel=False)
    if original_size:
        return resize(binned, im.shape, anti_aliasing=False, mode='constant')
    else:
        return binned


def estimate_gradient_local(im):
    bkg_estimator = MedianBackground()
    sigma_clip = SigmaClip(sigma=3.)
    bkg = Background2D(im, (50, 50), filter_size=(4, 4), sigma_clip=sigma_clip, bkg_estimator=bkg_estimator)
    return bkg.background - bkg.background_median



class Monochrome(Component, JSettings):

    tab_name = 'Luminance'

    redrawing = BooleanProperty(False)
    gradient = NumericProperty(100)
    white = NumericProperty(0.9)
    black = NumericProperty(0.1)
    p1 = NumericProperty(0.65)
    lift = NumericProperty(0)
    noise_reduction = NumericProperty(1)
    #fine = NumericProperty(0)
    autoblack = BooleanProperty(True)
    autowhite = BooleanProperty(False)
    fracbin = NumericProperty(1)
    TNR_amount = NumericProperty(0)         # was TNR_param
    TNR_kernel_size = NumericProperty(20)  # was TNR_kernel_size
    TNR_method = StringProperty('gaussian')
    unsharp_amount = NumericProperty(0)
    unsharp_radius = NumericProperty(2)
    TNR_binning = StringProperty('1')
    RL_width = NumericProperty(0)
    background_method = StringProperty('2D planar')
    imstats_units = StringProperty('percentage')

    configurables = [
        ('noise_reduction', {
            'name': 'noise reduction',
            'float': (0, 1, 0.01),
            'help': 'light touch noise reduction (0=off)'
            }),
        ('imstats_units', {
            'name': 'image stats units', 
            'options': ['percentage', 'ADUs'],
            'help': 'display min/max/mean in status line using these units'}),
        ('background_method', {
            'name': 'gradient removal', 
            'options': ['2D planar', 'regional'],
            'help': '2D planar is less flexible but more robust; regional can produce artefacts'}),
        ('TNR_method', {
            'name': 'noise reduction kernel', 
            'options': ['gaussian', 'median'],
            'help': 'convolve with this to compute background estimate'}),
        ('TNR_binning', {
            'name': 'bin image', 
            'options': ['1x1', '2x2', '3x3', '4x4', '5x5'],
            'help': 'bin image by this factor prior to background computation'}),
        ]

    save_settings = [
        'gradient', 'white', 'black', 'p1', 'lift', 'TNR_kernel_size', 
        'unsharp_radius', 'autoblack', 'autowhite'
        ]


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mono = None  # not 100% sure why this is needed on init
        self.view = Component.get("View")
        self.stacker = Component.get("Stacker")
        self.gui = App.get_running_app().gui


    def on_new_object(self):
        self.mono = None
        self.lum = None  # luminosity (after applying stretch, B/W etc to mono)
        self._gradient = None  # pixel-by-pixel zero-mean gradient estimate to subtract
        self._std_background = None  # std dev of background estimated from gradient
        self._blackpoint = None  # automatic estimate of blackpoint
        self._whitepoint = None  # automatic estimate of whitepoint
        self._background = None  # pixel-by-pixel background estimate used in TNR
        self._n = 0
        self.gui.set('TNR_amount', -1, update_property=True)
        self.gui.set('unsharp_amount', -.1, update_property=True)


    def on_p1(self, *args):
        self.adjust_lum()


    def on_white(self, *args):
        if not self.autowhite:
            self.adjust_lum()


    def on_black(self, *args):
        if not self.autoblack:
            self.adjust_lum()


    def on_gradient(self, *args):
        self.adjust_lum()


    def on_fracbin(self, *args):
        if self.fracbin < 1:
            return
        if self.fracbin > 3:
            return
        self.adjust_lum()


    def on_TNR_amount(self, *args):
        self.adjust_lum()


    def on_TNR_kernel_size(self, *args):
        self.adjust_lum()


    def on_unsharp_radius(self, *args):
        self.adjust_lum()


    def on_unsharp_amount(self, *args):
        self.adjust_lum()


    def on_lift(self, *args):
        self.adjust_lum()


    def on_noise_reduction(self, *args):
        self.adjust_lum()


    def on_RL_width(self, *args):
        self.adjust_lum()

    # def on_fine(self, *args):
    #     # move black by a tiny amount
    #     if not self.autoblack:
    #         newblack = min(1, max(0, self.black + 0.1 * self.fine))
    #         self.gui.set("black", float(newblack))  # causes update

    def on_autoblack(self, *args):
        if self.autoblack:
            if hasattr(self, "mono") and self.mono is not None:
                self.update_blackpoint(self.mono)
                self.adjust_lum()

    def on_autowhite(self, *args):
        if self.autowhite:
            if hasattr(self, "mono") and self.mono is not None:
                self.update_whitepoint(self.mono)
                self.adjust_lum()

    # def on_background_method(self, *args):
    #     self.update_gradient()

    def update_blackpoint(self, im):
        self._blackpoint, self._std_background = estimate_background(im)
        self.gui.set("black", float(self._blackpoint))


    def update_whitepoint(self, im):
        self._whitepoint = np.percentile(im.ravel(), 99.99)
        self.gui.set("white", float(self._whitepoint))


    def update_gradient(self, im):
        # Estimate gradient and normalise to zero mean
        if self.background_method == '2D planar':
            g = estimate_gradient(im)
            self._gradient = g - np.mean(g)
        else:
            self._gradient = estimate_gradient_local(im)


    def update_background(self, im):
        if self.TNR_method == 'gaussian':
            self._background = filters.gaussian(im, self.TNR_kernel_size)
        elif self.TNR_method == 'median':
            neighbourhood = disk(radius=self.TNR_kernel_size)
            self._background = filters.rank.median(im, neighbourhood) / 255.


    def display_sub(self, im, do_gradient=False, fwhm=None):
        ''' Called by Stacker when user selects sub, and by Capture, when 
            displaying short subs. Only compute gradient if light sub from 
            stacker, not when calibration, nor when short
            v0.5 added: also compute grad if dims changed
        '''

        # ensure we are displaying subs
        if self.stacker.viewing_stack:
            self.stacker.set_to_subs()

        # cache new image to allow user updates of B/W etc
        self.mono = im
        if do_gradient:
            self.update_gradient(im)
        # new in v0.5: if shape changes, update gradient
        elif self._gradient is not None and self._gradient.shape != im.shape:
            self.update_gradient(im) 
        if self.autoblack:
            self.update_blackpoint(im)
        if self.autowhite:
            self.update_whitepoint(im)
        self.view.display_image(self.luminance())
        self.update_info(im, fwhm=fwhm)


    def adjust_lum(self, *args):
        ''' User has changed control position so generate luminance and either
            display it (if sub or in mono mode) or advise multispectral of the update
        '''

        multispectral = Component.get("MultiSpectral")
        lum = self.luminance()
        if not self.stacker.viewing_stack:
            self.view.display_image(lum)
        else:
            if multispectral.spectral_mode == "mono":
                self.view.display_image(lum)
            else:
                multispectral.luminance_updated(lum)


    def L_changed(self, L):
        if L is not None:
            lum = self.update_lum(L)
            self.view.display_image(lum)


    def update_lum(self, im):
        ''' Create gradient-adjusted luminance image; called here by L_changed and by
            MultiSpectral. Does not directly update display.
        '''
        self.mono = im
        self.update_gradient(im)
        self.update_blackpoint(im)
        return self.luminance()


    def update_info(self, im, fwhm=None):

        stats = image_stats(im)

        satstr = '' if stats['over'] < .1 else f' sat {stats["over"]:.1f}%'
        fwhmstr = '' if fwhm is None else f'fwhm: {fwhm:.1f}px | ' 
        unitstr = 'ADU' if self.imstats_units == 'ADUs' else '%'
        rangestr = '' if self.imstats_units == 'ADUs' else 'range '

        for k, v in stats.items():
            if math.isnan(v):
                stats[k] = 0
            elif self.imstats_units == 'ADUs':
                stats[k] = int(2**16) * v
            else:
                stats[k] = 100 * v

        self.info(f"{fwhmstr}{rangestr}{stats['background']:.0f} - {stats['99.99']:.0f} {unitstr}{satstr}")


    def luminance(self, *args):
        # Applies black, white etc to current monochrome image, updating luminosity, returning the image.

        if self.mono is None:
            return None

        im = self.mono

        if self.fracbin > 1:
            im = fractional_bin(im, binfac=self.fracbin)

        # compute and display image stats
        self.update_info(im)

        # subtract some % of gradient if we have it computed (not the case for short subs)
        if (self._gradient is not None) and (self.gradient > 0.1):
            im = im - (self.gradient / 100) * self._gradient

        # set black based on automatic blackpoint estimate and lift setting
        # we also allow lift settings in non-auto case

        if self.autoblack and (self._std_background is not None):
            black = max(0, self._blackpoint - self.lift * self._std_background)

        elif self._std_background is not None:
            black = max(0, self.black - self.lift * self._std_background)

        else:
            black = self.black

        # why not working?
        if self.autowhite:
            self.update_whitepoint(im)
            white = self._whitepoint
        else:
            white = self.white

        im = (im - black) / (white - black)

        im[im > 1] = 1
        im[im < 0] = 0

        # timings: hyper:4, log: 7 asinh: 23, tanh: 6, gamma: 12
        if self._std_background is None:
            bkg = 0
        else:
            bkg = self.lift * self._std_background

        im = Component.get('Stretcher').apply_stretch(
            im,
            param=self.p1,
            NR=self.noise_reduction,
            background=bkg,
        )

        # order of these two is not clear; seem to get fewer ringing
        # artefacts if sharpening is done first

        # apply sharpening
        if self.unsharp_amount > 0 and self.unsharp_radius > 0:
            im = unsharp_masking(im, radius=self.unsharp_radius, amount=self.unsharp_amount)

        # apply noise reduction
        if self.TNR_amount > 0:
            im = TNR(
                im, 
                ksize=self.TNR_kernel_size, 
                method=self.TNR_method, 
                param=self.TNR_amount,
                binfac=int(self.TNR_binning[0]))

        # # apply sharpening
        # if self.unsharp_amount > 0 and self.unsharp_radius > 0:
        #     im = unsharp_masking(im, radius=self.unsharp_radius, amount=self.unsharp_amount)

        return im

