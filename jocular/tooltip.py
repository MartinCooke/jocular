''' tooltip (other exemplars don't work well)
'''

from functools import partial
from kivy.app import App
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivymd.uix.behaviors import HoverBehavior
from kivymd.uix.label import MDLabel
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.clock import Clock


from jocular.component import Component


Builder.load_string(
'''

<TooltipLabel>:
    background_color: app.theme_cls.accent_color
    canvas.before:
        Color:
            rgba: (*self.background_color[:-1], .3) if self.text else (0, 0, 0, 0)
        Rectangle:
            pos: self.pos
            size: self.size
    theme_text_color: 'Custom'
    text_size: self.size
	text_color: 1, 1, 1, 1
	size_hint: None, None
	font_style: 'Subtitle2'
	text:''
	padding: dp(10),dp(10)
	halign: 'center'
	valign: 'center'
	width: dp(200)
	height: dp(85)
''')

class TooltipLabel(MDLabel):
	pass

class TooltipBehavior(HoverBehavior):

	tooltip_text = StringProperty('')

	def on_enter(self, *args):
		Component.get('Tooltip').show(self.tooltip_text)

	def on_leave(self, *args):
		Component.get('Tooltip').hide()


class Tooltip(Component, TooltipLabel):

	show_tooltips = BooleanProperty(True)

	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		App.get_running_app().gui.add_widget(self)

	def show(self, text):
		delay = App.get_running_app().tooltip_delay
		if delay < 5:
			self.text = ''
			pos = Window.mouse_pos
			self.show_event = Clock.schedule_once(
				partial(self._show, text, pos),
				delay)

	def _show(self, text, pos, dt=None):
		width, height = Window.size
		self.text = text
		self.x = min(width - self.width - dp(20), pos[0] + dp(10))
		self.y = min(height - self.height - dp(20), pos[1])

	def hide(self):
		if hasattr(self, 'show_event'):
			Clock.unschedule(self.show_event)
		self.x = -2000
		self.text = ''
