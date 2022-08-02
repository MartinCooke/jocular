'''  Fast gradient and background estimation
'''

import math
import numpy as np
from numpy.polynomial import polynomial
from loguru import logger


def estimate_background(im):
    # requires about .7ms for Lodestar image on MacBook Pro 2020

    # fit at random pixels and remove outliers
    npts = 500
    r, c = im.shape

    x = np.random.random_integers(0, high=c-1, size=(npts))
    y = np.random.random_integers(0, high=r-1, size=(npts))
    z = np.array([im[j, i] for i, j in zip(x, y)])

    # remove outliers e.g. stars
    zlo, zhi = np.percentile(z, 20), np.percentile(z, 80)
    inds = [i for i, j in enumerate(z) if (j >= zlo) and (j <= zhi)]
    zinds = z[inds]

    return np.mean(zinds), np.std(zinds)
   

def estimate_gradient(im):
    # simple estimation of 2d linear gradient surface ~12ms

    def _polyfit2d(x, y, f, deg):
        deg = np.asarray(deg)
        vander = polynomial.polyvander2d(x, y, deg)
        vander = vander.reshape((-1, vander.shape[-1]))
        f = f.reshape((vander.shape[0],))
        c = np.linalg.lstsq(vander, f, rcond=None)[0]
        return c.reshape(deg+1)

    try:
        # fit at random pixels
        npts = 500
        r, c = im.shape

        x = np.random.random_integers(0, high=c-1, size=(npts))
        y = np.random.random_integers(0, high=r-1, size=(npts))
        z = np.array([im[j, i] for i, j in zip(x, y)])

        zlo, zhi = np.percentile(z, 20), np.percentile(z, 80)
        inds = [i for i, j in enumerate(z) if (j >= zlo) and (j <= zhi)]

        # perform fit
        return polynomial.polyval2d(*np.meshgrid(np.arange(c), np.arange(r)), 
            _polyfit2d(x[inds], y[inds], z[inds], deg=[2, 1]))

    except Exception as e:
        logger.warning(f'gradient estimation failed; returning zeros ({e})')
        return np.zeros(im.shape)


def image_stats(im):
 
    mean_back, std_back = estimate_background(im)
    if math.isnan(mean_back):
        mean_back = 0
    if math.isnan(std_back):
        std_back = 0

    imr = im.ravel()

    return {
        'background': mean_back,
        'std. dev.': std_back,
        #'central 75%': percentile_clip(imr, perc=75),
        '99.99': np.percentile(imr, 99.99),
        #'99.9 percentile': np.percentile(imr, 99.9),
        'min': np.min(imr),
        'max': np.max(imr),
        'mean': np.mean(imr),
        'over': np.mean(imr > .99) * 100
        }
