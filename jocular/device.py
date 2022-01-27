''' DeviceFamily:
		superclass of e.g. Camera, Telescope, FilterWheel
		handles communication with devices for generic functions such as
		select, connect, disconnect as well as common error handling

	Device:
		superclass of device instances e.g. SXCamera, ASCOMFilterWheel
'''

import json
import importlib

from kivy.app import App
from loguru import logger
from kivy.event import EventDispatcher

from kivy.properties import (
	ObjectProperty, 
	StringProperty, BooleanProperty, DictProperty
	)
from kivy.clock import Clock

from jocular.component import Component
from jocular.settingsmanager import SettingsBase


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
		''' finds and imports class representing chosen mode
			In future, place all devices in subdirs as in cameras to
			avoid having to import in 'parent' device 
		'''
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
	family = StringProperty('')

	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		''' register this device with the device manager e.g. so that it
			appears on the chooser
		'''
		if self.family:
			Component.get('DeviceManager').register(self, name=self.family)

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

