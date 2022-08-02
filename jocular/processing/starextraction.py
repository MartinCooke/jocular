''' Star extraction and estimation of star properties such 
    as FWHM/HFD, flux, background, centroids, etc.
    Currently somewhat experimental
'''

import warnings
import math
import numpy as np
from loguru import logger
from scipy.optimize import curve_fit
from skimage.transform import downscale_local_mean, rescale
from skimage.feature import blob_dog
from astropy.stats import mad_std
from photutils.detection import DAOStarFinder
# from photutils.aperture import aperture_photometry, CircularAperture, ApertureStats


def extract_stars(
    im, 
    star_method='photutils', 
    centroid_method='simple',
    target_stars=30,
    nstars=None,
    radius=8,
    binfac=1,
    reset_threshold=False, # for dog
    fwhm_method='count'):
    ''' Find stellar sources using specified method, aiming to find
        target_stars stars. Apply centroid processing within specified
        pixel radius.

        Returns a dict containing centroids, flux, fwhm
    '''

    im2 = im.copy()

    if binfac > 1:
        im2 = downscale_local_mean(im2, (binfac, binfac))

    if star_method == 'photutils':
        stars = _stars_DAO(im2, nstars=target_stars)

    elif star_method == 'DoG':
        stars = DoGStars.extract(
            im2, 
            reset_threshold=reset_threshold, 
            target_stars=target_stars, 
            nstars=nstars)

    if stars is None:
        return {'nstars': 0}

    # undo binning
    if binfac > 1:
        stars[:, :2] *= binfac

    # compute centroids, better flux and fwhm estimates
    if centroid_method == 'simple':
        stardata = simple_starprops(im, stars[:, :2], radius=radius)
    else:
        stardata = starprops(im, stars[:, :2], radius=radius)

    # stardata is N x 4 array of x, y, flux, fwhm
    # re-sort by flux here since it will have been improved 
    inds = np.argsort(np.array(stardata[:, 2]))[::-1]

    return {
        'nstars': len(inds),
        'xcentroid': stardata[inds, 0],
        'ycentroid': stardata[inds, 1],
        'flux': stardata[inds, 2],
        'fwhm': stardata[inds, 3]
    }


def simple_starprops(im, stars, radius=8):
    ''' Compute accurate locations for stars based on star pixel coords.
        This is the original Jocular method that has worked robustly.
    '''

    r = radius
    grid_x, grid_y = np.meshgrid(np.arange(2 * r + 1), np.arange(2 * r + 1))
    mask = np.sqrt((r - grid_x)**2 + (r - grid_y)**2) <= r

    rows, cols = im.shape
    star_data = np.zeros((len(stars), 4))
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
                hfd = compute_fwhm(imfrag, fwhm_method='count')
                star_data[ptr, :] = [cx + x - r, cy + y - r, np.mean(imfrag_sub), hfd]
                ptr += 1  
                 
    return star_data[:ptr, :]


def starprops(im, stars, radius=8, upfac=5, fwhm_method='count'):
    ''' Highly-experimental approach; needs more checking
    '''

    ptr = 0
    rows, cols = im.shape
    star_data = np.zeros((len(stars), 4))
    r = radius
    for x, y in stars:
        x, y = int(x), int(y)

        if (x >= r) and (y >= r) and (x < (cols - r)) and (y < (rows - r)):
            imfrag = im[(y - r):(y + r + 1), (x - r):(x + r + 1)].copy()

            # upsample
            imfrag = rescale(imfrag, upfac, preserve_range=True)
            h, w = imfrag.shape
            rr = (w - 1) // 2

            # remove background (might want to alter radfac so it doesn't use entire stellar radius)
            background = compute_background(imfrag, radfac=1)
            imfrag -= background

            # compute initial starsize
            ss = int(compute_starsize(imfrag, method='count'))

            ''' Use radius starsize to compute centroid in tighter radius, avoiding 
                contamination by other stars in region. Note that this is equivalent
                to a star size of twice the HFD
            '''

            # ensure size is not larger then available radius
            ss = min(ss, rr)

            # extract central part of image and compute its centroid
            cx, cy = centroid(imfrag[rr - ss: rr + ss + 1, rr - ss: rr + ss + 1])

            # if math.isnan(cx) or math.isnan(cy):
            #     print('nan', x, y, cx, cy)

            # convert centroid coordinates back to upscaled image
            cx += (rr - ss)
            cy += (rr - ss)

            ''' recenter image on new centroid cx, cy, which will typically reduce size of 
                image region; ensure that it is square
            '''

            # bug here: cx/cy can sometimes be None
            cxi, cyi = int(cx), int(cy)

            # find max radius of region 
            minr = min(cxi, w - cxi - 1, cyi, w - cyi - 1)

            # select square region
            im3 = imfrag[cyi - minr: cyi + minr + 1, cxi - minr: cxi + minr + 1].copy()

            # find star size using selected method
            radfac = 1 # optionally, could use a smaller radius
            fwhm = compute_starsize(im3, method=fwhm_method, radfac=radfac)

            # compute flux (here for now though it should be done with SAME radius throughout)
            fluxrad = int(min(minr, 2*fwhm))
            flux = np.mean(im3[circular_mask(2 * minr + 1, radius=fluxrad)])

            star_data[ptr, :] = [(cx / upfac) + x - r, (cy / upfac) + y - r, flux / upfac**2, fwhm / upfac]
            ptr += 1 

    return star_data[:ptr, :]


