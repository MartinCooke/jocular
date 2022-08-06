''' Jocular component that manages platesolving. Makes use of
    available platesolvers in platesolvers.py
'''


from loguru import logger

from kivy.properties import NumericProperty

from jocular.utils import toast
from jocular.component import Component
from jocular.settingsmanager import JSettings
from jocular.processing.platesolvers import platesolve, PlatesolverException


class PlateSolver(Component, JSettings):

    match_arcsec = NumericProperty(15)
    focal_length = NumericProperty(800)
    pixel_height = NumericProperty(8.4)
    n_stars_in_image = NumericProperty(30)
    min_sigma = NumericProperty(3)
    max_sigma = NumericProperty(5)
    star_thresh = NumericProperty(.001)
    min_matches = NumericProperty(10)
    target_matches = NumericProperty(10)
    binning = NumericProperty(1)

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
            'help': 'Pixel height of sensor; will be obtained from FITs where possible)'
            }),
        ('binning', {
            'name': 'binning', 'float': (1, 4, 1),
            'fmt': '{:.0f}',
            'help': 'If binning, specify amount here; will be obtained from FITs where possible (1=no binning)'
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
        ('target_matches', {
            'name': 'target number of stars to match', 'float': (5, 30, 1),
            'fmt': '{:.0f} stars',
            'help': 'stop when we reach this many matches; set to same as min_matches to return first match (factory: 25)'
            }),
        ('match_arcsec', {
            'name': 'star proximity for matching', 'float': (5, 25, 1),
            'fmt': '{:.0f} arcsec',
            'help': 'How close reference and image stars must be to match, in arcsec (factory: 15)'
            })
        ]

    def on_new_object(self):
        self.info('')
        self.fov = None
        self.fwhm = None


    def describe(self):
        return {'fov': self.fov, 'fwhm': self.fwhm}


    def solve(self):
        ''' Called when user clicks 'solve'. Try to solve currently displayed image.
        '''

        star_db = Component.get('Catalogues').get_star_db()

        if star_db is None:
            toast('Cannot solve: no platesolving database available')
            return

        ra0, dec0 = Component.get('DSO').current_object_coordinates()
        if ra0 is None:
            toast('Cannot solve: unknown DSO')
            self.info('unknown DSO')
            return

        # get current image
        im = Component.get('Stacker').get_current_displayed_image()
        if im is None:
            toast('Cannot solve: no current image')
            self.info('no current image')
            return

        pixel_height = Component.get('Stacker').get_pixel_height()
        # if we don't know pixel height, use user-supplied values
        if pixel_height is None:
            pixel_height = self.binning * self.pixel_height

        dpp = (pixel_height * 1e-6 / self.focal_length) * (206265 / 3.6)

        try:
            soln = platesolve(
                im=im, 
                ra0=ra0, 
                dec0=dec0, 
                star_db=star_db,
                degrees_per_pixel=dpp,
                verbose=True,
                nstars=self.n_stars_in_image, 
                star_method='photutils', 
                min_matches=self.min_matches,
                match_arcsec=self.match_arcsec,
                target_matches=self.target_matches
                ) 

        except PlatesolverException as e:
            logger.warning(e)
            toast(str(e))
            self.info(str(e))
            return

        desc = f"{soln['fov_w']:5.3f} x {soln['fov_h']:5.3f}, {soln['north']:.0f}\u00b0, RA: {soln['ra']} Dec: {soln['dec']}"

        logger.info(desc)

        fwhm = soln['fwhm'] * dpp * 3600.
        self.fwhm = fwhm
        self.fov = f"{soln['fov_w']:.2f}\u00b0 x {soln['fov_h']:.2f}\u00b0"

        self.info('fwhm: {:.1f}" | fov: {:.2f}\u00b0 x {:.2f}\u00b0'.format(
            fwhm,
            soln['fov_w'], 
            soln['fov_h']))

        toast(desc, duration=3)

        Component.get('Annotator').annotate(soln)


