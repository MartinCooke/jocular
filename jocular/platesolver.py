''' Local plate-solver. 
'''


import numpy as np
from scipy.spatial.distance import cdist
from skimage.feature import blob_dog
from skimage.transform import estimate_transform
from concurrent.futures import ThreadPoolExecutor

from kivy.app import App
from kivy.logger import Logger
from kivy.properties import ConfigParserProperty

from jocular.component import Component
from jocular.RA_and_Dec import RA, Dec
from jocular.uranography import (
    to360,
    make_tile,
    Eq2Cart,
    Cart2Eq,
    spherical_distance,
    compute_centroids,
)


def select_stars_in_FOV(ras, decs, ra0, dec0, fov):
    #  filter ras, decs, mags to just return those in given region
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
    """find possible match of image points im in star database cloud db
    both db and im are ordered by magnitude; works by choosing a pair
    of image points, rotating and scaling so they sit at (0, 0) and (1, 0);
    then searching across pairs of image points at a similar separation, applying
    similar rotation/scaling, then counting matches; if first_match is true, return
    first match that contains more than min_matches stars, otherwise return
    the match that contains the most correspondences.
    """

    max_matches = 0
    best_matches = None
    n_im, n_ref = len(im), len(ref)
    for i1 in range(0, n_im):
        #  normalise image based on star index i1
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
                        #  don't check if anything outside range
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


