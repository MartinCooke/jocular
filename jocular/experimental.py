''' All the experimental stuff (mainly sliders) goes in this panel
'''

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.gridlayout import GridLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.properties import NumericProperty

from jocular.component import Component
from jocular.widgets.widgets import JSlider, LabelR
from jocular.panel import Panel


class Experimental(Panel, Component):

    fracbin = NumericProperty(1)


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.build()
        self.panel_opacity = 0


    def on_show(self):
        pass


    def build(self, *args):

        content = self.contents
        layout = AnchorLayout(anchor_x='center', anchor_y='bottom', size_hint=(1, 1))
        content.add_widget(layout)
        gl = GridLayout(size_hint=(None, None), cols=2, 
            width=dp(400), height=dp(30), spacing=(dp(5), dp(5)))
        gl.add_widget(LabelR(text='fractional binning'))
        slider = JSlider(
            size_hint=(None, None), width=dp(200), height=dp(30), 
            step=0.1, min=1, max=3, value=self.fracbin)
        slider.bind(value=self.fracbin_changed)
        gl.add_widget(slider)
        layout.add_widget(gl)
        self.app.gui.add_widget(self)


    def fracbin_changed(self, widget, *args):
        Component.get('Monochrome').fracbin = widget.value

