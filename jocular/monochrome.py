''' Luminance channel manipulations, including B & W, stretch etc
'''

import numpy as np

from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, OptionProperty
from kivy.core.window import Window

from jocular.stretch import stretch
from jocular.gradient import estimate_gradient, estimate_background, image_stats
from jocular.component import Component
from jocular.metrics import Metrics


class Monochrome(Component):

    redrawing = BooleanProperty(False)

    stretch = OptionProperty(
        "asinh", options=["linear", "log", "asinh", "gamma", "hyper"]
    )
    gradient = NumericProperty(100)
    white = NumericProperty(0.9)
    black = NumericProperty(0.1)
    p1 = NumericProperty(0.65)
    lift = NumericProperty(0)
    noise_reduction = NumericProperty(0)
    fine = NumericProperty(0)
    autoblack = BooleanProperty(True)
    show_image_stats = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mono = None  # not 100% sure why this is needed on init
        self.view = Component.get("View")
        self.stacker = Component.get("Stacker")
        self.gui = App.get_running_app().gui

    def on_new_object(self):
        self.mono = None
        self.lum = None  #  luminosity (after applying stretch, B/W etc to mono)
        self._gradient = None  #  pixel-by-pixel zero-mean gradient estimate to subtract
        self._std_background = None  # std dev of background estimated from gradient
        self._blackpoint = None  # automatic estimate of blackpoint
        self._n = 0

    def on_p1(self, *args):
        self.adjust_lum()

    def on_white(self, *args):
        self.adjust_lum()

    def on_black(self, *args):
        if not self.autoblack:
            self.adjust_lum()

    def on_gradient(self, *args):
        self.adjust_lum()

    def on_lift(self, *args):
        self.adjust_lum()

    def on_noise_reduction(self, *args):
        self.adjust_lum()

    def on_stretch(self, *args):
        self.adjust_lum()

    def on_fine(self, *args):
        #  move black by a tiny amount
        if not self.autoblack:
            newblack = min(1, max(0, self.black + 0.1 * self.fine))
            self.gui.set("black", float(newblack))  # causes update

    def on_autoblack(self, *args):
        if self.autoblack:
            if hasattr(self, "mono") and self.mono is not None:
                self.update_blackpoint(self.mono)
                self.adjust_lum()

    def update_blackpoint(self, im):
        self._blackpoint, self._std_background = estimate_background(im)
        self.gui.set("black", float(self._blackpoint))

    def update_gradient(self, im):
        #  Estimate gradient and normalise to zero mean
        g = estimate_gradient(im)
        self._gradient = g - np.mean(g)

    def display_sub(self, im, do_gradient=False):
        """Called by Stacker when user selects sub, and by Capture, when displaying short subs
        Only compute gradient if light sub from stacker, not when calibration, nor when short
        """

        # ensure we are displaying subs
        if self.stacker.sub_or_stack == "stack":
            self.stacker.set_to_subs()

        # cache new image to allow user updates of B/W etc
        self.mono = im
        if do_gradient:
            self.update_gradient(im)
        if self.autoblack:
            self.update_blackpoint(im)
        self.view.display_image(self.luminance())

    def adjust_lum(self, *args):
        """User has changed control position so generate luminance and either
        display it (if sub or in mono mode) or advise multispectral of the update"""

        lum = self.luminance()
        if self.stacker.sub_or_stack == "sub":
            self.view.display_image(lum)
        else:
            if self.stacker.spectral_mode == "mono":
                self.view.display_image(lum)
            else:
                Component.get("MultiSpectral").luminance_updated(lum)

    def L_changed(self, L):
        if L is not None:
            lum = self.update_lum(L)
            self.view.display_image(lum)

    def update_lum(self, im):
        """Create gradient-adjusted luminance image; called here by L_changed and by
        MultiSpectral. Does not directly update display.
        """
        self.mono = im
        self.update_gradient(im)
        self.update_blackpoint(im)
        return self.luminance()

    def luminance(self, *args):
        # Applies black, white etc to current monochrome image, updating luminosity, returning the image.

        if self.mono is None:
            return

        im = self.mono



        # this is the point at which to compute image stats
        if self.show_image_stats:
            self.compute_image_stats()

        #  subtract some % of gradient if we have it computed (not the case for short subs)
        if (self._gradient is not None) and (self.gradient > 0.1):
            im = im - (self.gradient / 100) * self._gradient

        # set black based on automatic blackpoint estimate and lift setting
        #  we also allow lift settings in non-auto case

        if self.autoblack and (self._std_background is not None):
            black = max(0, self._blackpoint - self.lift * self._std_background)

        elif self._std_background is not None:
            black = max(0, self.black - self.lift * self._std_background)

        else:
            black = self.black

        im = (im - black) / (self.white - black)

        im[im > 1] = 1
        im[im < 0] = 0

        # timings: hyper:4, log: 7 asinh: 23, tanh: 6, gamma: 12
        im = stretch(
            im,
            method=self.stretch,
            param=self.p1,
            NR=self.noise_reduction,
            background=0
            if self._std_background is None
            else self.lift * self._std_background,
        )

        return im

    def compute_image_stats(self):
        if hasattr(self, "mono") and self.mono is not None:
            im = self.mono
            stats = image_stats(im)
            for s in [
                "min",
                "background",
                "100 x std. dev.",
                "central 75%",
                "99.9 percentile",
                "99.99 percentile",
                "max",
            ]:
                self.image_stats_fields[s].text = "{:}: {:.10f}%".format(
                    s, 100 * stats[s]
                )

    #  use kv for these?
    def make_image_stats_panel(self):
        p = BoxLayout(
            size_hint=(None, None), size=(dp(200), dp(200)), orientation="vertical"
        )
        App.get_running_app().gui.add_widget(p)
        self.image_stats_fields = {}
        for s in [
            "min",
            "background",
            "100 x std. dev.",
            "central 75%",
            "99.9 percentile",
            "99.99 percentile",
            "max",
        ]:
            self.image_stats_fields[s] = l = Label(
                text=s, size_hint=(None, None), size=(dp(200), dp(25))
            )
            p.add_widget(l)
        return p

    def on_show_image_stats(self, *args):
        if self.show_image_stats:
            if not hasattr(self, "image_stats"):
                self.image_stats = self.make_image_stats_panel()
            cx, cy = Metrics.get("origin")
            self.image_stats.center_x = cx
            self.image_stats.center_y = Window.height - dp(150)
            self.compute_image_stats()
        else:
            self.image_stats.y = 2 * Window.height
