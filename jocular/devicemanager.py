''' 
	DeviceManager: 
		a Component that manages different device families e.g. Telescope, Camera, FilterWheel
		via a GUI element that permits selection/connection/disconnection

	DeviceFamily:
		superclass of e.g. Camera, Telescope, FilterWheel
		handles communication with devices for generic functions such as
		select, connect, disconnect as well as common error handling

	Device:
		superclass of device instances e.g. SXCamera, ASCOMFilterWheel
'''

import json
import importlib

from functools import partial

from kivy.app import App
from loguru import logger
from kivy.metrics import dp
from kivy.uix.spinner import Spinner
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.event import EventDispatcher
from kivy.core.window import Window

from kivy.properties import (
	ObjectProperty, 
	StringProperty, BooleanProperty, DictProperty
	)
from kivy.clock import Clock

from jocular.component import Component
from jocular.settingsmanager import SettingsBase
from jocular.widgets import jicon, LabelL
from jocular.formwidgets import configurable_to_widget

from kivy.lang import Builder
Builder.load_string('''
<DeviceManager>:
	canvas:
		Color:
			rgba: .2, .2, .2, .7
		Ellipse:
			pos: self.x + dp(58) + (self.width - self.height) / 2, dp(58)
			size: self.height - dp(116), self.height - dp(116)
	orientation: 'vertical'
	pos_hint: {'center_x': 10, 'center_y': .5}
''')


class DeviceManager(Component, BoxLayout):

	devices = {'Camera': 'Camera', 'Telescope': 'Telescope', 'FilterWheel': 'Filter wheel'}

	def __init__(self, **args):
		super().__init__(**args)
		self.app = App.get_running_app()
		self.status = {}
		self.connect_buttons = {}
		self.connect_dots = {}
		self.size = Window.size
		self.app.gui.add_widget(self)
		#Clock.schedule_once(self.connect_devices, 0)

	def show(self, *args):
		Component.get('SettingsManager').hide()
		if self.pos_hint['center_x'] > 1:
			self.show_device_manager()
			self.pos_hint = {'center_x': .5, 'center_y': .5} 

	def hide(self, *args):
		if self.pos_hint['center_x'] < 1:
			self.pos_hint = {'center_x': 10, 'center_y': .5}

	def show_device_manager(self):
		''' Main device manager panel that handles mode selection and connection,
			and links to configuration of current devices. 
		'''

		self.clear_widgets()
		self.add_widget(Label(size_hint=(1, None), height=dp(90)))
		self.add_widget(Label(size_hint=(1, None), height=dp(60), text='Your devices', font_size='24sp'))
		self.add_widget(Label(size_hint=(1, 1)))

		for device, name in self.devices.items():

			current_device = Component.get(device).device

			bh = BoxLayout(size_hint=(1, None), height=dp(40))
			bh.add_widget(Label(size_hint=(1, 1)))

			# connection status
			lab = self.connect_dots[device] = LabelL(size_hint=(None, 1), width=dp(24), markup=True,
				text=jicon('dot', color='g' if current_device.connected else 'r'))
			bh.add_widget(lab)

			# device family
			bh.add_widget(LabelL(text=name, size_hint=(None, 1), width=dp(120)))

			# device chooser
			spinner = Spinner(size_hint=(None, 1), width=dp(120),
				text=Component.get(device).settings['current_mode'],
				values=Component.get(device).modes.keys())
			spinner.bind(text=partial(self.mode_changed, device))
			bh.add_widget(spinner)

			# mid spacer
			bh.add_widget(Label(size_hint=(None, 1), width=dp(40)))

			# connect/disconnect button
			but = self.connect_buttons[device] = Button(size_hint=(None, 1), width=dp(120),
				text='disconnect...' if current_device.connected else 'connect...', 
				on_press=partial(self.connect, device)) 
			bh.add_widget(but)

			# configure icon
			lab = Button(size_hint=(None, 1), width=dp(140), 
				markup=True, background_color=(0, 0, 0, 0),
				text=jicon('settings'), on_press=partial(self.config, device))
			bh.add_widget(lab)

			bh.add_widget(Label(size_hint=(1, 1)))
			self.add_widget(bh)

			# connection status message
			bh = BoxLayout(padding=(10, 1), size_hint=(1, None), height=dp(40))
			status = self.status[device] = Label(text=current_device.status, 
				size_hint=(1, 1), color=(.5, .5, .5, 1))
			bh.add_widget(status)
			self.add_widget(bh)

			# inter-device spacer
			# self.add_widget(Label(size_hint=(1, None), height=dp(40)))

		self.add_widget(Label(size_hint=(1, 1)))

		# done button
		hb = BoxLayout(size_hint=(1, None), height=dp(30))
		hb.add_widget(Label(size_hint=(1, 1)))
		hb.add_widget(Button(size_hint=(None, 1), width=dp(100), text='close', 
			on_press=self.hide))
		hb.add_widget(Label(size_hint=(1, 1)))
		self.add_widget(hb)

		self.add_widget(Label(size_hint=(1, None), height=dp(90)))


	def mode_changed(self, device, spinner, mode):
		Component.get(device).set_mode(mode)

	def connect_devices(self, dt=None):
		logger.debug('Attempting to connect devices')
		for d in self.devices.keys():
			try:
				Component.get(d).connect()
			except Exception as e:
				logger.exception(e)

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
		''' Build device settings panel 
		'''

		self.clear_widgets()

		self.add_widget(Label(size_hint=(1, None), height=dp(75)))

		self.add_widget(Label(text=device.name, size_hint=(1, None), height=dp(60), 
			font_size='24sp'))

		self.add_widget(Label(size_hint=(1, 1))) # spacer

		for pname, pspec in device.configurables:
			self.add_widget(configurable_to_widget(
				text=pspec.get('name', pname),
				name=pname,
				spec=pspec,
				helptext=pspec.get('help', ''),
				initval=getattr(self.current_device, pname), 
				changed=device.setting_changed))

		self.add_widget(Label(size_hint=(1, 1))) # spacer

		# done button
		hb = BoxLayout(size_hint=(1, None), height=dp(30))
		hb.add_widget(Label(size_hint=(1, 1)))
		hb.add_widget(Button(size_hint=(None, 1), width=dp(150), text='back to devices', 
			on_press=self._save_settings))
		hb.add_widget(Label(size_hint=(1, 1)))
		self.add_widget(hb)
		self.add_widget(Label(size_hint=(1, None), height=dp(75)))

	@logger.catch()	
	def _save_settings(self, *args):
		self.current_device.apply_and_save_settings()
		self.show_device_manager()

	def on_touch_down(self, touch):
		handled = super().on_touch_down(touch)
		if self.collide_point(*touch.pos):
			return True
		return handled


