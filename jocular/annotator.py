''' Supports annotation browsing functionality.
'''

import numpy as np

from kivy.app import App
from loguru import logger
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
from kivymd.uix.behaviors import HoverBehavior

from jocular.metrics import Metrics
from jocular.component import Component
from jocular.uranography import make_tile, radec2pix


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
        color: [.5, .5, .5, .7] # app.lowlight_color
        font_size: app.form_font_size
        background_color: .6, 0, .6, 0
        width: dp(100)
        padding: dp(5), dp(1)
        text: f'[b]{root.param}[/b]'
    Label:
        size_hint: None, 1
        markup: True
        halign: 'left'
        text_size: self.size
        color: [.5, .5, .5, .7] # app.lowlight_color
        font_size: app.form_font_size
        background_color: .6, 0, .6, 0
        width: dp(250)
        text: root.value


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
        font_size: str(int(app.form_font_size[:-2]) + 4) + 'sp'
        width: dp(350)
        text: f'[b]{root.Name}[/b]'


<DSOPopup>:
    size_hint: None, 1
    width: dp(350)
    orientation: 'vertical'
    padding: dp(5), dp(2)


<Annotation>:
    size_hint: None, None
    size: self.texture_size
    font_size: '15sp' if self.pinned else '20sp'
    text_size: None, None  # forces size to be that of text
    color: (self.label_color if self.pinned else self.marker_color) + [self.visible]
    pos: (self.lab_x - self.width / 2, self.lab_y - self.height / 2) if self.center and not self.pinned else (self.lab_x, self.lab_y)


<AnnotCluster>:
    canvas:
        Color:
            rgb: 1, 1, 1
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
            rgb: .4, .4, .4
            a: 1 if self.visible else 0
        Line:
            points: [self.sx - self.length/2, self.sy, self.sx + self.length/2, self.sy]
            width: 1
    color: 1, .4, .4, 1

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
   
    bx = NumericProperty(0)  #  pixel on boundary
    by = NumericProperty(0)
    lab_x = NumericProperty(0)
    lab_y = NumericProperty(0)
    center = BooleanProperty(True)
    mag = NumericProperty(0)
    radius = NumericProperty(0)

    # Members for drag behavior
    last_x = NumericProperty(0)
    last_y = NumericProperty(0)
    total_delta_x = NumericProperty(0)
    total_delta_y = NumericProperty(0)
    dragged = BooleanProperty(False)


    def on_enter(self, *args):
        if self.visible:
            self.display_DSOInfo()


    def on_leave(self, *args):
        if self.visible:
            self.close_DSOInfo()


    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if self.visible:
                self.last_x, self.last_y = touch.pos
                return True
        return False


    def on_touch_move(self, touch):
        if self.visible and self.pinned and self.collide_point(*touch.pos):
            self.dragged = True
            x, y = touch.pos
            delta_x = x - self.last_x
            delta_y = y - self.last_y
            self.last_x, self.last_y = touch.pos
            self.x += delta_x
            self.y += delta_y
            self.lab_x += delta_x
            self.lab_y += delta_y

            # These are needed for when the view is dragged after dragging the label
            self.total_delta_x += delta_x
            self.total_delta_y += delta_y
            return True
        return False


    def on_touch_up(self, touch):
        if self.visible and self.collide_point(*touch.pos):
            if self.dragged:
                self.dragged = False
            else:
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
            # for quasars, label with mag + redshift
            if self.ot == 'QS':
                lab = f'{self.info["Mag"]:4.1f}'
                z = self.info.get('z', '?')
                if not np.isnan(z):
                    lab += f' z {z:3.1f}'
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
            self.total_delta_x = 0
            self.total_delta_y = 0
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

        # display if visible and set to display
        if self.visible:
            bx, by = self.mapping(self.bx, self.by)
            if self.pinned:
                self.radius = ((self.sx - bx) ** 2 + (self.sy - by) ** 2) ** 0.5
                ang_r = np.radians(self.ang)
                self.lab_x = float(self.sx + self.radius * np.cos(ang_r)) + self.total_delta_x
                self.lab_y = float(self.sy + self.radius * np.sin(ang_r)) + self.total_delta_y
            else:
                self.lab_x = self.sx
                self.lab_y = self.sy


class AnnotCluster(Annotation):
    pass


