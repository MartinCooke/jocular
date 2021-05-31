''' Special-purpose widgets for Jocular
'''

import math
from math import radians

from kivy.uix.boxlayout import BoxLayout
from kivy.lang import Builder
from kivy.uix.label import Label
from kivy.properties import (
    NumericProperty,
    ObjectProperty,
    BooleanProperty,
    StringProperty,
    ListProperty,
)
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.vector import Vector
from kivy.graphics.transformation import Matrix
from kivymd.uix.button import MDIconButton

from jocular.utils import angle360

Builder.load_string(
    '''

#:import Clipboard kivy.core.clipboard.Clipboard

<Rotatable>:
    canvas.before:
        PushMatrix
        Translate:
            x: -self.width/2
            y: -self.height/2
        Rotate:
            angle: self.rotangle if self.rotated else 0
            origin: self.center
    canvas.after:
        PopMatrix

<JWidget>:
    # canvas.before:
    #     Color:
    #         rgb: 1, 0, 0
    #         a: .9
    #     Ellipse:
    #         pos: self.pos
    #         size: self.size
    size_hint: None, None
    # highlight_color: app.highlight_color
    highlight_color: app.theme_cls.accent_palette
    background_color: .6, 0, .6, 0
    color: app.lowlight_color
    # color: app.theme_cls.primary_color
    disabled_color: .1, .1, .1, 1   
    markup: True
    halign: 'center'
    valign: 'middle'
    size: self.texture_size
    font_size: app.ring_font_size
    text_size: None, None  # forces size to be that of text
    padding: 2, 2

<JFilterButton>:
    canvas.before:
        Color:
            rgb: self.filter_color
            a: .9
        Ellipse:
            pos: self.pos
            size: self.size
    markup: True
    color: (.1, .1, .1, 1)
    background_color: 0, 0, 0, 0
    size: dp(28), dp(28)
    font_size: '16sp'
    size_hint: None, None

<JLever>:
    color: app.lever_color

<JIconButton>:
    text: self.myicon

<JToggleButton>:
    # color: app.highlight_color if self.state == 'down' else app.lowlight_color
    color: app.theme_cls.accent_color if self.state == 'down' else app.lowlight_color

<ELabel>:
    size_hint: 1, None
    markup: True
    text_size: self.size

<ParamValue>:
    size_hint: 1, None
    height: dp(20)
    Button:
        size_hint: None, 1
        markup: True
        halign: 'left'
        text_size: self.size
        color: app.lowlight_color
        # color: app.theme_cls.primary_color
        font_size: app.info_font_size
        background_color: .6, 0, .6, 0
        width: dp(65)
        padding: dp(3), dp(1)
        text: '[b]{:}[/b]'.format(root.param)
        on_press: root.callback() if root.callback else root.null_action()
    Button:
        size_hint: None, 1
        markup: True
        halign: 'left'
        text_size: self.size
        color: app.lowlight_color
        #color: app.theme_cls.primary_color
        font_size: app.info_font_size
        background_color: .6, 0, .6, 0
        width: dp(220)
        text: '{:}'.format(root.value)

<Panel>:
    canvas:
        Color:
            rgba: .2, .2, .2, .8
        Rectangle:
            pos: self.pos
            size: self.width, self.height
    padding: 20, 20
    orientation: 'vertical'
    size_hint: None, None
    size: dp(450), dp(450)
    pos_hint: {'center_x': 10, 'center_y': .5}


<LabelR>:
    halign: 'right'
    valign: 'middle'
    text_size: self.size
    padding: [dp(7), 0]

<LabelL>:
    halign: 'left'
    valign: 'middle'
    text_size: self.size
    padding: [dp(7), 0]

# vertically aligned text box
<TextInputC>:
    padding: [5, self.height / 2.0 - (self.line_height / 2.0) * len(self._lines), 5, self.height / 2.0 - (self.line_height / 2.0) * len(self._lines)]


<WarningBanner>:
    right_action: ['CLOSE', lambda x: None]

'''
)


class TextInputC(TextInput):
    pass

class LabelR(Label): 
    pass

