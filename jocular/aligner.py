''' Star extraction, centroid estimation and alignment.
'''

import warnings
import numpy as np

from skimage.measure import ransac
from skimage.transform import EuclideanTransform, matrix_transform, warp
from skimage.feature import blob_dog

from kivy.properties import BooleanProperty, NumericProperty
from loguru import logger

from jocular.component import Component
from jocular.settingsmanager import Settings
from jocular.gradient import estimate_background

def star_centroids(im, stars, r=8):
    ''' Compute accurate locations for stars based on star pixel coords
        given in stars. Takes c 2-10 ms for a Lodestar image depending on star count
    '''

    grid_x, grid_y = np.meshgrid(np.arange(2 * r + 1), np.arange(2 * r + 1))
    mask = np.sqrt((r - grid_x)**2 + (r - grid_y)**2) <= r

    rows, cols = im.shape
    star_data = np.zeros((len(stars), 3))
    ptr = 0
    for x, y in stars:
        x, y = int(x), int(y)
        if (x >= r) and (y >= r) and (x < (cols - r)) and (y < (rows - r)):
            imfrag = im[(y - r):(y + r + 1), (x - r):(x + r + 1)].copy()
            
            # mean intensity within masked circle
            mean_intensity = np.mean(imfrag[mask])
    
            # star pixels are in mask and above mean intensity
            candidates = mask & (imfrag > mean_intensity)
    
            if candidates.any():
                # estimate background and subtract from image
                mean_background = np.mean(imfrag[np.logical_not(candidates)])
                imfrag_sub = candidates * (imfrag - mean_background)       
                wim = np.sum(imfrag_sub)
                cx = np.sum(grid_x * imfrag_sub) / wim
                cy = np.sum(grid_y * imfrag_sub) / wim
                star_data[ptr, :] = [cx + x - r, cy + y - r, np.mean(imfrag_sub)]
                ptr += 1                    
    
    return star_data[:ptr, :]


