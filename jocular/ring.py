''' Class to construct circular parts of the eyepiece
'''

from kivy.uix.widget import Widget
from kivy.lang import Builder
from kivy.properties import NumericProperty

Builder.load_string('''

<Ring>:
    canvas:
        Color:
            rgba: self.color
            rgba: self.grey, self.grey, self.grey, 1 - app.transparency
        Line:
            circle: self.x, self.y, self.radius, self.start_angle, self.end_angle, self.nsegs
            width: self.thickness
''')

class Ring(Widget):

    thickness = NumericProperty(0)

    def __init__(self, pos=[0, 0], radius=1, thickness=1, grey=.4, 
        start_angle=0, end_angle=360, nsegs=240):
        self.selected = False
        self.pos = pos
        self.radius = radius
        self.thickness = thickness
        self.grey = grey
        self.color = [grey, grey, grey, 1]
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.nsegs = nsegs
        super().__init__()

    def relocate(self, origin=None, radius=None, thickness=None):
        self.pos = origin
        self.radius = radius
        if thickness:
            self.thickness = thickness
