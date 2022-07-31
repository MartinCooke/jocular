''' Home to platesolvers. Currently just the one: fastmatch. 
'''


import numpy as np
from scipy.spatial.distance import cdist
from skimage.transform import estimate_transform
from loguru import logger

from jocular.processing.starextraction import extract_stars
from jocular.RA_and_Dec import RA, Dec
from jocular.uranography import (
    to360,
    make_tile, get_tiles, in_tile,
    Eq2Cart,
    spherical_distance,
    radec2pix, pix2radec
)

class PlatesolverException(Exception):
    pass


''' generalise fast match so it is not dependent on units of measurement; in particular,
    the proximity & match thresholds need to be altered for the case where star1 and star2
    are quite close (ie unit distance represents two close points)

    also, rename it pointcloud_match or similar
    might be other optimisations (might wish to pregenerate the combinations, but
    taking note of recomputation)

    also, magrange doesn't seem to be that useful and is too specific; if idea
    is to reduce the mag diff between star1 and star2 perhaps have a max depth instead
'''


def fastmatch(
    ref=None,
    im=None,
    mag_range=5,
    min_matches=8,
    proximity=0.05,
    match_threshold=None,
    target_matches=20
):
    ''' find possible match of image points 'im' to reference stars 'ref' ;
    both ref and im are ordered by magnitude; works by choosing a pair
    of image points, rotating and scaling so they sit at (0, 0) and (1, 0);
    then searching across pairs of image points at a similar separation, applying
    similar rotation/scaling, then counting matches; return as soon as we get
    max_matches, or search exhausted
    '''

    max_matches = 0
    best_matches = None
    kk = match_threshold ** 2
    n_im, n_ref = len(im), len(ref)
    cnt = 0

    for i1 in range(0, n_im):
        # normalise image based on star index i1
        im1 = im - im[i1, :]
        for i2 in [i for i in range(i1 + 1, min(n_im, i1 + mag_range)) if i != i1]:
            # rotate and scale so i2 is at (1, 0)
            cos, sin = im1[i2, 0], -im1[i2, 1]
            d = cos ** 2 + sin ** 2
            im2 = np.dot(im1, np.array([[cos, -sin], [sin, cos]]).T) / d
            # match threshold takes into account scaling by d
            # mt = (match_arcsec / (3600 * (d ** 0.5))) ** 2.0  # we match squared dist
            mt = kk / d  # we match squared dist
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
                            cnt += 1
                            dists = cdist(im2, ref2, metric='sqeuclidean')
                            matches = [
                                (i, j)
                                for i, j in enumerate(np.argmin(dists, axis=1))
                                if dists[i, j] < mt
                            ]
                            n_matches = len(matches)
                            if n_matches >= target_matches:
                                return matches
                            if n_matches > max_matches:
                                max_matches = n_matches
                                best_matches = matches
    # return matches
    logger.debug('count {:}'.format(cnt))
    return best_matches


def get_platesolving_stars(star_db, tile):
    # get stars in tile; star_db is a npz file indexed by
    # ra and dec

    ra_tiles, dec_tiles = get_tiles(tile, 30, 10)
    ras, decs, mags = np.array([]), np.array([]), np.array([])
    for ra in ra_tiles:
        for dec in dec_tiles:
            quad = 'r{:}_d{:}_'.format(ra, dec)
            ras = np.append(ras, star_db[quad+'ra'])
            decs = np.append(decs, star_db[quad+'dec'])
            mags = np.append(mags, star_db[quad+'mag']/100.) # mags were stored as ints * 100

    locs = in_tile(tile, ras, decs)
    return ras[locs], decs[locs], mags[locs]


