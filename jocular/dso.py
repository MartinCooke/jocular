''' Represents DSO name and object panel (including entry of new DSO info)
'''

import os
import math

from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty, DictProperty
from kivy.lang import Builder
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.logger import Logger
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.clipboard import Clipboard

from jocular.component import Component
from jocular.widgets import JWidget, JPopup
from jocular.RA_and_Dec import RA, Dec

Builder.load_string(
    '''

<MatchButton>:
    size_hint: 1, None
    markup: True
    text_size: self.size
    padding: dp(10), dp(1)
    halign: 'left'
    font_size: '14sp'
    color: app.lowlight_color
    height: dp(18)

<DSO>:
    size_hint: None, None
    orientation: 'vertical'
    padding: dp(5), dp(2)
    size: app.gui.width / 3, app.gui.height / 3
    y: .67 * app.gui.height
    x: 0 if root.show_DSO else -self.width

    Button:
        size_hint: 1, None
        font_size: '20sp'
        text: '[b]{:}[/b]'.format(root.Name) if root.Name else 'DSO name'
        on_press: root.edit()
        height: dp(30)
        markup: True
        text_size: self.size
        padding: dp(3), dp(1)
        halign: 'left'
        color: app.lowlight_color
        background_color: 0, 0, 0, 0

    ParamValue:
        param: 'Type'
        value: root.otypes.get(root.OT, root.OT)
        callback: root.edit
    ParamValue:
        param: 'Con'
        value: root.Con
        callback: root.edit
    ParamValue:
        param: 'RA'
        value: root.RA
        callback: root.paste_RA
        #callback: Clipboard.copy(self.value)
    ParamValue:
        param: 'Dec'
        value: root.Dec
        #callback: Clipboard.copy(self.value)
        callback: root.paste_Dec
    ParamValue:
        param: 'Mag'
        value: root.Mag 
        callback: root.edit
    ParamValue:
        param: 'Diam'
        value: root.Diam
        callback: root.edit
    ParamValue:
        param: 'Info'
        value: root.Other
        callback: root.edit

    Label:
        size_hint: 1, 1

<ParamLabel@Label>:
    size_hint: None, None
    size: dp(100), dp(26)
    text_size: self.size
    padding: dp(5), dp(1)
    markup: True
    halign: 'right'
    valign: 'center'
    color: app.lowlight_color
    font_size: app.form_font_size

<WhiteParamLabel@ParamLabel>:
    canvas.before:
        Color:
            rgba: .8, .8, .8, 1
        Rectangle:
            pos: self.pos
            size: self.size
    color: 0, 0, 0, 1

<ParamValue2@TextInput>:
    size_hint: None, None
    size: dp(50), dp(26)
    halign: 'right'
    valign: 'center'
    background_color: .8, .8, .8, 1
    font_size: app.form_font_size

<MyBoxLayout>:
    size_hint: 1, None
    height: dp(24)

<DSOInfo>:
    orientation: 'vertical'
    size_hint: None, None
    size: dp(360), dp(630)
    spacing: dp(2) # 3 # dp(3)
    matches: _matches
    dso_input: _dso

    Label:
        size_hint: 1, None
        height: dp(20)
        color: app.lowlight_color
        background_color: 0, 0, 0, 0
        text: 'Type DSO name below, choose from list and "select"'
    Label:
        size_hint: 1, None
        height: dp(20)
        color: app.lowlight_color
        background_color: 0, 0, 0, 0
        text: 'Or add/edit object information and "update catalogue"'

    TextInput:
        unfocus_on_touch: False
        id: _dso
        font_size: '18sp'
        text: root.dso.Name
        size_hint: 1, None
        valign: 'center'
        height: dp(30)
        on_text: root.lookup_dso(self.text)
        background_color: .8, .8, .8, 1

    Label:
        size_hint: 1, 1

    BoxLayout:
        canvas.before:
            Color:
                rgba: .1, .1, .1, 1
            Rectangle:
                pos: self.pos
                size: self.size
        id: _matches
        size_hint: 1, None
        height: dp(200)
        orientation: 'vertical'

    Label:
        size_hint: 1, 1

    MyBoxLayout:
        ParamLabel:
            text: '[b]Name[/b]'
        ParamValue2:
            text: root.Name
            on_text: root.check(self, 'Name')
            size_hint: 1, 1
            halign: 'left'

    MyBoxLayout:
        ParamLabel:
            text: '[b]Object type[/b]'
        ParamValue2:
            text: root.OT
            on_text: root.check(self, 'OT')
        ParamLabel:
            size_hint: .3, 1
            text: '1-3 char code'
            halign: 'left'

    MyBoxLayout:
        ParamLabel:
            text: '[b]Constellation[/b]'
        ParamValue2:
            on_text: root.check(self, 'Con')
            text: root.Con
        ParamLabel:
            size_hint: .3, 1
            text: '3 char code'
            halign: 'left'

    MyBoxLayout:
        ParamLabel:
            text: '[b]RA[/b]'
        ParamValue2:
            text: root.RA_h
            on_text: root.check(self, 'RA_h')
        WhiteParamLabel:
            width: dp(15)
            text: 'h'
        ParamValue2:
            on_text: root.check(self, 'RA_m')
            text: root.RA_m
        WhiteParamLabel:
            width: dp(15)
            text: "m"
        ParamValue2:
            text: root.RA_s
            on_text: root.check(self, 'RA_s')
        WhiteParamLabel:
            width: dp(15)
            text: 's'

    MyBoxLayout:
        ParamLabel:
            text: '[b]Dec[/b]'
        ParamValue2:
            text: root.Dec_d
            on_text: root.check(self, 'Dec_d')
        WhiteParamLabel:
            width: dp(15)
            text: '\u00b0'
        ParamValue2:
            text: root.Dec_m
            on_text: root.check(self, 'Dec_m')
        WhiteParamLabel:
            width: dp(15)
            text: "'"
        ParamValue2:
            text: root.Dec_s
            on_text: root.check(self, 'Dec_s')
        WhiteParamLabel:
            width: dp(15)
            text: '"'

    MyBoxLayout:
        ParamLabel:
            text: '[b]Magnitude[/b]'
        ParamValue2:
            text: root.Mag
            on_text: root.check(self, 'Mag')
 
    MyBoxLayout:
        ParamLabel:
            text: '[b]Diameter[/b]'
        ParamValue2:
            text: root.Diam
            on_text: root.check(self, 'Diam')
        ParamLabel:
            size_hint: .3, 1
            text: 'arcmins'
            halign: 'left'

    MyBoxLayout:
        ParamLabel:
            text: '[b]Other[/b]'
        ParamValue2:
            text: root.Other
            on_text: root.Other = self.text
            size_hint: 1, 1
            halign: 'left'

    MyBoxLayout:
        height: dp(30)
        Label:
            size_int: .67, .8
        Button:
            text: 'Clear fields'
            size_hint: .33, .8
            on_press: root.clear_DSO()

    Label:
        size_hint: 1, 1

    MyBoxLayout:
        height: dp(35)
        Button:
            text: 'Select'
            size_hint: .3, .8
            on_press: root.done()
        Button:
            text: 'Update catalogue'
            size_hint: .4, .8
            on_press: root.add_to_catalogue()
        Button:
            text: 'Cancel'
            size_hint: .3, .8
            on_press: root.dso.popup.dismiss()

    ParamLabel:
        size_hint: 1, None
        height: dp(35)
        text: root.message
        halign: 'center'

'''
)


