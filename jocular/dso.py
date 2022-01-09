''' Handles DSO details including lookup and catalogue entry
    Code is quite complex due to need for 2-way format conversion etc
'''

import math
from functools import partial

from loguru import logger

from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty
from kivy.lang import Builder
from kivymd.uix.stacklayout import MDStackLayout
from kivymd.uix.button import MDRectangleFlatButton, MDRectangleFlatIconButton, MDRaisedButton
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
    type_field: _type_field
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
            id: _type_field
            hint_text: 'type'
            #helper_text: 'e.g. PN, GX'
            on_focus: root.dso.OT_changed(self) if not self.focus else None
            text: root.dso.OT
        JTextField:
            width: '140dp'
            hint_text: 'con'
            #helper_text: 'e.g. PER'
            on_text: root.dso.Con_changed(self)
            text: root.dso.Con

    DSOBoxLayout:
        JTextField:
            hint_text: 'RA'
            #helper_text: "e.g. 21h30'42"
            on_text: root.dso.RA_changed(self)
            text: '' if root.dso.RA == 'nan' else root.dso.RA
            on_focus: root.dso.RA_changed(self, defocus=True) if not self.focus else None

        JTextField:
            width: '130dp'
            hint_text: 'dec'
            #helper_text: "-3 21' 4"
            on_text: root.dso.Dec_changed(self)
            text: '' if root.dso.Dec == 'nan' else root.dso.Dec
            on_focus: root.dso.Dec_changed(self, defocus=True) if not self.focus else None

    DSOBoxLayout:
        JTextField:
            hint_text: 'diam'
            #helper_text: "e.g. 21'"
            on_text: root.dso.Diam_changed(self)
            text: '' if root.dso.Diam == 'nan' else root.dso.Diam
            on_focus: root.dso.Diam_changed(self, defocus=True) if not self.focus else None

        JTextField:
            width: '110dp'
            hint_text: 'mag'
            #helper_text: "e.g. 14.1"
            #on_focus: root.dso.Mag_changed(self) if not self.focus else None
            on_text: root.dso.Mag_changed(self)
            text: '' if root.dso.Mag == 'nan' else root.dso.Mag

    DSOBoxLayout:
        JTextField:
            width: '200dp'
            hint_text: 'other'
            #helper_text: ""
            text: root.dso.Other
            on_text: root.dso.Other_changed(self)