def compute_fwhm(imfrag, upfac=5, fwhm_method='count'):
    ''' using specified method; uses upsampling by factor upfac
        to get better estimate
    '''

    imfrag2 = rescale(imfrag, upfac, preserve_range=True)
    h, w = imfrag2.shape

    # remove background (might want to alter radfac so it doesn't use entire stellar radius)
    background = compute_background(imfrag2, radfac=1)
    imfrag2 -= background

    # compute HFD
    HFD = int(compute_starsize(imfrag2, method=fwhm_method))

    return HFD / upfac


def _stars_DAO(im, nstars=30, fwhm=4, nsigmas=5):
    ''' Star extraction using DAOStarFinder from photutils; return centroids and
        peak pixel value at centroid
    '''

    imc = im - np.median(im)    # subtract rough background estimate
    bkg_sigma = mad_std(imc)    # median absolute deviation
    # extract a few more than requested as we will remove those close to boundary
    daofind = DAOStarFinder(fwhm=fwhm, threshold=nsigmas * bkg_sigma, 
        brightest=int(nstars*1.1))
    stars = daofind(imc)
    if stars is None:
        return None

    return np.transpose([stars['xcentroid'], stars['ycentroid'], stars['peak']])


class DoGStars:
    ''' Simple class that extracts stars using difference of Gaussian
        blob detection. A class is used to enable the threshold for
        extraction to be stored in between successive calls to extract.
    '''

    threshold = None

    @classmethod
    def extract(cls, 
        im, 
        target_stars=30,    # find threshold to detect this many stars
        nstars=None,        # desired number of stars (can be more than target)
        reduce_by=1,        # reduce threshold to allow in more stars (not needed prob.)
        sort_by_mag=True,   # sort by decreasing brightness
        min_sigma=3,
        max_sigma=5,
        reset_threshold=False  # if True, recompute star threshold
        ):
        ''' Find stars in image
        '''

        if reset_threshold:
            cls.threshold = None

        # if threshold is None, find it
        if cls.threshold is None:
            cls.threshold, converged = \
                cls._best_threshold(im, target_stars=target_stars, 
                    tol=.2, maxits=20)
            logger.debug('threshold {:.4f} converged {:}'.format(cls.threshold, converged))
 
        # use Dog-based blob extraction for stars
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            stars = blob_dog(im, 
                min_sigma=min_sigma, 
                max_sigma=max_sigma, 
                threshold=cls.threshold * reduce_by, 
                overlap=0)[:, [1, 0]]

        if len(stars) == 0:
            return None

        # very approximate flux
        flux = [im[int(y), int(x)] for x, y in stars]

        if sort_by_mag:
            inds = np.argsort(flux)[::-1]
            x = np.array([x for x, y in stars])[inds]
            y = np.array([y for x, y in stars])[inds]
            flux = np.array(flux)[inds]

        # select n brightest
        if nstars is None:
            nstars = len(x)

        return np.transpose([x[:nstars], y[:nstars], flux[:nstars]])


    @classmethod
    def _best_threshold(cls, im, target_stars=30, tol=.2, maxits=20):
        ''' Find threshold that delivers target number of stars.
            Stop when within tol or maxits reached.
        '''

        t = .01 
        converged = False
        lo, hi = 0, 10
        its = 0
        while not converged:
            nstars = len(blob_dog(im, min_sigma=3, max_sigma=5, threshold=t, overlap=0))
            its += 1
            diff = nstars - target_stars
            converged = (abs(diff / target_stars) < tol) or (its > maxits)
            if not converged:
                if diff > 0:
                    lo = t
                    t = (hi + t) / 2
                else:
                    hi = t
                    t = (lo + t) / 2
        return t, its <= maxits


''' materials for future photometry
    
    positions = np.transpose((sources['xcentroid'], sources['ycentroid']))
    apertures = CircularAperture(positions, r=3.)
    from photutils import aperture_photometry
    ap = aperture_photometry(imc, apertures)
    aperstats = ApertureStats(imc, apertures)
    flux = sources['flux']
    flux2 = np.array(aperstats.sum)
    flux3 = np.array(ap['aperture_sum'])
    fwhm = np.array(aperstats.fwhm)
'''



''' All the stuff below here is homegrown star property computation in case
    photutils is not used; needs to be rationalised and HFD stuff separated
    out as an alternative to photutils aperturestats computation of FWHM.
'''


