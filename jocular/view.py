''' View: represents the actual image on the screen
'''

import os
import time
import numpy as np
import math

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.scatter import Scatter
from kivy.graphics.texture import Texture
from kivy.graphics.transformation import Matrix
from kivy.properties import (
    BooleanProperty, 
    NumericProperty, 
    BoundedNumericProperty, 
    ConfigParserProperty
)
from kivy.core.window import Window
from kivy.base import stopTouchApp

from jocular.utils import angle360
from jocular.component import Component
from jocular.metrics import Metrics
from jocular.widgets import JBubble

Builder.load_string('''
<View>:
    size: image.size
    size_hint: None, None 
    auto_bring_to_front: False
    do_rotation: True
    do_translation: True
    do_scale: True
    Image:
        id: image
''')

class View(Scatter, Component):

    zoom = NumericProperty(0)  # zoom lever ranges from 0 to 1 and maps from min-max zoom using curve
    show_help = BooleanProperty(False)
    invert = BooleanProperty(False)
    orientation = BoundedNumericProperty(0, min=0, max=360)
    show_reticle = BooleanProperty(False)
    brightness = NumericProperty(0)
    transparency = NumericProperty(0)
    flip_UD = ConfigParserProperty(0, 'Flipping', 'flip_UD', 'app', val_type=int)
    flip_LR = ConfigParserProperty(0, 'Flipping', 'flip_LR', 'app', val_type=int)
    min_zoom = ConfigParserProperty(.5, 'Zoom', 'min_zoom', 'app', val_type=float)
    max_zoom = ConfigParserProperty(30, 'Zoom', 'max_zoom', 'app', val_type=float)
    zoom_power = ConfigParserProperty(1, 'Zoom', 'zoom_power', 'app', val_type=float)
    confirm_on_close = ConfigParserProperty(0, 'Confirmations', 'confirm_on_close', 'app', val_type=int)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cached_image = None
        self.last_image_time = 0
        self.app = App.get_running_app()
        # self.last_image_dir = 'lastimage'
        # add_if_not_exists(self.last_image_dir) # need to fix this
        self.app.gui.add_widget(self, index=100)
        self._set_center((0, 0))
        self.ring_selected = False
        self.image_selected = False

    def reset(self):
        # Keep as separate method because most likely called on stack reset
        self.last_image = None
        self.reset_texture()

    def on_new_object(self):
        # until we receive the new object' sizes we cannot really zoom, so do this on first draw
        self.reset()
        # preserve orientation for new objects
        if Component.get('ObjectIO').existing_object:
            self.settings = Component.get('Metadata').get({'orientation'})

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
        flipstr = ' | flip {:}'.format(s) if s else ''
        invstr = ' | inv' if self.invert else ''
        self.info('rot {:.0f}\u00b0 | {:4.1f}x{:}{:}'.format(
            self.orientation, self.lever_to_zoom(self.zoom), flipstr, invstr))
        Component.get('Annotator').update()

    def lever_to_zoom(self, z):
        return self.min_zoom + (z ** self.zoom_power) *(self.max_zoom - self.min_zoom)

    def zoom_to_lever(self, z):
        if z < self.min_zoom: 
            return 0
        return ((z - self.min_zoom) / (self.max_zoom - self.min_zoom)) ** (1 / self.zoom_power)

    def on_zoom(self, *args):
        # zoom anchored on window centre
        scale = self.lever_to_zoom(self.zoom) / self.scale
        mat = Matrix().scale(scale, scale, scale)
        self.apply_transform(mat, anchor=Metrics.get('origin'))
        self.update_state()

    # eventually find a better place for these
    def confirm_close(self, *args):
        if self.confirm_on_close:
            JBubble(actions={'Really close?': self.close}, loc='mouse').open()
        else:
            self.close()

    def close(self, *args):
        stopTouchApp()

    def open_settings(self, *args):
        self.app.open_settings()
 
    def on_orientation(self, *args):
        # rotate anchored on window center
        rot = self.orientation - self._get_rotation()
        self.apply_transform(Matrix().rotate((np.pi/180)*rot, 0 ,0, 1), anchor=Metrics.get('origin'))
        self.update_state()

    def fit_to_window(self, *args):
        # compute zoom to fit to window
        if self.last_image is None:
            return
        shape = self.last_image.shape
        h, w = shape[0], shape[1]  # done like this because might be 3-D
        if  w < 101:
            return
        z = self.zoom_to_lever(Window.height / h)
        App.get_running_app().gui.set('zoom', z)
        self.zoom = z
        self.orientation = 0
        self._set_center(Metrics.get('origin'))

    def on_invert(self, *args):
        if self.last_image is None:
            return
        # only invert if not colour image    
        if self.ids.image.texture.colorfmt == 'luminance':
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
        self.ids.image.size = h, w
        self.ids.image.texture = Texture.create(size=(h, w), colorfmt=colorfmt)
        self._set_center(Metrics.get('origin'))
        self.w, self.h = w, h
        self.colorfmt = colorfmt

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
        w, h = im.shape[0], im.shape[1]
        if (w != self.w) or (h != self.h) or (colorfmt != self.colorfmt):
            # for some reason, image is recentered after texture reset but orientation/size not affected 
            old_center = self._get_center()
            self.reset_texture(w=w, h=h, colorfmt=colorfmt)
            self._set_center(old_center)

        im = self.do_flips(im)

        # only invert if luminance and not RGB image
        if self.invert and colorfmt == 'luminance':
            im = np.subtract(1, im, dtype=im.dtype)

        self.last_image = np.uint8(im * 255)
        self.ids.image.texture.blit_buffer(self.last_image.flatten(), colorfmt=colorfmt, bufferfmt='ubyte')

        # first time through for each object, apply settings
        if hasattr(self, 'settings') and self.settings is not None:
            z = self.zoom_to_lever(Window.height / self.last_image.shape[0])
            App.get_running_app().gui.set('zoom', z)
            self.zoom = z
            if 'orientation' in self.settings:
                self.orientation = self.settings['orientation']
            self._set_center(Metrics.get('origin'))
            self.invert = False
            self.settings = None  # indicates that they have been applied

        # refresh image for monitor at most every 300 ms
        # currently disabled
        if False:
            if (time.time() - self.last_image_time) > .3:
                np.save(os.path.join(
                    self.last_image_dir, 'im_{:}.npy'.format(time.time())), self.last_image)
                self.last_image_time = time.time()


    # handle mouse events for rotation/translation

    def on_touch_down(self, touch):
        # check if touch is within eyepiece and if so, where

        x, y = touch.pos
        xc, yc = Metrics.get('origin')
        r = (((xc - x) ** 2 + (yc - y) ** 2) ** .5) / Metrics.get('inner_radius')

        # touch is not in the eyepiece
        if r  >  .98:
            return False

        # in image
        in_image = self.collide_point(*touch.pos)

        # is it in the outer zone of the image, or not touching image, rotate
        if not in_image or r > .8:
            self.ring_selected = True
            self.theta = math.atan2(y - yc, x - xc) / (math.pi/ 180)
            self.xc = xc
            self.yc = yc
            return True

        if in_image:
            if touch.is_double_tap:
                self.invert = not self.invert
                return True
            self.image_selected  = True
            self.last_x = x
            self.last_y = y
            return True

        return False

    def on_touch_move(self, touch):
        if self.ring_selected:
            x, y = touch.pos
            theta = math.atan2(y - self.yc, x - self.xc) / (math.pi / 180)
            self.orientation = angle360(self.orientation + (theta - self.theta))
            self.theta = theta
            return True
        if self.image_selected:
            x, y = touch.pos
            self.x += (x - self.last_x)
            self.y += (y - self.last_y)
            self.last_x = x
            self.last_y = y
            Component.get('Annotator').update()
            return True
        return False

    def on_touch_up(self, touch):
        self.ring_selected = False
        self.image_selected = False
