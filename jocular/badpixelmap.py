''' Maintains and applies bad pixel map that persists between sessions
    new in V0.3: creates a new BPM for each sensor shape encountered to avoid applying
    BPM to the wrong sensor and to enable multiple sensors to be used 
'''

import os
import numpy as np
from scipy.ndimage import convolve

from kivy.app import App
from kivy.properties import ConfigParserProperty
from kivy.logger import Logger

from jocular.component import Component

class BadPixelMap(Component):

    apply_BPM = ConfigParserProperty(1, 'BadPixelMap', 'apply_BPM', 'app', val_type=int)
    bpm_frames = ConfigParserProperty(3, 'BadPixelMap', 'bpm_frames', 'app', val_type=int)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.bpm = None

    def load_BPM(self, shape):
        # load BPM for this shape, creating if necessary

        self.bplist = []  # acts as a circular buffer of BPs from recent frames
        self.frame_count = 0
        self.bpm = None
        self.bpm_shape = shape
        self.bpm_name = 'BPM_{:}x{:}.npy'.format(shape[0], shape[1])
        path = os.path.join(self.app.get_path('calibration'), self.bpm_name)
        if os.path.exists(path):
            bpm = np.load(path)
            self.update_bpm({(x, y) for x, y in zip(bpm[0], bpm[1])})
            self.info('loaded')
            Logger.info('BPM: loaded map with {:} members'.format(len(bpm[0])))
        else:
            self.info('new map')
            Logger.info('BPM: new map')

    def on_close(self):
        self.save_BPM()

    def process_bpm(self, sub):

        if not self.apply_BPM:
            return

        # we don't have one yet, so create one of correct shape
        if self.bpm is None:
            self.load_BPM(sub.shape)

        # we have one, but it is the wrong shape (ie different sensor) so save & load
        elif self.bpm_shape != sub.shape:
            self.save_BPM()
            self.load_BPM(sub.shape)

        im = sub.get_image()
        badpix = self.find_hot_pixels(im)

        # only update map if it is a light sub
        if sub.sub_type == 'light':
            self.update_bpm(badpix)
            if self.bpm is not None:
                self.info('{:} pix, {:} in map'.format(len(badpix), len(self.bpm)))
        self.do_bpm(im, self.bpm)


    def find_hot_pixels(self, im):
        '''Return hot pixel candidates.
        We look for non-edge pixels whose intensity is significantly greater
        than their neighbours. Approach is conservative in order to
        find all hot pixels, since (a) we remove any imposters by comparing
        across most recent 'bpm_frames' when building the hot pixel map; and (b) in the
        EAA use case the only adverse effect is to replace a few non-hot pixels
        by their median. Returns a set of (row, col) coordinates
        ''' 
                
        # set min to zero
        im_norm = im - np.min(im)

        # divide im by local sum in 3x3 region
        im2 = im_norm / convolve(im_norm, np.ones((3, 3)), mode='constant')

        # Define hot pix as more than 5 SD from mean
        hp_cands = (im2 > np.mean(im2) + 5*np.std(im2))

        # set boundaries to zero
        hp_cands[0, :] = 0
        hp_cands[-1, :] = 0
        hp_cands[:, 0] = 0
        hp_cands[:, -1] = 0

        # coordinates of hot pixels as 2 x N array
        hps = np.where(hp_cands>0)

        # return hot pixel coordinates as a set of row-col pairs
        return {(r, c) for r, c in zip(hps[0], hps[1])}

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

    def save_BPM(self):
        # Save as npy file
        if self.bpm is None:
            return
        bpm = np.array([[x for x, y in self.bpm], [y for x, y in self.bpm]])
        path = os.path.join(self.app.get_path('calibration'), self.bpm_name)
        np.save(path, bpm)
        Logger.info('BPM: saved map with {:} members'.format(len(bpm[0])))