class DeviceFamily:

	device = ObjectProperty(None)

	# these three need to be set in each subclass
	family = StringProperty('Unknown')
	modes = DictProperty({})
	default_mode = StringProperty('')

	def __init__(self, **kwargs):
		self.app = App.get_running_app()
		try:
			with open(self.app.get_path('{:}.json'.format(self.family)), 'r') as f:
				self.settings = json.load(f)
		except:
			self.settings = {}
		Clock.schedule_once(self.post_init, 0)

	def post_init(self, dt):
		self.set_mode(self.settings.get('current_mode', self.default_mode))
		self.connect()

	def save(self):
		with open(self.app.get_path('{:}.json'.format(self.family)), 'w') as f:
			json.dump(self.settings, f, indent=1)       

	def set_mode(self, mode):
		self.disconnect()
		try:
			if mode in self.modes:
				devmod = importlib.import_module('jocular.{:}'.format(self.family.lower()))
				devclass = getattr(devmod, self.modes[mode])
				self.device = devclass()
				self.settings['current_mode'] = mode
				self.device.settings_have_changed()
				# self.save()
		except Exception as e:
			logger.exception(e)

	def get_configurables(self):
		if self.device is not None:
			return self.device.configurables

	def configure(self):
		if self.device is not None:
			logger.debug('family {:} settings {:}'.format(self.family, self.settings['current_mode']))
			self.device.configure()

	def connect(self):
		logger.debug('Connecting {:} (current mode: {:})'.format(
			self.family, self.settings['current_mode']))
		if self.device is not None:
			self.device.connect()
			# only save current mode if we are able to connect
			if self.device.connected:
				self.save()
				self.device_connected()
				self.device.on_new_object()

	def disconnect(self):
		if self.device is None:
			return
		if self.connected():
			self.device.disconnect()
			self.device_disconnected()

	def connected(self):
		if self.device is None:
			return False
		return self.device.connected

	# def on_new_object(self, *args):
	# 	if self.connected():
	# 		logger.info('connected, about to call device on new object')
	# 		self.device.on_new_object()

	# def on_previous_object(self, *args):
	# 	if self.connected():
	#		self.device.on_previous_object()

	def device_connected(self):
		pass

	def device_disconnected(self):
		pass

	def on_close(self, *args):
		if self.connected():
			self.disconnect()

	def choose(self, *args):
		if self.device is not None:
			self.device.choose()


''' Each actual device e.g. ASCOMTelescope, ManualFilterwheel etc is a subclass of this
''' 

class Device(EventDispatcher, SettingsBase):

	connected = BooleanProperty(False)
	status = StringProperty('')
	family = StringProperty('unknown family')

	def on_close(self):
		pass

	def on_new_object(self):
		pass

	def on_previous_object(self):
		pass

	def connect(self):
		self.status = 'Not implemented for this {:}'.format(self.family)
		self.connected = False

	def disconnect(self):
		self.status = 'not connected'
		self.connected = False

	def on_connected(self, *args):
		Component.get('DeviceManager').connection_changed(self.family, self.connected)

	def on_status(self, *args):
		Component.get('DeviceManager').status_changed(self.family, self.status)

	def select(self, f):
		return None

	def choose(self):
		pass

	def handle_failure(self, message='problem'):
		logger.error('{:}: failure {:}'.format(self.family, message))
		self.disconnect()
		self.connected = False
		self.status = message
		if hasattr(self, 'on_failure') and self.on_failure is not None:
			self.on_failure()