class LabelL(Label): 
    pass

class Panel(BoxLayout):
    ''' Represents the centre panel used for config/choosers etc
    '''

    def show(self, *args):
        self.on_show()
        self.pos_hint = {'center_x': .5, 'center_y': .5}       

    def hide(self, *args):
        self.on_hide()
        self.pos_hint = {'center_x': 10, 'center_y': .5}       

    def on_show(self):
        pass

    def on_hide(self):
        pass

    def toggle(self, *args):
        if self.pos_hint['center_x'] > 1:
            self.show()
        else:
            self.hide()


class ParamValue(BoxLayout):

    param = StringProperty('')
    value = StringProperty('')
    callback = ObjectProperty(None)

    def null_action(self, *args):
        pass


class Polar:
    def __init__(self, origin=[0, 0], angle=0, radius=0):
        self.origin = origin
        self.angle = angle
        self.radius = radius

    def to_pos(self):
        ang = self.angle * math.pi / 180
        return (
            self.origin[0] + self.radius * math.cos(ang),
            self.origin[1] + self.radius * math.sin(ang),
        )

    def dist_to(self, pos):
        return Vector(self.to_pos()).distance(pos)


class Rotatable(Widget, Polar):

    rotangle = NumericProperty(0.0)
    rotated = BooleanProperty(True)
    inv = ObjectProperty(Matrix())

    deltas = {
        (1, True): 0,
        (1, False): -90,
        (2, True): -180,
        (2, False): -90,
        (3, True): -180,
        (3, False): 90,
        (4, True): 0,
        (4, False): 90,
    }

    def __init__(self, radial=False, **kwargs):
        super().__init__(**kwargs)
        self.radial = radial
        self.on_angle()

    def on_angle(self, *args):
        q = min(4, (self.angle // 90) + 1)
        self.pos = self.to_pos()
        self.rotangle = self.angle + self.deltas[(q, self.radial)]
        self.generate_inverse()

    def on_width(self, *args):
        self.generate_inverse()

    def on_height(self, *args):
        self.generate_inverse()

    def relocate(self, origin=None, radius=None):
        self.origin = origin
        self.radius = radius
        # self.pos = self.to_pos() # is this causing issues on Windows?
        ang = self.angle * math.pi / 180
        self.x = self.origin[0] + self.radius * math.cos(
            ang
        )  #  is this causing issues on Windows?
        self.y = self.origin[1] + self.radius * math.sin(
            ang
        )  #  is this causing issues on Windows?
        self.generate_inverse()

    def generate_inverse(self, *args):
        # create forward transformation matrix
        # NB this is done on width and height as well as init
        # because when using texture size to compute size
        # correct w/h info is not available on init!

        ang = radians(self.rotangle) if self.rotated else 0
        t = Matrix().translate(-self.width / 2 - self.x, -self.height / 2 - self.y, 0)
        t = Matrix().rotate(ang, 0, 0, 1).multiply(t)
        t = Matrix().translate(self.x, self.y, 0).multiply(t)
        self.inv = t.inverse()

    def collide_point(self, x, y):
        # transform touchpos using the inverse transform of the rotation
        # takes about 150 microseconds

        xt, yt, _ = self.inv.transform_point(x, y, 0)
        return (self.x < xt < (self.x + self.width)) and (
            self.y < yt < (self.y + self.height)
        )


class JWidget(Widget):
    pass

class JRotWidget(JWidget, Rotatable):
    pass

class JLabel(JRotWidget, Label):
    pass

class JToggleButton(ToggleButton, JRotWidget):
    pass

class JButton(Button, JRotWidget):
    pass

class JIconTextButton(JButton, JRotWidget):
    pass

class JFilterButton(Rotatable, Button):
    filter_color = ListProperty([0.2, 0.2, 0.2, 1])

class JIconButton(JButton, JRotWidget):
    myicon = StringProperty('')


class JMDIconButton(MDIconButton, Rotatable):
    pass

class JMulti(JButton):
    def __init__(self, values=None, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type('on_press')
        if values is None:
            self.values = []
        else:
            self.values = values
        if self.text not in self.values:
            self.values.append(self.text)  #  default is a single state button

    def on_touch_down(self, touch):
        if super().collide_point(*touch.pos):
            #  find location of self.text in self.values
            if len(self.values) > 1:
                loc = [i for i, x in enumerate(self.values) if x == self.text][0] + 1
                if loc == len(self.values):
                    loc = 0
                self.text = self.values[loc]
            self.dispatch('on_press')
            return True
        return False

    def on_press(self):
        pass


def angle_diff(t1, t2):
    # anticlockwise angle between 2 positions relative to 0 = positive x-axis
    return angle360(math.atan2(t2[1] - t1[1], t2[0] - t1[0]) / (math.pi / 180))


class JLever(JRotWidget, Label):

    value = NumericProperty(0.0)
    disabled = BooleanProperty(False)

    def __init__(self, value=0, values=[0, 1], angles=[0, 1], radial=True, springy=None, **kwargs):

        super().__init__(radial=radial, **kwargs)
        self.min_angle, self.max_angle = angles[0], angles[1]
        self.min_value, self.max_value = values[0], values[1]
        self.font_size = '18sp'
        self.springy = springy if springy else None
        self.value = value
        self.selected = False
        self._k = (self.max_angle - self.min_angle) / (self.max_value - self.min_value)
        self.rotangle = self.value_to_angle(self.value)
        self.update(self.rotangle)

    def reset_value(self, v):
        # force update of lever position
        ang = self._k * (v - self.min_value) + self.min_angle
        self.update(ang)

    def value_to_angle(self, v):
        return self._k * (v - self.min_value) + self.min_angle

    def on_touch_down(self, touch):
        if not self.disabled and self.collide_point(*touch.pos):
            self.selected = True
            return True
        return False

        # WAS THIS
        # if self.disabled:
        #     return super().on_touch_down(touch)

        # if self.collide_point(*touch.pos):
        #     self.selected = True
        #     return True
        # return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.selected:
            self.update(angle_diff(self.origin, touch.pos))

    def ang2value(self, angle):
        # x = float(((angle - self.min_angle) / self._k) + self.min_value)
        x = ((angle - self.min_angle) / self._k) + self.min_value
        return min(self.max_value, max(x, self.min_value))

    def on_touch_up(self, touch):
        if self.selected:
            if self.springy is not None:
                self.update(self.value_to_angle(0))
            self.selected = False

    def update(self, angle, update_value=True):
        if update_value:
            mina, maxa = self.min_angle, self.max_angle

            # return if angle outside range
            if (angle < min(mina, maxa)) or (angle > max(mina, maxa)):
                return

            self.value = self.ang2value(angle)

            # convert value to angle in case it hasn't changed
            angle = self.value_to_angle(self.value)

        self.angle = angle
        self.on_angle()


class ELabel(Label):
    pass



joc_icons = {
    'pause': '3',
    'play': 'n',
    'oculus': 'o',
    'last_sub': 'f',
    'first_sub': 'e',
    'next_sub': '>',
    'prev_sub': '<',
    'camera': 'b',
    'reticle': 'v',
    'fit': 'y',
    'stack': 'E',
    'clear': '0',
    'quit': 'Q',
    'settings': 'x',
    'snapshotter': 'o',
    'prev': 'F',
    'list': 'w',
    'lever': '1',
    'dot': '1',
    'redo': 'h',  # was '4'
    'new': 'i',
    'warn': '!',
    'error': 'W',
    'solve': 'T',
    'slew': 'H',
    'info': '}',
}


def jicon(nm, font_size=None, color=None):
    fs = '{:}sp'.format(font_size) if font_size else '16sp'
    icon = joc_icons.get(nm, 'm')
    if color is None:
        return '[font=Jocular][size={:}]{:}[/size][/font]'.format(fs, icon)
    color = {'r': 'ff0000', 'y': 'ffff00', 'g': '00ff00'}[color]
    return '[font=Jocular][size={:}][color={:}]{:}[/color][/size][/font]'.format(fs, color, icon)
