''' Handles DSO details including lookup and catalogue entry
'''

import math
from functools import partial

from loguru import logger

from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty, DictProperty
from kivy.lang import Builder
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog

from jocular.component import Component
from jocular.RA_and_Dec import RA, Dec

Builder.load_string('''

<DSOBoxLayout@MDBoxLayout>:
    size_hint: (1, None)
    height: '42dp'

<DSO_panel>:
    name_field: _name
    ot_field: _ot
    padding: '10dp'
    adaptive_height: True
    pos_hint: {'top': .99, 'x': 0} if root.dso.show_DSO else {'top': .99, 'right': -1000} 
    size_hint: None, None
    orientation: 'vertical'
    spacing: dp(10)

    BoxLayout:
        size_hint: (1, None)
        height: '48dp'
        JTextField:
            id: _name
            width: '300dp'
            height: '40dp'
            hint_text: 'name'
            on_text: root.dso.Name_changed(self.text)
            font_size: '{:}sp'.format(int(app.form_font_size[:-2]) + 8) # 28sp

    DSOBoxLayout:
        JTextField:
            id: _ot
            hint_text: 'type'
            #helper_text: 'e.g. PN, GX'
            on_focus: root.dso.OT_changed(self) if not self.focus else None
            text: root.dso.OT
        JTextField:
            width: '140dp'
            hint_text: 'con'
            #helper_text: 'e.g. PER'
            on_text: root.dso.prop_changed(self, 'Con')
            text: root.dso.Con

    DSOBoxLayout:
        JTextField:
            hint_text: 'RA'
            #helper_text: "e.g. 21h30'42"
            on_text: root.dso.prop_changed(self, 'RA', update=False)
            text: '' if root.dso.RA == 'nan' else root.dso.RA
            on_focus: root.dso.prop_changed(self, 'RA') if not self.focus else None

        JTextField:
            width: '130dp'
            hint_text: 'dec'
            #helper_text: "-3 21' 4"
            on_text: root.dso.prop_changed(self, 'Dec', update=False)
            text: '' if root.dso.Dec == 'nan' else root.dso.Dec
            on_focus: root.dso.prop_changed(self, 'Dec') if not self.focus else None

    DSOBoxLayout:
        JTextField:
            hint_text: 'diam'
            #helper_text: "e.g. 21'"
            on_text: root.dso.prop_changed(self, 'Diam', update=False)
            text: '' if root.dso.Diam == 'nan' else root.dso.Diam
            on_focus: root.dso.prop_changed(self, 'Diam') if not self.focus else None

        JTextField:
            width: '110dp'
            hint_text: 'mag'
            #helper_text: "e.g. 14.1"
            # on_focus: root.dso.prop_changed(self, 'Mag') if not self.focus else None
            on_text: root.dso.prop_changed(self, 'Mag')
            text: '' if root.dso.Mag == 'nan' else root.dso.Mag

    DSOBoxLayout:
        JTextField:
            width: '200dp'
            hint_text: 'other'
            #helper_text: ""
            text: root.dso.Other
            on_text: root.dso.prop_changed(self, 'Other')

''')


def prop_to_str(prop, val):
    ''' convert DSO to canonical str format for display/comparison purposes
    '''
    if prop in {'Con', 'Name', 'OT', 'Other'}:
        return val
    if prop == 'RA':
        return str(RA(val)) if val else ''
    if prop == 'Dec':
        return str(Dec(val)) if val else ''
    if prop == 'Mag':
        return float_to_str(val)
    if prop == 'Diam':
        return arcmin_to_str(val)

def float_to_str(x):
    ''' nans with return empty string
    '''
    try:
        s = str(x)
        if s == 'nan':
            return ''
        return s
    except:
        return ''

def str_to_float(s):
    try:
        return float(s)
    except:
        return math.nan

