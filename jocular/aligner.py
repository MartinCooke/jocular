""" aligner
"""

import warnings
import numpy as np

from skimage.measure import ransac
from skimage.transform import EuclideanTransform, matrix_transform, warp

from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from loguru import logger

from jocular.component import Component
from jocular.settingsmanager import JSettings
from jocular.processing.starextraction import extract_stars


class Aligner(Component, JSettings):
    """RANSAC-based image aligner"""

    do_align = BooleanProperty(True)
    ideal_star_count = NumericProperty(30)
    min_stars = NumericProperty(5)
    binfac = NumericProperty(1)
    star_method = StringProperty("DoG")
    centroid_method = StringProperty("simple")
    do_warp = BooleanProperty(True)

    configurables = [
        (
            "do_align",
            {
                "name": "align?",
                "switch": "",
                "help": "Switching align off can help diagnose tracking issues",
            },
        ),
        (
            "star_method",
            {
                "name": "star extraction method",
                "options": ["DoG", "photutils"],
                "help": "DoG is the original Jocular method; photutils may be faster",
            },
        ),
        (
            "centroid_method",
            {
                "name": "centroid extraction method",
                "options": ["simple", "experimental"],
                "help": "simple is the original method; experimental may be more accurate",
            },
        ),
        (
            "ideal_star_count",
            {
                "name": "ideal number of stars",
                "float": (10, 100, 5),
                "help": "Detect this many stars per sub (30 for DoG, more for photutils)",
                "fmt": "{:.0f} stars",
            },
        ),
        (
            "min_stars",
            {
                "name": "minimum number of matching stars",
                "float": (3, 20, 1),
                "help": "require this many matches for sub to be aligned",
                "fmt": "{:.0f} stars",
            },
        ),
        (
            "binfac",
            {
                "name": "bin image?",
                "float": (1, 4, 1),
                "help": "Extract stars from binned image (faster but use with care)",
                "fmt": "{:.0f}",
            },
        ),
        (
            "do_warp",
            {
                "name": "project keystars?",
                "switch": "",
                "help": "Use warp model from previous sub to shift keystars prior to matching",
            },
        ),
    ]


    def __init__(self):
        super().__init__()
        self.reset()


    def on_new_object(self):
        self.reset()


    def reset(self):
        self.keystars = None
        self.warp_model = None
        self.align_count = 0
        self.starcounts = []
        self.info("reset")


    def align(self, sub):

        if not self.do_align:
            return

        # extract stars & compute centroids
        stars = extract_stars(
            sub.get_image(),
            star_method=self.star_method,
            centroid_method=self.centroid_method,
            binfac=self.binfac,
            target_stars=self.ideal_star_count,
            nstars=None,
            reset_threshold=self.keystars is None,
        )

        nstars = stars["nstars"]
        self.starcounts += [nstars]

        if nstars > 0:
            sub.fwhm = np.median(stars["fwhm"])

        sub.aligned = False

        # if enough stars, try to align
        if nstars > self.min_stars:
            centroids = np.transpose([stars["xcentroid"], stars["ycentroid"]])

            # first sub with stars -> keystars
            if self.keystars is None:
                self.keystars = centroids
                sub.aligned = True

            else:
                # star registration
                self.warp_model = register(
                    centroids,
                    self.keystars,
                    min_stars=self.min_stars,
                    warp_model=self.warp_model if self.do_warp else None,
                )

                if self.warp_model is not None:
                    sub.image = warp(
                        sub.image, self.warp_model, order=3, preserve_range=True
                    )
                    sub.aligned = True

        if sub.aligned:
            # default sub staus is select (set in Image)
            # but if it was not rejected by user, change it to select
            # since alignment has been successful
            if sub.status == "nalign":
                sub.status = "select"
            self.align_count += 1
        else:
            sub.status = "nalign"

        sc = np.array(self.starcounts)
        self.info(
            f"{self.align_count}/{len(sc)} subs | {np.min(sc)}-{np.max(sc)} stars"
        )


def register(stars, keystars, min_stars=None, warp_model=None):
    """Find a Euclidean transformation that matches stars
    against keystars, returning the warp model
    or None if number of inliers after RANSAC is
    less than min_stars
    """

    logger.debug("registering")

    # if we have a warp model (from prev registration),
    # use it to move keystars in the right direction
    # prior to matching stars [it does make a slight difference]
    keys = keystars.copy()
    if warp_model is not None:
        keys = matrix_transform(keys, warp_model.params)

    # find closest matches between (warped) keystars and stars
    nstars = min(len(keystars), len(stars))
    matched_stars = np.zeros((nstars, 2))
    for i, (x1, y1) in enumerate(keystars):
        if i < nstars:
            matched_stars[i, :] = stars[
                np.argmin([(x1 - x2) ** 2 + (y1 - y2) ** 2 for x2, y2 in stars])
            ]

    # do we have enough matched stars?
    if len(matched_stars) < min_stars:
        return None

    # apply RANSAC to find which matching pairs best fitting Euclidean model
    # can throw a warning in cases where no inliers (bug surely) which we ignore
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        warp_model, inliers = ransac(
            (np.array(keystars[:nstars]), matched_stars),
            EuclideanTransform,
            min_stars,
            0.5,
            max_trials=100,
        )

    # enough?
    if inliers is None or sum(inliers) < min_stars:
        return None

    return warp_model
