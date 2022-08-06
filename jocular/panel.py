''' panel for central region of eyepiece; provides contents and header
	need to make it scrollable!
'''

from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.lang import Builder
from kivy.properties import (
	NumericProperty,
	ObjectProperty,
	StringProperty,
)
from jocular.metrics import Metrics


Builder.load_string(
	'''

<Panel>:
	header: _header
	contents: _contents
	canvas:
		Color:
			rgba: .2, .2, .2, self.panel_opacity
		Ellipse:
			pos: self.x + dp(47) + (self.width - self.height) / 2, dp(47)
			size: self.height - dp(94), self.height - dp(94)
	orientation: 'vertical'
	pos_hint: {'center_x': 10, 'center_y': .5}
	size_hint: None, None
	# padding at top to avoid ring
	Label:
		size_hint: 1, None
		height: dp(64)
	BoxLayout:
		size_hint: 1, None
		height: dp(35)
		orientation: 'horizontal'
		Label:
			size_hint: 1, 1
		BoxLayout:
			id: _header
			size_hint: None, 1
			width: dp(200)
		Label:
			size_hint: 1, 1
	BoxLayout:
		orientation: 'horizontal'
		size_hint: 1, 1
		Label:
			size_hint: 1, 1
		BoxLayout:
			canvas.before:
				Color:
					rgb: 1, 0, 0
					a: 0
				Rectangle:
					pos: self.pos
					size: self.size
			id: _contents
			orientation: 'vertical'
			size_hint: None, 1
			width: dp(480)
		Label:
			size_hint: 1, 1

	# padding at base to avoid ring
	Label:
		size_hint: 1, None
		height: dp(89)

''')


class Panel(BoxLayout):
	''' Represents the centre panel used for config/choosers etc
	'''

	# ensure only one panel is showing at a time
	current_panel = None

	contents = ObjectProperty(None)
	header = ObjectProperty(None)
	title = StringProperty('')
	panel_opacity = NumericProperty(.4)


	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		Panel.current_panel = None


	def show(self, *args):

		if Panel.current_panel is not None:
			Panel.current_panel.hide()

		Panel.current_panel = self

		# bind mouse for this panel only (not all panels!)
		Window.bind(mouse_pos=self.on_mouse_pos)

		self.on_show()
		self.pos_hint = {'center_x': .5, 'center_y': .5}  
		width, height = Window.size
		self.width = height
		self.height = height


	def hide(self, *args):

		if Panel.current_panel is None:
			return

		# important to unbind mouse pos
		Window.unbind(mouse_pos=self.on_mouse_pos)
		Panel.current_panel = None

		self.on_hide()
		self.pos_hint = {'center_x': 10, 'center_y': .5}


	def on_mouse_pos(self, *args):
		''' if mouse is outside ring, hide panel
		'''

		if Panel.current_panel is None:
			return

		x, y = args[1]
		xc, yc = Metrics.get('origin')
		r = (((xc - x) ** 2 + (yc - y) ** 2) ** .5) / Metrics.get('outside_ring')
		if r > 1:
			self.on_leave()


	def on_show(self):
		pass


	def on_hide(self):
		pass


	def on_leave(self, *args):
		self.hide()


	def toggle(self, *args):
		if self.pos_hint['center_x'] > 1:
			self.show()
		else:
			self.hide()