def str_to_arcmin(diam):
    ''' convert string representation of diameter to float, taking
        account of possible suffices (degrees, min, secs); 
        need to raise correct exception (to do)
    '''
    diam = diam.strip()
    if diam == 'nan':
        return math.nan
    if not diam:
        return math.nan
    if diam.endswith('d') or diam.endswith('\u00b0'):
        return float(diam[:-1]) * 60
    if diam.endswith('"'):
        return float(diam[:-1]) / 60
    if diam.endswith("'"):
        return float(diam[:-1])
    return float(diam)

def arcmin_to_str(diam):
    ''' convert float representation of diam to a string with
        the most suitable suffix (degree, arcmin, arcsec)
    '''
    if type(diam) == str:
        return diam
    if math.isnan(diam):
        return ''
    if diam > 60:
        return "{:.2f}\u00b0".format(diam / 60)
    if diam < 1:
        return '{:.2f}"'.format(diam * 60)
    return "{:.2f}\'".format(diam)


def validated_prop(val, prop):
    ''' is val a valid property of type prop
    '''
    if prop == 'OT':
        return None if len(val) != 2 else val
    if prop == 'Con':
        return None if len(val) != 3 else val
    if prop == 'RA':
        RA_deg = RA.parse(val)        
        return None if RA_deg is None else str(RA(RA_deg))
    if prop == 'Dec':
        Dec_deg = Dec.parse(val)
        return None if Dec_deg is None else str(Dec(Dec_deg))
    if prop == 'Mag':
        try:
            return str(float(val))
        except:
            return None
    if prop == 'Diam':
        try:
            diam_str = str_to_arcmin(val)
            return arcmin_to_str(diam_str)
        except:
            return None
    if prop == 'Other':
        return val
    return False


class DSO_panel(MDBoxLayout):
    ''' visual representation of editable DSO properties
    '''

    def __init__(self, dso, **kwargs):
        self.dso = dso
        super().__init__(**kwargs)

