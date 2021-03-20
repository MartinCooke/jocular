''' Observing notes panel.
'''

from kivy.clock import Clock
from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout

from jocular.component import Component
from jocular.widgets import JPopup

Builder.load_string('''
<Notes>:
    canvas.before:
        Color:
            rgba: 1, 0, 0, 0
        Rectangle:
            pos: self.pos
            size: self.size
    size_hint: None, None
    orientation: 'vertical'
    padding: dp(5), dp(2)
    size: ((app.gui.width - app.gui.height) / 2) - dp(4), app.gui.height / 3
    y: 2 * app.gui.height / 3
    x: app.gui.width - self.width if root.show_notes else app.gui.width

    Button:
        text: 'Observational notes: {:}'.format(root.notes)
        # size: self.texture_size
        background_color: .6, 0, .6, 0
        size_hint: 1, 1
        valign: 'top'
        halign: 'right'
        color: app.lowlight_color
        on_press: root.edit()
        markup: True
        font_size: app.info_font_size
        text_size: self.size

<NotesInfo>:
    orientation: 'vertical'
    size_hint: None, None
    size: dp(300), dp(360)
    spacing: dp(5)
    notes_input: _notes

    TextInput:
        id: _notes
        unfocus_on_touch: False
        background_color: app.background_color
        foreground_color: app.lowlight_color
        hint_text_color: app.lowlight_color
        hint_text: 'type your observing notes here'
        text: root.notes.notes
        multiline: True
        size_hint: 1, None
        height: dp(300)
        font_size: app.form_font_size
        valign: 'top'

    BoxLayout:
        size_hint: 1, None
        height: dp(40)
        Button:
            text: 'Save'
            size_hint: .5, .8
            on_press: root.notes.edited(_notes.text)
        Button:
            text: 'Cancel'
            size_hint: .5, .8
            on_press: root.notes.cancel_edit()

''')

class NotesInfo(BoxLayout): 
    notes_input = ObjectProperty(None)
    def __init__(self, notes, **kwargs):
        self.notes = notes
        super().__init__(**kwargs)
        Clock.schedule_once(self.set_focus, 0)

    def set_focus(self, dt):
        self.notes_input.focus = True

class Notes(BoxLayout, Component):

    notes = StringProperty('')
    show_notes = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        App.get_running_app().gui.add_widget(self) # , index=2) 

    def on_new_object(self):
        self.notes =  Component.get('Metadata').get('Notes', default='')

    def on_save_object(self):
        if len(self.notes) > 0:
            Component.get('Metadata').set('Notes', self.notes)

    def edit(self, *args):
        content = NotesInfo(self)
        self.popup = JPopup(title='Observing notes', content=content, posn='top-right')
        self.popup.open()
        
    def edited(self, notes):
        self.notes = notes
        self.changed = self.notes != Component.get('Metadata').get('Notes', default='') and \
            not Component.get('Stacker').is_empty()
        self.popup.dismiss()

    def cancel_edit(self, *args):
        self.popup.dismiss()
