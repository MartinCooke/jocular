''' Help panel, currently used for tooltips only, but could be
    extended to provide more help
'''


from kivy.app import App
from kivymd.uix.behaviors import HoverBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.properties import BooleanProperty, StringProperty 
from kivy.lang import Builder

from jocular.component import Component


Builder.load_string(
'''
<Help>:
    helplabel: _label
    MDLabel:
        # canvas.before:
        #     Color:
        #         rgb: 1, 0, 0
        #         a: .1
        #     Rectangle:
        #         pos: self.pos
        #         size: self.size
        id: _label
        halign : 'center'
        font_style: 'H6'
''')


class TooltipBehavior(HoverBehavior):

    tooltip_text = StringProperty('')

    def on_enter(self, *args):
        Component.get('Help').show_tooltip(self.tooltip_text)

    def on_leave(self, *args):
        Component.get('Help').show_tooltip('')


class Help(MDBoxLayout, Component):

    show_tooltips = BooleanProperty(False)


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        App.get_running_app().gui.add_widget(self)
        Component.get('Appearance').show_tooltips = False


    def on_show_tooltips(self, *args):
        if not self.show_tooltips:
            self.helplabel.text  = ''


    def show_tooltip(self, text):
        if self.show_tooltips:
            self.helplabel.text = text