class AnnotQuasar(Annotation):
    # a couple of lines set a few pix from QSO
    length = NumericProperty(20)  # indicator line length in pixels
    gap = NumericProperty(20)  # gap from quasar to line in pixels


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
        exclude = {'OT', 'Name', 'RA', 'Dec', 'Con', 'Obs', 'List', 'Added', 'MaxAlt', 'Transit'}

        self.clear_widgets()
        tb = TitleBar(Name=info.get('Name', ''))
        if title_color is not None:
            tb.title_color = title_color
        self.add_widget(tb)

        for k, v in info.items():
            if str(v) and str(v) != 'nan' and k not in exclude:
                if type(v) == float:
                    pv = PropVal(param=k, value=f'{v:.3f}')
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
            n_annots = len(self.annotations)
            for k in self.annotations:
                gui.remove_widget(k)
            logger.info(f'Cleared {n_annots:d} annotations')
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
        # just keep scale marker
        elif ml <= -3:
            for annot in self.annotations:
                annot.display = annot.info.get('Name', '') == 'FOV'
            mesg = 'fov'
        # if below 0, just turn on pinned annotations
        elif ml < 0:
            for annot in self.annotations:
                annot.display = annot.pinned
            mesg = 'pin'
        # otherwise apply magnitude limit to unpinned cases
        else:
            for annot in self.annotations:
                annot.display = annot.pinned or annot.mag < ml
            mesg = f'{ml:4.1f}'

        self.app.gui.set_prop('mag_limit', 'text', f'   {mesg}')

        self.update()


    @staticmethod
    def get_diam(info):
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


    def annotate(self, solution):
        ''' called by platesolver when finished a platesolve
        '''

        ''' solution is a dict like this:
            {
                'ra_centre': ra_centre,
                'dec_centre': dec_centre,
                'ra': str(RA(ra_centre)),
                'dec': str(Dec(dec_centre)),
                'width': w,
                'height': h,
                'fov_w': fov_w,
                'fov_h': fov_h,
                'north': north,
                'projection': projection,
                'im_stars': im_stars,
                'ref_stars': ref_stars
            }
        '''

        self.clear_annotations()
        # solver = Component.get('PlateSolver')
        cats = Component.get('Catalogues')

        # rotate view to north
        Component.get('View').orientation = solution['north']

        # find objects in FOV from tile large enough to encompass sensor
        w, h = solution['width'], solution['height']
        deg_per_pixel = float(solution['fov_h'] / h)
        fov = 1.5 * max(solution['fov_w'], solution['fov_h'])
        # possible that these should be tile ra/dec]
        ra0, dec0 = solution['tile_ra0'], solution['tile_dec0']
        tile = make_tile(ra0, dec0, fov=fov)

        dsos = cats.get_annotation_dsos(tile=tile)

        target = Component.get('DSO').Name

        # add FOV annotator
        self.annotations = [
            AnnotFOV(
                text="1'",
                info={'Name': 'FOV'},
                color=[0.4, 0.4, 0.4, 1],
                px=0,
                py=0,
                bx=1 / (3600 * deg_per_pixel),
                by=0,
                mag=-3,
                pinned=True
            )
        ]

        # object type properties and defaults
        OT_props = cats.get_object_types()
        default_props = {'name': '?', 'col': [0, 0, 0], 'text': '¤', 'mag': 0}

        ''' dsos is a dict of names and properties
        '''

        atypes = []
        for nm, info in dsos.items():
            px, py = radec2pix(info['RA'], info['Dec'], ra0, dec0, solution['projection'])

            # px, py = solver.ra_dec_to_pixels(info['RA'], info['Dec'])
            px, py = float(px[0]), float(py[0])
            # check it is actually within the image dimensions
            if (px >= 0) & (py >= 0) & (px < w) & (py < h):
                # replace OT acronym in info by full OT name
                ot = info['OT']
                atypes += [ot] # diagnostic
                props = OT_props.get(ot, default_props)
                # fill in missing props
                for k, v in default_props.items():
                    if k not in props:
                        props[k] = v
                info['Object type'] = props['name']
                # try to get a diameter value in case we need it
                diam = self.get_diam(info)
                ang = 45
                center = True
                if ot in {'OC', 'GC', 'CG', 'GG', 'G+', 'PG'}:
                    cls = AnnotCluster
                    diam *= 1.3  # make circle slightly larger
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
        mapping = Component.get('View').scatter.to_parent
        xc, yc = Metrics.get('origin')
        r2 = Metrics.get('inner_radius') ** 2
        gui = App.get_running_app().gui
        for lab in self.annotations:
            # gui.add_widget(lab, index=101)
            gui.add_widget(lab, index=0)
            lab.update(mapping=mapping, xc=xc, yc=yc, r2=r2)
            # sort out situations where several have same target name
            if lab.info['Name'] == target:
                lab.pin()
            ''' check if its a G2V and if so get image pixel values in RGB and report (for now)
            '''
            # if lab.ot == 'G2':
            #     px, py = lab.px, lab.py
            #     Component.get('Stacker').get_RGB_at_pixel(lab.px, lab.py)
                # print('found G2V im px {:} {:}'.format(lab.px, lab.py), props)

        self.on_mag_limit()


    def update(self):

        # called whenever a redraw is required e.g. View or maglimit changes
        if not self.has_annotations():
            return

        mapping = Component.get('View').scatter.to_parent
        xc, yc = Metrics.get('origin')
        r2 = Metrics.get('inner_radius') ** 2
        for annot in self.annotations:
            annot.update(mapping=mapping, xc=xc, yc=yc, r2=r2)

