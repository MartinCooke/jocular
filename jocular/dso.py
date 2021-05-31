''' Handles DSO details including lookup and catalogue entry
'''

import math
from functools import partial

from loguru import logger

from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty, DictProperty
from kivy.lang import Builder
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.textfield import MDTextField
from kivymd.uix.stacklayout import MDStackLayout
from kivymd.uix.button import MDTextButton

from jocular.component import Component
from jocular.RA_and_Dec import RA, Dec

Builder.load_string('''

<MyTextField>:
    current_hint_text_color: app.hint_color
    size_hint: (None, None)
    height: '28dp'
    width: '100dp'
    helper_text_mode: 'on_focus'        
    color_mode: 'accent'
    #foreground_color: app.hint_color    
    #color_mode: 'custom'
    font_size: app.form_font_size # '20sp'
    current_hint_text_color: [1, 0, 0, 1] if (root.invalid and self.text)  else app.hint_color
    on_text: root.invalid = False


<DSOBoxLayout@BoxLayout>:
    size_hint: (1, None)
    height: '36dp'

<DSO_panel>:
    name_field: _name
    padding: '10dp'
    adaptive_height: True
    #adaptive_width: True
    pos_hint: {'top': .99, 'x': 0} if root.dso.show_DSO else {'top': .99, 'right': -1000} 
    size_hint: None, None
    orientation: 'vertical'

    BoxLayout:
        size_hint: (1, None)
        height: '48dp'

        MyTextField:
            id: _name
            width: '300dp'
            height: '32dp'
            helper_text: 'DSO'
            hint_text: 'dso'
            on_text: root.dso.Name_changed(self.text)
            font_size: '{:}sp'.format(int(app.form_font_size[:-2]) + 8) # 28sp

    DSOBoxLayout:
        MyTextField:
            hint_text: 'type'
            helper_text: 'e.g. PN, GX'
            on_focus: root.dso.OT_changed(self) if not self.focus else None
            text: root.dso.OT
        MyTextField:
            hint_text: 'con'
            helper_text: 'e.g. PER'
            on_focus: root.dso.Con_changed(self) if not self.focus else None
            text: root.dso.Con

    DSOBoxLayout:
        MyTextField:
            hint_text: 'RA'
            helper_text: "e.g. 21h30'42"
            on_focus: root.dso.RA_changed(self) if not self.focus else None
            text: '' if root.dso.RA == 'nan' else root.dso.RA
        MyTextField:
            hint_text: 'dec'
            helper_text: "-3 21' 4"
            on_focus: root.dso.Dec_changed(self) if not self.focus else None
            text: '' if root.dso.Dec == 'nan' else root.dso.Dec

    DSOBoxLayout:
        MyTextField:
            hint_text: 'diam'
            helper_text: "e.g. 21'"
            on_focus: root.dso.Diam_changed(self) if not self.focus else None
            text: root.dso.Diam

        MyTextField:
            hint_text: 'mag'
            helper_text: "e.g. 14.1"
            on_focus: root.dso.Mag_changed(self) if not self.focus else None
            text: root.dso.Mag

    DSOBoxLayout:
        MyTextField:
            width: '200dp'
            hint_text: 'other'
            helper_text: ""
            on_focus: root.dso.Other_changed(self) if not self.focus else None
            text: root.dso.Other
''')


