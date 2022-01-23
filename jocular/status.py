''' Manages status panel showing information about a subset of components
'''

from kivy.app import App
from kivy.lang import Builder
from kivymd.uix.label import MDLabel
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.properties import BooleanProperty

from jocular.component import Component

Builder.load_string('''

<StatusLabel>:
    size_hint: 1, None
    height: dp(int(app.form_font_size[:-2]) + 2)
    halign: 'right'
    markup: True
    font_size: app.form_font_size
    text_size: self.size
    size: self.texture_size
    padding: dp(3), dp(1)
    shorten: True
    theme_text_color: 'Custom'
    text_color: app.theme_cls.accent_color

<Status>:
    size_hint: None, None
    orientation: 'vertical'
    padding: dp(5), dp(2)
    size: '300dp', app.gui.height / 2
    pos: app.gui.width - self.width if root.show_status else app.gui.width, 0
    Label:
        size_hint: 1, 1

<StatusBox>:
    component: _component
    size_hint: 1, None
    height: dp(40)
    orientation: 'vertical'
    padding: dp(10)
    spacing: dp(10)
    MDLabel:
        id: _component
        size_hint: 1, .3
        halign: 'right'
        font_size: '12sp'
        color: app.hint_color
''')

class StatusLabel(MDLabel):
   pass

class StatusBox(MDBoxLayout):
    pass

class Status(MDBoxLayout, Component):

    show_status = BooleanProperty(False)
    comps = ['Capture', 'Calibrator', 'View', 'Aligner', 'Stacker', 'PlateSolver']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        App.get_running_app().gui.add_widget(self, index=2)

        # add a status label for each component where we are interested in status updates
        self.labs = {c: StatusLabel(text='') for c in self.comps}
        for name, lab in self.labs.items():
            w = StatusBox()
            w.component.text = name.lower()
            w.add_widget(lab)
            self.add_widget(w)

    def bind_status(self, name, attr):
        # called by Component when a component is loaded
        if name in self.labs:
            attr.bind(infoline=self.labs[name].setter('text'))
