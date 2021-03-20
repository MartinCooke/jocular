''' Astrometry utilities. Will support future extension to charting.
'''

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

''' to do: combine these functions with those used in Aligner -- not
    clear any more why they are defined here.
'''

def compute_centroids(im, stars):
    # extract info from all candidate stars and return centroids
    r = 8  # centroid patch radius
    patch_size = 2 * r + 1
    grid_x, grid_y = np.meshgrid(np.arange(patch_size), np.arange(patch_size))
    mask = np.sqrt((r - grid_x)**2 + (r - grid_y)**2) <= r
    rows, cols = im.shape
    ptr = 0
    xdata =[]
    ydata =[] 
    mags=[]
    for x, y in stars:
        x, y = int(x), int(y)
        if (x >= r) and (y >= r) and (x < (cols - r)) and (y < (rows - r)):
            imfrag = im[(y - r):(y + r + 1), (x - r):(x + r + 1)].copy()
            cx, cy, mag = compute_centroid(imfrag, mask, grid_x, grid_y)
            if cx > 0:
                xdata.append(cx + x - r)
                ydata.append(cy + y - r)
                mags.append(mag)
                ptr += 1
    return np.array(xdata), np.array(ydata), np.array(mags)

def compute_centroid(imfrag, mask, grid_x, grid_y):
    mean_intensity = np.mean(imfrag[mask])

    # star pixels are in mask and above mean intensity
    candidates = mask & (imfrag > mean_intensity)

    if candidates.any():
        # estimate background and subtract from image
        mean_background = np.mean(imfrag[np.logical_not(candidates)])
        imfrag_sub = candidates * (imfrag - mean_background)       
        wim = np.sum(imfrag_sub)
        wmean = np.mean(imfrag_sub)
        cx = np.sum(grid_x * imfrag_sub) / wim
        cy = np.sum(grid_y * imfrag_sub) / wim
        return cx, cy, wmean

    return -1, -1, -1