class MyTextField(MDTextField):
    invalid = BooleanProperty(False)

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

    props = ['Name', 'Con', 'OT', 'RA', 'Dec', 'Mag', 'Diam', 'Other']

    show_DSO = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        otypes = Component.get('Catalogues').get_object_types()
        self.otypes = {k: v['name'] for k, v in otypes.items()}
        self.dso_panel = DSO_panel(self)
        self.app.gui.add_widget(self.dso_panel)
        self.initial_values = {}

    def on_new_object(self):
        ''' Called when user clicks new
        '''

        self.check_ambiguity = True

        # empty DSO details
        self.update_props({})

        # store initial values so we can check for changes 
        self.initial_values = {p: getattr(self, p) for p in self.props}


    def on_previous_object(self):
        ''' Called when user selected object in observations table
        '''

        # switch off ambiguity check because no ambiguity on previous object's OT
        self.check_ambiguity = False

        # Data for new object is in Metadata
        settings = Component.get('Metadata').get({'Name', 'OT'})

        # lookup rest from name and object type
        full_settings = Component.get('ObservingList').lookup_name(
            '{:}/{:}'.format(settings.get('Name', ''), settings.get('OT', '')))

        # update DSO display
        self.update_props(full_settings)

        # store initial values so we can check for changes 
        self.initial_values = {p: getattr(self, p) for p in self.props}

        # switch back on in case user does wish to change OT after the event
        self.check_ambiguity = True


    def new_DSO_name(self, settings):
        ''' Called when user selects a name from the DSO table. What we do depends
            on whether we already have an object loaded, in which case we note the
            change of name so that it can be confirmed on save.
        '''

        self.check_ambiguity = False

        # lookup rest
        full_settings = Component.get('ObservingList').lookup_name(
            '{:}/{:}'.format(settings.get('Name', ''), settings.get('OT', '')))

        # update DSO properties
        self.update_props(full_settings)

        # if stack is empty, treat this as a new observation
        if Component.get('Stacker').is_empty():
            logger.info('new DSO from table {:}'.format(full_settings))
            self.initial_values = {p: getattr(self, p) for p in self.props}
        else:
            logger.info('user changes DSO name {:}'.format(full_settings))

        self.check_ambiguity = True


    @logger.catch()
    def Name_changed(self, val, *args):
        ''' Name is changed as soon as the text is altered to allow lookup
            while other properties are changed on defocus
        '''

        if not self.check_ambiguity:
            return

        # lookup
        OTs = Component.get('ObservingList').lookup_OTs(val)

        # if unique match, fill in
        if len(OTs) ==  1:
            self.exact_match(val + '/' + OTs[0])
            return

        # clear all but name field to signal ambiguity
        for p in set(self.props) - {'Name'}:
            setattr(self, p, '')

        if len(OTs) == 0:
            # no match so set name
            self.Name = val
            self.new_values['Name'] = val
            self.check_for_change()
            return

        self.choose_OT = MDStackLayout(pos_hint={'x': .1, 'top': 1}, spacing=[20, 20])
        self.app.gui.add_widget(self.choose_OT)
        for ot in OTs:
            self.choose_OT.add_widget(MDTextButton(text=ot,
                on_press=partial(self.exact_match, val + '/' + ot)))

    def exact_match(self, m, *args):
        if hasattr(self, 'choose_OT'):
            self.choose_OT.clear_widgets()
            del self.choose_OT
        logger.debug('Found match: {:}'.format(m))
        self.update_props(Component.get('ObservingList').lookup_name(m), 
            update_name_field=False)
        self.new_values['Name'] = self.Name
        self.check_for_change()

    @logger.catch()
    def update_props(self, settings, update_name_field=True):
        ''' update DSO properties, causing display update
        '''

        self.Name = settings.get('Name', '')
        self.RA = str(RA(settings.get('RA', math.nan)))
        self.Dec = str(Dec(settings.get('Dec', math.nan)))
        self.Con = settings.get('Con', '')
        self.OT = settings.get('OT', '')
        self.Mag = float_to_str(settings.get('Mag', ''))
        self.Other = settings.get('Other', '')
        self.Diam = arcmin_to_str(str_to_arcmin(str(settings.get('Diam', ''))))
        # update new values to reflect changes
        self.new_values = {p: getattr(self, p) for p in self.props}
        if update_name_field:
            self.dso_panel.name_field.text = self.Name
        # check for change at this point
        self.check_for_change()

    def OT_changed(self, widget):
        ''' For the moment we allow any object type but in the future
            could check if one of known types and allow user to
            introduce a new type via a dialog
        '''
        widget.current_hint_text_color = self.app.hint_color
        ot = widget.text.upper()
        if len(ot) > 3:
            widget.current_hint_text_color = [1, 0, 0, 1]
        else:
            self.OT = ot
            self.new_values['OT'] = ot
            self.check_for_change() 

    def Con_changed(self, widget):
        ''' Likewise, we should check constellations in future
        '''
        widget.current_hint_text_color = self.app.hint_color
        con = widget.text.upper()
        if len(con) > 3:
            widget.current_hint_text_color = [1, 0, 0, 1]
        else:
            self.Con = con
            self.new_values['Con'] = con
            self.check_for_change() 

    @logger.catch()
    def RA_changed(self, widget):
        '''
        '''
        widget.current_hint_text_color = self.app.hint_color
        RA_str = widget.text.strip()
        if not RA_str:
            return
        ra_deg = RA.parse(RA_str)
        if ra_deg is None:
            widget.current_hint_text_color = [1, 0, 0, 1]
        else:
            self.RA = '-'  # need to force an update
            self.RA = str(RA(ra_deg))
            self.new_values['RA'] = self.RA
            self.check_for_change() 

    def Dec_changed(self, widget):
        widget.current_hint_text_color = self.app.hint_color
        Dec_str = widget.text.strip()
        if not Dec_str:
            return
        dec_deg = Dec.parse(Dec_str)
        if dec_deg is None:
            widget.current_hint_text_color = [1, 0, 0, 1]
        else:
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
            # normalise diam by converting to arcmin then back to string
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
    def check_for_change(self):
        ''' Check if any property has changed and stack is not empty
        '''

        changes = []
        for k, v in self.initial_values.items():
            if k in self.new_values and self.new_values[k] != v:
                changes += [True]

        # tell gui about any changes
        self.app.gui.has_changed('DSO', any(changes))


    @logger.catch()
    def on_save_object(self):

        ''' On saving we ensure that Name, OT and Con is saved as these 
            appear in the previous object table; other props don't need to
            be saved as they are looked up from the DSO database on each
            load.
        '''
        Component.get('Metadata').set(
            {'Name': self.Name.strip(), 'OT': self.OT, 'Con': self.Con}
        )

        ''' If there have been any changes update user objects catalogue
        '''

        props = {p: getattr(self, p) for p in self.props}

        # convert RA/Dec etc
        if 'RA' in props:
            props['RA'] = RA.parse(props['RA'])
        if 'Dec' in props:
            props['Dec'] = Dec.parse(props['Dec'])
        if 'Diam' in self.props:
            try:
                diam = str_to_arcmin(props['Diam'])
            except:
                diam = math.nan 
            props['Diam'] = diam

        Component.get('Catalogues').update_user_catalogue(props)


    def current_object_coordinates(self):
        if self.RA and self.Dec:
            return (float(RA(self.RA)), float(Dec(self.Dec)))
        return None, None