''')


def prop_to_str(prop, val):
    ''' convert DSO to canonical str format for display/comparison purposes
    '''
    if prop in {'Con', 'Name', 'OT', 'Other'}:
        return val
    if prop == 'RA':
        return str(RA(val))
    if prop == 'Dec':
        if val == '':
            return ''
        return str(Dec(val))
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


''' Main classes here
'''

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
    can_delete = BooleanProperty(True)

    props = ['Name', 'Con', 'OT', 'RA', 'Dec', 'Mag', 'Diam', 'Other']

    show_DSO = BooleanProperty(False)
    # check_ambiguity = BooleanProperty(False) # check for ambiguous Names e.g. PN/GG

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.dso_panel = DSO_panel(self)
        self.app.gui.add_widget(self.dso_panel)
        self.del_button = MDRectangleFlatIconButton(
            pos_hint={"center_y": .63},
            icon='delete', 
            text='delete user-defined DSO')
        self.del_button.bind(on_press=self.delete_DSO)
        self.app.gui.add_widget(self.del_button)
        

    def on_new_object(self):
        ''' Called when user clicks new
        '''
        self.update_properties({})
        self.can_delete = False
        self.orig_name = None

    def on_previous_object(self):
        ''' User selected an object in observations table
        '''

        # get data for object from Metadata
        md = Component.get('Metadata').get({'Name', 'OT'})

        # store original name so we can see if has been changed later
        self.orig_name = '{:}/{:}'.format(md.get('Name', ''), md.get('OT', ''))

        # lookup using name and object type
        reference_settings = Component.get('ObservingList').lookup_name(
            self.orig_name)

        # use ref settings if available, else Name/OT from metadata
        settings = md if reference_settings is None else reference_settings

        # update all properties which causes screen updates
        self.update_properties(settings)

        logger.info('loading DSO')
        for p, val in settings.items():
            logger.info('{:} = {:}'.format(p, val))



    def update_properties(self, props, update_name_field=True):
        ''' Fill in fields with properties
        '''

        for p in self.props:
            setattr(self, p, prop_to_str(p, props.get(p, '')))

        if update_name_field:
            self.dso_panel.name_field.text = self.Name


    def new_DSO_name(self, settings):
        ''' Called from ObservingList when user selects a name from the DSO table. 
        '''
        
        # if we already have a name and a non-empty stack, ask user to confirm
        if not Component.get('Stacker').is_empty() and self.Name:
            change = 'from {:} to {:}'.format(self.Name, settings.get('Name',''))
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

        self.dialog.dismiss()

        # lookup all properties
        all_settings = Component.get('ObservingList').lookup_name(
            '{:}/{:}'.format(settings.get('Name', ''), settings.get('OT', '')))
 
        # update DSO properties
        self.update_properties(all_settings, update_name_field=True)


    def _cancel(self, *args):
        self.dialog.dismiss()



    ''' handle changes to DSO properties
    '''

    def Name_changed(self, val, *args):
        ''' Name is changed as soon as the text is altered to allow lookup
        '''

        # don't do any lookups if we are initialising 
        # if not self.check_ambiguity:
        #    return

        # lookup all possible object types for this name
        OTs = Component.get('ObservingList').lookup_OTs(val)

        self.can_delete = False

        # no match
        if len(OTs) == 0:
            self.Name = val

        # unique match, fill in
        elif len(OTs) ==  1:
            self.exact_match(val + '/' + OTs[0])

        # ambiguous OT, so present alternatives
        else:
            self.choose_OT = MDStackLayout(pos_hint={'x': .1, 'top': .98}, spacing=[20, 20])
            self.app.gui.add_widget(self.choose_OT)
            for ot in OTs:
                self.choose_OT.add_widget(MDRaisedButton(text=ot,
                    on_press=partial(self.exact_match, val + '/' + ot)))
        self.check_for_change()

    def OT_changed(self, widget):
        ''' For the moment we allow any object type but in the future
            could check if one of known types and allow user to
            introduce a new type via a dialog
        '''
        ot = widget.text.upper()
        widget.invalid = len(ot) > 3
        if not widget.invalid:
            self.OT = ot
            # lookup object
            key = '{:}/{:}'.format(self.Name, ot).upper()
            props = Component.get('ObservingList').lookup_name(key)
            if props is not None:
                self.update_properties(props)
        self.check_for_change()

    def exact_match(self, m, *args):
        ''' We have exact match for DSO (name/OT) so clear any OT choice
            widgets and update values
        '''
        if hasattr(self, 'choose_OT'):
            self.choose_OT.clear_widgets()
            del self.choose_OT
        logger.debug('Found match: {:}'.format(m))
        self.update_properties(
            Component.get('ObservingList').lookup_name(m), 
            update_name_field=False)

        # check if we can allow delete of this entry
        key = '{:}/{:}'.format(self.Name, self.OT).upper()
        self.can_delete = Component.get('Catalogues').is_user_defined(key)



    def Con_changed(self, widget):
        ''' Ought to check constellation TLAs in future
        '''
        widget.invalid = len(widget.text) != 3
        if not widget.invalid:
            self.Con = widget.text
        self.check_for_change()

    def RA_changed(self, widget, defocus=False):
        ''' Signal RA format errors immediately, and
            convert to canonical form on defocus
        '''
        RA_str = widget.text.strip()
        if RA_str != '':
            RA_deg = RA.parse(RA_str)
            widget.invalid = RA.parse(RA_str) is None 
            if defocus and not widget.invalid:
                self.RA = str(RA(RA_deg))
                self.check_for_change()

    def Dec_changed(self, widget, defocus=False):
        Dec_str = widget.text.strip()
        if Dec_str != '':
            Dec_deg = Dec.parse(Dec_str)
            widget.invalid = Dec.parse(Dec_str) is None
            if defocus and not widget.invalid:
                self.Dec = str(Dec(Dec_deg))
                self.check_for_change()

    def Mag_changed(self, widget):
        ''' should be a int or float
        '''
        mag_str = widget.text.strip()
        try:
            float(mag_str)
            self.Mag = mag_str
            widget.invalid = False
            self.check_for_change()
        except:
            widget.invalid = True

    def Diam_changed(self, widget, defocus=False):
        ''' Suffix can be d or degree symbol, ' or "
            assume arcmin if no suffix
        '''

        diam = widget.text.strip()
        try:
            diam_str = str_to_arcmin(diam)
            widget.invalid = False
            if defocus:
                self.Diam = arcmin_to_str(diam_str)
                self.check_for_change()
        except:
            widget.invalid = True

    def Other_changed(self, widget):
        self.Other = widget.text.strip()
        self.check_for_change()


    def check_for_change(self):
        ''' Extract properties for current object by looking up on database
            each time, and compare with current properties
        '''

        key = '{:}/{:}'.format(self.Name, self.OT).upper()

        # check if name/OT is already known
        ref_props = Component.get('ObservingList').lookup_name(key)

        # not known, so can add but not delete
        if ref_props is None:
            if self.Name and self.OT:
                self.app.gui.has_changed('DSO', True)
        else:
            self.app.gui.has_changed('DSO', self.has_any_property_changed(ref_props))

    def has_any_property_changed(self, props):
        ''' Check if there has been any change; has to be
            done carefully due to format conversions
        '''

        for p in self.props:
            if p in props:
                # print(p, prop_to_str(p, getattr(self, p)), prop_to_str(p, props[p]), end='')
                if prop_to_str(p, getattr(self, p)) != prop_to_str(p, props[p]):
                    # print(p, 'changed')
                    return True

        # also signal change if the current name has been changed
        if self.orig_name is None:
            return False
        return '{:}/{:}'.format(self.Name, self.OT).upper() != self.orig_name

    def on_can_delete(self, *args):
        self.del_button.x = 0 if self.can_delete else -1000
 
    def delete_DSO(self, *args):
        ''' Remove current DSO from user objects list
        '''
        name = '{:}/{:}'.format(self.Name, self.OT).upper()
        Component.get('Catalogues').delete_user_object(name)
        self.on_new_object()

 
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
        # Component.get('Catalogues').check_update(props)

        # better to do it like this
        name = '{:}/{:}'.format(self.Name.strip(), self.OT.strip()).upper()
        Component.get('Catalogues').update_user_objects(name, props)


    def current_object_coordinates(self):
        ''' Called by platesolver
        '''
        if self.RA and self.Dec:
            return (float(RA(self.RA)), float(Dec(self.Dec)))
        return None, None
