''' Manages status panel showing information about a subset of components
'''

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.properties import BooleanProperty

from jocular.component import Component

Builder.load_string('''

<StatusLabel>:
    size_hint: 1, None
    height: dp(20) 
    halign: 'right'
    markup: True
    font_size: app.info_font_size
    text_size: self.size
    size: self.texture_size
    padding: dp(3), dp(1)
    color: app.lowlight_color
    shorten: True

<Status>:
    size_hint: None, None
    orientation: 'vertical'
    padding: dp(5), dp(2)
    size: app.gui.height / 8 + (app.gui.width - app.gui.height) / 2, app.gui.height / 2
    pos: app.gui.width - self.width if root.show_status else app.gui.width, 0
    Label:
        size_hint: 1, 1
''')

class StatusLabel(Label):
    pass

class Status(BoxLayout, Component):

    show_status = BooleanProperty(False)
    comps = ['Camera', 'FilterWheel', 'Capture', 'ObjectIO', 'BadPixelMap',   
                'Calibrator', 'View', 'Observations',
                'ObservingList', 'Aligner', 'Stacker', 'PlateSolver', 'Snapshotter']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        App.get_running_app().gui.add_widget(self, index=2)

        # add a status label for each component where we are interested in status updates
        self.labs = {c: StatusLabel(text=c) for c in self.comps}
        for name, lab in self.labs.items():
            self.add_widget(lab)

    def bind_status(self, name, attr):
        # called by Component when a component is loaded
        if name in self.labs:
            attr.bind(infoline=self.labs[name].setter('text'))