class DSO(Component):

    save_settings = ['show_DSO']

    Name = StringProperty('')
    Con = StringProperty('')
    RA = StringProperty('')
    Dec = StringProperty('')
    OT = StringProperty('')
    Mag = StringProperty('')
    Diam = StringProperty('')
    Other = StringProperty('')
    otypes = DictProperty({})
    updating = BooleanProperty(False)
    original_props = DictProperty(None, allownone=True)

    props = ['Name', 'Con', 'OT', 'RA', 'Dec', 'Mag', 'Diam', 'Other']

    show_DSO = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.cats = Component.get('Catalogues')
        otypes = self.cats.get_object_types()
        self.otypes = {k: v['name'] for k, v in otypes.items()}
        self.dso_panel = DSO_panel(self)
        self.app.gui.add_widget(self.dso_panel)        

    def on_new_object(self):
        ''' Called when user clicks new
        '''
        self.update_properties({})
        self.original_props = {}

    def on_previous_object(self):
        ''' User selected an object in observations table
        '''

        # get data for object from Metadata
        md = Component.get('Metadata').get(self.props)

        # lookup using name and object type
        reference_settings = self.cats.lookup(md.get('Name', ''), OT=md.get('OT', ''))

        # use ref settings if available, else Name/OT from metadata
        settings = md if reference_settings is None else reference_settings

        # update all properties which causes screen updates
        self.update_properties(settings)

        # store original props so as to be able to spot changes
        self.original_props = settings

        for p, val in settings.items():
            logger.info('{:} = {:}'.format(p, val))

    def update_properties(self, props, update_name=True, update_OT=True):
        ''' Fill in fields with properties
        '''

        if props is None:
            return

        self.updating = True
        for p in set(self.props):
            setattr(self, p, prop_to_str(p, props.get(p, '')))
        if update_name:
            self.dso_panel.name_field.text = self.Name
        if update_OT:
            self.dso_panel.ot_field.text = self.OT
        self.updating = False
 
    def new_DSO_name(self, settings):
        ''' Called from ObservingList when user selects a name from the DSO table. 
        '''
        
        # if we already have a name and a non-empty stack, ask user to confirm
        new_name = settings.get('Name','')
        if not Component.get('Stacker').is_empty() and self.Name and self.Name != new_name:
            change = 'from {:} to {:}'.format(self.Name, new_name)
            self.dialog = MDDialog(
                auto_dismiss=False,
                text="Are you sure you wish to change the name of the current DSO\n" + change,
                buttons=[
                    MDFlatButton(text="YES", 
                        on_press=partial(self.change_name, settings)),
                    MDFlatButton(
                        text="CANCEL", 
                        on_press=self._cancel)
                ],
            )
            self.dialog.open()
        else:
            self.change_name(settings)

    def change_name(self, settings, *args):

        if hasattr(self, 'dialog'):
            self.dialog.dismiss()

        # update properties
        self.update_properties(self.cats.lookup(
            settings.get('Name', ''), OT=settings.get('OT', '')))

    def _cancel(self, *args):
        self.dialog.dismiss()

    def Name_changed(self, val, *args):
        ''' Name is changed as soon as the text is altered to allow lookup
        '''

        if self.updating:
            return

        matches = self.cats.lookup(val)
        if matches is None:
            self.update_properties({}, update_name=False)
        else:
            logger.debug('Found match: {:}'.format(matches))
            self.update_properties(matches)
        self.Name = val
        # self.check_for_change()

    def OT_changed(self, widget):
        ''' Allow any object type of 1-3 chars
        '''

        if self.updating:
            return

        widget.invalid = False
        ot = widget.text.upper()
        widget.invalid = len(ot) > 3
        if not widget.invalid:
            self.OT = ot
            props = self.cats.lookup(self.Name, OT=ot)
            if props is not None:
                self.update_properties(props)
        self.check_for_change()

    def prop_changed(self, widget, prop, update=True):
        if self.updating:
            return
        self.updating = True
        widget.invalid = False
        val = widget.text.strip()
        if val == '':
            widget.text = '='
            widget.text = ''
            setattr(self, prop, val)
        else:
            valid_prop = validated_prop(val, prop)
            widget.invalid = valid_prop is None
            if valid_prop is not None:
                if update:
                    setattr(self, prop, valid_prop)
        self.check_for_change()
        self.updating = False


    def check_for_change(self):
        ''' Compare original with current properties
        '''

        orig = {p: prop_to_str(p, self.original_props.get(p, '')) for p in  self.props}
        now = {p: prop_to_str(p, getattr(self, p)) for p in self.props}
        self.changed = 'DSO properties changed' if orig != now else ''
        if orig != now:
            logger.trace('orig {:}  now {:}'.format(orig, now))
        # self.app.gui.has_changed('DSO', orig != now)
        return orig != now
 
    def on_save_object(self):
        ''' Update metadata and add any new or changed DSO to user catalogue
        '''

        props = {
            'Name': self.Name.strip(),
            'OT': self.OT.strip(),
            'RA': RA.parse(self.RA),
            'Dec': Dec.parse(self.Dec),
            'Con': self.Con.strip(),
            'Diam': str_to_arcmin(self.Diam),
            'Mag': str_to_float(self.Mag),
            'Other': self.Other.strip()
            }

        logger.trace('Checking for change')


        # update metadata
        if props['Name'] == '':
            props['Name'] = 'anon'
        Component.get('Metadata').set(props)

        known_props = self.cats.lookup(props['Name'], OT=props['OT'])

        # existing object and not changed => do nothing
        if known_props is not None:
            orig = {p: prop_to_str(p, known_props.get(p, '')) for p in self.props}
            now = {p: prop_to_str(p, getattr(self, p)) for p in self.props}
            if orig == now:
                logger.trace('known object and has not changed')
                return
 
        ''' add to user DSO catalogue if new or update if modified and has 
            well-formed name/OT/RA/Dec
        ''' 
        if props['Name'] and props['OT'] and props['RA'] is not None and props['Dec'] is not None:
            logger.trace('New or modified object and has Name/OT/RA/Dec so updating user catalogue')
            self.cats.update_user_object(props)
 


    def current_object_coordinates(self):
        ''' Called by platesolver
        '''
        if self.RA and self.Dec:
            return (float(RA(self.RA)), float(Dec(self.Dec)))
        return None, None