class PlateSolver(Component):

    focal_length = ConfigParserProperty(
        800.0, 'PlateSolver', 'focal_length', 'app', val_type=float
    )
    pixel_height = ConfigParserProperty(
        8.4, 'PlateSolver', 'pixel_height', 'app', val_type=float
    )
    binning = ConfigParserProperty(1, 'PlateSolver', 'binning', 'app', val_type=int)
    n_stars_in_image = ConfigParserProperty(
        30, 'PlateSolver', 'n_stars_in_image', 'app', val_type=int
    )
    min_matches = ConfigParserProperty(
        8, 'PlateSolver', 'min_matches', 'app', val_type=int
    )
    match_arcsec = ConfigParserProperty(
        15, 'PlateSolver', 'match_arcsec', 'app', val_type=float
    )
    mag_range = ConfigParserProperty(5, 'PlateSolver', 'mag_range', 'app', val_type=int)
    first_match = ConfigParserProperty(
        1, 'PlateSolver', 'first_match', 'app', val_type=int
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.cart2pix = None

    def on_new_object(self):
        self.cart2pix = None
        self.can_solve = Component.get('Catalogues').has_platesolving_db()
        self.info('ready' if self.can_solve else 'no database')

    def match(self):
        # runs in separate thread

        try:
            self.h, self.w = self.im.shape
            # degrees per pixel
            dpp = self.binning * (self.pixel_height * 1e-6 / self.focal_length) * (206265 / 3.6)
            fov = self.h * dpp

            #  extract image stars
            star_thresh = 0.001
            x, y, flux = compute_centroids(
                self.im,
                blob_dog(
                    self.im, min_sigma=3, max_sigma=5, threshold=star_thresh, overlap=0
                )[:, [1, 0]],
            )

            #  convert flux to relative magnitude
            mags = -2.5 * np.log10(flux / np.max(flux))

            # select N-brightest
            inds = np.argsort(mags)[: self.n_stars_in_image]
            x_im, y_im = x[inds], y[inds]

            if len(x_im) < self.min_matches:
                self.warn('too few stars ({:})'.format(len(x_im)))
                return

            # get reference stars for search field (NB larger fov is worse)
            ras, decs, mags = Component.get('Catalogues').get_platesolving_stars(
                make_tile(self.ra0, self.dec0, fov=2 * fov)
            )

            #  sort by magnitude and limit to N-brightest (should depend on area re stars extracted in central zone)
            inds = np.argsort(mags)[:80]

            #  convert to cartesian coords
            ras, decs = Eq2Cart(ras[inds], decs[inds], self.ra0, self.dec0)

            # do fastmatch with ref and im stars in degrees
            matches = fastmatch(
                ref=np.degrees(np.vstack([ras, decs]).T),
                im=dpp * np.vstack([x_im, y_im]).T,
                match_arcsec=self.match_arcsec,
                min_matches=self.min_matches,
                mag_range=self.mag_range,
                proximity=0.05,
                first_match=self.first_match,
            )

            # check if we have a result
            if matches is None:
                self.warn('failed to match')
                Logger.warn('Platesolver: no match, {:} im stars, {:} ref stars'.format(
                    len(x_im), len(ras)))
                return

            self.info('matched {:}'.format(len(matches)))

            # use result to find transform from ref in cartesian to im  in pixels
            src = np.vstack([ras, decs]).T[[j for (i, j) in matches], :]
            dst = np.vstack([x_im, y_im]).T[[i for (i, j) in matches], :]

            # consider doing RANSAC or alternative transform here
            # self.cart2pix = estimate_transform('similarity', src, dst)
            self.cart2pix = estimate_transform('affine', src, dst)

            # find centre of frame in RA/Dec
            self.tile_ra0, self.tile_dec0 = self.pixels_to_ra_dec(
                self.h // 2, self.w // 2
            )

            # estimate FOV
            self.FOV_h = spherical_distance(
                *self.pixels_to_ra_dec(0, 0), *self.pixels_to_ra_dec(self.h, 0)
            )
            self.FOV_w = spherical_distance(
                *self.pixels_to_ra_dec(0, 0), *self.pixels_to_ra_dec(0, self.w)
            )

            #  and compute where North is
            xx, yy = self.ra_dec_to_pixels(
                np.array([self.ra0, self.ra0]),
                np.array([self.dec0 - 0.5, self.dec0 + 0.5]),
            )
            self.north = to360(
                90 - np.degrees(np.arctan2(yy[1] - yy[0], xx[1] - xx[0]))
            )

            Logger.info(
                'PlateSolver: {:5.3f} x {:5.3f}, {:.0f}\u00b0, RA: {:} Dec: {:}'.format(
                    self.FOV_w,
                    self.FOV_h,
                    self.north,
                    str(RA(self.tile_ra0)),
                    str(Dec(self.tile_dec0)),
                )
            )

        except Exception as e:
            Logger.warn('PlateSolver: error in match')

    def solve(self, *args):
        # called when user presses loc icon

        self.cart2pix = None

        if not self.can_solve:
            return

        self.ra0, self.dec0 = Component.get('DSO').current_object_coordinates()
        if self.ra0 is None:
            self.warn('unknown DSO')
            return

        # get current image (sub or stack)
        self.im = Component.get('Stacker').get_image_for_platesolving()
        if self.im is None:
            self.warn('no current image')
            return

        pool = ThreadPoolExecutor(3)
        future = pool.submit(self.match)
        future.add_done_callback(self.annotate)

    def annotate(self, *args):
        if self.cart2pix is None:
            self.warn('failed')
        else:
            Component.get('Annotator').annotate()

    def ra_dec_to_pixels(self, ra, dec):
        # generate pixel coordinates corresponding to ra and dec
        # referenced to centre of closest matching tile
        if self.cart2pix is None:
            return
        if type(ra) != list and type(ra) != np.ndarray:
            ra = np.array([ra])
            dec = np.array([dec])

        x, y = Eq2Cart(ra, dec, self.ra0, self.dec0)
        d = self.cart2pix(np.array([x, y]).T)
        return d[:, 0], d[:, 1]

    def pixels_to_ra_dec(self, x, y):
        # generate pixel coordinates corresponding to ra and dec
        # referenced to centre of closest matching tile
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

    # def get_stars(self, tile):
    #     # get stars in tile by reading npys that are spaced at 30 x 10 degrees in RA/Dec
    #     # star_db = self.app.get_path('star_db')
    #     min_ra, max_ra = tile['min_ra'], tile['max_ra']
    #     min_dec, max_dec = tile['min_dec'], tile['max_dec']
    #     dec_tiles = np.arange(dec2tile(min_dec), dec2tile(max_dec) + DEC_STEP, DEC_STEP)
    #     if min_ra < max_ra:
    #         ra_tiles = np.arange(ra2tile(min_ra), ra2tile(max_ra) + RA_STEP, RA_STEP)
    #     else:
    #         ra_tiles = list(range(ra2tile(min_ra), 360, RA_STEP)) + list(
    #             range(0, ra2tile(max_ra) + RA_STEP, 30)
    #         )

    #     # here we could cache when implemented as Joc component
    #     ras, decs, mags = np.array([]), np.array([]), np.array([])
    #     for ra in ra_tiles:
    #         for dec in dec_tiles:
    #             #dat = np.load(os.path.join(star_db, 'r{:}_d{:}.npz'.format(ra, dec)))
    #             quad = 'r{:}_d{:}_'.format(ra, dec)
    #             ras = np.append(ras, self.db[quad+'ra'])
    #             decs = np.append(decs, self.db[quad+'dec'])
    #             mags = np.append(mags, self.db[quad+'mag']/100.) # mags are ints * 100

    #     # restrict to tile
    #     if min_ra < max_ra:
    #         locs = (
    #             (ras >= min_ra) & (ras < max_ra) & (decs >= min_dec) & (decs < max_dec)
    #         )
    #     else:
    #         locs = (
    #             ((ras >= min_ra) | (ras < max_ra))
    #             & (decs >= min_dec)
    #             & (decs < max_dec)
    #         )
    #     return ras[locs], decs[locs], mags[locs]

    def degrees_per_pixel(self):
        arcsec_pp = (
            self.binning
            * (self.pixel_height * 1e-6 / (self.focal_length / 1000))
            * (206265)
        )
        #  self.info('{:4.2f}"/pixel'.format(arcsec_pp))
        return arcsec_pp / 3600
