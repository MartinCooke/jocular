''' Simple widgets for Jocular
    See other classes in jocular.widgets for more
        specialised icons (levers etc)
'''

import math
from math import radians

from kivy.lang import Builder
from kivy.uix.label import Label
from kivy.properties import (
    NumericProperty,
    ObjectProperty,
    BooleanProperty,
    StringProperty,
)
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.vector import Vector
from kivy.graphics.transformation import Matrix
from kivymd.uix.button import MDIconButton
from kivymd.uix.textfield import MDTextField
from kivy.uix.behaviors import ToggleButtonBehavior
from kivymd.uix.button import MDFlatButton
from kivymd.uix.slider import MDSlider

from jocular.help import TooltipBehavior


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
    highlight_color: app.theme_cls.accent_palette
    background_color: .6, 0, .6, 0
    color: app.lowlight_color
    disabled_color: .1, .1, .1, 1   
    markup: True
    halign: 'center'
    valign: 'middle'
    size: self.texture_size
    font_size: app.ring_font_size
    text_size: None, None  # forces size to be that of text
    padding: 2, 2


<JIconButton>:
    text: self.myicon


<JToggleButton>:
    color: app.theme_cls.accent_color if self.state == 'down' else app.lowlight_color


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


# vertically aligned text box
<TextInputC>:
    padding: [5, self.height / 2.0 - (self.line_height / 2.0) * len(self._lines), 5, self.height / 2.0 - (self.line_height / 2.0) * len(self._lines)]


# this works with the kivymd master
<JTextField>:
    size_hint: (None, None)
    width: '140dp'
    line_color_normal: 0, 0, 0, 0
    foreground_color: app.theme_cls.accent_color
    text_color_normal: app.theme_cls.accent_color
    font_size: app.form_font_size # '20sp'
    on_text: root.invalid = False
    # for latest kivymd these two lines produce coloured text
    fill_color_normal: .1, 0, 0, 0
    fill_color_focus: .1, 0, 0, .1
    hint_text_color_normal: [1, 0, 0, 1] if (root.invalid and self.text.strip()) else app.hint_color
    mode: 'fill'
    spacing: dp(2)


# I can't get KivyMD toggle behavior to work so this is my implementation
<JMDToggleButton>:
    size_hint: 1, None 
    shift_y: dp(40)
    height: dp(16)
    #width: dp(50)
    md_bg_color: .25, .25, .25, 1
    theme_text_color: 'Custom'
    text_color: .6, .6, .6, 1
    #font_size: '12sp'
    #border: dp(2), dp(2), dp(2), dp(2)
    #padding_x: dp(1)


<Pin>:
    size_hint: None, None
    size: dp(100), dp(20)
    markup: True
    text_color: app.lowlight_color
    theme_text_color: 'Custom'
    background_color: 0, 0, 0, 0

''')


class Pin(MDFlatButton, TooltipBehavior):
    
    def __init__(self, loc=None, comp=None, field='show', show_text='show', 
        tooltip_text='', **kwargs):
        self.comp = comp
        self.field = field
        super().__init__(**kwargs)
        if loc == 'upper-right':
            self.pos_hint = {'right': 1, 'top': 1}
        elif loc == 'upper-left':
            self.pos_hint = {'left': 0, 'top': 1}
        elif loc == 'lower-left':
            self.pos_hint = {'left': 0, 'bottom': 0}
        elif loc == 'lower-right':
            self.pos_hint = {'right': 1, 'bottom': 0}
        if 'left' in loc:
            self.open_text = f'[font=Jocular][size=18sp]>[/size][/font] {show_text}'
            self.close_text = '[font=Jocular][size=18sp]<[/size][/font]'
            self.halign = 'left'
        else:
            self.open_text = f'{show_text} [font=Jocular][size=18sp]<[/size][/font]'
            self.close_text = '[font=Jocular][size=18sp]>[/size][/font]'
            self.halign = 'right'
        self.size_hint = None, None
        self.bind(on_press=self.toggle)
        showing = getattr(self.comp, self.field)
        self.text = self.close_text if showing else self.open_text
        self.tooltip_text = tooltip_text

    def toggle(self, *args):
        cval = getattr(self.comp, self.field)
        setattr(self.comp, self.field, not cval)
        self.text = self.open_text if cval else self.close_text


class JMDToggleButton(MDFlatButton, ToggleButtonBehavior, TooltipBehavior):
    def on_state(self, widget, value):
        widget.text_color = (1, 1, 1, 1) if value == 'down' else (.6, .6, .6, 1)


class JTextField(MDTextField):
    invalid = BooleanProperty(False)


class TextInputC(TextInput):
    pass


class LabelR(Label): 
    pass


class LabelL(Label): 
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
        ang = self.angle * math.pi / 180
        self.x = self.origin[0] + self.radius * math.cos(ang) 
        self.y = self.origin[1] + self.radius * math.sin(ang)
        self.generate_inverse()


    def generate_inverse(self, *args):
        ''' done on width and height as well as init because when 
            using texture size to compute size correct w/h info is 
            not available on init
        '''
        ang = radians(self.rotangle) if self.rotated else 0
        t = Matrix().translate(-self.width / 2 - self.x, -self.height / 2 - self.y, 0)
        t = Matrix().rotate(ang, 0, 0, 1).multiply(t)
        t = Matrix().translate(self.x, self.y, 0).multiply(t)
        self.inv = t.inverse()


    def collide_point(self, x, y):
        ''' transform touchpos using the inverse transform of the rotation;
            takes about 150 microseconds
        '''
        xt, yt, _ = self.inv.transform_point(x, y, 0)
        return (self.x < xt < (self.x + self.width)) and (
            self.y < yt < (self.y + self.height)
        )


class JWidget(Widget, TooltipBehavior):
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


class JIconButton(JButton, JRotWidget):
    myicon = StringProperty('')


class JMDIconButton(MDIconButton, Rotatable):
    pass


class JSlider(MDSlider):

    def on_touch_down(self, touch):
        ''' Ensure touch isn't passed thru to scatter
        '''
        if self.collide_point(*touch.pos):
            super().on_touch_down(touch)
            return True
        return False

