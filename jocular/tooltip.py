''' tooltip (other exemplars don't work well)
'''

from functools import partial
from kivy.app import App
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivymd.uix.behaviors import HoverBehavior
from kivy.uix.label import Label
from kivy.metrics import dp
from kivymd.uix.label import MDLabel
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.clock import Clock


from jocular.component import Component


Builder.load_string(
'''

<TooltipLabel>:
	theme_text_color: 'Custom'
	text_color: .8, .8, .8, 1
	size_hint: None, None
	font_style: 'Subtitle2'
	text:''
	halign: 'left'
	width: dp(250)
	#height: dp(60)
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
