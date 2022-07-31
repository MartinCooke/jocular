import math

from kivy.lang import Builder
from kivy.uix.scatter import Scatter

from jocular.uranography import angle360
from jocular.component import Component
from jocular.metrics import Metrics


Builder.load_string('''

<ScatterView>:
    size: image.size
    size_hint: None, None 
    auto_bring_to_front: False
    do_rotation: True
    do_translation: True
    do_scale: True
    Image:
        id: image
''')


class ScatterView(Scatter):
    ''' A class representing the moveable image displayed in
        the eyepiece
    '''

    def __init__(self, controller, **kwargs):
        super().__init__(**kwargs)
        self.controller = controller


    def on_touch_down(self, touch):
        # check if touch is within eyepiece and if so, where

        x, y = touch.pos
        xc, yc = Metrics.get('origin')
        r = (((xc - x) ** 2 + (yc - y) ** 2) ** .5) / Metrics.get('inner_radius')

        # touch is not in the eyepiece
        if r  >  .98:
            return False

        # in image
        in_image = self.collide_point(*touch.pos)

        # is it in the outer zone of the image, or not touching image, rotate
        if not in_image or r > .8:
            self.controller.ring_selected = True
            self.theta = math.atan2(y - yc, x - xc) / (math.pi/ 180)
            self.xc = xc
            self.yc = yc
            return True

        if in_image:
            if touch.is_double_tap:
                self.controller.invert = not self.controller.invert
                return True
            self.controller.image_selected  = True
            self.last_x = x
            self.last_y = y
            return True

        return False


    def on_touch_move(self, touch):
        if self.controller.ring_selected:
            x, y = touch.pos
            theta = math.atan2(y - self.yc, x - self.xc) / (math.pi / 180)
            self.controller.orientation = angle360(self.controller.orientation + (theta - self.theta))
            self.theta = theta
            return True
        if self.controller.image_selected:
            x, y = touch.pos
            delta_x = (x - self.last_x)
            delta_y = (y - self.last_y)
            self.x += delta_x
            self.y += delta_y
            self.last_x = x
            self.last_y = y
            Component.get('Annotator').update()
            return True
        return False


    def on_touch_up(self, touch):
        self.controller.ring_selected = False
        self.controller.image_selected = False

