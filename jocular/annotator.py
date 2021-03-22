''' Supports annotation browsing functionality.
'''

import numpy as np

from kivy.app import App
from kivy.logger import Logger
from kivy.properties import (
    NumericProperty,
    StringProperty,
    BooleanProperty,
    ListProperty,
    DictProperty,
)
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.metrics import dp
from kivy.lang import Builder
from kivy.core.window import Window

from jocular.hoverable import HoverBehavior
from jocular.metrics import Metrics
from jocular.component import Component
from jocular.uranography import make_tile

Builder.load_string(
'''

#:import np numpy

<PropVal>:
    canvas.before:
        Color:
            rgba: .3, .3, .3, .9
        Rectangle:
            pos: self.pos
            size: self.size
    size_hint: 1, None
    height: dp(20)
    Label:
        size_hint: None, 1
        markup: True
        halign: 'left'
        text_size: self.size
        color: app.lowlight_color
        font_size: app.info_font_size
        background_color: .6, 0, .6, 0
        width: dp(100)
        padding: dp(5), dp(1)
        text: '[b]{:}[/b]'.format(root.param)
    Label:
        size_hint: None, 1
        markup: True
        halign: 'left'
        text_size: self.size
        color: app.lowlight_color
        font_size: app.info_font_size
        background_color: .6, 0, .6, 0
        width: dp(250)
        text: '{:}'.format(root.value)

<TitleBar>:
    canvas.before:
        Color:
            rgba: .4, .4, .4, .3
        Rectangle:
            pos: self.pos
            size: self.size
    size_hint: 1, None
    height: dp(30)
    padding: dp(5), dp(2)
    Label:
        size_hint: None, 1
        markup: True
        halign: 'left'
        shorten: True
        shorten_from: 'right'
        valign: 'middle'
        text_size: self.size
        color: root.title_color
        font_size: str(int(app.info_font_size[:-2]) + 4) + 'sp'
        width: dp(350)
        text: '[b]{:}[/b]'.format(root.Name)

<DSOPopup>:
    size_hint: None, 1
    width: dp(350)
    orientation: 'vertical'
    padding: dp(5), dp(2)

<Annotation>:
    size_hint: None, None
    size: self.texture_size
    font_size: '15sp'
    text_size: None, None  # forces size to be that of text
    color: (self.label_color if self.pinned else self.marker_color) + [self.visible]
    pos: (self.lab_x - self.width / 2, self.lab_y - self.height / 2) if self.center and not self.pinned else (self.lab_x, self.lab_y)

<AnnotCluster>:
    canvas:
        Color:
            rgb: 1, 0, 0
            a: 1 if self.visible else 0
        Line:
            circle: self.sx, self.sy, self.radius
            dash_offset: 16
            dash_length: 4
            width: 1

<AnnotQuasar>:
    canvas:
        Color:
            rgb: 1, 0, 0
            a: 1 if self.visible else 0
        Line:
            points: [self.sx - self.gap - self.length, self.sy, self.sx - self.gap, self.sy]
            width: 1
        Line:
            points: [self.sx, self.sy - self.gap - self.length, self.sx, self.sy - self.gap]
            width: 1

<AnnotFOV>:
    canvas:
        Color:
            rgb: .8, .8, .8
            a: 1 if self.visible else 0
        Line:
            points: [self.sx - self.length/2, self.sy, self.sx + self.length/2, self.sy]
            width: 1
    color: .8, .8, .8, 1

'''
)


