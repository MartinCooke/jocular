''' Component to choose and apply stretch functions
'''

import numpy as np
from functools import partial

from skimage.exposure import (
    equalize_hist, equalize_adapthist, adjust_gamma, 
    adjust_log, adjust_sigmoid
    )
from skimage.filters import rank
from skimage.morphology import disk

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.gridlayout import GridLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.properties import StringProperty

from jocular.component import Component
from jocular.widgets.widgets import JMDToggleButton
from jocular.panel import Panel


class Stretcher(Panel, Component):

    stretch = StringProperty('asinh')


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.stretches = [
            'sublin', 'linear', 'gamma', 'log', 'asinh', 'hyper']
        # self.stretches = [
        #     'sublin', 'linear', 'hyper', 'log', 'gamma', 'asinh', 
        #     'hyper', 'histeq', 'clahe', 'rank',
        #     'gamma2', 'log2', 'ilog', 'sigmoid']
        self.build()
        self.panel_opacity = 0


    def on_show(self):
        for c, but in self.buttons.items():
            but.state = 'down' if c == self.stretch else 'normal'


    def _button(self, name):
        return JMDToggleButton(
                text=name, 
                size_hint=(1, None),
                group='stretch',
                font_size='16sp',
                on_press=partial(self.choose, name))


    def build(self, *args):

        content = self.contents
        self.buttons = {c: self._button(c) for c in self.stretches}
        layout = AnchorLayout(anchor_x='center', anchor_y='bottom', size_hint=(1, 1))
        content.add_widget(layout)
        gl = GridLayout(size_hint=(1, None), cols=6, height=dp(100), spacing=(dp(5), dp(5)))
        for b in self.buttons.values():
            gl.add_widget(b)
        layout.add_widget(gl)
        self.app.gui.add_widget(self)


    def choose(self, stretch, *args):
        if stretch != self.stretch:
            self.app.gui.set('stretch', stretch)
            self.stretch = stretch
            Component.get('Monochrome').adjust_lum()


    def apply_stretch(self, x, param=None, NR=1, background=None):
        ''' apply stretch, called in monochrome
        '''

        # if no noise reduction just use stretch alone
        if (NR <= 0) or (background is None):
            return stretch_main(x, method=self.stretch, param=param)

        # get stretched data and lightly suppress low end
        y = stretch_main(x, method=self.stretch, param=param)
        # y = y / np.max(y)
        hyper_param = 1 - .1 * (NR / 100)
        return y * stretch_main(x, method='hyper', param=hyper_param)


def stretch_main(x, method='linear', param=None):
    ''' Many of these are experimental and not exposed to the user
    '''

    if method == 'linear':
        return x

    if method == 'sigmoid':
        return adjust_sigmoid(x, cutoff=param)

    if method == 'gamma2':
        c = param
        return adjust_gamma(x, gamma=c)

    if method == 'log2':
        c = param
        return adjust_log(x, gain=c)

    if method == 'ilog':
        c = param
        return adjust_log(x, gain=c, inv=True)

    if method == 'histeq':
        return equalize_hist(x)

    if method == 'rank':
        footprint = disk(int((param + 2)*20))
        return rank.equalize(x, footprint=footprint)

    if method == 'clahe':
        return equalize_adapthist(x, clip_limit=param)

    if method == 'sublin':
        c = (param + 1)
        return x ** c

    if method == 'hyper':
        d = .02
        c = d * (1 + d - param)
        return (1 + c) * (x / (x + c))

    if method == 'log':
        c = param * 200
        return np.log(c*x + 1) / np.log(c + 1)

    if method == 'asinh':
        # c = param * 250
        c = param * 2000
        return np.arcsinh(c*x) / np.arcsinh(c + .0000001)

    if method == 'gamma':
        # with noise reduction, linear from x=0-a, with slope s
        y = x.copy()
        # g = .5 - .5 * param
        # g = .75 - .75 * param
        g = max(.01, 1 - param)
        a0 = .01
        s = g / (a0 * (g - 1) + a0 ** (1 - g))
        d = (1 / (a0 ** g * (g - 1) + 1)) - 1
        y[x < a0] = x[x < a0] * s
        y[x >= a0] =  (1 + d) * (x[x >= a0] ** g) - d
        return y
    
    return x

