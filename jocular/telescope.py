''' telescope is really the mount of course...
'''

from loguru import logger
from kivy.properties import StringProperty
from kivymd.toast.kivytoast import toast

from jocular.component import Component
from jocular.devicemanager import DeviceFamily, Device
from jocular.ascom import connect_to_ASCOM_device

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

	def slew(self, RA=None, Dec=None):
		if self.connected():
			# get RA/Dec from DSO
			RA, Dec = Component.get('DSO').current_object_coordinates()
			if RA is not None:
				self.device.slew(RA=RA, Dec=Dec)
			else:
				toast('Cannot slew without coordinates')

class GenericTelescope(Device):
	family = StringProperty('Telescope')


class ManualTelescope(GenericTelescope):

	def connect(self):
		self.status = 'connected'
		self.connected = True

	def slew(self, RA=None, Dec=None):
		toast('Slewing not possible for manual telescope')

class SimulatorTelescope(GenericTelescope):
	pass

class ASCOMTelescope(GenericTelescope):
	# https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_ITelescopeV3.htm

	driver = StringProperty(None)

	def disconnect(self):
		logger.debug('closing ASCOM filterwheel')
		self.scope.connected = False

	def connect(self):

		if self.connected:
			return
		res = connect_to_ASCOM_device(device_type='Telescope', driver=self.driver)
		self.connected = res.get('connected', False)
		self.status = res['status']
		if self.connected:
			self.driver = res.get('driver', self.driver)
			self.scope = res['device']
		else:
			if 'exception' in res:
				self.status += ' ({:})'.format(res['exception'])

	def slew(self, RA=None, Dec=None):
		# don't forget to turn tracking on at some point...
		pass