class Annotation(Label, HoverBehavior):

    px = NumericProperty(0)  # image pixel centre
    py = NumericProperty(0)
    sx = NumericProperty(0)  # screen pixel centre
    sy = NumericProperty(0)

    ot = StringProperty('')
    ang = NumericProperty(45)
    visible = BooleanProperty(False)  # in eyepiece and within mag limit
    display = BooleanProperty(False)  # within mag limit
    pinned = BooleanProperty(False)
    marker_color = ListProperty([0.5, 0.3, 0.3])
    label_color = ListProperty([0.5, 0.5, 0.5])
    infoline = StringProperty('')
    info = DictProperty({})
    radius = NumericProperty(0)
    bx = NumericProperty(0)  #  pixel on boundary
    by = NumericProperty(0)
    lab_x = NumericProperty(0)
    lab_y = NumericProperty(0)
    center = BooleanProperty(True)
    mag = NumericProperty(0)

    def on_enter(self, *args):
        if self.visible:
            self.display_DSOInfo()

    def on_leave(self, *args):
        if self.visible:
            self.close_DSOInfo()

    def on_touch_down(self, touch):
        if self.visible:
            if self.collide_point(*touch.pos):
                if not self.pinned:
                    self.pin()
                else:
                    self.unpin()
                return True
        return False

    def pin(self, dt=None):
        if not self.pinned:
            lab = self.info['Name']
            self.font_size = '15sp'
            # for quasars, label with mag + redshift
            if self.ot == 'QS':
                lab = '{:4.1f}'.format(self.info['Mag'])
                z = self.info.get('z', '?')
                if not np.isnan(z):
                    lab += ' z {:3.1f}'.format(z)
                self.font_size = '14sp'
            # for members, use member number
            elif self.ot == 'ME':
                lab = self.info['Mem']
            self.text = str(lab)
            self.pinned = True
            self.close_DSOInfo()
            self.update()

    def unpin(self, dt=None):
        if self.pinned:
            if self.ot == 'QS':
                self.text = ' '
            else:
                self.text = '¤'
            self.pinned = False
            self.display_DSOInfo()
            self.update()

    def close_DSOInfo(self, *args):
        dsopopup.hide()

    def display_DSOInfo(self, *args):
        dsopopup.display(info=self.info, title_color=self.marker_color)

    def in_eyepiece(self, xc, yc, r2):
        return (xc - self.sx) ** 2 + (yc - self.sy) ** 2 < r2

    def update(self, mapping=None, xc=None, yc=None, r2=None):
        if xc is not None:
            self.xc = xc
        if yc is not None:
            self.yc = yc
        if mapping is not None:
            self.mapping = mapping
        if r2 is not None:
            self.r2 = r2
        self.sx, self.sy = self.mapping(self.px, self.py)
        self.visible = self.in_eyepiece(self.xc, self.yc, self.r2) and self.display

        #  display if visible and set to display
        if self.visible:
            bx, by = self.mapping(self.bx, self.by)
            if self.pinned:
                self.radius = ((self.sx - bx) ** 2 + (self.sy - by) ** 2) ** 0.5
                ang_r = np.radians(self.ang)
                self.lab_x = float(self.sx + self.radius * np.cos(ang_r))
                self.lab_y = float(self.sy + self.radius * np.sin(ang_r))
            else:
                self.lab_x = self.sx
                self.lab_y = self.sy


class AnnotCluster(Annotation):
    pass


class AnnotQuasar(Annotation):
    # a couple of lines a few pix from QSO
    length = NumericProperty(20)  # indicator line length in pixels
    gap = NumericProperty(10)  # gap from quasar to line in pixels


class AnnotFOV(Annotation):
    # represents FOV line
    length = NumericProperty(0)

    def update(self, mapping=None, **args):
        # compute length and update text based on FOV
        # sx is location
        if mapping is not None:
            self.mapping = mapping
        sx, sy = self.mapping(self.px, self.py)
        bx, by = self.mapping(self.bx, self.by)
        arcsecs = ((sx - bx) ** 2 + (sy - by) ** 2) ** 0.5
        self.length = arcsecs * 60
        self.sx = Window.width // 2
        self.sy = 200
        self.lab_x = self.sx
        self.lab_y = self.sy + 20
        self.visible = self.display

    def on_enter(self, *args):
        pass

    def on_touch_down(self, touch):
        return False


class TitleBar(BoxLayout):
    Name = StringProperty('')
    title_color = ListProperty([1, 0, 0, 1])


class PropVal(BoxLayout):
    param = StringProperty('')
    value = StringProperty('')


class DSOPopup(BoxLayout):
    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        Window.add_widget(self)
        self.hide()

    def display(self, info=None, title_color=None):

        # ideally, exclude some of these in Catalogue
        exclude = {'OT', 'Name', 'RA', 'Dec', 'List', 'Con', 'Obs', 'List', 'Added', 'MaxAlt', 'Transit'}
        # there is a subtle bug here which this is going to catch one day
        try:
            self.clear_widgets()
            tb = TitleBar(Name=info.get('Name', ''))
            if title_color is not None:
                tb.title_color = title_color
            self.add_widget(tb)

            for k, v in info.items():
                if str(v) and str(v) != 'nan' and k not in exclude:
                    if type(v) == float:
                        pv = PropVal(param=k, value='{:.3f}'.format(v))
                    else:
                        pv = PropVal(param=k, value=str(v))
                    self.add_widget(pv)

            # position to popup info; not yet working in terms of limiting it to screen
            pos = Window.mouse_pos
            self.x = min(pos[0] + dp(9), Window.width - self.minimum_width - dp(20))
            self.y = min(pos[1], Window.height - self.minimum_height - dp(20))
        except Exception as e:
            Logger.debug('Annotator: DSOPopup.display ({:})'.format(e))

    def hide(self):
        self.x = 10 * Window.width

# ensures that there is only one ie singleton popup
dsopopup = DSOPopup()

