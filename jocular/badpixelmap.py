""" Multi-frame bad pixel map
"""

import numpy as np
from scipy.ndimage import convolve
from loguru import logger

from kivy.app import App
from kivy.properties import BooleanProperty, NumericProperty

from jocular.component import Component
from jocular.settingsmanager import JSettings


class BadPixelMap(Component, JSettings):

    apply_BPM = BooleanProperty(True)
    sigmas = NumericProperty(5)
    bpm_frames = NumericProperty(3)

    tab_name = "Bad pixel map"
    configurables = [
        (
            "apply_BPM",
            {
                "name": "remove hot pixels?",
                "switch": "",
                "help": "Switching this off can help diagnose tracking issues",
            },
        ),
        (
            'bpm_frames', {
                'name': 'successive subs used to create BPM', 'float': (1, 10, 1),
                'help': 'Only treat as a bad pixel if it occurs in this many subs in succession',
                'fmt': '{:.0f} subs'
            },
        ),
        (
            "sigmas",
            {
                "name": "outlier rejection threshold",
                "float": (1, 10, 1),
                "help": "reject any pixel if this many sigmas from mean of 8-neighbourhood (factory: 5)",
                "fmt": "{:.0f} sigmas",
            },
        ),
    ]


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()


    def on_new_object(self, *args):
        self.bpm = None
        self.bplist = []
        self.frame_count = 0


    def process_bpm(self, sub):
        ''' Called by Stacker
        '''

        if not self.apply_BPM:
            return

        im = sub.get_image()
        badpix = self.find_hot_pixels(im)

        # only update map if it is a light sub
        if sub.sub_type == 'light':
            self.update_bpm(badpix)
            if self.bpm is not None:
                logger.debug(f'{len(badpix)} pix, {len(self.bpm)} in map')
        self.do_bpm(im, self.bpm)


    def find_hot_pixels(self, im):
        """Return hot pixel candidates.
        Look for non-edge pixels whose intensity is significantly greater
        than their neighbours. Approach is conservative in order to
        find all hot pixels, since for EAA the only adverse effect is to
        replace a few non-hot pixels by their median. Returns a set of (row, col)
        coordinates.

        10ms for Lodestar, 50ms for ASI 290MM
        """

        # set min to zero
        im_norm = im - np.min(im)

        # divide im by local sum in 3x3 region
        im2 = im_norm / convolve(im_norm, np.ones((3, 3)), mode="constant")

        # Define hot pix as more than 'sigmas' SD from mean
        hp_cands = im2 > np.mean(im2) + self.sigmas * np.std(im2)

        # set boundaries to zero
        hp_cands[0, :] = 0
        hp_cands[-1, :] = 0
        hp_cands[:, 0] = 0
        hp_cands[:, -1] = 0

        # coordinates of hot pixels as 2 x N array
        hps = np.where(hp_cands > 0)

        return set(zip(hps[0], hps[1]))
        # return {(r, c) for r, c in zip(hps[0], hps[1])}


    def do_bpm(self, im, bpm=None):
        # Replace each pixel in bad pixel map by median of neighbours
        if bpm is None:
            bpm = self.bpm
        if bpm is not None:
            for r, c in bpm:
                im[r, c] = np.median(im[r-1:r+2, c-1:c+2].ravel())
        return im
 

    def compute_bpm(self):
        # Use intersection of bad pixels from previous N frames to compute bad pixel map
        if self.bplist:
            self.bpm = self.bplist[0]
            for bpl in self.bplist[1:]:
                self.bpm = self.bpm.intersection(bpl)


    def update_bpm(self, bpm):
        # Add new BPM set to BPM, recomputing BPM
        if len(self.bplist) == self.bpm_frames:
            self.bplist[self.frame_count % self.bpm_frames] = bpm
        else:
            self.bplist.append(bpm)
        self.frame_count += 1
        self.compute_bpm()

