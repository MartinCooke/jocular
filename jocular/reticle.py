''' Basic class to draw reticle
'''

from kivy.properties import NumericProperty, BooleanProperty, ObjectProperty
from kivy.lang import Builder
from kivy.uix.widget import Widget
from kivy.metrics import dp
from kivymd.uix.button import MDIconButton

from jocular.metrics import Metrics
from jocular.component import Component


# NB for kivy prior to RC 2 could use :set inner dp(10)
Builder.load_string('''

#:set inner 10

<Arrow>:
    text_color: app.theme_cls.primary_color
    theme_text_color: "Custom"
    #icon: 'arrow-{:}-thick'.format(root.direction)
    icon: 'arrow-{:}'.format(root.direction)
    x: root.reticle.x + root.xoffset - self.width / 2
    y: root.reticle.y + root.yoffset - self.height / 2 if root.reticle.show and root.reticle.mount else -1000

<Reticle>:
    id: _reticle
    canvas:
        Color: 
            rgba: app.theme_cls.primary_color if root.show else self.disabled_color
        Line:
            circle: self.x, self.y, inner, 0, 360, 100
        Line:
            circle: self.x, self.y, 3 * inner, 0, 360, 100
        Line:
            circle: self.x, self.y, 6 * inner, 0, 360, 100
        Line:
            points: self.x, self.y - inner, self.x, self.y - 2 * self.radius 
        Line:
            points: self.x, self.y + inner, self.x, self.y + 2 * self.radius 
        Line:
            points: self.x - 2 * self.radius , self.y, self.x - inner, self.y
        Line:
            points: self.x + 2 * self.radius , self.y, self.x + inner, self.y
    disabled_color: [0, 0, 0, 0]

''')

class Arrow(MDIconButton):

    xoffset = NumericProperty(0)
    yoffset = NumericProperty(0)
    reticle = ObjectProperty(None)

    def __init__(self, direction='down', rate=1, reticle=None, **kwargs):

        self.direction = direction
        self.rate = rate
        self.reticle = reticle
        dist = dp(20 + self.rate * 80)
        if direction == 'left':
            self.xoffset = -dist
        elif direction == 'right':
            self.xoffset = dist
        elif direction == 'up':
            self.yoffset = dist
        elif direction == 'down':
            self.yoffset = -dist
        self.user_font_size = '{:}sp'.format(20 + 7*rate)
        super().__init__(**kwargs)


class Reticle(Component, Widget):

    radius = NumericProperty(1)
    show = BooleanProperty(False)
    mount = BooleanProperty(False)

    def __init__(self, **kwargs):
        self.pos = Metrics.get('origin')
        self.radius = Metrics.get('ring_radius')['image']
        super().__init__(**kwargs)
        # don't add arrows
        # until mount control working
        # for direction in ['left', 'right', 'up', 'down']:
        #     for rate in [1, 2, 3]:
        #         arrow = Arrow(
        #             direction=direction, rate=rate, reticle=self,
        #             on_press=partial(self.move, direction, rate),
        #             on_release=self.stop_moving)
        #         self.add_widget(arrow)


    # use these if ever get mount control going
    
    # def on_show(self, *args):
    #     if self.show:
    #         # check if we have a mount connected
    #         self.mount = Component.get('Telescope').connected()

    # def move(self, direction, rate, widget):
    #     # supposedly rate is in degrees per second so reduce it as follows
    #     Component.get('Telescope').move(direction=direction, rate=rate)

    # def stop_moving(self, *args):
    #     Component.get('Telescope').stop_moving()