class Annotator(Component):

    mag_limit = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.annotations = []

    def on_new_object(self):
        self.clear_annotations()
        self.on_mag_limit()

    def clear_annotations(self):
        # remove previous annotations
        gui = App.get_running_app().gui
        if self.has_annotations():
            for k in self.annotations:
                gui.remove_widget(k)
            self.annotations = []

    def has_annotations(self):
        return len(self.annotations) > 0

    def on_mag_limit(self, *args):
        # modify what is visible
        ml = self.mag_limit

        # if limit is below -5, turn off all annotations
        if ml <= -5:
            for annot in self.annotations:
                annot.display = False
            mesg = 'off'
        # if below 0, just turn on pinned annotations
        elif ml < 0:
            for annot in self.annotations:
                annot.display = annot.pinned
            mesg = 'pin'
        # otherwise apply magnitude limit to unpinned cases
        else:
            for annot in self.annotations:
                annot.display = annot.pinned or annot.mag < ml
            mesg = '{:4.1f}'.format(ml)

        self.app.gui.set_prop('mag_limit', 'text', '   {:}'.format(mesg))

        self.update()

    def get_diam(self, ot, info):
        if 'Diam' in info:
            d = info['Diam']
        elif 'diam' in info:
            d = info['diam']
        elif 'Major' in info:
            d = info['Major']
        else:
            d = .2
        if np.isnan(d):
            d = .2 
        return d


    def annotate(self):
        ''' called by platesolver when finished a platesolve
        '''

        self.clear_annotations()
        solver = Component.get('PlateSolver')
        cats = Component.get('Catalogues')

        # rotate view to north
        Component.get('View').orientation = solver.north

        # find objects in FOV from tile large enough to encompass sensor
        w, h = solver.w, solver.h
        deg_per_pixel = float(solver.FOV_h / h)
        fov = 1.5 * max(solver.FOV_w, solver.FOV_h)
        tile = make_tile(solver.tile_ra0, solver.tile_dec0, fov=fov)

        dsos = cats.get_annotation_dsos(tile=tile)

        target = Component.get('DSO').Name

        # add FOV annotator
        self.annotations = [
            AnnotFOV(
                text="1'",
                info={'Name': ''},
                color=[0.6, 0.6, 0.6, 1],
                px=0,
                py=0,
                bx=1 / (3600 * deg_per_pixel),
                by=0,
            )
        ]

        # object type properties and defaults
        OT_props = cats.get_object_types()
        default_props = {'name': '?', 'col': [0, 0, 0], 'text': '¤', 'mag': 0}

        ''' dsos is a dict of names and properties
        '''
        for nm, info in dsos.items():
            px, py = solver.ra_dec_to_pixels(info['RA'], info['Dec'])
            px, py = float(px[0]), float(py[0])
            #  check it is actually within the image dimensions
            if (px >= 0) & (py >= 0) & (px < w) & (py < h):
                # replace OT acronym in info by full OT name
                ot = info['OT']
                props = OT_props.get(ot, default_props)
                # fill in missing props
                for k, v in default_props.items():
                    if k not in props:
                        props[k] = v
                info['Object type'] = props['name']
                # try to get a diameter value in case we need it
                diam = self.get_diam(ot, info)
                ang = 45
                center = True
                if ot in {'OC', 'GC', 'CG', 'GG', 'G+', 'PG'}:
                    cls = AnnotCluster
                    diam *= 1.3  # make circle slightly larger
                    center = False
                elif ot in {'QS', 'BQ', 'DQ'}:
                    cls = AnnotQuasar
                else:
                    cls = Annotation
                    if ot in {'ME'}:
                        diam = .15   # put labels closer
                        ang = 0
                    elif ot in {'PN'}:
                        diam *= 1.5

                # diam is in arcmin
                # print('Obj: {:} OT {:} diam: {:}'.format(info['Name'], ot, diam))
                pixel_rad = (((diam / (2 * 60.0)) / deg_per_pixel)) / 2**.5

                self.annotations += [cls(
                        ot=ot,
                        text=props['text'],
                        px=px, 
                        py=py,
                        info=info,
                        ang=ang,
                        center=center,
                        mag=info.get('Mag', props['mag']),
                        marker_color=props['col'],
                        bx=px + pixel_rad, 
                        by=py + pixel_rad)
                ]

        # create annotation labels
        mapping = Component.get('View').to_parent
        xc, yc = Metrics.get('origin')
        r2 = Metrics.get('inner_radius') ** 2
        gui = App.get_running_app().gui
        for lab in self.annotations:
            gui.add_widget(lab, index=101)
            lab.update(mapping=mapping, xc=xc, yc=yc, r2=r2)
            #  sort out situations where several have same target name
            if lab.info['Name'] == target:
                lab.pin()
        self.on_mag_limit()

    def update(self):

        # called whenever a redraw is required e.g. View or maglimit changes
        if not self.has_annotations():
            return

        mapping = Component.get('View').to_parent
        xc, yc = Metrics.get('origin')
        r2 = Metrics.get('inner_radius') ** 2
        for annot in self.annotations:
            annot.update(mapping=mapping, xc=xc, yc=yc, r2=r2)

