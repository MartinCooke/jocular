'''  Fast gradient and background estimation
'''

import numpy as np
from numpy.polynomial import polynomial
from kivy.logger import Logger
from jocular.utils import percentile_clip

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
        Logger.debug('Gradient: gradient estimation failed; returning zeros ({:})'.format(e))
        return np.zeros(im.shape)


def image_stats(im):

    mean_back, std_back = estimate_background(im)
    imr = im.ravel()

    return {
        'background': mean_back,
        '100 x std. dev.': 100 * std_back,
        'central 75%': percentile_clip(imr, perc=75),
        '99.99 percentile': np.percentile(imr, 99.99),
        '99.9 percentile': np.percentile(imr, 99.9),
        'min': np.min(imr),
        'max': np.max(imr)
        }
