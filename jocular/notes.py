''' Observing notes
'''

from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty
from kivy.lang import Builder
from kivymd.uix.boxlayout import MDBoxLayout
from jocular.component import Component

Builder.load_string('''
<Notes>:
    observing_notes: _notes
    adaptive_height: True
    pos_hint: {'top': .99, 'right': .99} if root.show_notes else {'top': .99, 'right': 0} 
    size_hint: None, None
    width: dp(200) 

    JTextField:
        id: _notes
        width: dp(200)
        multiline: True
        hint_text: 'Observing notes'
        helper_text: ''
        helper_text_mode: 'on_focus'
        on_focus: root.notes_changed() if not self.focus else None
        font_size: app.form_font_size
''')


class Notes(MDBoxLayout, Component):

    notes = StringProperty('')
    show_notes = BooleanProperty(False)
    save_settings = ['show_notes']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.app.gui.add_widget(self) 

    def on_new_object(self):
        self.notes = ''
        self.orig_notes = Component.get('Metadata').get('Notes', default='')
        self.observing_notes.text = self.orig_notes
        self.notes = self.observing_notes.text        

    def on_save_object(self):
        Component.get('Metadata').set('Notes', self.notes.strip())

    def notes_changed(self, *args):
        self.notes = self.observing_notes.text
        self.changed = '' if self.notes == self.orig_notes else 'observing notes'
