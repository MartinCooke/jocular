''' v0.5 simply apply hotpixel removal in each frame
    simplified from original bad pixel map
'''

import numpy as np
from scipy.ndimage import convolve

from kivy.app import App
from kivy.properties import BooleanProperty, NumericProperty
from loguru import logger

from jocular.component import Component
from jocular.settingsmanager import Settings

class BadPixelMap(Component, Settings):

    apply_BPM = BooleanProperty(True)
    sigmas = NumericProperty(5)

    tab_name = 'Bad pixel map'
    configurables = [
        ('apply_BPM', {'name': 'remove hot pixels?', 'switch': '',
            'help': 'Switching this off can help diagnose tracking issues'}),
        ('sigmas', {'name': 'outlier rejection threshold', 'float': (1, 6, 1),
            'help': 'reject any pixel if this many sigmas from mean of 8-neighbourhood (factory: 5)',
            'fmt': '{:.0f} sigmas'})
        ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()

    def remove_hotpix(self, im, apply_BPM=False):
        ''' Called by Stacker, in which case whether we apply or not is determined
            by BPM settings, and by calibrator, in which apply_BPM will
            be set to true
        '''
        if self.apply_BPM or apply_BPM:
            hotpix = self.find_hot_pixels(im)
            logger.trace('removing {:} hot pixels'.format(len(hotpix)))
            return self.do_bpm(im, hotpix)
        else:
            return im

    def find_hot_pixels(self, im):
        '''Return hot pixel candidates.
        Look for non-edge pixels whose intensity is significantly greater
        than their neighbours. Approach is conservative in order to
        find all hot pixels, since for EAA the only adverse effect is to 
        replace a few non-hot pixels by their median. Returns a set of (row, col) 
        coordinates.

        10ms for Lodestar, 50ms for ASI 290MM
        ''' 
                
        # set min to zero
        im_norm = im - np.min(im)

        # divide im by local sum in 3x3 region
        im2 = im_norm / convolve(im_norm, np.ones((3, 3)), mode='constant')

        # Define hot pix as more than 'sigmas' SD from mean
        hp_cands = (im2 > np.mean(im2) + self.sigmas * np.std(im2))

        # set boundaries to zero
        hp_cands[0, :] = 0
        hp_cands[-1, :] = 0
        hp_cands[:, 0] = 0
        hp_cands[:, -1] = 0

        # coordinates of hot pixels as 2 x N array
        hps = np.where(hp_cands>0)

        return {(r, c) for r, c in zip(hps[0], hps[1])}

    def do_bpm(self, im, bpm):
        # Replace each pixel in bad pixel map by median of neighbours
        for r, c in bpm:
            im[r, c] = np.median(im[r-1:r+2, c-1:c+2].ravel())
        return im
 
