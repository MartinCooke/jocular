''' Alignment. 
    (Star extraction and property estimation now done in stars.py)
'''

import warnings
import numpy as np

from skimage.measure import ransac
from skimage.transform import EuclideanTransform, matrix_transform, warp

from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from loguru import logger

from jocular.component import Component
from jocular.settingsmanager import Settings
from jocular.stars import star_extraction, best_threshold

from photutils.detection import DAOStarFinder
from astropy.stats import mad_std
from photutils.aperture import aperture_photometry, CircularAperture, ApertureStats


class Aligner(Component, Settings):

    do_align = BooleanProperty(True)
    use_photutils = BooleanProperty(True)
    fwhm_method = StringProperty('Moffat')
    ideal_star_count = NumericProperty(30)
    star_sigmas = NumericProperty(3)
    photutils_fwhm = NumericProperty(4)
    downsample = StringProperty('no')

    configurables = [
        ('do_align', {'name': 'align?', 'switch': '',
            'help': 'Switching align off can help diagnose tracking issues'}),
        ('use_photutils', {'name': 'use photutils?', 'switch': '',
            'help': 'use photutils for centroiding instead of home-grown method'}),
        ('star_sigmas', {'name': 'sigmas above background', 'float': (2, 10, 1),
            'help': '3 is good, 5 is faster (used for photutils only)',
            'fmt': '{:.0f} sigmas'}),
        ('photutils_fwhm', {'name': 'fwhm (in pixels) to use in star extraction', 'float': (2, 10, 1),
            'help': '4 is good for Lodestar',
            'fmt': '{:.0f} pixels'}),
        ('fwhm_method', {
            'name': 'FWHM method', 
            'options': ['count', 'Moffat', 'Gaussian'],
            'help': 'count is fastest and most robust, Moffat and Gaussian are traditional/slower'}),
        ('ideal_star_count', {'name': 'ideal number of stars', 'float': (5, 50, 1),
            'help': 'Find an appropriate threshold to detect this many stars on the first sub',
            'fmt': '{:.0f} stars'}),
        ('downsample', {
            'name': 'extract stars using image', 
            'options': ['binned 1x1', 'binned 2x2', 'binned 3x3', 'binned 4x4'],
            'help': 'for large images, much faster to extract using binning'})
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
    def do_alignment(self, sub, centroids):
        # align sub to current keystars, updating its status.
        
        logger.trace('. align')

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

            logger.trace('... done alignment')

            # return inverse transform of centroids (for platesolver)
            if self.warp_model:
                return self.warp_model.inverse(centroids)
            return None



    def extract_stars_photutils(self, im):
        ''' extract stars and magnitudes via photutils
            80ms for Lodestar-sized image, including read for threshold 3 * sigma
            64ms for 5 * sigma, 47ms for thresh 10 * sigma
            50ms if we only keep a few
        '''

        logger.trace('starting extract stars photutils')

        # subtract rough estimate of background
        imc = im.copy()
        imc = imc - np.median(imc)
        # im -= np.median(im)
        # find median absolute deviation
        bkg_sigma = mad_std(imc)
        # detect stars using DAOFIND, keeping 'keep' brightest
        daofind = DAOStarFinder(
            fwhm=self.photutils_fwhm, 
            threshold=self.star_sigmas * bkg_sigma, 
            brightest=self.ideal_star_count)
        sources = daofind(imc)
        positions = np.transpose((sources['xcentroid'], sources['ycentroid']))
        logger.trace('   done centroids')

        # this is a temporary approach: r = aperture radius should really be
        # estimated based on FWHM, which in turn is based on building a 
        # PSF model from brighter stars... we are just doing this to
        # provide a quick FWHM estimate, but it is rather circular...

        apertures = CircularAperture(positions, r=3.)
        aperstats = ApertureStats(imc, apertures)
        logger.trace('   done aperture stats')

        # when we do aperture phot, use this
        # phot_table = aperture_photometry(imc, apertures)
        return np.transpose((sources['xcentroid'], sources['ycentroid'], sources['flux'], aperstats.fwhm ))


    def extract_stars(self, im):
        ''' Extracts star coordinates, flux and FWHM estimates.
        '''

        logger.trace('. extract stars')
        dfac = int(self.downsample[-1])
        if self.keystars is None:
            # find best intensity threshold
            self.star_intensity, nstars, nits, converged = best_threshold(
                im, 
                target_stars=self.ideal_star_count, 
                downsample=dfac)
            logger.info('threshold {:6.4f} produces {:} stars after {:} iterations (converged: {:})'.format(
                self.star_intensity, nstars, nits, converged))

        stardata = star_extraction(
            im, 
            threshold=self.star_intensity, 
            downsample=dfac,
            fwhm_method=self.fwhm_method)
        nstars, _ = stardata.shape
        logger.info('... extracted {:} stars'.format(nstars))
        return stardata


    def extract_stars_for_platesolver(self, im):
        ''' Potentially extract stars using different criteria from those required
            for alignment; for now we'll use same criteria
            Scope for optimisation e.g. if im is a sub that we have already processed,
            pick up centroids already done

        BUG: if we use photutils for star extraction we end up with no star_intensity set


        '''
        dfac = int(self.downsample[-1])
        if self.star_intensity is None:
            # find best threshold; we'll use same ideal star count
            self.star_intensity, nstars, nits, converged = best_threshold(
                im, 
                target_stars=self.ideal_star_count, 
                downsample=dfac)
            logger.info('threshold {:6.4f} produces {:} stars after {:} iterations (converged: {:})'.format(
                self.star_intensity, nstars, nits, converged))
        return star_extraction(
            im, 
            threshold=self.star_intensity, 
            downsample=dfac)


    def align(self, sub):
        ''' called by Stacker to extract stars and align sub; hot pixel removal will
            already have been applied before this method is called
        '''

        if not self.do_align:
            return

        # extract stars & compute centroids before aligning
        im = sub.get_image()

        # star data is N x 4 array of cx, cy, flux and fwhm organised

        if self.use_photutils:
            stardata = self.extract_stars_photutils(im)
        else:
            stardata = self.extract_stars(im)

        nstars, _ = stardata.shape
        sub.centroids = stardata[:, :2]
        sub.flux = stardata[:, 2]
        mags = stardata[:, 2]
        fwhm = stardata[:, 3]

        # centroids = star_centroids(im, raw_stars, compute_FWHM=self.compute_FWHM, FWHM_method=self.FWHM_method)
        # sub.fwhm = np.median(centroids[:, 3])

        # I don't think I need to store centroids any more

        # store centroids for later platesolving
        #sub.centroids = stardata[:, :2]

        #sub.flux = np.zeros(nstars)

        # sub.flux = stardata[:, 2]
        self.starcounts += [nstars]

        if nstars == 0:
            sub.status = 'nalign'
            sub.fwhm = 0
        else:
            sub.fwhm = np.median(fwhm) # stardata[:, 3])
            print(sub.fwhm)
            if self.keystars is None:
                # first sub with stars so save keystars & mags (latter for platesolving)
                self.keystars = sub.centroids # stardata[:, :2]
                self.mags = mags # stardata[:, 2]
                self.align_count = 1
            else:
                warped = self.do_alignment(sub, sub.centroids) # stardata[:, :2])
                if warped is not None:
                    sub.centroids = warped
                    # sub.centroids[:, :2] = warped
                logger.trace('. aligned finish')

        sc = np.array(self.starcounts)
        self.info('{:}/{:} frames | {:}-{:} stars'.format(
            self.align_count, len(sc), np.min(sc), np.max(sc)))
            
