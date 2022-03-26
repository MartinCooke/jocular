''' Local plate-solver. 
'''


import numpy as np
from scipy.spatial.distance import cdist
from skimage.feature import blob_dog
from skimage.transform import estimate_transform
from loguru import logger

from kivy.app import App
from kivy.properties import BooleanProperty, NumericProperty

from jocular.utils import toast
from jocular.component import Component
from jocular.settingsmanager import Settings
from jocular.RA_and_Dec import RA, Dec
from jocular.uranography import (
    to360,
    make_tile,
    Eq2Cart,
    Cart2Eq,
    spherical_distance
)

from jocular.aligner import star_centroids

def select_stars_in_FOV(ras, decs, ra0, dec0, fov):
    # filter ras, decs, mags to just return those in given region
    tile = make_tile(ra0, dec0, fov=fov)
    min_ra, max_ra = tile['min_ra'], tile['max_ra']
    min_dec, max_dec = tile['min_dec'], tile['max_dec']
    if min_ra < max_ra:
        locs = (ras >= min_ra) & (ras < max_ra) & (decs >= min_dec) & (decs < max_dec)
    else:
        locs = ((ras >= min_ra) | (ras < max_ra)) & (decs >= min_dec) & (decs < max_dec)
    return locs


def fastmatch(
    ref=None,
    im=None,
    mag_range=5,
    min_matches=8,
    proximity=0.05,
    match_arcsec=15,
    first_match=True,
):
    ''' find possible match of image points im in star database;
    both db and im are ordered by magnitude; works by choosing a pair
    of image points, rotating and scaling so they sit at (0, 0) and (1, 0);
    then searching across pairs of image points at a similar separation, applying
    similar rotation/scaling, then counting matches; if first_match is true, return
    first match that contains more than min_matches stars, otherwise return
    the match that contains the most correspondences.
    '''

    max_matches = 0
    best_matches = None
    n_im, n_ref = len(im), len(ref)
    for i1 in range(0, n_im):
        # normalise image based on star index i1
        im1 = im - im[i1, :]
        for i2 in [i for i in range(i1 + 1, min(n_im, i1 + mag_range)) if i != i1]:
            # rotate and scale so i2 is at (1, 0)
            cos, sin = im1[i2, 0], -im1[i2, 1]
            d = cos ** 2 + sin ** 2
            im2 = np.dot(im1, np.array([[cos, -sin], [sin, cos]]).T) / d
            # match threshold takes into account scaling by d
            mt = (match_arcsec / (3600 * (d ** 0.5))) ** 2.0  # we match squared dist
            min_x, min_y = np.min(im2, axis=0) - mt
            max_x, max_y = np.max(im2, axis=0) + mt
            for r1 in range(0, n_ref):
                ref1 = ref - ref[r1, :]
                for r2 in [
                    r for r in range(r1 + 1, min(n_ref, r1 + mag_range)) if r != r1
                ]:
                    cos, sin = ref1[r2, 0], -ref1[r2, 1]
                    d2 = cos ** 2 + sin ** 2
                    if np.abs(d - d2) < proximity:
                        ref2 = np.dot(ref1, np.array([[cos, -sin], [sin, cos]]).T) / d2
                        mind_x, mind_y = np.min(ref2, axis=0)
                        maxd_x, maxd_y = np.max(ref2, axis=0)
                        # don't check if anything outside range
                        if (
                            max_x < maxd_x
                            and max_y < maxd_y
                            and min_x > mind_x
                            and min_y > mind_y
                        ):
                            dists = cdist(im2, ref2, metric='sqeuclidean')
                            matches = [
                                (i, j)
                                for i, j in enumerate(np.argmin(dists, axis=1))
                                if dists[i, j] < mt
                            ]
                            n_matches = len(matches)
                            if n_matches >= max(min_matches, max_matches):
                                if first_match:
                                    return matches
                                max_matches = n_matches
                                best_matches = matches
                                # return matches
    return best_matches


