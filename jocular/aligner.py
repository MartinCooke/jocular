''' Star extraction, centroid estimation and alignment.
'''

import warnings
import numpy as np

from scipy import signal
from skimage.measure import ransac
from skimage.transform import EuclideanTransform, matrix_transform, warp
from skimage.feature import blob_dog

from kivy.properties import ConfigParserProperty
from kivy.logger import Logger

from jocular.component import Component
from jocular.gradient import estimate_background, estimate_gradient


class Aligner(Component):

    do_align = ConfigParserProperty(1, 'Aligner', 'do_align', 'app', val_type=int)
    smooth_edges = ConfigParserProperty(1, 'Aligner', 'smooth_edges', 'app', val_type=int)
    ideal_star_count = ConfigParserProperty(30, 'Aligner', 'ideal_star_count', 'app', val_type=int)

    def __init__(self):
        super().__init__()
        self.min_sigma = 3
        self.max_sigma = 5
        self.min_stars = 5
        self.centroid_radius = 8
        r = self.centroid_radius
        patch_size = 2 * r + 1
        self.grid_x, self.grid_y = np.meshgrid(np.arange(patch_size), np.arange(patch_size))
        self.mask = np.sqrt((r - self.grid_x)**2 + (r - self.grid_y)**2) <= r
        self.star_intensity = None

    def on_new_object(self):
        self.reset()

    def reset(self):
        self.keystars = None
        self.warp_model = None
        self.align_count = 0
        self.starcounts = []
        self.info('reset')

    def update_status(self):
        sc = np.array(self.starcounts)
        self.info('{:}/{:} | stars {:}-{:}, mu:{:3.0f}'.format(
            self.align_count, len(sc), np.min(sc), np.max(sc), np.mean(sc)))
    
    def align(self, sub, centroids):
        # Align sub to current keystars, updating its status.
        
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

        # do we have enough matched stars?
        if len(matched_stars) < self.min_stars:
            sub.status = 'nalign'
        else:            

            # apply RANSAC to find which matching pairs best fitting Euclidean model
            # can throw a warning in cases where no inliers (bug surely) which we ignore
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                warp_model, inliers = ransac(
                    (np.array(self.keystars[:nstars]), matched_stars),
                    EuclideanTransform, 4, .5, max_trials=100)

            # managed to align
            if (inliers is not None) and (sum(inliers) >= min_inliers):
                # update warp model
                self.warp_model = warp_model

                # new in v0.4: can sometimes get artefacts that screw up platesolving
                # this is one way to handle them, but it isn't to all tastes and is slow
                # so allow use not to do it

                if self.smooth_edges:
                    # apply warp, ensuring values outside the range are filled with 
                    # a known value to mitigate edge effects on platesolving
                    sub.image = warp(sub.image, self.warp_model, order=3, 
                        preserve_range=True, mode='constant', cval=0.0001)

                    # identify unwarped points
                    unwarped = sub.image < .001

                    # grow these points inwards by convolution with block
                    # 76 ms to convolve is quite slow
                    unwarped = signal.convolve2d(unwarped, np.ones((9, 9)), mode='same')

                    # find positive points, but none away from boundary
                    pos = unwarped > 0
                    npix = 100
                    pos[npix:-npix, npix:-npix] = 0

                    # fill these with noise: ~ 14ms
                    bg_mu, bg_std = estimate_background(sub.image)
                    grad = estimate_gradient(sub.image)
                    # 10 ms
                    noi = np.random.normal(bg_mu, bg_std, sub.image.shape) * grad / np.mean(grad)
                    sub.image[pos] = noi[pos]

                else:
                    sub.image = warp(sub.image, self.warp_model, order=3, preserve_range=True)


                self.align_count += 1

                # change to select if it was nalign before; if reject before, leave it as reject
                if sub.status == 'nalign':
                    sub.status = 'select'
            else:
                sub.status = 'nalign'

        self.update_status()


    def extract_stars(self, im):
        # Extracts star coordinates. Return array of x, y coordinates.

        # if this is the first sub in the stack (perhaps after shuffle), find best intensity threshold
        if self.keystars is None:
            self.star_intensity = self.find_intensity_threshold(im)

        # extract using this threshold
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            stars = blob_dog(im, 
                min_sigma=self.min_sigma, 
                max_sigma=self.max_sigma, 
                threshold=self.star_intensity, 
                overlap=0)[:, [1, 0]]

        # new for v2: order stars by decreasing intensity
        intens = [im[int(y), int(x)] for x, y in stars]
        return np.array(stars)[[i for (v, i) in sorted((v, i) for (i, v) in enumerate(intens))][::-1]]


    def find_intensity_threshold(self, im):
        # Binary search to find intensity threshold for star extraction producing ideal star count 

        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            # image_cube = compute_image_cube(im, min_sigma=self.min_sigma, max_sigma=self.max_sigma)
            t0 , _ = estimate_background(im)
            # sometimes can fail due to background estimate being zero or too large
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

                # this approach appears to cause problems on Windows, so going back to the slower approach
                # nstars = len(peak_local_max(image_cube, threshold_abs=est, footprint=np.ones((3,) * 3),
                #     threshold_rel=0.0, exclude_border=(0,) * 3))

                nstars = len(blob_dog(im, 
                    min_sigma=self.min_sigma, 
                    max_sigma=self.max_sigma, 
                    threshold=est, 
                    overlap=0)[:, [1, 0]])

                # Logger.debug('Aligner: iteration {:} nstars (slow method) {:}'.format(its, nstars))
                # stop when within crit percent of required
                if abs(nstars - self.ideal_star_count) / self.ideal_star_count < crit:
                    break
                if nstars < self.ideal_star_count:
                    hi = est
                else:
                    lo = est
                est = (hi + lo) / 2

        Logger.info('Aligner: bkgd {:6.4f} threshold {:6.4f} after {:} iterations'.format(t0, est, its))
        return est


    def compute_centroids(self, im, stars):
        # extract info from all candidate stars and return centroids
 
        r = self.centroid_radius
        rows, cols = im.shape
        star_data = np.zeros((len(stars), 2))
        ptr = 0
        for x, y in stars:
            x, y = int(x), int(y)
            if (x >= r) and (y >= r) and (x < (cols - r)) and (y < (rows - r)):
                imfrag = im[(y - r):(y + r + 1), (x - r):(x + r + 1)].copy()
                cx, cy = self.compute_centroid(imfrag)
                if cx > 0:
                    star_data[ptr, :] = [cx + x - r, cy + y - r]
                    ptr += 1

        return star_data[:ptr, :]

    def compute_centroid(self, imfrag):
        # slightly more sophisticated approach
        
        # mean intensity within masked circle
        mean_intensity = np.mean(imfrag[self.mask])
        
        # star pixels are in mask and above mean intensity
        candidates = self.mask & (imfrag > mean_intensity)
        
        if candidates.any():
            # estimate background and subtract from image
            mean_background = np.mean(imfrag[np.logical_not(candidates)])
            imfrag_sub = candidates * (imfrag - mean_background)       
            wim = np.sum(imfrag_sub)
            cx = np.sum(self.grid_x * imfrag_sub) / wim
            cy = np.sum(self.grid_y * imfrag_sub) / wim
            return cx, cy

        return -1, -1

    def process(self, sub):

        if not self.do_align:
            return

        # extract stars & compute centroids before aligning, if possible
        im = sub.get_image()
        raw_stars = self.extract_stars(im)
        centroids = self.compute_centroids(im, raw_stars)
        self.starcounts += [len(centroids)]

        if len(centroids) == 0:
            # no stars so don't do anything
            pass
        elif self.keystars is None:
            # first sub with stars so set keystars
            self.keystars = centroids
            self.align_count = 1
        else:
            self.align(sub, centroids)
            
