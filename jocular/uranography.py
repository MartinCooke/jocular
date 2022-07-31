''' Astrometry utilities. Will support future extension to charting.
'''

import math
import numpy as np
from scipy.special import cotdg

def to360(v):
    if type(v) == list or type(v) == np.ndarray:
        v[v > 360] = v[v > 360] - 360
        v[v < 0] = v[v < 0] + 360
    else:
        if v > 360:
            v -= 360
        elif v < 0:
            v += 360
    return v


def angle360(angle):
    if angle < 0:
        return angle + 360
    elif angle > 360:
        return angle - 360
    else:
        return angle

def angle_diff(t1, t2):
    # anticlockwise angle between 2 positions relative to 0 = positive x-axis
    return angle360(math.atan2(t2[1] - t1[1], t2[0] - t1[0]) / (math.pi / 180))


def spherical_distance(ra, dec, ra0, dec0):
    # return distances of points in ra, dec arrays to point (ra0, dec0)
    d1 = np.sin(np.abs(np.radians(dec) - np.radians(dec0)) / 2) ** 2
    d2 = np.cos(np.radians(dec0)) * np.cos(np.radians(dec)) * (np.sin(np.abs(np.radians(ra) - np.radians(ra0)) / 2) ** 2)
    return np.degrees(2 * np.arcsin((d1 + d2) ** .5))


def Eq2Cart(ra, dec, ra0, dec0):
    # conversion from RA/Dec to standard coords; Snyder (1987) ch 22
    # from matlab version; not fully tested

    rads = np.pi / 180.
    dec = rads * dec
    ra_norm = rads * (ra - ra0)

    if dec0 == 90: 
        # north or south pole so use polar gnomic
        x = np.cos(dec) * np.sin(ra_norm)
        y = -cotdg(dec / rads) * np.cos(ra_norm)

    elif dec0 == -90:
        x = -np.cos(dec) * np.sin(ra_norm)
        y = cotdg(dec / rads) * np.cos(ra_norm)
        
    else:
        # oblique gnomic
        dec0 = rads * dec0
        cos0 = np.cos(dec0)
        sin0 = np.sin(dec0)
        cosdec = np.cos(dec)
        sindec = np.sin(dec)
        cos_ra_norm = np.cos(ra_norm)
        den = cos0 * cosdec * cos_ra_norm + sin0 * sindec
        x = (cosdec * np.sin(ra_norm)) / den
        y = (cos0 * sindec - sin0 * cosdec * cos_ra_norm ) / den

    return -x, y  # reverse RA axis

def Cart2Eq(x, y, ra0, dec0):
    # convert from standard coords to RA/Dec (Snyder ch22)
        
    rads = np.pi / 180.

    # unreverse 'ra'
    x = -x
    rho = (x**2 + y**2)**.5
    c = np.arctan(rho)
    cosc, sinc = np.cos(c), np.sin(c)
    
    if dec0 == 90:
        dec = np.arcsin(cosc)
        ra = np.arctan2(x, -y)
        
    elif dec0 == -90:
        dec = np.arcsin(-cosc)
        ra = np.arctan2(x, y)
        
    else:
        cos0, sin0 = np.cos(rads * dec0), np.sin(rads * dec0)
        dec = np.arcsin(cosc * sin0 + ((y * sinc * cos0 / rho)))
        ra = np.arctan2(x * sinc, rho * cosc * cos0 - y * sinc * sin0)
        
    dec /= rads
    ra = ra0 + ra / rads
    dec[rho==0] = dec0
    ra[rho==0] = ra0
    ra[ra > 360] -= 360
    ra[ra < 0] += 360
    return ra, dec


''' tile represent fields of view
''' 

def intstep(d, step):
    return int(np.floor(step * np.floor(d / step)))


def make_tile(ra0, dec0, fov=3):
    ''' A tile represents all pertinent information about a field
        centred on ra0, dec0 with given fov
    '''
    rads = np.pi / 180.
    fov2 = fov / 2
    polar = ((dec0 + fov2) >= 90) | ((dec0 - fov2) <= -90)
    northern = dec0 >= 0
    if polar:
        min_ra, max_ra = 0, 360
        if northern:
            min_dec, max_dec = 90 - fov2, 90
        else:
            min_dec, max_dec = -90, -90 + fov2
    else:
        ra_width = fov2 / np.cos(dec0 * rads)
        min_ra, max_ra =  to360(ra0 - ra_width), to360(ra0 + ra_width)
        min_dec, max_dec = dec0 - fov2, dec0 + fov2
    return {
        'fov': fov, 'min_ra': min_ra, 'max_ra': max_ra,
        'min_dec': min_dec, 'max_dec': max_dec, 'ra0': ra0, 'dec0': dec0,
        'polar': polar, 'northern': northern
    }

def get_tiles(tile, rstep, dstep):
    ''' return database tiles covering region defined in tile
    '''
    rmin, rmax = tile['min_ra'], tile['max_ra']
    dmin, dmax = tile['min_dec'], tile['max_dec']

    dec_tiles = np.arange(intstep(dmin, dstep), intstep(dmax, dstep) + dstep, dstep)
    if rmin < rmax:
        ra_tiles = np.arange(intstep(rmin, rstep), intstep(rmax, rstep) + rstep, rstep)
    else:
        # handle wraparound
        ra_tiles = \
            list(range(intstep(rmin, rstep), 360, rstep)) + \
            list(range(0, intstep(rmax, rstep) + rstep, rstep))
    return ra_tiles, dec_tiles        

def in_tile(tile, ras, decs):
    ''' return indices of coordinates within tile
    '''
    rmin, rmax = tile['min_ra'], tile['max_ra']
    dmin, dmax = tile['min_dec'], tile['max_dec']
    if rmin < rmax:
        return (decs >= dmin) & (decs < dmax) & (ras >= rmin) & (ras < rmax)
    else:
        return (decs >= dmin) & (decs < dmax) & ((ras >= rmin) | (ras < rmax))


def radec2pix(ra, dec, ra0, dec0, projection):
    ''' return pixel coordinates corresponding to ra and dec,
        referenced to centre of closest matching tile
    '''
    if type(ra) != list and type(ra) != np.ndarray:
        ra = np.array([ra])
        dec = np.array([dec])
    x, y = Eq2Cart(ra, dec, ra0, dec0)
    d = projection(np.array([x, y]).T)
    return d[:, 0], d[:, 1]


def pix2radec(x, y, ra0, dec0, projection):
    ''' find RA/Dec at pixel value
    '''
    if type(x) != list and type(x) != np.ndarray:
        x = np.array([x])
        y = np.array([y])
    d = projection.inverse(np.array([x, y]).T)
    x, y = Cart2Eq(d[:, 0], d[:, 1], ra0, dec0)
    if len(x) == 1:
        return x[0], y[0]
    return x, y

