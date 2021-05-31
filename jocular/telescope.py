''' telescope is really the mount of course...
'''

from loguru import logger
from kivy.properties import StringProperty
from jocular.component import Component
from jocular.devicemanager import DeviceFamily, Device

class Telescope(Component, DeviceFamily):

	modes = {
		'Manual': 'ManualTelescope', 
		'Simulator': 'SimulatorTelescope',
		'ASCOM': 'ASCOMTelescope'
	}
	default_mode = 'Manual'
	family = 'Telescope'

	def on_new_object(self, *args):
		logger.debug('-')
		if self.connected():
			self.device.on_new_object()

	def on_previous_object(self, *args):
		logger.debug('-')
		if self.connected():
			self.device.on_previous_object()

class GenericTelescope(Device):
	family = StringProperty('Telescope')


class ManualTelescope(GenericTelescope):

	def connect(self):
		self.status = 'connected'
		self.connected = True

class SimulatorTelescope(GenericTelescope):
	pass

class ASCOMTelescope(GenericTelescope):
	pass