class MyBoxLayout(BoxLayout):
    pass


class MatchButton(Button, JWidget):
    pass


class DSOInfo(BoxLayout):

    Name = StringProperty('')
    OT = StringProperty('')
    Con = StringProperty('')
    RA_h = StringProperty('')
    RA_m = StringProperty('')
    RA_s = StringProperty('')
    Dec_d = StringProperty('')
    Dec_m = StringProperty('')
    Dec_s = StringProperty('')
    Mag = StringProperty('')
    Diam = StringProperty('')
    Other = StringProperty('')
    message = StringProperty('')
    matches = ObjectProperty(None)
    all_valid = BooleanProperty(False)
    dso_input = ObjectProperty(None)

    def __init__(self, dso, **kwargs):
        self.dso = dso

        # fill in current values
        for p in ['Name', 'Con', 'OT', 'Mag', 'Diam', 'Other']:
            setattr(self, p, getattr(dso, p))

        # deal with RA/Dec
        try:
            self.RA_h, self.RA_m, self.RA_s = dso.RA.replace('h', '').split()
            self.Dec_d, self.Dec_m, self.Dec_s = dso.Dec.replace('\u00b0', '').split()
        except:
            pass

        super().__init__(**kwargs)
        self.max_matches = 12
        self.match_buttons = [
            MatchButton(on_press=self.choose_dso) for i in range(self.max_matches)
        ]
        for b in self.match_buttons:
            self.matches.add_widget(b)

        Clock.schedule_once(self.set_focus, 0)

    def set_focus(self, dt):
        self.dso_input.focus = True

    def on_Mag(self, *args):
        if self.Mag == 'nan':
            self.Mag = ''

    def on_Diam(self, *args):
        if self.Diam == 'nan':
            self.Diam = ''

    def check_value(self, name, value):
        try:
            if name == 'Name':
                ok = len(value) > 0
                mess = 'must supply a name'
            elif name == 'Mag':
                ok = self.in_range(value, -20, 40, nonempty=False)
                mess = 'magnitude out of range'
            elif name == 'OT':
                ok = len(value) in [1, 2, 3]
                mess = 'object type must be 1 to 3-char code'
            elif name == 'Con':
                ok = len(value) == 3
                mess = 'constellation must be 3-char code'
            elif name == 'RA_h':
                ok = self.in_range(value, 0, 23)
                mess = 'RA hours must be 0-23'
            elif name == 'RA_m':
                ok = self.in_range(value, 0, 60)
                mess = 'RA mins must be 0-60'
            elif name == 'RA_s':
                ok = self.in_range(value, 0, 60)
                mess = 'RA secs must be 0-60'
            elif name == 'Dec_d':
                ok = self.in_range(value, -90, 90)
                mess = 'Dec degrees must be -90 to +90'
            elif name == 'Dec_m':
                ok = self.in_range(value, 0, 60)
                mess = 'Dec mins must be 0-60'
            elif name == 'Dec_s':
                ok = self.in_range(value, 0, 60)
                mess = 'Dec secs must be 0-60'
            elif name == 'Diam':
                ok = self.in_range(value, 0, 9999, nonempty=False)
                mess = 'Diameter must be a positive number'
            elif name == 'Other':
                ok = True
                mess = ''
        except Exception:
            ok = False
            mess = 'validation issue'

        if ok:
            mess = None

        return mess

    def check(self, field, name):
        value = field.text.strip()
        mess = self.check_value(name, value)
        setattr(self, name, value)
        if mess is None:
            self.message = ''
            field.foreground_color = 0, 0, 0, 1
        else:
            self.message = mess
            field.foreground_color = 1, 0, 0, 1

    def in_range(self, val, lo, hi, nonempty=True):
        if nonempty and not val:
            return False
        if not nonempty and val == 'nan':
            return True
        if not nonempty and not val:
            return True
        try:
            v = float(val)
            return v <= hi and v >= lo
        except:
            return False

    def done(self, *args):
        # validate properties and form into suitable dict for DSO to display

        props = {}
        for p in ['OT', 'Con', 'Diam', 'Mag', 'Other']:
            value = getattr(self, p)
            if self.check_value(p, value) is None:
                props[p] = value
            else:
                props[p] = ''

        props['Name'] = self.Name

        if (
            self.check_value('RA_h', self.RA_h) is None
            and self.check_value('RA_m', self.RA_m) is None
            and self.check_value('RA_s', self.RA_s) is None
        ):
            props['RA'] = '{:2s}h {:2s} {:2s}'.format(self.RA_h, self.RA_m, self.RA_s)
        else:
            props['RA'] = ''

        if (
            self.check_value('Dec_d', self.Dec_d) is None
            and self.check_value('Dec_m', self.Dec_m) is None
            and self.check_value('Dec_s', self.Dec_s) is None
        ):
            props['Dec'] = '{:s}\u00b0 {:2s} {:2s}'.format(
                self.Dec_d, self.Dec_m, self.Dec_s
            )
        else:
            props['Dec'] = ''

        self.dso.selected(props)

    def choose_dso(self, but):
        if len(but.text.strip()) > 0:
            try:
                ot, name = but.text.split(':')
                self.show_DSO(name.strip(), ot.strip())
            except:
                pass

    def show_DSO(self, name, ot):
        self.Name = name
        details = Component.get('ObservingList').lookup_details(
            '{:}/{:}'.format(name, ot)
        )
        self.OT = details.get('OT', '')
        self.Con = details.get('Con', '')
        self.Mag = str(details.get('Mag', ''))
        self.Diam = str(details.get('Diam', ''))
        self.Other = str(details.get('Other', ''))
        ra1, ra2, ra3 = str(RA(details.get('RA', ''))).split(' ')
        self.RA_h = ra1.strip()[:-1]
        self.RA_m = ra2.strip()
        self.RA_s = ra3.strip()
        dec1, dec2, dec3 = str(Dec(details.get('Dec', ''))).split(' ')
        self.Dec_d = dec1.strip()[:-1]
        self.Dec_m = dec2.strip()
        self.Dec_s = dec3.strip()



    def clear_DSO(self):
        for p in ['Name', 'OT', 'Con', 'RA_h', 'RA_m', 'RA_s', 'Dec_d', 'Dec_m', 'Dec_s', 'Mag', 'Diam', 'Other']:
            setattr(self, p, '')

    def add_to_catalogue(self):

        # check that data is all valid
        for p in [
            'Name',
            'OT',
            'Con',
            'RA_h',
            'RA_m',
            'RA_s',
            'Dec_d',
            'Dec_m',
            'Dec_s',
            'Mag',
            'Diam',
            'Other',
        ]:
            resp = self.check_value(p, getattr(self, p))
            if resp is not None:
                self.message = resp
                return

        # check if catalogue exists; if not, create it and write header
        # append row of data
        try:
            path = App.get_running_app().get_path('catalogues')
            obj_file = os.path.join(path, 'user_objects.csv')
            if not os.path.exists(obj_file):
                with open(obj_file, 'w') as f:
                    f.write('Name,RA,Dec,Con,OT,Mag,Diam,Other\n')
        except Exception as e:
            self.message = 'Problem creating user objects file'
            Logger.error('DSO: problem creating objects list ({:})'.format(e))
            return

        try:
            ra = 15 * float(self.RA_h) + float(self.RA_m) / 4 + float(self.RA_s) / 240
            if float(self.Dec_d) < 0:
                dec = (
                    float(self.Dec_d)
                    - float(self.Dec_m) / 60
                    - float(self.Dec_s) / 3600
                )
            else:
                dec = (
                    float(self.Dec_d)
                    + float(self.Dec_m) / 60
                    + float(self.Dec_s) / 3600
                )
        except Exception as e:
            self.message = 'Problem converting RA or Dec'
            Logger.error('DSO: coverting RA or Dec ({:})'.format(e))
            return

        try:
            Name = self.Name.strip()
            OT = self.OT.strip().upper()
            Con = self.Con.strip().upper()
            Mag = self.Mag.strip()
            if len(Mag) == 0:
                Mag = math.nan
            Diam = self.Diam.strip()
            if len(Diam) == 0:
                Diam = math.nan
            Other = self.Other.strip().replace(',', ';')
            with open(obj_file, 'a') as f:
                f.write(
                    '{:},{:.6f},{:.6f},{:},{:},{:},{:},{:}\n'.format(
                        Name, ra, dec, Con, OT, Mag, Diam, Other
                    )
                )
        except Exception as e:
            self.message = 'Problem writing to user objects file'
            Logger.error('DSO: writing to user objects file ({:})'.format(e))
            return

        # update objects listing (overwriting, if duplicate exists)
        ol = Component.get('ObservingList')
        try:
            ol.objects['{:}/{:}'.format(Name, OT)] = {
                'Name': Name,
                'RA': ra,
                'Dec': dec,
                'Con': Con,
                'OT': OT,
                'Obs': 0,
                'Added': '',
                'List': 'N',
                'Other': Other,
                'Notes': '',
                'Mag': float(Mag),
                'Diam': float(Diam),
            }
            ol.compute_transits()
            ol.update_status()

        except Exception as e:
            self.message = 'Problem updating objects list'
            Logger.error('DSO: problem updating objects list ({:})'.format(e))
            return

        self.message = 'Written to catalogue!'

    def lookup_dso(self, name):
        """User has changed name field so look it up"""

        self.clear_DSO()
        for b in self.match_buttons:
            b.text = ''
        name = name.strip()
        if name:
            matches = sorted(
                Component.get('ObservingList').lookup(
                    name, max_matches=self.max_matches
                )
            )
            if len(matches) == 1:
                name, ot = matches[0].split('/')
                self.show_DSO(name.strip(), ot.strip())
            else:
                for i, m in enumerate(matches):
                    nm, ot = m.split('/')
                    self.match_buttons[i].text = '{:}: {:}'.format(ot, nm)


