''' Handles DSO details including lookup and catalogue entry
    Code is quite complex due to need for 2-way format conversion etc
'''

import math
from functools import partial

from loguru import logger

from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty, DictProperty
from kivy.lang import Builder
from kivymd.uix.stacklayout import MDStackLayout
from kivymd.uix.button import MDRoundFlatButton, MDRoundFlatIconButton
from kivymd.uix.boxlayout import MDBoxLayout

from jocular.component import Component
from jocular.RA_and_Dec import RA, Dec
from jocular.utils import is_null

Builder.load_string('''

<DSOBoxLayout@MDBoxLayout>:
    size_hint: (1, None)
    height: '40dp'

<DSO_panel>:
    name_field: _name
    type_field: _type_field
    padding: '10dp'
    adaptive_height: True
    #adaptive_width: True
    pos_hint: {'top': .99, 'x': 0} if root.dso.show_DSO else {'top': .99, 'right': -1000} 
    size_hint: None, None
    orientation: 'vertical'
    spacing: "10dp"

    BoxLayout:
        size_hint: (1, None)
        height: '48dp'
        JTextField:
            id: _name
            width: '300dp'
            height: '40dp'
            hint_text: 'dso'
            on_text: root.dso.Name_changed(self.text)
            font_size: '{:}sp'.format(int(app.form_font_size[:-2]) + 8) # 28sp

    DSOBoxLayout:
        JTextField:
            id: _type_field
            hint_text: 'type'
            #helper_text: 'e.g. PN, GX'
            on_focus: root.dso.OT_changed(self) if not self.focus else None
            text: root.dso.OT
        JTextField:
            width: '140dp'
            hint_text: 'con'
            #helper_text: 'e.g. PER'
            on_focus: root.dso.Con_changed(self) if not self.focus else None
            text: root.dso.Con

    DSOBoxLayout:
        JTextField:
            hint_text: 'RA'
            #helper_text: "e.g. 21h30'42"
            #helper_text_mode: 'on_focus'
            on_focus: root.dso.RA_changed(self) if not self.focus else None
            text: '' if root.dso.RA == 'nan' else root.dso.RA
        JTextField:
            width: '130dp'
            hint_text: 'dec'
            #helper_text: "-3 21' 4"
            on_focus: root.dso.Dec_changed(self) if not self.focus else None
            text: '' if root.dso.Dec == 'nan' else root.dso.Dec

    DSOBoxLayout:
        JTextField:
            hint_text: 'diam'
            #helper_text: "e.g. 21'"
            on_focus: root.dso.Diam_changed(self) if not self.focus else None
            text: root.dso.Diam

        JTextField:
            width: '110dp'
            hint_text: 'mag'
            #helper_text: "e.g. 14.1"
            on_focus: root.dso.Mag_changed(self) if not self.focus else None
            text: root.dso.Mag

    DSOBoxLayout:
        JTextField:
            width: '200dp'
            hint_text: 'other'
            #helper_text: ""
            on_focus: root.dso.Other_changed(self) if not self.focus else None
            text: root.dso.Other

''')




class DSO_panel(MDBoxLayout):
    ''' visual representation of editable DSO properties
    '''

    def __init__(self, dso, **kwargs):
        self.dso = dso
        super().__init__(**kwargs)

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