class PlateSolver(Component, Settings):

    match_arcsec = NumericProperty(15)
    focal_length = NumericProperty(800)
    pixel_height = NumericProperty(8.4)
    n_stars_in_image = NumericProperty(30)
    min_sigma = NumericProperty(3)
    max_sigma = NumericProperty(5)
    star_thresh = NumericProperty(.001)
    min_matches = NumericProperty(10)
    mag_range = NumericProperty(5)    # don't allow user to set this
    first_match = BooleanProperty(False)
    binning = NumericProperty(1)
    #star_source = StringProperty('current sub')

    tab_name = 'Plate-solving'

    configurables = [
        ('focal_length', {
            'name': 'focal length', 'float': (50, 2400, 10),
            'fmt': '{:.0f} mm',
            'help': 'Focal length of scope (including reducers)'
            }),
        ('pixel_height', {
            'name': 'pixel height', 
            'double_slider_float': (1, 16),
            'fmt': '{:.2f} um',
            'help': 'Pixel height of sensor'
            }),
        ('binning', {
            'name': 'binning', 'float': (1, 4, 1),
            'fmt': '{:.0f}',
            'help': 'If binning, specify amount here (1=no binning)'
            }),
        ('n_stars_in_image', {
            'name': 'number of stars to extract', 'float': (5, 50, 1),
            'fmt': '{:.0f} stars',
            'help': 'Ideal number of stars to extract from image (factory: 30)'
            }),
        ('min_matches', {
            'name': 'minimum number of stars to match', 'float': (5, 30, 1),
            'fmt': '{:.0f} stars',
            'help': 'Must match at least this many stars in stellar database (factory: 10)'
            }),
        ('match_arcsec', {
            'name': 'star proximity for matching', 'float': (5, 25, 1),
            'fmt': '{:.0f} arcsec',
            'help': 'How close reference and image stars must be to match, in arcsec (factory: 15)'
            }),
        ('first_match', {
            'name': 'return after finding', 
            'boolean': {'first match': True, 'best match': False},
            'help': 'tradeoff speed and accuracy'
            }),
        # ('min_sigma', {
        #     'name': 'min sigma', 'float': (1, 5, 1),
        #     'fmt': '{:.0f}',
        #     'help': 'used in star extraction (factory: 3)'
        #     }),
        # ('max_sigma', {
        #     'name': 'max sigma', 'float': (1, 7, 1),
        #     'fmt': '{:.0f}',
        #     'help': 'used in star extraction (factory: 5)'
        #     })
        ('star_thresh', {
            'name': 'star threshold', 'float': (0, .005, .0001),
            'fmt': '{:.4f}',
            'help': 'used in star extraction (factory: .001); set to 0 to find this adaptively'
            })

        # ('star_source', {
        #     'name': 'get stars from', 
        #     'options': ['first sub', 'current sub', 'stack', 'displayed image'],
        #     })
        ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.can_solve = False
        self.cart2pix = None

    def on_new_object(self):
        self.cart2pix = None
        self.can_solve = Component.get('Catalogues').has_platesolving_db()
        self.info('available' if self.can_solve else 'no db')

    def solve(self):
        ''' Called when user clicks loc. Try to solve currently displayed image; 
            if that fails, try to solve first image (since occasionally image 
            artefacts due to field rotation prevent solution of stacked subs)
        '''

        if not self.can_solve:
            toast('Cannot solve: no platesolving database available')
            return

        self.ra0, self.dec0 = Component.get('DSO').current_object_coordinates()
        if self.ra0 is None:
            toast('Cannot solve: unknown DSO')
            self.info('unknown DSO')
            return

        # get current image
        im = Component.get('Stacker').get_current_displayed_image()
        if im is None:
            toast('Cannot solve: no current image')
            self.info('no current image')
            return

        # can't solve, so try solving first image in stack
        if not self._solve(im):
            logger.warning('failed to solve -- trying first sub')
            im = Component.get('Stacker').get_current_displayed_image(first_sub=True)
            if not self._solve(im):
                logger.warning('failed to solve first sub')
                # toast('Failed to solve: is image flipped correctly?')
                # self.info('failed (check LR/UD flips)')
                return

        Component.get('Annotator').annotate()


    def _solve(self, im):
        ''' Attempts to solve 'im'; returns True if successful
        '''

        if self.star_thresh < 1e-6:
            thresh = Component.get('Aligner').get_intensity_threshold()
        else:
            thresh = self.star_thresh

        logger.trace('using intensity threshold {:.5f}'.format(
            0 if thresh is None else thresh))

        # extract stars and their mags
        blobs = blob_dog(
            im, 
            min_sigma=self.min_sigma, 
            max_sigma=self.max_sigma, 
            threshold=thresh, 
            overlap=0)[:, [1, 0]]

        if len(blobs) < self.min_matches:
            msg = 'Not enough stars to platesolve ({:})'.format(len(blobs))
            toast(msg)
            self.info(msg)
            #logger.warning('Too few stars to platesolve ({:})'.format(len(x_im)))
            return False

        centroids = star_centroids(im, blobs)
        x = centroids[:, 0]
        y = centroids[:, 1]
        flux = centroids[:, 2]

        self.im_height, self.im_width = im.shape

        self.binned_pixel_height = Component.get('Stacker').get_pixel_height()
        # if we don't know pixel height, use user-supplied values
        if self.binned_pixel_height is None:
            self.binned_pixel_height = self.binning * self.pixel_height

        logger.trace('binned pixel height {:.1f}'.format(self.binned_pixel_height))

        degrees_per_pixel = (self.binned_pixel_height * 1e-6 / self.focal_length) * (206265 / 3.6)
        fov = self.im_height * degrees_per_pixel

        # convert flux to relative magnitude
        mags = -2.5 * np.log10(flux / np.max(flux))

        logger.debug('nstars = {:}; mag range {:.1f}'.format(len(x), np.max(mags)))

        # select N-brightest
        inds = np.argsort(mags)[: self.n_stars_in_image]
        x_im, y_im, im_mags = x[inds], y[inds], mags[inds]

        if len(x_im) < self.min_matches:
            msg = 'Not enough stars to platesolve ({:})'.format(len(x_im))
            toast(msg)
            self.info(msg)
            #logger.warning('Too few stars to platesolve ({:})'.format(len(x_im)))
            return False

        # get reference stars for search field (NB larger fov is worse)
        ras, decs, mags = Component.get('Catalogues').get_platesolving_stars(
            make_tile(self.ra0, self.dec0, fov=2 * fov)
        )

        # sort by magnitude and limit to N-brightest (should depend on area re stars extracted in central zone)
        inds = np.argsort(mags)[:80]
        ref_mags = mags[inds]

        # convert to cartesian coords
        ras, decs = Eq2Cart(ras[inds], decs[inds], self.ra0, self.dec0)

        # do fastmatch with ref and im stars in degrees
        matches = fastmatch(
            ref=np.degrees(np.vstack([ras, decs]).T),
            im=degrees_per_pixel * np.vstack([x_im, y_im]).T,
            match_arcsec=self.match_arcsec,
            min_matches=self.min_matches,
            mag_range=self.mag_range,
            proximity=0.05,
            first_match=self.first_match,
        )

        # check if we have a result
        if matches is None:
            toast('no match')
            logger.warning('no match, {:} im stars, {:} ref stars'.format(
                len(x_im), len(ras)))
            return False

        toast('Solved ({:} matched)'.format(len(matches)), duration=.7)

        # use result to find transform from ref in cartesian to im  in pixels
        src = np.vstack([ras, decs]).T[[j for (i, j) in matches], :]
        dst = np.vstack([x_im, y_im]).T[[i for (i, j) in matches], :]

        # consider doing RANSAC or alternative transform here
        # self.cart2pix = estimate_transform('similarity', src, dst)
        self.cart2pix = estimate_transform('affine', src, dst)

        # find centre of frame in RA/Dec
        self.tile_ra0, self.tile_dec0 = self.pixels_to_ra_dec(
            self.im_height // 2, self.im_width // 2
        )

        # estimate FOV
        self.FOV_h = spherical_distance(
            *self.pixels_to_ra_dec(0, 0), *self.pixels_to_ra_dec(self.im_height, 0)
        )
        self.FOV_w = spherical_distance(
            *self.pixels_to_ra_dec(0, 0), *self.pixels_to_ra_dec(0, self.im_width)
        )

        # and compute where North is
        xx, yy = self.ra_dec_to_pixels(
            np.array([self.ra0, self.ra0]),
            np.array([self.dec0 - 0.5, self.dec0 + 0.5]),
        )
        self.north = to360(
            90 - np.degrees(np.arctan2(yy[1] - yy[0], xx[1] - xx[0]))
        )

        desc = '{:5.3f} x {:5.3f}, {:.0f}\u00b0, RA: {:} Dec: {:}'.format(
            self.FOV_w,
            self.FOV_h,
            self.north,
            str(RA(self.tile_ra0)),
            str(Dec(self.tile_dec0)))

        # toast('Solved ({:} matched)'.format(len(matches)), duration=.7)
        logger.info(desc)
        self.info('{:.2f}\u00b0 x {:.2f}\u00b0 | {:} | {:}'.format(
            self.FOV_w, self.FOV_h,
            str(RA(self.tile_ra0)),
            str(Dec(self.tile_dec0))))

        return True

        #if self.cart2pix is not None:
        # Component.get('Annotator').annotate()

        # self.annotate()


    # def solve(self, *args):
    #     # called when user presses loc icon

    #     self.cart2pix = None

    #     if not self.can_solve:
    #         return

    #     self.ra0, self.dec0 = Component.get('DSO').current_object_coordinates()
    #     if self.ra0 is None:
    #         toast('Cannot solve: unknown DSO')
    #         return

    #     # get current image
    #     self.im = Component.get('Stacker').get_current_displayed_image()
    #     if self.im is None:
    #         toast('Cannot solve: no current image')
    #         return

    #     self.match()
    #     self.annotate()

    # def annotate(self, *args):
    #     if self.cart2pix is not None:
    #         Component.get('Annotator').annotate()

    def ra_dec_to_pixels(self, ra, dec):
        ''' return pixel coordinates corresponding to ra and dec,
            referenced to centre of closest matching tile
        '''
        if self.cart2pix is None:
            return
        if type(ra) != list and type(ra) != np.ndarray:
            ra = np.array([ra])
            dec = np.array([dec])

        x, y = Eq2Cart(ra, dec, self.ra0, self.dec0)
        d = self.cart2pix(np.array([x, y]).T)
        return d[:, 0], d[:, 1]

    def pixels_to_ra_dec(self, x, y):
        if self.cart2pix is None:
            return
        if type(x) != list and type(x) != np.ndarray:
            x = np.array([x])
            y = np.array([y])

        d = self.cart2pix.inverse(np.array([x, y]).T)
        x, y = Cart2Eq(d[:, 0], d[:, 1], self.ra0, self.dec0)
        if len(x) == 1:
            return x[0], y[0]
        return x, y

    def degrees_per_pixel(self):
        arcsec_pp = (
            (self.binned_pixel_height * 1e-6 / (self.focal_length / 1000))
            * (206265)
        )
        return arcsec_pp / 3600

