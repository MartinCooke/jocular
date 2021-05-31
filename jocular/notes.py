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
    adaptive_width: True
    pos_hint: {'top': .99, 'right': .99} if root.show_notes else {'top': .99, 'right': 0} 
    size_hint: None, None
    width: dp(200) 

    MDTextField:
        id: _notes
        multiline: True
        hint_text: 'Observing notes'
        helper_text: ''
        helper_text_mode: 'on_focus'
        current_hint_text_color: app.hint_color        
        color_mode: 'accent'
        on_focus: root.notes_changed() if not self.focus else None
        font_size: app.form_font_size # '20sp'
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
        self.orig_notes = Component.get('Metadata').get('Notes', default='')
        self.observing_notes.text = self.orig_notes

    def on_save_object(self):
        if len(self.notes) > 0:
            Component.get('Metadata').set('Notes', self.notes)

    def notes_changed(self, *args):
        self.notes = self.observing_notes.text
        self.app.gui.has_changed('Notes', self.notes != self.orig_notes)