def platesolve(
    path=None, 
    im=None, 
    ra0=None, 
    dec0=None, 
    star_db=None,
    nstars=30, 
    min_matches=10, 
    max_matches=10, 
    degrees_per_pixel=None,
    nrefs=80,
    match_arcsec=15, 
    mag_range=5, 
    star_method='photutils', 
    target_matches=25,
    verbose=False):

    ''' Attempt to solve image at around ra0, dec0
    '''

    if path is None and im is None:
        raise PlatesolverException('must supply either an image or a FITs file path')

    if path is not None:
        raise PlatesolverException('Reading fits not yet supported')

    if ra0 is None or dec0 is None:
        raise PlatesolverException('must supply ra0/dec0 for approx centre of field')

    # extract star centroids and fluxes
    if verbose:
        logger.info('extracting stars')

    # extract stars (uses photutils; could place this in starextraction library)
    stars = extract_stars(
        im, 
        star_method=star_method, 
        target_stars=nstars,
        nstars=nstars,
        binfac=2,
        reset_threshold=False)

    x, y, flux = stars['xcentroid'], stars['ycentroid'], stars['flux']
    fwhm = np.median(stars['fwhm'])
    
    if len(x) < min_matches:
        raise PlatesolverException('insufficient stars found (needs {:}, found {:})'.format(min_matches, len(x)))

    if verbose:
        logger.info('extracted {:} stars'.format(len(x)))

    h, w = im.shape
    fov = h * degrees_per_pixel

    # convert flux to mags
    mags = -2.5 * np.log10(flux / np.max(flux))

    if verbose:
        logger.debug('mag range {:.1f}'.format(np.max(mags)))

    # sort in descending order of brightness anbd limit to nstars
    inds = np.argsort(mags)[:nstars]
    x_im, y_im = x[inds], y[inds]

    im_stars = degrees_per_pixel * np.vstack([x_im, y_im]).T

    # get platesolving reference stars in sufficiently large FOV
    ras, decs, mags = get_platesolving_stars(star_db, make_tile(ra0, dec0, fov=2*fov))

    # sort refs by mag and limit to N-brightest
    inds = np.argsort(mags)[:nrefs]

    # convert to cartesian coords
    ras, decs = Eq2Cart(ras[inds], decs[inds], ra0, dec0)

    ref_stars = np.degrees(np.vstack([ras, decs]).T)

    # do fastmatch with ref and im stars in degrees
    matches = fastmatch(
        ref=ref_stars,
        im=im_stars,
        match_threshold=match_arcsec / 3600.,
        min_matches=min_matches,
        target_matches=target_matches,
        mag_range=mag_range,
        proximity=0.05
    )

    if matches is None:
        raise PlatesolverException('no match')
    if len(matches) < min_matches:
        raise PlatesolverException('insufficient match')
    
    logger.info('matched {:}'.format(len(matches)))

    # create coord pairs of matching stars  
    src = np.vstack([ras, decs]).T[[j for (i, j) in matches], :]
    dst = np.vstack([x_im, y_im]).T[[i for (i, j) in matches], :]

    # estimate transform with scale, rotation and translation
    projection = estimate_transform('affine', src, dst)

    # find centre of frame in RA/Dec
    ra_centre, dec_centre = pix2radec(
        w // 2, h // 2, ra0, dec0, projection)

    # compute where North is (TO DO: second line might not work at poles....)
    xx, yy = radec2pix(
        np.array([ra0, ra0]),
        np.array([dec0 - 0.5, dec0 + 0.5]),
        ra0, dec0,
        projection
    )
    rotation = np.degrees(np.arctan2(yy[1] - yy[0], xx[1] - xx[0]))
    north = to360(90 - rotation)

    fov_w = spherical_distance(
        *pix2radec(0, 0, ra0, dec0, projection), 
        *pix2radec(w, 0, ra0, dec0, projection)
        )
    fov_h = spherical_distance(
        *pix2radec(0, 0, ra0, dec0, projection), 
        *pix2radec(0, h, ra0, dec0, projection)
        )

    return {
        'tile_ra0': ra0,
        'tile_dec0': dec0,
        'ra_centre': ra_centre,
        'dec_centre': dec_centre,
        'ra': str(RA(ra_centre)),
        'dec': str(Dec(dec_centre)),
        'width': w,
        'height': h,
        'fov_w': fov_w,
        'fov_h': fov_h,
        'north': north,
        'projection': projection,
        'im_stars': im_stars,
        'ref_stars': ref_stars,
        'fwhm': fwhm
    }


