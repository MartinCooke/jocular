''' DeviceManager: a Component that manages different device families 
	e.g. Telescope, Camera, FilterWheel via a GUI element that permits 
	selection/connection/disconnection
'''


from functools import partial

from kivy.app import App
from loguru import logger
from kivy.metrics import dp
from kivy.uix.spinner import Spinner
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout

from jocular.component import Component
from jocular.widgets import jicon, LabelL, Panel
from jocular.formwidgets import configurable_to_widget


class DeviceManager(Component, Panel):


	def __init__(self, **args):
		super().__init__(**args)
		self.app = App.get_running_app()
		self.status = {}
		self.instances = {}
		self.current_panel = 'Camera'
		self.connect_buttons = {}
		self.connect_dots = {}
		self.app.gui.add_widget(self)


	def register(self, device, name=None):
		''' keep a record of all device instances
		'''
		self.instances[name] = device
		logger.debug('registered device for {:}'.format(name))


	def on_leave(self, *args):
		self.current_device.apply_and_save_settings()
		self.hide()


	def on_show(self):
		''' Main device manager panel that handles mode selection and connection,
			and links to configuration of current devices. 
		'''

		self.contents.clear_widgets()
		self.header.clear_widgets()
		self.contents.width = dp(600)

		# top spinner
		hb = BoxLayout(size_hint=(1, None), height=dp(32))
		hb.add_widget(Label(size_hint=(1, 1)))
		self.spinner = Spinner(
			text=self.current_panel,
			values=self.instances.keys(),
			size_hint=(None, 1), width=dp(130), font_size='20sp')
		self.spinner.bind(text=self.device_panel_changed)
		hb.add_widget(self.spinner)
		hb.add_widget(Label(size_hint=(1, 1)))
		self.header.add_widget(hb)

		# spacer
		self.contents.add_widget(Label(size_hint=(1, None), height=dp(20)))

		# panel for device-specific contents will go
		self.panel = BoxLayout(
			orientation='vertical', 
			size_hint=(1, 1))

		self.contents.add_widget(self.panel)

		self.show_panel()


	def device_panel_changed(self, spinner, *args):
		self.current_panel = spinner.text
		self.show_panel()


	def show_panel(self):
		''' update panel with current class settings
		'''

		self.panel.clear_widgets()

		device = self.current_panel
		current_device = Component.get(device).device

		# connection line
		bh = BoxLayout(
			size_hint=(1, None), 
			height=dp(32),
			spacing=dp(20))

		bh.add_widget(Label(size_hint=(1, 1)))

		# connection status
		lab = self.connect_dots[device] = LabelL(
			size_hint=(None, 1), 
			width=dp(24), 
			markup=True,
			text=jicon(
				'dot', 
				font_size=12,
				color='g' if current_device.connected else 'r'))
		bh.add_widget(lab)

		# device chooser
		spinner = Spinner(size_hint=(None, 1), width=dp(120),
			text=Component.get(device).settings['current_mode'],
			values=Component.get(device).modes.keys())
		spinner.bind(text=partial(self.mode_changed, device))
		bh.add_widget(spinner)

		# connect/disconnect button
		but = self.connect_buttons[device] = Button(size_hint=(None, 1), width=dp(120),
			text='disconnect...' if current_device.connected else 'connect...', 
			on_press=partial(self.connect, device)) 
		bh.add_widget(but)
		
		bh.add_widget(Label(size_hint=(1, 1)))

		self.panel.add_widget(bh)

		# connection status message
		bh = BoxLayout(padding=(10, 1), size_hint=(1, None), height=dp(40))
		status = self.status[device] = Label(text=current_device.status, 
			size_hint=(1, 1), color=(.5, .5, .5, 1))
		bh.add_widget(status)
		self.panel.add_widget(bh)

		# config panel: device-specific config params
		self.config_panel = BoxLayout(
			orientation='vertical', 
			size_hint=(1, 1))

		self.panel.add_widget(self.config_panel)

		self.config(device)


	def mode_changed(self, device, spinner, mode):
		Component.get(device).set_mode(mode)
		self.config(device)


	def connect(self, device, widget=None):
		try:
			if self.connect_buttons[device].text == 'connect...':
				Component.get(device).connect()
			else:
				Component.get(device).disconnect()
			Component.get(device).save()
		except Exception as e:
			logger.exception(e)


	def status_changed(self, device, status):
		if device in self.status:
			self.status[device].text = status


	def connection_changed(self, device, connected):
		if device in self.connect_dots:
			self.connect_dots[device].text = jicon('dot', color=('g' if connected else 'r'))
			Component.get(device).info('not connected')
		if device in self.connect_buttons:
			self.connect_buttons[device].text = 'disconnect...' if connected else 'connect...'
			Component.get(device).info('connected')


	def config(self, device, *args):
		''' user wants to configure device
		'''
		logger.debug('Configuring {:} device'.format(device))
		try:
			self.current_device = Component.get(device).device
			self.changed_settings = {}
			if self.current_device is not None:
				self.show_device_config_panel(name=device, device=self.current_device)
		except Exception as e:
			logger.exception(e)


	def show_device_config_panel(self, name=None, device=None):
		''' Build device config panel 
		'''
		self.config_panel.clear_widgets()
		self.config_panel.add_widget(Label(size_hint=(1, 1))) # spacer
		for pname, pspec in device.configurables:
			self.config_panel.add_widget(configurable_to_widget(
				text=pspec.get('name', pname),
				name=pname,
				spec=pspec,
				helptext=pspec.get('help', ''),
				initval=getattr(self.current_device, pname), 
				changed=device.setting_changed))
		self.config_panel.add_widget(Label(size_hint=(1, 1))) # spacer


	def on_touch_down(self, touch):
		handled = super().on_touch_down(touch)
		if self.collide_point(*touch.pos):
			return True
		return handled
