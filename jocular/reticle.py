''' Basic class to draw reticle
'''

from kivy.properties import NumericProperty, BooleanProperty
from kivy.lang import Builder
from kivy.uix.widget import Widget

# NB for kivy prior to RC 2 could use :set inner dp(10)
Builder.load_string('''

#:set inner 10

<Reticle>:
    canvas:
        Color: 
            rgba: app.highlight_color if root.show else self.disabled_color
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

class Reticle(Widget):

    radius = NumericProperty(1)
    show = BooleanProperty(False)