def f_gauss(x, A, x0, sigma):
    return A * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2))


def f_moffat(x, A, mu, sigma, beta):
    return A * (1 + ((x-mu)/sigma)**2) ** -beta


def fwhm_moffat(A, mu, sigma, beta):
    return 2 * sigma * (2**(1/beta)-1) **.5


def circular_mask(side, radius=None):
    centre = (side - 1) // 2
    if radius is None:
        radius = side - centre - 1
    return distance_mask(side) <= radius


def distance_mask(side):
    centre = (side - 1) // 2
    Y, X = np.ogrid[:side, :side]
    return np.sqrt((X - centre)**2 + (Y - centre)**2)


def centroid(im):
    ''' should really check if centroid is within im (ie in range of 0..h etc)
        but this presumably occurs only if im has negative pixels, which now it
        doesn't
    '''
    h, w = im.shape
    im2 = im.copy()
    im2[im2 < 0] = 0
    grid_x, grid_y = np.meshgrid(np.arange(w), np.arange(w))
    imsum = np.sum(im2)
    return np.sum(grid_x * im2) / imsum, np.sum(grid_y * im2) / imsum


def compute_flux(im, cx, cy, fwhm=None, n_widths=3):
    ''' compute stellar flux for all centroids cx, cy based on
        estimated fwhm; don't use upsampling (yet)
    '''

    # width of window to compute fwhm in
    r = int(n_widths * fwhm)
    star_mask = circular_mask(2 * r + 1)
    h, w = im.shape

    flux = []
    for xx, yy in zip(cx, cy):
        x, y = int(xx), int(yy)
        if x >= r and y >= r and x + r < w and y + r < h:
            imfrag = im[y - r: y + r + 1, x - r: x + r + 1].copy()
            flux += [np.sum(imfrag[star_mask])]
        else:
            # TO DO: this actually occurs so work out why
            # print('outside bounds in computing flux -- should not happen')
            flux += [0]
    return np.array(flux)


def compute_starsize(im, method='count', radfac=1):
    ''' compute HFD/FWHM based on chosen method
        Assumes im has already had background removed.
        All methods operate on circular star mask that occupies all (if radfac=1) or
        part (radfac < 1) of the analysis window defined by the shape of im.
    '''

    h, w = im.shape
    radius = int(radfac * (h - 1) // 2)
    star_mask = circular_mask(w, radius=radius)

    if method == 'count':
        ''' method used in ASTAP: counts all pixels above
            half peak value and converts count to radius
        '''
        pmax = np.max(im[star_mask]) 
        above = np.count_nonzero(im[star_mask] > 0.5 * pmax)
        return 2 * (above / np.pi) ** .5

    if method == 'moments':
        ''' tends to overestimate FWHM?
        '''
        dist_mask = distance_mask(w)
        return 2 * np.sum(dist_mask[star_mask] * im[star_mask]) / np.sum(im[star_mask])

    if method == 'cumsum':
        ''' original FHD method that also tends to 
            overestimate FWHM
        '''
        dist_mask = distance_mask(w)
        dists = dist_mask[star_mask].ravel()
        order = np.argsort(dists)
        cs = np.cumsum(im[star_mask][order])
        half_point = len(cs) - len(cs[cs > (.5 * cs[-1])])
        return 2*sorted(dists)[half_point]

    if method in {'Gaussian', 'Moffat'}:
        ''' curve-fitting approaches to estimate FWHM; can
            suffer problems of poor fits; could be improved perhaps
            by using all pixels in star mask although trials using
            their radii haven't improved things
        '''     
        h2 = (h - 1) // 2
        # operates using a column crossing central pixel
        counts = im[:, h2].copy()
        rads = np.arange(-h2, h2+1)
        mean = np.sum(counts * rads) / np.sum(counts)
        sigma = np.sqrt(sum(counts * (rads - mean) ** 2) / sum(counts))
        if method == 'Gaussian':
            try:
                p_gaussian, pcov = curve_fit(f_gauss, rads, counts, p0=[max(counts), mean, sigma], maxfev=10000)
                # can sometimes fail to converge
                if math.isnan(p_gaussian[2]):
                    return -1
                return 2.3548 * p_gaussian[2]
            except:
                return -1
        elif method == 'Moffat':
            try:
                p_moffat, pcov = curve_fit(f_moffat, rads, counts, p0=[max(counts), mean, 1, 1], maxfev=10000)
                return fwhm_moffat(*p_moffat)
            except:
                return -1


def compute_background(im, radfac=1):
    ''' compute background in im after excluding central star
        region which takes up radfac of the radius
    '''
    h, w = im.shape
    radius = int(radfac * (h - 1) // 2)
    star_mask = circular_mask(w, radius=radius)
    bkg_pixels = im[~(star_mask)]
    background = np.median(bkg_pixels)
    return background