@logger.catch()
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
    if math.isnan(diam):
        return ''
    if diam > 60:
        return "{:.2f}\u00b0".format(diam / 60)
    if diam < 1:
        return '{:.2f}"'.format(diam * 60)
    return "{:.2f}\'".format(diam)


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
    can_delete = BooleanProperty(True)
    can_update = BooleanProperty(True)

    props = ['Name', 'Con', 'OT', 'RA', 'Dec', 'Mag', 'Diam', 'Other']

    show_DSO = BooleanProperty(False)
    check_ambiguity = BooleanProperty(False) # check for ambiguous Names e.g. PN/GG

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        otypes = Component.get('Catalogues').get_object_types()
        self.otypes = {k: v['name'] for k, v in otypes.items()}
        self.dso_panel = DSO_panel(self)
        self.app.gui.add_widget(self.dso_panel)
        self.add_button = MDRoundFlatIconButton(
            pos_hint={"center_y": .65},
            icon='plus', 
            text='update DSO')
        self.add_button.bind(on_press=self.update_DSO)
        self.app.gui.add_widget(self.add_button)
        self.del_button = MDRoundFlatIconButton(
            pos_hint={"center_y": .6},
            icon='minus', 
            text='delete DSO')
        self.del_button.bind(on_press=self.delete_DSO)
        self.app.gui.add_widget(self.del_button)
        self.current_props = {}

    def on_new_object(self):
        ''' Called when user clicks new
        '''

        # empty DSO details & store initial values
        self.update_props()
        self.store_current_props()
        self.can_update = False
        self.can_delete = False

    def on_can_update(self, *args):
        self.add_button.x = 0 if self.can_update else -1000

    def on_can_delete(self, *args):
        self.del_button.x = 0 if self.can_delete else -1000

    def on_previous_object(self):
        ''' Called when user selects object in observations table
        '''

        # Data for new object is in Metadata
        settings = Component.get('Metadata').get({'Name', 'OT'})

        # lookup rest from name and object type
        full_settings = Component.get('ObservingList').lookup_name(
            '{:}/{:}'.format(settings.get('Name', ''), settings.get('OT', '')))

        # update props if we managed a lookup, else use metadata values
        if full_settings.get('Name', ''):
            self.update_props(settings=full_settings)
        else:
            self.update_props(settings=settings)

        self.store_current_props()

        self.can_update = self.is_user_defined()
        self.can_delete = self.is_user_defined()

        logger.info('loading DSO {:}'.format(full_settings.get('Name', 'anon')))

    def store_current_props(self):
        logger.info('current props {:}'.format(self.current_props))
        self.current_props = {p: getattr(self, p) for p in self.props}

    def new_DSO_name(self, settings):
        ''' Called when user selects a name from the DSO table. What we do depends
            on whether we already have an object loaded, in which case we note the
            change of name so that it can be confirmed on save.
        '''

        # lookup rest
        full_settings = Component.get('ObservingList').lookup_name(
            '{:}/{:}'.format(settings.get('Name', ''), settings.get('OT', '')))

        # update DSO properties
        self.update_props(settings=full_settings)

        # if stack is empty, treat this as a new observation
        if Component.get('Stacker').is_empty():
            logger.info('new DSO from table {:}'.format(full_settings))
            self.store_current_props()
            # self.initial_values = {p: getattr(self, p) for p in self.props}
        else:
            logger.info('user changes DSO name {:}'.format(full_settings))


    @logger.catch()
    def Name_changed(self, val, *args):
        ''' Name is changed as soon as the text is altered to allow lookup
            while other properties are changed on defocus.
        '''

        # don't do any lookups if we are initialising 
        if not self.check_ambiguity:
            return

        # lookup
        OTs = Component.get('ObservingList').lookup_OTs(val)

        # if unique match, fill in
        if len(OTs) ==  1:
            self.exact_match(val + '/' + OTs[0])
            self.can_update = False
            return
 
        self.can_update = True

        # no match
        if len(OTs) == 0:
            self.Name = val
            self.new_values['Name'] = val
            self.check_for_change()
            return

        self.choose_OT = MDStackLayout(pos_hint={'x': .1, 'top': .99}, spacing=[20, 20])
        self.app.gui.add_widget(self.choose_OT)
        for ot in OTs:
            self.choose_OT.add_widget(MDRoundFlatButton(text=ot,
                on_press=partial(self.exact_match, val + '/' + ot)))

    def exact_match(self, m, *args):
        ''' We have exact match for DSO (name/OT) so clear any OT choice
            widgets and update values
        '''
        if hasattr(self, 'choose_OT'):
            self.choose_OT.clear_widgets()
            del self.choose_OT
        logger.debug('Found match: {:}'.format(m))
        self.update_props(settings=Component.get('ObservingList').lookup_name(m), 
            update_name_field=False, initialising=False)
        self.new_values['Name'] = self.Name
        self.can_delete = self.is_user_defined()
        self.check_for_change()

    def update_DSO(self, *args):
        ''' User clicks update DSOs so store current props (to detect
            any future edits) and ask Catalogues to update
        '''

        # don't update if it has no name
        if is_null(self.Name):
            return

        props = {'Name': self.Name}

        # clear OT if it doesn't exist
        props['OT'] = '' if is_null(self.OT) else self.OT

        # form key (ensure upper)
        name = '{:}/{:}'.format(props['Name'], props['OT']).upper()

        # ensure values are updates
        for k, v in self.current_props.items():
            if k in self.new_values and self.new_values[k] != v:
                self.current_props[k] = self.new_values[k]

        # ensure props are in the correct format, removing them if not
        try:
            props['Con'] = self.current_props['Con']
        except:
            pass
        try:
            props['RA'] = RA(self.current_props['RA'])
        except:
            pass
        try:
            props['Dec'] = Dec(self.current_props['Dec'])
        except:
            pass
        try:
            props['Diam'] = str_to_arcmin(self.current_props['Diam'])
        except:
            pass
        try:
            props['Mag'] = float(self.current_props['Mag'])
        except:
            pass
        try:
            props['Other'] = self.current_props['Other']
        except:
            pass

        Component.get('Catalogues').update_user_objects(name, props)
        self.can_update = False
        self.can_delete = True


    def delete_DSO(self, *args):
        ''' Remove current DSO from user objects list
        '''
        name = '{:}/{:}'.format(self.Name, self.OT).upper()
        Component.get('Catalogues').delete_user_object(name)
        self.on_new_object()


    @logger.catch()
    def update_props(self, settings=None, update_name_field=True, initialising=True):
        ''' update DSO properties, causing display update
        '''

        if initialising:
            self.check_ambiguity = False

        if settings is None:
            settings = {}

        self.Name = settings.get('Name', '')
        self.RA = str(RA(settings.get('RA', math.nan)))
        self.Dec = str(Dec(settings.get('Dec', math.nan)))
        self.Con = settings.get('Con', '')
        self.OT = settings.get('OT', '')
        self.Mag = float_to_str(settings.get('Mag', ''))
        self.Other = settings.get('Other', '')

        self.Diam = arcmin_to_str(str_to_arcmin(str(settings.get('Diam', ''))))

        self.store_current_props()

        # update new values to reflect changes
        self.new_values = {p: getattr(self, p) for p in self.props}
        if update_name_field:
            self.dso_panel.name_field.text = self.Name
        self.check_for_change()

        self.check_ambiguity = True


    @logger.catch()
    def check_for_change(self):
        ''' Check if any property has changed since we last saved
        '''
        changes = []
        for k, v in self.current_props.items():
            if k in self.new_values and self.new_values[k] != v:
                logger.info('{:} has changed from {:} to {:}'.format(k, v, self.new_values[k]))
                changes += [True]

        self.can_update = any(changes)
        # self.add_button.disabled = not any(changes)

    def is_user_defined(self):
        key = '{:}/{:}'.format(self.Name, self.OT).upper()
        return Component.get('Catalogues').is_user_defined(key)

    def OT_changed(self, widget):
        ''' For the moment we allow any object type but in the future
            could check if one of known types and allow user to
            introduce a new type via a dialog
        '''
        ot = widget.text.upper()
        widget.invalid = len(ot) > 3
        if not widget.invalid:
            self.OT = ot
            self.new_values['OT'] = ot
            self.can_delete = self.is_user_defined()
            #key = '{:}/{:}'.format(self.Name, self.OT).upper()
            #self.del_button.disabled = not self.is_user_defined()
            self.check_for_change()

    def Con_changed(self, widget):
        ''' Likewise, we should check constellations in future
        '''
        con = widget.text.upper()
        widget.invalid = len(con) > 3
        if not widget.invalid:
            self.Con = con
            self.new_values['Con'] = con
            self.check_for_change() 

    def RA_changed(self, widget):
        ''' RA has to be in correct format
        '''
        RA_str = widget.text.strip()
        if not RA_str:
            return
        ra_deg = RA.parse(RA_str)
        widget.invalid =  ra_deg is None    
        if not widget.invalid:
            self.RA = '-'  # need to force an update
            self.RA = str(RA(ra_deg))
            self.new_values['RA'] = self.RA
            self.check_for_change() 

    def Dec_changed(self, widget):
        Dec_str = widget.text.strip()
        if not Dec_str:
            return
        dec_deg = Dec.parse(Dec_str)
        widget.invalid = dec_deg is None
        if not widget.invalid:
            self.Dec = '-'  # need to force an update
            self.Dec = str(Dec(dec_deg))
            self.new_values['Dec'] = self.Dec
            self.check_for_change() 

    def Mag_changed(self, widget):
        ''' should be a int or float
        '''
        mag_str = widget.text.strip()
        if not mag_str:
            return
        try:
            mag = str(float(mag_str))
            self.Mag = '-'
            self.Mag = mag
            self.new_values['Mag'] = mag_str
            self.check_for_change() 
        except:
            widget.invalid = True

    def Diam_changed(self, widget):
        ''' Suffix can be d or degree symbol, ' or "
            assume arcmin if no suffix
        '''

        diam = widget.text.strip()
        if not diam:
            return
        try:
            # normalise diam by converting to arcmin then back to string
            diam = arcmin_to_str(str_to_arcmin(diam))
            self.new_values['Diam'] = diam
            self.Diam = diam
            self.check_for_change() 
        except:
            logger.warning('invalid format for diameter {:}'.format(diam))
            widget.invalid = True

    def Other_changed(self, widget):
        self.Other = widget.text.strip()
        self.new_values['Other'] = self.Other
        self.check_for_change() 
 
    @logger.catch()
    def on_save_object(self):
        ''' On saving we ensure that Name, OT and Con is saved as these 
            appear in the previous object table; other props don't need to
            be saved as they are looked up from the DSO database on each
            load.
        '''

        Component.get('Metadata').set({
            'Name': self.Name.strip(), 
            'OT': self.OT, 
            'Con': self.Con
            })

        # prepare props in canonical format
        props = {
            'Name': self.Name.strip(),
            'OT': self.OT.strip(),
            'Con': self.Con.strip(),
            'RA': RA.parse(self.RA),
            'Dec': Dec.parse(self.Dec),
            'Diam': str_to_arcmin(self.Diam),
            'Mag': str_to_float(self.Mag),
            'Other': self.Other}

        # get catalogue to check if anything has changed and update user objects if necc.
        Component.get('Catalogues').check_update(props)


    def current_object_coordinates(self):
        ''' Called by platesolver
        '''
        if self.RA and self.Dec:
            return (float(RA(self.RA)), float(Dec(self.Dec)))
        return None, None
