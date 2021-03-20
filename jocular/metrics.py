''' Convenient place to support ring metrics.
'''

from kivy.metrics import dp
from kivy.logger import Logger
from kivy.core.window import Window

class Metrics():

    metrics = {}
    width = 0
    height = 0

    @classmethod
    def get(cls, p):
        width, height = Window.size
        if (cls.width != width) or (cls.height != height):
            cls.update()
        if p in cls.metrics:
            return cls.metrics[p]
        else:
            Logger.error('Metrics: no such metric {:}'.format(p))

    @classmethod
    def update(cls):

        width, height = Window.size

        origin = .5 * width, .5 * height
        radius = .5 * height if width > height else .5 * width
        diag = (origin[0] ** 2 +origin[1] ** 2) ** .5

        # scope rings: 3 + outer (obscuring) ring
        inner_width = dp(8)
        middle_width = dp(28)
        outer_width = dp(22)

        radii = {}
        radii['background'] = radius, diag
        radii['outer'] = radii['background'][0] - outer_width, radii['background'][0]
        radii['middle'] = radii['outer'][0] - middle_width, radii['outer'][0]
        radii['inner'] = radii['middle'][0] - inner_width, radii['middle'][0]
        radii['image'] = 0, radii['inner'][0]

        ring_radius = {nm: (r_inner + r_outer) / 2 for nm, (r_inner, r_outer) in radii.items()}

        ring_thickness = {nm: (r_outer - r_inner) / 2 for nm, (r_inner, r_outer) in radii.items()} 
        inner_ring = radii['middle'][0] + middle_width / 2
        outer_ring = radii['outer'][0] + outer_width / 2
        outside_ring = radii['outer'][1] + outer_width / 2 

        ring_radius['capture_ring'] = (inner_ring + outer_ring - inner_width)/ 2
        ring_thickness['capture_ring'] = (outer_ring - inner_ring)

        cls.width = width
        cls.height = height

        cls.metrics = {
            'origin': origin,
            'radius': radius,
            'inner_radius': radii['inner'][0],
            'inner_ring': inner_ring, 
            'outer_ring': outer_ring, 
            'outside_ring': outside_ring,
            'fine_control': outside_ring + dp(20),
            'mid_ring': (inner_ring + outer_ring)/ 2,
            'outer_width': outer_width,
            'radii': radii,
            'ring_radius': ring_radius,
            'ring_thickness': ring_thickness
        }
