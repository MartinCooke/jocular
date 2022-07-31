''' View: represents the actual image on the screen; works with
    ScatterView class
'''

import os
import time
import numpy as np
from loguru import logger

from kivy.app import App
from kivy.graphics.texture import Texture
from kivy.graphics.transformation import Matrix
from kivy.properties import (
    BooleanProperty, NumericProperty, 
    BoundedNumericProperty, ListProperty
    )
from kivy.core.window import Window

from jocular.utils import toast
from jocular.component import Component
from jocular.settingsmanager import JSettings
from jocular.metrics import Metrics
from jocular.widgets.scatterview import ScatterView


class View(Component, JSettings):  # must be in this order

    zoom = NumericProperty(0)
    invert = BooleanProperty(False)
    orientation = BoundedNumericProperty(0, min=0, max=360)
    show_reticle = BooleanProperty(False)
    brightness = NumericProperty(1)
    is_dimmed = BooleanProperty(False)
    transparency = NumericProperty(0)
    ROI = ListProperty(None, allownone=True)
    flip_UD = BooleanProperty(False)
    flip_LR = BooleanProperty(False)
    min_zoom = NumericProperty(.5)
    max_zoom = NumericProperty(30)
    zoom_power = NumericProperty(1)
    continuous_update = BooleanProperty(True)


    configurables = [
        ('flip_UD', {
            'name': 'flip up-down?', 
            'switch': '',
            'help': 'Flip image in the vertical plane. '}),
        ('flip_LR', {
            'name': 'flip left-right?', 
            'switch': '',
            'help': 'Flip image in the horizontal plane'}),
        ('continuous_update', {
            'name': 'update continuously?', 
            'switch': '',
            'help': 'Controls update display continuously by default (takes effect on restart)'}),
        ('min_zoom', {
            'name': 'minimum zoom', 'float': (.2, 1, .1),
            'fmt': '{:.1f} times',
            'help': 'amount of zoom at the low end of the zoom slider'}),
        ('max_zoom', {
            'name': 'max zoom', 'float': (10, 50, 1),
            'fmt': '{:.0f} times',
            'help': 'amount of zoom at the high end of the zoom slider'}),
        ('zoom_power', {
            'name': 'zoom power', 'float': (.5, 2, .1),
            'fmt': 'zoom ^ {:.2f}',
            'help': 'apply a power curve to provide more sensitivity'})
        ]


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cached_image = None
        self.last_image_time = 0
        self.app = App.get_running_app()        
        self.scatter = ScatterView(self)
        self.app.gui.add_widget(self.scatter, index=100)
        self.scatter._set_center((0, 0))
        self.ring_selected = False
        self.image_selected = False
        self.old_transparency = self.transparency
        self.old_brightness = self.brightness
        # logger.debug(f'View scatter {self.scatter}')


    def on_new_object(self):
        ''' until we receive the new object size we cannot zoom, 
            so zoom first draw
        '''
        self.reset()


    def on_previous_object(self):
        ''' Reset read for previous observation but also match
            orientation to that stored
        '''
        self.reset()
        self.orientation_settings = Component.get('Metadata').get({'orientation'}) 


    def reset(self):
        # Keep as separate method because most likely called on stack reset
        self.ROI = None
        self.pre_ROI_image = None   # stored so we can undo ROI
        self.last_image = None
        self.reset_texture()
        self.update_state()


    def on_save_object(self):
        Component.get('Metadata').set('orientation', self.orientation)


    def on_show_reticle(self, *args):
        self.app.gui.gui['reticle']['widget'].show = self.show_reticle


    def on_brightness(self, *args):
        self.app.brightness = self.brightness


    def on_transparency(self, *args):
        self.app.transparency = max(0, self.transparency)


    def update_state(self):
        s = 'L-R, ' if self.flip_LR else ''
        s += 'U-D' if self.flip_UD else ''
        if s.endswith(', '):
            s = s[:-2]
        flipstr = f' | flip {s}' if s else ''
        invstr = ' | inv' if self.invert else ''
        self.info(f'rot {self.orientation:.0f}\u00b0 | {self.lever_to_zoom(self.zoom):4.1f}x{flipstr}{invstr}')
        Component.get('Annotator').update()


    def lever_to_zoom(self, z):
        return self.min_zoom + (z ** self.zoom_power) *(self.max_zoom - self.min_zoom)


    def zoom_to_lever(self, z):
        if z < self.min_zoom: 
            return 0
        return ((z - self.min_zoom) / (self.max_zoom - self.min_zoom)) ** (1 / self.zoom_power)


    def on_zoom(self, *args):
        # zoom anchored on window centre
        scale = self.lever_to_zoom(self.zoom) / self.scatter.scale
        mat = Matrix().scale(scale, scale, scale)
        self.scatter.apply_transform(mat, anchor=Metrics.get('origin'))
        self.update_state()


    def on_orientation(self, *args):
        # rotate anchored on window center
        rot = self.orientation - self.scatter._get_rotation()
        self.scatter.apply_transform(Matrix().rotate((np.pi/180)*rot, 0 ,0, 1), anchor=Metrics.get('origin'))
        self.update_state()


    def fit_to_window(self, zero_orientation=True, *args):
        ''' Apply original orientation (from sensor) to image
            and set zoom to just fit to window
        '''
        if self.last_image is None:
            return
        shape = self.last_image.shape
        h, w = shape[0], shape[1]  # done like this because might be 3-D
        if w < 101:
            return
        z = self.zoom_to_lever(Window.height / h)
        App.get_running_app().gui.set('zoom', z)
        self.zoom = z
        if zero_orientation:
            self.orientation = 0
        self.scatter._set_center(Metrics.get('origin'))


    def apply_ROI(self, *args):
        ''' force or undo ROI
        '''

        if Component.get('ObjectIO').existing_object:
            toast('ROI only applies to live captures at present', 3)
            return

        # only allow ROI if we have an image
        if self.last_image is None:
            return

        # if we are undoing a ROI, load pre-ROI image if we have one
        if self.ROI is not None:
            if self.pre_ROI_image is not None:
                self.display_image(self.pre_ROI_image)
                self.fit_to_window(zero_orientation=False)
            # signal ROI change
            self.ROI = None
            return

        ''' before applying a ROI,  store a copy of the current image
        '''
        self.pre_ROI_image = self.cached_image.copy()

        # extract its dims
        shape = self.pre_ROI_image.shape
        h, w = shape[0], shape[1]  # done like this because might be 3-D

        xc, yc = Metrics.get('origin')
        r = Metrics.get('inner_radius') # could add * 1.05 as a margin

        # converts from screen to image pixels
        mapping = self.scatter.to_local

        # pixel coords of centre
        xcp, ycp = mapping(xc, yc)

        # pixel coords of edge
        xep, yep = mapping(xc - r, yc)

        # distance in pixels
        dpix = ((xcp - xep) ** 2 + (ycp - yep) ** 2) ** 0.5

        # don't allow width < min width
        min_width = 32
        dpix = int(max(dpix, min_width // 2))
  
        # ensure image is in eyepiece fully
        if (xcp + dpix > w) or (ycp + dpix > h):
            toast('Must have image completely in eyepiece to apply ROI')
            return

        if self.flip_LR:
            xcp = (w - xcp)
        if self.flip_UD:
            ycp = (h - ycp)

        self.ROI = (
            max(0, int(xcp) - dpix), 
            2 * dpix, 
            max(0, int(ycp) - dpix), 
            2 * dpix)


    def on_ROI(self, *args):
        cam = Component.get('Camera')
        cam.set_ROI(self.ROI)
        self.app.gui.gui['apply_ROI']['widget'].color = \
            self.app.lowlight_color if self.ROI is None else self.app.theme_cls.primary_color

        if self.ROI is not None:
            xstart, width, ystart, height = self.ROI
            im = self.pre_ROI_image[ystart: ystart + height, xstart: xstart + width]
            self.reset_texture(w=width, h=width)
            self.display_image(im)


    def on_invert(self, *args):
        if self.last_image is None:
            return
        # only invert if not colour image    
        if self.scatter.ids.image.texture.colorfmt == 'luminance':
            self.display_image(use_cached_image=True)
            self.update_state()
        elif self.invert:
            self.invert = False


    def on_flip_LR(self, *args):
        self.display_image(use_cached_image=True)
        self.update_state()


    def on_flip_UD(self, *args):
        self.display_image(use_cached_image=True)
        self.update_state()

 
    def reset_texture(self, w=10, h=10, colorfmt='luminance'):
        self.scatter.ids.image.size = w, h
        self.scatter.ids.image.texture = Texture.create(size=(w, h), colorfmt=colorfmt)
        self.scatter._set_center(Metrics.get('origin'))
        self.w, self.h = w, h
        self.colorfmt = colorfmt
        logger.debug(f'texture reset w {w} h {h} colorfmt {colorfmt}')


    def display_blank(self):
        self.display_image(0 * np.ones((self.w, self.h)))


    def do_flips(self, im):
        # perform flips (< 1 ms)
        if self.flip_UD:
            im = im[::-1]
        if self.flip_LR:
            im = np.fliplr(im)
        return im


    def display_image(self, im=None, use_cached_image=False):
        ''' Called with an image, in which case update cached image, perform flips etc
        and display; or without an image, in which case use cached image and perform
        flips/invert directly on that.
        '''

        if (im is None) and (not use_cached_image):
            return

        if use_cached_image and (self.cached_image is None):
            return

        if im is not None:
            self.cached_image = im

        if use_cached_image:
            im = self.cached_image  # just for shorthand below

        # we now have a cached image
        colorfmt = 'luminance' if im.ndim == 2 else 'rgb'

        # check if shape or color has changed
        h, w = im.shape[0], im.shape[1]
        if (w != self.w) or (h != self.h) or (colorfmt != self.colorfmt):
            old_center = self.scatter._get_center()
            self.reset_texture(w=w, h=h, colorfmt=colorfmt)
            self.scatter._set_center(old_center)

        im = self.do_flips(im)

        # only invert if luminance and not RGB image
        if self.invert and colorfmt == 'luminance':
            im = np.subtract(1, im, dtype=im.dtype)

        self.last_image = np.uint8(im * 255)
        self.scatter.ids.image.texture.blit_buffer(
            self.last_image.flatten(), 
            colorfmt=colorfmt, 
            bufferfmt='ubyte')

        # first time through for each object, apply settings
        if hasattr(self, 'orientation_settings') and self.orientation_settings is not None:
            z = self.zoom_to_lever(Window.height / self.last_image.shape[0])
            App.get_running_app().gui.set('zoom', z)
            self.zoom = z
            if 'orientation' in self.orientation_settings:
                self.orientation = self.orientation_settings['orientation']
            self.scatter._set_center(Metrics.get('origin'))
            self.invert = False
            self.orientation_settings = None  # indicates that they have been applied

        # refresh image for monitor at most every 300 ms
        # currently disabled
        if False:
            if (time.time() - self.last_image_time) > .3:
                np.save(os.path.join(self.last_image_dir, f'im_{time.time()}.npy'), 
                    self.last_image)
                self.last_image_time = time.time()

