''' Saves currently displayed image in various formats.
'''

import mss
import os
from functools import partial
from datetime import datetime
import numpy as np
from skimage.io import imsave
from PIL import Image, ImageDraw, ImageFont
from loguru import logger

from kivy.app import App
from kivy.core.window import Window
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.metrics import Metrics as KivyMetrics
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.clock import Clock

from jocular.component import Component
from jocular.settingsmanager import JSettings
from jocular.image import save_image
from jocular.metrics import Metrics
from jocular.utils import s_to_minsec, purify_name, toast
from jocular.widgets.widgets import JMDToggleButton
from jocular.widgets.icons import get_icon
from jocular.panel import Panel


class Snapshotter(Panel, Component, JSettings):

    save_settings= ['style', 'annotation', 'save_format']
    
    style = StringProperty('eyepiece')
    annotation = StringProperty('full')
    save_format = StringProperty('png')

    styles = {
        'eyepiece': 'circular image exactly as seen, with DSO labels if any',
        'landscape': 'rectangular image with no rotation/zoom/DSO labels'
    }

    annotations = {
        'plain': 'just the image',
        'name': 'image plus DSO name',
        'full': 'image plus all details (exposure, coords, date etc)'
    }

    save_formats = {
        'png': 'save as a .png format file',
        'jpg': 'save as a .jpg format file',
        'fits': 'save as a 16-bit FITs format file',
        'animated gif': 'save whole sequence of images as an animated gif'
    }

    imreduction = NumericProperty(1.8)
    framewidth = NumericProperty(0)
    dark_surround = BooleanProperty(True)

    configurables = [
        ('dark_surround', {
            'name': 'surround is', 
            'boolean': {'dark': True, 'light': False},
            'help': 'Shade of the region surrounding the eyepiece view'}),
        ('imreduction', {
            'name': 'image size reduction (eyepiece view)', 'float': (.5, 4, .1),
            'help': 'Reduces image size by this factor (useful on high-density screens)',
            'fmt': '{:.1f} x smaller'}),
        ('framewidth', {
            'name': 'add frame size around image', 'float': (0, 15, 1),
            'help': 'Adds a frame margin (landscape image only)',
            'fmt': '{:.0f} pixels'})
        ]


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.build()
        config = self.app.gui.config
        self.style = config.get('style', 'eyepiece')
        self.annotation = config.get('annotation', 'full')
        self.save_format = config.get('save_format', 'jpg')


    def on_show(self):
        for c, but in self.style_buttons.items():
            but.state = 'down' if c == self.style else 'normal'
        for c, but in self.annotation_buttons.items():
            but.state = 'down' if c == self.annotation else 'normal'
        for c, but in self.save_format_buttons.items():
            but.state = 'down' if c == self.save_format else 'normal'


    def _button(self, name, group, fn, tooltip=None):
        if tooltip is None:
            tooltip = group
        return JMDToggleButton(
                text=name, 
                size_hint=(1, None),
                group=group,
                font_size='16sp',
                tooltip_text=tooltip,
                on_press=partial(fn, name))


    def build(self, *args):

        content = self.contents
        content.add_widget(Label(text='', size_hint=(1, 1)))

        gl = GridLayout(size_hint=(1, None), cols=5, height=dp(40), spacing=(dp(5), dp(5)))
        self.style_buttons = {c: self._button(c, 'style', self.choose_style, tooltip=tt)
            for c, tt in self.styles.items()}
        for b in self.style_buttons.values():
            gl.add_widget(b)
        content.add_widget(gl)

        gl = GridLayout(size_hint=(1, None), cols=5, height=dp(40), spacing=(dp(5), dp(5)))
        self.annotation_buttons = {c: self._button(c, 'annotation', self.choose_annotation, tooltip=tt)
            for c, tt in self.annotations.items()}
        for b in self.annotation_buttons.values():
            gl.add_widget(b)
        content.add_widget(gl)

        gl = GridLayout(size_hint=(1, None), cols=5, height=dp(40), spacing=(dp(5), dp(5)))
        self.save_format_buttons = {c: self._button(c, 'save_format', self.choose_save_format, tooltip=tt)
            for c, tt in self.save_formats.items()}
        for b in self.save_format_buttons.values():
            gl.add_widget(b)
        content.add_widget(gl)

        content.add_widget(Label(text='', size_hint=(1, None), height=dp(30)))

        snap_text = get_icon('snapshotter', font_size=40) + '\n' + 'snap!'  
        snap_button = Button(
            text=snap_text,
            markup=True,
            background_color=(0, 0, 0, 0),
            size_hint=(1, None),
            height=dp(80),
            on_press=self.snap_no_return)

        content.add_widget(snap_button)

        self.app.gui.add_widget(self)


    def choose_style(self, style, *args):
        if style != self.style:
            self.style = style


    def choose_save_format(self, save_format, *args):
        if save_format != self.save_format:
            self.save_format = save_format


    def choose_annotation(self, annotation, *args):
        if annotation != self.annotation:
            self.annotation = annotation


    def mss_grabber(self, bbox=None):
        with mss.mss() as sct:
            im = sct.grab(bbox)
            return Image.frombytes('RGB', im.size, im.bgra, 'raw', 'BGRX').convert('RGBA')


    def large_font(self, w):
        f = max(18, int(w / 32))
        font = ImageFont.truetype(self.app.get_path('Roboto-Medium.ttf'), f)
        (width, height), (offset_x, offset_y) = font.font.getsize('A')
        return font, f, height


    def small_font(self, w):
        f = max(13, int(w / 60))
        font = ImageFont.truetype(self.app.get_path('Roboto-Medium.ttf'), f)
        (width, height), (offset_x, offset_y) = font.font.getsize('A')
        return font, f, height


    def grey(self):
        if self.dark_surround:
            return (150, 150, 150, 255)
        else:
            return (50, 50, 50, 255)


    def snap_no_return(self, *args):
        self.hide()
        Clock.schedule_once(self.delayed_snap, 1)


    def delayed_snap(self, dt=None):
        try:
            if self.save_format == 'animated gif':
                Component.get('Stacker').make_animated_gif()
            else:
                self.snap()
        except:
            pass


    def snap(self, return_image=False, *args):

        self.return_image = return_image

        view = Component.get('View')
        if not hasattr(view, 'last_image') or (view.last_image is None):
            return

        dso = Component.get('DSO')

        self.save_path = '{:} {:}.{:}'.format(
                os.path.join(self.app.get_path('snapshots'), purify_name(dso.Name)), 
                datetime.now().strftime('%d%b%y_%H_%M_%S'),
                self.save_format)

        if not return_image and self.save_format == 'fits':
            self.save_as_fits()

        elif self.style == 'eyepiece':
            im = self.eyepiece_view()

        elif self.style == 'landscape':
            im = self.landscape_view()

        if return_image:
            return im


    def save_as_fits(self):
        stacker = Component.get('Stacker')
        im = stacker.get_stack()
        if im is not None:
            im = im * (2**16 - 1)
            logger.debug(f'min {np.min(im)} max {np.max(im)}')
            capture_props = {
                'exposure': stacker.describe().get('total_exposure', None),
                'sub_type': stacker.get_prop('sub_type'),
                'filt': stacker.get_prop('filter')
            }
            save_image(data=im.astype(np.uint16), path=self.save_path,
                capture_props=capture_props)
            toast(f'Saved fits to {os.path.basename(self.save_path)}', duration=2.5)
        else:
            toast('no image to save')

    # construct annotations

    def DSO_details(self):
        dso = Component.get('DSO')
        obj_details = []
        if len(dso.OT) > 0 and (dso.OT in dso.otypes):
            if len(dso.Con) > 0:
                obj_details  += [f'{dso.otypes[dso.OT]} in {dso.Con}']
            else:
                obj_details  += [format(dso.otypes[dso.OT])]

        elif len(dso.Con) > 0:
            obj_details += [dso.Con]

        if dso.RA:
            obj_details += [f'RA {str(dso.RA)}']
        if dso.Dec:
            obj_details += [f'Dec {str(dso.Dec)}']
        if dso.Mag:
            obj_details += [f'mag {dso.Mag}']
        if dso.Diam:
            obj_details += [f"diam {dso.Diam}"]

        return obj_details


    def kit_details(self):
        s = Component.get('Session')
        kit = [s.telescope, s.camera]
        ps = Component.get('PlateSolver').describe()

        fov = ps['fov']
        if fov is not None:
            kit += [fov]

        return kit


    def session_details(self):
        sesh = Component.get('Session').describe()
        ps = Component.get('PlateSolver').describe()
        fwhm = ps['fwhm']
        if fwhm is not None:
            sesh += [f'fwhm: {fwhm:.1f}"']
        return sesh


    def processing_details(self):

        block = []
        stacker = Component.get('Stacker')
        d = stacker.describe()
        if d is None:
            return []

        if d['gain'] > 0:
            block += [f"gain {d['gain']:.0f}"]

        block += [f"{Component.get('StackCombiner').combine_method} stack" if d['nsubs'] > 1 else 'single sub']
        block += [f"{Component.get('Stretcher').stretch} stretch"]

        calib = ','.join([c for c in ['dark', 'flat', 'bias'] if d[c]])
        calib = calib if calib else 'no darks/flats'
        block += [calib]

        if not d['filters'].endswith('L'):
            block += [d['filters']]

        smode = Component.get('MultiSpectral').describe_mode()
        block += [f'mode {smode}']

        if 'total_exposure' in d:
            composition = 'varied expos' if d['multiple_exposures'] else f"{d['nsubs']} x {s_to_minsec(d['sub_exposure'])}"
            block += [f"{s_to_minsec(d['total_exposure'])} ({composition})"]

        return block # block[::-1]  # reverse!


    def eyepiece_view(self, dt=None):


        ox, oy = Metrics.get('origin')
        radius = Metrics.get('radius')

        # thanks to callump for the use of scrn_density
        scrn_density = KivyMetrics.density
        cx = int(Window.left + ox / scrn_density)
        cy = int(Window.top + Window.height / scrn_density - oy / scrn_density)
        r = int(radius / scrn_density - 40)
        w = 2 * r

        try:
            im = self.mss_grabber(bbox=(cx - r, cy - r, cx + r, cy + r))
        except Exception as e:
            logger.exception(f'problem with screen grab ({e})') 
            toast(f'screen grab error ({e})')
            return

        blur = 17                     # radius of blurred edge in pixels

        # new from callump
        w = im.width
        r = w / 2

        # construct alpha channel to composite eyepiece circle
        # quite likely some of these steps are redundant
        alpha = Image.new('L', (w, w), color=0)
        _alpha = np.ones((w, w))
        grid_x, grid_y = np.meshgrid(np.arange(w), np.arange(w))
        d = pow((grid_x - r) ** 2 + (grid_y - r) ** 2, .5) - (r - 30)
        db = d <= blur
        _alpha[db] = d[db] / blur
        alpha.putdata(_alpha.ravel(), scale=255)
        if self.dark_surround:
            grad_im = Image.new('RGBA', (w, w), color=(0, 0, 0))
        else:
            grad_im = Image.new('RGBA', (w, w), color=(255, 255, 255)) 
        grad_im.putalpha(alpha)

        # composite with scope image, converting if needed (to test)
        try:
            if im.mode != 'RGBA':
                im = im.convert('RGBA')
            im = Image.alpha_composite(im, grad_im)
        except Exception as e:
            logger.exception(f'problem compositing ({e})')
            toast(f'compositing error ({e})')
            return

        # annotate Draw object with required level of detail
        sf, sf_size, hh = self.small_font(w)
        lf, lf_size, hh = self.large_font(w)
        rowsep = sf_size + 6
        if self.annotation != 'plain':    
            draw = ImageDraw.Draw(im)
            w, h = im.size
            row = self.draw_aligned(draw, 0, 0, w, Component.get('DSO').Name, lf, 
                align='left', rowsep=lf_size+30)

        if self.annotation == 'full':
            self.draw_block(self.DSO_details(), draw, row, 0, w, sf, 
                align='left', rowsep=rowsep)
            self.draw_block(self.processing_details()[::-1], draw, h - 1.5*rowsep, 0, w, sf, 
                align='right', rowsep=-rowsep)
            self.draw_block(self.kit_details(), draw, h - 1.5*rowsep, 0, w, sf, 
                align='left', rowsep=-rowsep) # neg builds from base
            self.draw_block(self.session_details(), draw, 5, 0, w, sf, 
                align='right', rowsep=rowsep)

        # for high density screens, reduce size a little
        im = im.resize((int(im.width/self.imreduction) , int(im.height/self.imreduction)))

        if self.return_image:
            return im

        self.save(im)


    @logger.catch
    def landscape_view(self):

        # to do: better scaling of fonts based on image size

        # v0.5: ensure tmp is in snapshots dir now that user can start from anywhere
        nm = os.path.join(self.app.get_path('snapshots'), '_tmp.png')
        im = Component.get('View').last_image.copy()
        try:
            imsave(nm, im[::-1])
            orig_im = Image.open(nm)
        except Exception as e:
            logger.exception(f'load/save problem ({e})')
            toast(f'load/save error ({e})')
            return

        w, h = orig_im.size
 
        # NB this is indep of screen size, unlike eyepiece view 
        sf, sf_size, small_text_height = self.small_font(w)
        lf, lf_size, large_text_height = self.large_font(w)

        rowgap = small_text_height / 2
        obj_details = self.DSO_details()
        proc_details = self.processing_details()
        sesh_details = self.session_details() + self.kit_details()
        max_rows = max([len(obj_details), len(proc_details), len(sesh_details)]) + 1
        total_height = h
        if self.annotation != 'plain':
            total_height = int(total_height + 2 * rowgap + large_text_height)
        if self.annotation == 'full':
            total_height = int(total_height + max_rows * small_text_height + (max_rows) * rowgap + 5)

        fw = int(self.framewidth)
        im = Image.new('RGBA', (w + 2 * fw, total_height + 2 * fw), 
            color=(0, 0, 0) if self.dark_surround else (255, 255, 255))

        im.paste(orig_im, (fw, fw))
        draw = ImageDraw.Draw(im)

        w += 2 * fw
        h += 2 * fw

        # move row base to base of text
        w += large_text_height

        if self.annotation != 'plain':
            row = self.draw_aligned(draw, h , 0, w, Component.get('DSO').Name, lf, 
                align='center', rowsep=large_text_height + 2 * rowgap)

        if self.annotation == 'full':
            row += rowgap
            draw.line((5, row, w - 5, row), fill=self.grey(), width=1)
            row += (rowgap + small_text_height - 10)
            cols = [int(x) for x in orig_im.size[0] * np.linspace(0, 1, 4)]
            self.draw_block(sesh_details, draw, row,
                cols[0], cols[1], sf, align='left', rowsep=small_text_height + rowgap)
            self.draw_block(obj_details, draw, row, 
                cols[1], cols[2], sf, align='center', rowsep=small_text_height + rowgap)
            self.draw_block(proc_details, draw, row, 
                cols[2], cols[3], sf, align='right', rowsep=small_text_height + rowgap)

        # delete temporary file and save
        os.remove(nm)

        if self.return_image:
            return im
        
        self.save(im)


    def draw_aligned(self, draw, row, l, r, text, font=None, margin=15, rowsep=20, align='center'):
        # helper to draw pixel text aligned; return new row position
        # alignment is within range of cols, a pair (l, r)
        textwidth, textheight = draw.textsize(text, font)
        if align == 'left':
            col = l + margin
        elif align == 'right':
            col = r - textwidth - margin
        elif align == 'center':
            col = (l + r - textwidth) / 2
        draw.text((col, row), text, font=font, fill=self.grey())
        return row + rowsep


    def draw_block(self, block, draw, row, l, r, font, align='center', rowsep=20):
        for v in block:
            if v:
                row = self.draw_aligned(draw, row, l, r, v, font, align=align, rowsep=rowsep)


    def save(self, im):
        # save, handling any format conversions
        try:
            if self.save_format == 'png':
                im.save(self.save_path)
            elif self.save_format == 'jpg':
                bg = Image.new('RGB', im.size, (255, 255, 255))
                bg.paste(im, im)
                bg.save(self.save_path)
            toast(f'saved to {self.save_path}', duration=2)
        except Exception as e:
            logger.exception(f'problem with _save ({e})')
            toast(f'error saving ({e})', duration=2)
