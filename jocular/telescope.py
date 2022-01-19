''' telescope is really the mount of course...
'''

from loguru import logger
from kivy.properties import StringProperty

from jocular.component import Component
from jocular.device import DeviceFamily, Device
from jocular.ascom import connect_to_ASCOM_device
from jocular.utils import toast

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

	def move(self, direction=None, rate=None):
		if self.connected():
			self.device.move(direction=direction, rate=rate)

	def stop_moving(self):
		if self.connected():
			self.device.stop_moving()



class GenericTelescope(Device):
	family = StringProperty('Telescope')

	def move(self, direction=None, rate=None):
		logger.debug('moving {:} at rate {:}'.format(direction, rate))

	def stop_moving(self):
		logger.debug('stop moving')


class ManualTelescope(GenericTelescope):

	def connect(self):
		self.status = 'connected'
		self.connected = True

	def slew(self, RA=None, Dec=None):
		toast('Slewing not possible for manual scope')

class SimulatorTelescope(GenericTelescope):
	pass

class ASCOMTelescope(GenericTelescope):
	# https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_ITelescopeV3.htm

	driver = StringProperty(None)

	def disconnect(self):
		logger.debug('disconnecting AASCOM telescope')
		self.scope.Connected = False
		self.connected = False
		self.status = 'disconnected'

	def connect(self):

		if self.connected:
			return
		res = connect_to_ASCOM_device(device_type='Telescope', driver=self.driver)
		self.connected = res.get('connected', False)
		self.status = res['status']
		if self.connected:
			self.driver = res.get('driver', self.driver)
			self.scope = res['device']
			logger.info('current sidereal time  from scope {:}'.format(
				self.scope.SiderealTime))
		else:
			if 'exception' in res:
				self.status += ' ({:})'.format(res['exception'])



	def slew(self, RA=None, Dec=None):
		# don't forget to turn tracking on at some point...
		pass

	def move(self, direction=None, rate=None):

		logger.debug('moving {:} at rate {:}'.format(direction, rate))
		''' for ASCOM, negative rate implies moving in other direction
			so need to convert directions up down etc
			We will map left right to RA axis for Eq and to azimuth for altaz
		''' 
		# map left right to RA axis for Eq and to azimuth for altaz
		axis = 0 if direction in {'left', 'right'} else 1

		# convert rate to degs/sec
		rate = {1: .1, 2: .2, 3: .3}[rate]

		# map left/down to negative rates
		rate = -rate if direction in {'left', 'down'} else rate

		# check if we can move axis
		if self.scope.CanMoveAxis(axis):
			self.scope.MoveAxis(axis, rate)

	def stop_moving(self):
		logger.debug('stop moving')
		if self.scope.CanMoveAxis(0):
			self.scope.MoveAxis(0, 0)
		if self.scope.CanMoveAxis(1):
			self.scope.MoveAxis(1, 0)



