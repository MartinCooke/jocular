''' Special-purpose widgets for Jocular
'''


from kivy.core.window import Window
from kivy.lang import Builder
from kivy.uix.label import Label
from kivy.properties import (
    NumericProperty,
    BooleanProperty
)

from jocular.uranography import angle_diff
from jocular.widgets.widgets import JRotWidget


Builder.load_string('''
<JLever>:
    color: app.lever_color
    font_size: '17sp'
''')


class JLever(JRotWidget, Label):
    ''' circular sliders
    '''

    value = NumericProperty(0.0)
    disabled = BooleanProperty(False)


    def __init__(self, value=0, values=None, angles=None, radial=True,
        continuous_update=None, shortcut=None, sc_inc=0.0, **kwargs):

        super().__init__(radial=radial, **kwargs)
        if values is None:
            values = [0, 1]
        if angles is None:
            angles = [0, 1]
        self.min_angle, self.max_angle = angles[0], angles[1]
        self.min_value, self.max_value = values[0], values[1]
        self.value = value
        self.selected = False

        # disabled this because can't get View on init reliably it seems
        # if continuous_update is None:
        #     self.update_on_move = Component.get('View').continuous_update # True
        # else:
        #     self.update_on_move = continuous_update
        self.update_on_move = True

        self._k = (self.max_angle - self.min_angle) / (self.max_value - self.min_value)
        self.rotangle = self.value_to_angle(self.value)

        # Use a simple helper class for keyboard shortcuts.
        # JLever has already been bound in a superclass to the touch handlers,
        # and cannot be itself rebound
        self.keyhandler = JLeverKeyHandler(self, shortcut)

        # Factor to increment by when shortcut is used
        self.sc_inc = sc_inc

        self.update(self.rotangle)


    def reset_value(self, v):
        # force update of lever position
        ang = self._k * (v - self.min_value) + self.min_angle
        self.update(ang)


    def value_to_angle(self, v):
        return self._k * (v - self.min_value) + self.min_angle


    def on_touch_down(self, touch):
        if not self.disabled and self.collide_point(*touch.pos):
            if touch.is_double_tap:
                self.update_on_move = not self.update_on_move
            self.selected = True
            return True
        return False


    def on_touch_move(self, touch):
        ''' If this lever is selected, update position, and update value if
            update_on_move is True
        '''
        if self.selected:
            self.update(
                angle_diff(self.origin, touch.pos),
                update_value=self.update_on_move)


    def ang2value(self, angle):
        # x = float(((angle - self.min_angle) / self._k) + self.min_value)
        x = ((angle - self.min_angle) / self._k) + self.min_value
        return min(self.max_value, max(x, self.min_value))


    # Called by the keyboard shortcut handler
    def increment(self, sign):
        angle = self.angle + sign * self.sc_inc
        self.update(angle, update_value=True)


    def on_touch_up(self, touch):
        ''' Unselect lever and update value if update_on_move is False
        '''
        if self.selected:
            self.selected = False
            if not self.update_on_move:
                _ang = angle_diff(self.origin, touch.pos)
                self.value = self.ang2value(_ang)
                # fake a transparency change to ensure interface is updated
                _t = self.color[-1]
                self.color[-1] = 0
                self.color[-1] = _t


    def update(self, angle, update_value=True):
        ''' If angle within range, update angle of level, and
            update corresponding value if update_value is True
        '''

        # return if angle outside range
        if (angle >= min(self.min_angle, self.max_angle)) and \
            (angle <= max(self.min_angle, self.max_angle)):
            if update_value:
                self.value = self.ang2value(angle)
                # convert value to angle in case it hasn't changed
                angle = self.value_to_angle(self.value)
            self.angle = angle
            self.on_angle()



# Helper class to bind to keyboard events
class JLeverKeyHandler:

    def __init__(self, jlever, shortcut):
        self.jlever = jlever
        self.shortcut = shortcut
        Window.bind(on_key_down=self.on_key_down)

    # Window.on_key_down has an undocumented fifth argument. A test program
    # shows this is the correct set of arguments.
    def on_key_down(self, window, key, scancode, codepoint, modifiers):
        if not (self.jlever.disabled or self.shortcut == None):
            if codepoint == self.shortcut and 'ctrl' in modifiers:
                self.jlever.increment(1)
            elif codepoint == self.shortcut and 'alt' in modifiers:
                self.jlever.increment(-1)