class Aligner(Component, Settings):

    do_align = BooleanProperty(True)
    smooth_edges = BooleanProperty(False)
    ideal_star_count = NumericProperty(30)
    min_sigma = NumericProperty(3)
    max_sigma = NumericProperty(5)

    configurables = [
        ('do_align', {'name': 'align?', 'switch': '',
            'help': 'Switching align off can help diagnose tracking issues'}),
        ('ideal_star_count', {'name': 'ideal number of stars', 'float': (5, 50, 1),
            'help': 'Find an appropriate threshold to detect this many stars on the first sub',
            'fmt': '{:.0f} stars'}),
        # ('min_sigma', {
        #     'name': 'min sigma', 'float': (1, 10, 1),
        #     'fmt': '{:.0f}',
        #     'help': 'Used in DoG blob extraction stage (factory: 3)'}),
        # ('max_sigma', {
        #     'name': 'max sigma', 'float': (1, 10, 1),
        #     'fmt': '{:.0f}',
        #     'help': 'Used in DoG blob extraction stage (factory: 5)'})
        ]

    def __init__(self):
        super().__init__()
        self.min_stars = 5
        self.star_intensity = None

    def on_new_object(self):
        self.reset()

    def reset(self):
        self.star_intensity = None
        self.keystars = None
        self.mags = None
        self.warp_model = None
        self.align_count = 0
        self.starcounts = []
        self.info('reset')
    
    @logger.catch()
    def align(self, sub, centroids):
        # Align sub to current keystars, updating its status.
        
        min_inliers = 4

        # choose warp model to project existing keystars so they lie closer to centroids (in theory)
        keys = self.keystars
        if self.warp_model:
            keys = matrix_transform(self.keystars, self.warp_model.params)
        else:
            keys = self.keystars

        # find closest matching star to each transformed keystar
        nstars = min(len(keys), len(centroids))

        matched_stars = np.zeros((nstars, 2))
        for i, (x1, y1) in enumerate(keys):
            if i < nstars:
                matched_stars[i, :] = centroids[np.argmin([(x1 - x2) ** 2 + (y1 - y2) ** 2 for x2, y2 in centroids])]

        # do we have enough matched stars?
        if len(matched_stars) < self.min_stars:
            sub.status = 'nalign'
        else:            

            # apply RANSAC to find which matching pairs best fitting Euclidean model
            # can throw a warning in cases where no inliers (bug surely) which we ignore
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                warp_model, inliers = ransac(
                    (np.array(self.keystars[:nstars]), matched_stars),
                    EuclideanTransform, 4, .5, max_trials=100)

            # managed to align
            if (inliers is not None) and (sum(inliers) >= min_inliers):
                # update warp model
                self.warp_model = warp_model
                sub.image = warp(sub.image, self.warp_model, order=3, preserve_range=True)
                self.align_count += 1

                # change to select if it was nalign before; if reject before, leave it as reject
                if sub.status == 'nalign':
                    sub.status = 'select'
            else:
                sub.status = 'nalign'

            # return inverse transform of centroids (for platesolver)
            if self.warp_model:
                return self.warp_model.inverse(centroids)
            return None



    def extract_stars(self, im):
        ''' Extracts star coordinates. Return array of x, y coordinates.
        '''

        # if this is the first sub in the stack (perhaps after shuffle), 
        # find best intensity threshold
        if self.keystars is None:
            self.star_intensity = self.find_intensity_threshold(im)

        # extract using this threshold
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            stars = blob_dog(im, 
                min_sigma=self.min_sigma, 
                max_sigma=self.max_sigma, 
                threshold=self.star_intensity, 
                overlap=0)[:, [1, 0]]

        # new for v2: order stars by decreasing intensity
        # better to do this using mags after computing centroids (to do)
        intens = [im[int(y), int(x)] for x, y in stars]
        return np.array(stars)[[i for (v, i) in sorted((v, i) for (i, v) in enumerate(intens))][::-1]]


    def get_intensity_threshold(self):
        ''' used by platesolver to find current star intensity threshold
        '''
        if self.star_intensity is not None:
            return self.star_intensity
        return .001

    def find_intensity_threshold(self, im):
        ''' Binary search to find intensity threshold for star extraction 
            producing ideal star count 
        '''

        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            t0 , _ = estimate_background(im)
            # sometimes can fail due to background estimate being zero or too large
            if t0 < .001:
                t0 = .1
            if t0 > .5:
                t0 = .45
            crit = 20 / 100  # stop when within 20%
            lo, hi = 0, 1
            est = t0
            its = 0
            maxits = 8
            while True and (its < maxits):
                its += 1
                nstars = len(blob_dog(im, 
                    min_sigma=self.min_sigma, 
                    max_sigma=self.max_sigma, 
                    threshold=est, 
                    overlap=0)[:, [1, 0]])

                # stop when within crit percent of required
                if abs(nstars - self.ideal_star_count) / self.ideal_star_count < crit:
                    break
                if nstars < self.ideal_star_count:
                    hi = est
                else:
                    lo = est
                est = (hi + lo) / 2

        logger.info('bkgd {:6.4f} threshold {:6.4f} after {:} iterations'.format(t0, est, its))
        return est

    def process(self, sub):

        if not self.do_align:
            return

        # extract stars & compute centroids before aligning, if possible
        #logger.trace('. get image')
        im = sub.get_image()
        #logger.trace('. extract stars')
        raw_stars = self.extract_stars(im)
        #logger.trace('. centroids')
        centroids = star_centroids(im, raw_stars)

        # store centroids for later platesolving
        sub.centroids = centroids
        self.starcounts += [len(centroids)]

        if len(centroids) == 0:
            sub.status = 'nalign'
        elif self.keystars is None:
            # first sub with stars so save keystars & mags (latter for platesolving)
            self.keystars = centroids[:, :2]
            self.mags = centroids[:, 2]
            self.align_count = 1
        else:
            #logger.trace('. align')
            warped = self.align(sub, centroids[:, :2])
            if warped is not None:
                sub.centroids[:, :2] = warped
            # self.align(sub, centroids[:, :2])
            #logger.trace('. aligned finish')

        sc = np.array(self.starcounts)
        self.info('{:}/{:} frames | {:}-{:} stars'.format(
            self.align_count, len(sc), np.min(sc), np.max(sc)))
            
