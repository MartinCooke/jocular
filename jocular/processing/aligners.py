''' Home to star registration algorithms; currently
    two but only align_ransac is robust enough for the moment

    This is not part of the current Jocular release
'''

import warnings
import numpy as np
import math
from skimage.measure import ransac
from scipy.spatial.distance import cdist
from skimage.transform import EuclideanTransform, warp, estimate_transform


class AlignerException(Exception):
    pass


def align_ransac(im, keystars, centroids, min_stars=5, min_inliers=4, warp_model=None):
    ''' given a new image with centroids extracted, attempt to align
        against centroids represented by keystars
        return warped image
        raises AlignerException
    '''
    
    # we used to do this but it makes things worse...
    # if warp_model is not None:
    #     keystars = matrix_transform(keystars, warp_model.params)

    nstars = min(len(keystars), len(centroids))

    # find closest matching star to each transformed keystar
    matched_stars = np.zeros((nstars, 2))
    for i, (x1, y1) in enumerate(keystars):
        if i < nstars:
            matched_stars[i, :] = \
                centroids[np.argmin([(x1 - x2) ** 2 + (y1 - y2) ** 2 for x2, y2 in centroids])]

    # do we have enough matched stars?
    if len(matched_stars) < min_stars:
        raise AlignerException('not enough matched stars')
                
    # apply RANSAC to find which matching pairs best fitting Euclidean model
    # can throw a warning in cases where no inliers (bug surely) which we ignore
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        warp_model, inliers = ransac(
            (np.array(keystars[:nstars]), matched_stars),
            EuclideanTransform, 4, .5, max_trials=100)

        # if inliers is None:
        #     print('inliers is None')
        # elif sum(inliers) < min_inliers:
        #     print('sum inliers {:} less than min inliers {:}'.format(sum(inliers), min_inliers))

        # managed to align, so return warped image
        if (inliers is not None) and (sum(inliers) >= min_inliers):
            return warp(im, warp_model, order=3, preserve_range=True), warp_model

    raise AlignerException('not enough inliers after RANSAC')



def align_martin(im, keystars, centroids, min_stars=10):

    # assumes keystars and centroids are ordered by magnitude


    matches, _ = fastmatch(
        ref=keystars,
        im=centroids,
        match_threshold=5,  # pixels
        target_matches=25
    )

    if matches is None:
        raise AlignerException('no alignments found')
       
    src = keystars[[j for (i, j) in matches], :]
    dst = centroids[[i for (i, j) in matches], :]

    if len(src) < min_stars:
        raise AlignerException('not enough stars to align ({:} but need {:})'.format(len(src), min_stars))

    warp_model = estimate_transform('euclidean', src, dst)
    return warp(im, warp_model, order=3, preserve_range=True), warp_model
    

def fastmatch(
    ref=None,            # N x 2 array of centroids from keystars image
    im=None,             # N x 2 array of centroids from comparison image
    depth=5,             # points ordered by decreasing mag, so how far down do we go
    match_threshold=1 ,  # proximity in same units as centroids to claim a match
    target_matches=20,   # desired number of matches required before returning solution
    max_rot=90,           # degrees
    max_scale=100,        # percent
    max_translation=50   # in pixels
):
    ''' matches 2D point clouds allowing for rotatiom, translation and scaling
        limits on each of these can be set; if None, don't apply any limits
    '''
    max_matches = 0
    best_matches = None
    kk = match_threshold ** 2
    n_im, n_ref = len(im), len(ref)
    cnt = 0
    if max_scale is not None:
        min_scale = (100 - max_scale) / 100
        max_scale = (100 + max_scale) / 100

    for i1 in range(0, n_im):
        # normalise image based on star index i1
        im1 = im - im[i1, :]
        for i2 in [i for i in range(i1 + 1, min(n_im, i1 + depth)) if i != i1]:
            # rotate and scale so i2 is at (1, 0)
            cos, sin = im1[i2, 0], -im1[i2, 1]
            rot1 = np.degrees(math.atan2(sin, cos))
            d = cos ** 2 + sin ** 2
            im2 = np.dot(im1, np.array([[cos, -sin], [sin, cos]]).T) / d
            # match threshold takes into account scaling by d
            mt = kk / d  # we match squared dist
            min_x, min_y = np.min(im2, axis=0) - mt
            max_x, max_y = np.max(im2, axis=0) + mt
            for r1 in range(0, n_ref):
                ref1 = ref - ref[r1, :]
                for r2 in [
                    r for r in range(r1 + 1, min(n_ref, r1 + depth)) if r != r1
                ]:
                    cos, sin = ref1[r2, 0], -ref1[r2, 1]
                    rot2 = np.degrees(math.atan2(sin, cos))
                    # is rotation within limits?
                    if max_rot is None or np.abs(rot1 - rot2) < max_rot:
                        d2 = cos ** 2 + sin ** 2
                        scaling = (d/d2)**.5
                        # is scaling within limits?
                        if max_scale is None or scaling > min_scale and scaling < max_scale:
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
                                    return matches, cnt
                                if n_matches > max_matches:
                                    max_matches = n_matches
                                    best_matches = matches
        # return matches
    return best_matches, cnt


