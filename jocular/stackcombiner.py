''' Handles all aspects of stack combination, including chooser
    for combination method & stack caching
'''

import numpy as np
from functools import partial
from loguru import logger

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.gridlayout import GridLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.properties import StringProperty

from jocular.component import Component
from jocular.widgets.widgets import JMDToggleButton
from jocular.utils import percentile_clip
from jocular.panel import Panel


class StackCombiner(Panel, Component):

    combine_method = StringProperty('mean')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.methods = ['mean', '90', '80', '70', 'median']
        self.build()
        self.panel_opacity = 0


    def on_new_object(self):
        self.reset()


    def on_combine_method(self, *args):
        self.app.gui.set('combine_method', self.combine_method)


    def on_show(self):
        for c, but in self.buttons:
            but.state = 'down' if c == self.combine_method else 'normal'


    def _button(self, name):
        return JMDToggleButton(
                text=name, 
                size_hint=(.1, None),
                group='combine',
                font_size='16sp',
                height=dp(20),
                on_press=partial(self.choose, name))


    def build(self, *args):

        content = self.contents
        self.buttons = [(c, self._button(c)) for c in self.methods]
        layout = AnchorLayout(anchor_x='center', anchor_y='bottom', size_hint=(1, 1))
        content.add_widget(layout)
        gl = GridLayout(size_hint=(1, None), cols=5, height=dp(100), spacing=(dp(5), dp(5)))
        for _, b in self.buttons:
            gl.add_widget(b)
        layout.add_widget(gl)
        self.app.gui.add_widget(self)


    def choose(self, method, *args):
        if method != self.combine_method:
            # self.app.gui.set('stretch', stretch)
            self.combine_method = method
            Component.get('Stacker').stack_changed()


    def reset(self):
        self.stack_cache = {}


    def combine(self, stk, orig_sub_map, filt='all', calibration=False):

        logger.trace(f'combining stack for filt {filt}')

        # if calibrating, use user-selected method, otherwise use mean for non-L channels
        if calibration or filt in ['L', 'all']:
            method = self.combine_method
        else:
            method = 'mean' 

        sub_map = {s.name: s for s in stk}
        sub_names = set(sub_map)

        # check if we already have this in the cache
        if filt in self.stack_cache:
            cached = self.stack_cache[filt]
            cached_subs = cached['sub_names']
            ncache = len(cached_subs)

            # we have exactly this set of subs in the cache
            if (cached['method'] == method) and (cached_subs == sub_names):
                return cached['stack']

            # new: if mean combination and diff in just one sub, we can combine quickly
            if method == 'mean':
                onemore = sub_names - cached_subs
                onefewer = cached_subs - sub_names
                if len(onemore) == 1 or len(onefewer) == 1:
                    if len(onemore) == 1:
                        c_op = 1
                        dsub = list(onemore)[0]
                    else:
                        c_op = -1
                        dsub = list(onefewer)[0]
                    if dsub not in orig_sub_map:
                        logger.error(f'sub to add/delete not in orig_sub_map {dsub}')
                        # drop thru to recombination
                    else:
                        stacked = (cached['stack'] * ncache + c_op * orig_sub_map[dsub].get_image()) / (ncache + c_op)
                        self.stack_cache[filt]['stack'] = stacked
                        self.stack_cache[filt]['sub_names'] = sub_names
                        return stacked

        # if not, we need to update
        stacked = combine_stack(stk, method=method)

        logger.trace('-- full stack recompute!')

        # cache results
        self.stack_cache[filt] = {
            'stack': stacked, 
            'method': method,
            'sub_names': sub_names
            }

        return stacked


def combine_stack(subs, method='mean'):
    stk = np.stack([s.get_image() for s in subs], axis=0)
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