class DSO(BoxLayout, Component):

    Name = StringProperty('')
    Con = StringProperty('')
    RA = StringProperty('')
    Dec = StringProperty('')
    OT = StringProperty('')
    Mag = StringProperty('')
    Diam = StringProperty('')
    Other = StringProperty('')
    otypes = DictProperty({})

    props = ['Name', 'Con', 'OT', 'RA', 'Dec', 'Mag', 'Diam', 'Other']

    show_DSO = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        otypes = Component.get('Catalogues').get_object_types()
        self.otypes = {k: v['name'] for k, v in otypes.items()}
        App.get_running_app().gui.add_widget(self, index=8)
        Logger.info('DSO: initialised')

    def on_Mag(self, *args):
        if self.Mag == 'nan':
            self.Mag = ''

    def on_Diam(self, *args):
        if self.Diam == 'nan':
            self.Diam = ''
        else:
            try:
                self.Diam = '{:.2f}'.format(float(self.Diam))
            except Exception:
                self.Diam = ''

    def on_new_object(self, settings=None):
        ''' Called at start and whenever user selects new object. Also called
            when user selects a row from the DSO table.
        '''
        if settings is None:
            self.settings = Component.get('Metadata').get({'Name', 'OT'})
            self._new_object()
        else:
            ''' Ask user for confirmation that they wish to rename the object
            '''
            self.settings = settings
            if self.Name:
                self.popup = JPopup(
                    title='Change name to {:}?'.format(settings['Name']),
                    actions={
                        'Cancel': self.cancel_name_change,
                        'Yes': self.confirmed_name_change,
                    },
                )
                self.popup.open()
            else:
                self.confirmed_name_change()

    def confirmed_name_change(self, *args):
        self.changed = not Component.get('Stacker').is_empty()
        self._new_object()

    def cancel_name_change(self, *args):
        pass

    def _new_object(self, *args):
        ''' Helper method called after normal new object selection or confirmation
            of change of name
        '''
        settings = self.settings

        if 'Name' in settings and 'OT' in settings:
            #  translate a few cases to new OTs
            nm = settings['Name']
            ot = settings['OT'].upper()
            # deal with some legacies from v1
            if ot == 'G+':
                if nm.startswith('Arp') or nm.startswith('VV') or nm.startswith('AM '):
                    ot = 'PG'
                elif (
                    nm.startswith('Hick')
                    or nm.startswith('PCG')
                    or nm.startswith('SHK')
                ):
                    ot = 'CG'
            lookup_settings = Component.get('ObservingList').lookup_name(
                '{:}/{:}'.format(nm, ot)
            )
            if lookup_settings is not None:
                settings = lookup_settings

        # now extract all
        for p in self.props:
            setattr(self, p, str(settings.get(p, '')))
        self.saved_props = {p: getattr(self, p) for p in self.props}

    def on_save_object(self):
        Component.get('Metadata').set(
            {'Name': self.Name.strip(), 'OT': self.OT, 'Con': self.Con}
        )

    def current_object_coordinates(self):
        if self.RA and self.Dec:
            return (float(RA(self.RA)), float(Dec(self.Dec)))
        return None, None

    def paste_RA(self, *args):
        Clipboard.copy(self.RA)

    def paste_Dec(self, *args):
        Clipboard.copy(self.Dec)

    def edit(self, *args):
        content = DSOInfo(self)
        self.popup = JPopup(
            title='Select, add or edit DSO', content=content, posn='top-left'
        )
        self.popup.open()

    def selected(self, new_props, *args):
        for p in self.props:
            if p in new_props:
                setattr(self, p, new_props[p])
            else:
                setattr(self, p, '')
        self.changed = (
            self.saved_props != {p: getattr(self, p) for p in self.props}
            and not Component.get('Stacker').is_empty()
        )
        self.popup.dismiss()

    # commented this while seeking weird touch down bug
    def on_touch_down(self, touch):
        # print(' TD in DSO')
        if (
            self.collide_point(*touch.pos)
            and touch.pos[0] < dp(100)
            and App.get_running_app().showing == 'main'
        ):
            return super().on_touch_down(touch)
        return False
