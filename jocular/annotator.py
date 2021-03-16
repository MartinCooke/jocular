''' Annotator. Very simple for now.
'''


import os
import time
import json
import numpy as np

from kivy.app import App
from kivy.logger import Logger
from kivy.properties import (
    ConfigParserProperty,
    NumericProperty,
    StringProperty,
    BooleanProperty,
    ListProperty,
    DictProperty,
    ObjectProperty,
)
from kivy.clock import Clock
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.metrics import dp
from kivy.lang import Builder
from kivy.core.window import Window

from jocular.widgets import ParamValue
from jocular.hoverable import HoverBehavior
from jocular.metrics import Metrics
from jocular.component import Component
from jocular.uranography import make_tile, DEC_STEP, RA_STEP, to360, dec2tile, ra2tile


Builder.load_string(
    '''

#:import np numpy

<PropVal>:
    canvas.before:
        Color:
            rgba: .3, .3, .3, .3
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
        #color: app.lowlight_color
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
            try:
                if self.info['OT'] == 'Quasar':
                    lab = '{:4.1f} z {:3.1f}'.format(self.info['Mag'], self.info['z'])
                    self.font_size = '14sp'
            except:
                pass
            self.text = str(lab)
            self.pinned = True
            self.close_DSOInfo()
            self.update()

    def unpin(self, dt=None):
        if self.pinned:
            self.text = 'o'
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
                x = float(self.sx + self.radius * np.cos(ang_r))
                y = float(self.sy + self.radius * np.sin(ang_r))
                self.lab_x = x
                self.lab_y = y
                # self.font_size = '16sp'
            else:
                self.lab_x = self.sx
                self.lab_y = self.sy
                # self.font_size = '16sp'


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
        self.visible = True

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

        self.clear_widgets()
        # populate popup
        nm = '{:} ({:})'.format(info.get('Name', ''), info.get('OT'))
        tb = TitleBar(Name=nm)
        if title_color is not None:
            tb.title_color = title_color
        self.add_widget(tb)

        for k, v in info.items():
            if str(v) != 'nan' and k not in {'Name', 'Cat', 'RA', 'Dec'}:
                if type(v) == float:
                    pv = PropVal(param=k, value='{:.3f}'.format(v))
                else:
                    pv = PropVal(param=k, value=str(v))
                self.add_widget(pv)

        # position to popup info; not yet working in terms of limiting it to screen
        pos = Window.mouse_pos
        self.x = min(pos[0] + dp(9), Window.width - self.minimum_width - dp(20))
        self.y = min(pos[1], Window.height - self.minimum_height - dp(20))

    def hide(self):
        self.x = 10 * Window.width


# ensures that there is only one ie singleton popup
dsopopup = DSOPopup()


class Annotator(Component):

    mag_limit = NumericProperty(0)
    qso_prob = ConfigParserProperty(95, 'Annotator', 'qso_prob', 'app', val_type=float)
    show_variables = ConfigParserProperty(
        False, 'Annotator', 'show_variables', 'app', val_type=int
    )
    show_doubles = ConfigParserProperty(
        False, 'Annotator', 'show_doubles', 'app', val_type=int
    )
    show_spectral = ConfigParserProperty(
        True, 'Annotator', 'show_spectral', 'app', val_type=int
    )
    show_quasars = ConfigParserProperty(
        True, 'Annotator', 'show_quasars', 'app', val_type=int
    )
    # show_members = ConfigParserProperty(False, 'Annotator', 'show_members', 'app', val_type=int)
    # show_members = BooleanProperty(False)
    AnnotColour = ListProperty([0.5, 0.5, 0.5])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.annotations = []

    def on_new_object(self):
        self.clear_annotations()
        self.on_mag_limit()
        self.info('ready')

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

        # self.show_members = ml > 24

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

    def annotate(self):
        # called by platesolver when finished a platesolve

        self.clear_annotations()
        solver = Component.get('PlateSolver')
        clusters = {'OC', 'G+', 'GG', 'CG'}

        # rotate view to north
        Component.get('View').orientation = solver.north

        # find objects in FOV from tile large enough to encompass sensor
        w, h = solver.w, solver.h
        deg_per_pixel = float(solver.FOV_h / h)
        tile = make_tile(
            solver.tile_ra0, solver.tile_dec0, fov=1.5 * max(solver.FOV_w, solver.FOV_h)
        )

        ras, decs, infos, otypes = self.get_dsos(tile)

        # colours from https://www.rapidtables.com/web/color/RGB_Color.html
        colours = {
            # groups and members in green shades
            'CompactGroup': [124, 252, 0],  # lawn green
            'GalaxyGroup': [173, 255, 47],  # green yellow
            'Member': [152, 251, 152],  # pale green
            # galaxies and quasar in yellow shades
            'Galaxy': [240, 230, 140],  # khaki
            'Peculiar': [255, 215, 0],  # gold
            'Quasar': [255, 165, 0],  # orange
            # stars in shades of blue
            'Stellar': [72, 209, 204],  # medium turquoise
            'Variable': [127, 255, 212],  # aquamarine
            'Multiple': [0, 191, 255],  # dep sky blue
            # clusters in reddish hues
            'OpenCluster': [139, 0, 139],  # dark magenta
            'Globular': [138, 43, 226],  # blue violet
            # nebulae in browns/greys
            'Planetary': [160, 82, 45],  # sienna
            'DarkNebula': [176, 196, 222],  #  light steel blue
            'Nebula': [188, 143, 143],  # rosy brown
        }

        colours = {k: [v[0] / 255, v[1] / 255, v[2] / 255] for k, v in colours.items()}
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

        for r, d, info, ot in zip(ras, decs, infos, otypes):
            info['OT'] = ot
            px, py = solver.ra_dec_to_pixels(r, d)
            px, py = float(px[0]), float(py[0])
            #  check it is actually within the image dimensions
            if (px >= 0) & (py >= 0) & (px < w) & (py < h):
                # try to get a diameter value in case we need it
                try:
                    diam = float(info['Diam'])
                except:
                    diam = 0
                #  ang = np.random.uniform(10, 80)
                ang = 45
                if ot in {
                    'OpenCluster',
                    'Globular',
                    'CompactGroup',
                    'GalaxyGroup',
                    'Peculiar',
                }:
                    pixel_rad = 1.2 * ((diam / (2 * 60.0)) / deg_per_pixel)
                    annot = AnnotCluster(
                        text='o',
                        px=px,
                        py=py,
                        info=info,
                        ang=ang,
                        center=False,
                        mag=info.get('Mag', 0),
                        marker_color=colours.get(ot, [1, 0.5, 0.5]),
                        bx=px + pixel_rad / 2 ** 0.5,
                        by=py + pixel_rad / 2 ** 0.5,
                    )

                elif ot == 'Quasar':
                    annot = AnnotQuasar(
                        text=' ',
                        px=px,
                        py=py,
                        info=info,
                        mag=info.get('Mag', 20),
                        bx=px,
                        by=py,
                        marker_color=colours.get(ot, [1, 0.5, 0.5]),
                    )

                elif ot in {'Galaxy'}:
                    pixel_rad = (diam / (4 * 60.0)) / deg_per_pixel
                    annot = Annotation(
                        text='o',
                        px=px,
                        py=py,
                        info=info,
                        ang=ang,
                        mag=info.get('Mag', 0),
                        center=True,
                        marker_color=colours.get(ot, [1, 0.5, 0.5]),
                        bx=px + pixel_rad / 2 ** 0.5,
                        by=py + pixel_rad / 2 ** 0.5,
                    )
                elif ot in {'Member'}:
                    annot = Annotation(
                        text='.',
                        px=px,
                        py=py,
                        info=info,
                        bx=px,
                        by=py,
                        mag=info.get('Mag', 24),
                        ang=ang,
                        center=True,
                        marker_color=colours.get(ot, [1, 0.5, 0.5]),
                    )
                else:
                    annot = Annotation(
                        text='o',
                        px=px,
                        py=py,
                        info=info,
                        bx=px,
                        by=py,
                        mag=info.get('Mag', 0),
                        ang=ang,
                        center=True,
                        marker_color=colours.get(ot, [1, 0.5, 0.5]),
                    )

                self.annotations += [annot]

        # create annotations (this will change when we add different types)
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

    def show_object_type(self, md):
        ot = md['object_type']
        if ot == 'Variable':
            return self.show_variables
        if ot == 'Quasar':
            return self.show_quasars
        if ot == 'Multiple':
            return self.show_doubles
        # if ot == 'Member':
        #     return self.show_members
        if md['catalogue'] == 'SkiffSpectralType':
            return self.show_spectral
        return True

    def get_dsos(self, tile):
        # get dsos by reading tiles that are spaced at 30 x 10 degrees in RA/Dec

        def mergetile(tile, cat, data, min_ra, max_ra, min_dec, max_dec):
            # incorporate data e.g. 'RA': [ras], 'Dec': [decs] into cat on tile
            # restrict to current tile
            r, d = data['RA'], data['Dec']
            if min_ra < max_ra:
                locs = (r >= min_ra) & (r < max_ra) & (d >= min_dec) & (d < max_dec)
            else:
                locs = ((r >= min_ra) | (r < max_ra)) & (d >= min_dec) & (d < max_dec)
            if len(r[locs]) > 0:
                if cat not in tile:
                    tile[cat] = {}
                for col, arr in data.items():
                    if col not in tile[cat]:
                        tile[cat][col] = arr[locs]
                    else:
                        tile[cat][col] = np.append(tile[cat][col], arr[locs])
            return tile

        def make_info(data, use_cols=None):
            cols = data.keys()
            if use_cols is not None:
                cols = use_cols
            dicts = []
            for i in range(len(data['RA'])):
                d = {c: data[c][i] for c in cols if data[c][i]}
                d = {c: v for c, v in d.items() if str(v).strip()}
                dicts += [d]
            return np.array(dicts)

        def nullvalue(x):
            if type(x) == str:
                return x.strip() == 'nan' or len(x.strip()) == 0
            else:
                return x == np.nan

        dso_db = self.app.get_path('dso_db')

        # load column definitions
        with open(os.path.join(dso_db, 'metadata.json'), 'r') as f:
            metadata = json.load(f)

        min_ra, max_ra = tile['min_ra'], tile['max_ra']
        min_dec, max_dec = tile['min_dec'], tile['max_dec']
        dec_tiles = np.arange(dec2tile(min_dec), dec2tile(max_dec) + DEC_STEP, DEC_STEP)
        if min_ra < max_ra:
            ra_tiles = np.arange(ra2tile(min_ra), ra2tile(max_ra) + RA_STEP, RA_STEP)
        else:
            ra_tiles = list(range(ra2tile(min_ra), 360, RA_STEP)) + list(
                range(0, ra2tile(max_ra) + RA_STEP, 30)
            )

        # load one or more tiles containing the current FOV
        dsos = {}
        for ra in ra_tiles:
            for dec in dec_tiles:
                dat = np.load(
                    os.path.join(dso_db, 'r{:}_d{:}.npz'.format(ra, dec)),
                    allow_pickle=True,
                )
                # extract catalogues & restrict to FOV
                for catname, md in metadata.items():
                    if self.show_object_type(md):
                        cat = dat[catname]
                        cols = md['columns']
                        contents = {c: cat[i] for i, c in enumerate(cols)}
                        dsos = mergetile(
                            dsos, catname, contents, min_ra, max_ra, min_dec, max_dec
                        )

        # simple format for now
        ras = np.array([])
        decs = np.array([])
        info = np.array([])
        otype = np.array([])
        for k, v in dsos.items():
            ot = [metadata[k]['object_type']]
            ras = np.append(ras, v['RA'])
            decs = np.append(decs, v['Dec'])
            info = np.append(info, make_info(v))
            otype = np.append(otype, np.array(len(v['RA']) * ot))

        return ras, decs, info, otype
