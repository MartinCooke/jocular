''' Filterwheel device family
'''

from functools import partial
from loguru import logger

from kivy.clock import Clock
from kivy.properties import StringProperty
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog

from jocular.component import Component
from jocular.device import DeviceFamily, Device
from jocular.ascom import connect_to_ASCOM_device
from jocular.utils import toast

_filter_types = ['L', 'R', 'G', 'B', 'Ha', 'OIII', 'SII', 'dark', 'spec', '-']

class FilterWheel(Component, DeviceFamily):

	modes = {
		'Single': 'SingleFW',
		#'Simulator': 'SimulatorFW',
		'Manual': 'ManualFW', 
		'SX EFW': 'SXFW',
		'ASCOM': 'ASCOMFW'
	}

	default_mode = 'Single'
	family = 'FilterWheel'

	current_filter = StringProperty('L')

	def get_state(self):
		return {
			'current_filter': self.current_filter,
			'filtermap': self.filtermap()}

	def filtermap(self):
		# create map from filtername to position e.g. {'L': 1, 'R': 2}
		if self.device is None:
			return {}
		return {getattr(self.device, 'f{:}'.format(p)): p for p in range(1, 10)}

	def select_filter(self, name='L', changed_action=None, not_changed_action=None):

		logger.debug('trying to change to filter {:}'.format(name))
		self.changed_action = changed_action
		self.not_changed_action = not_changed_action

		# no change of filter
		if self.current_filter == name:
			logger.debug('no need to change filter {:}'.format(name))
			changed_action()
			return

		# filter not in wheel
		if name not in self.filtermap():
			# if we want dark or we currently have dark, special case
			if name == 'dark' or self.current_filter == 'dark':
				if name == 'dark':
					title = 'Is scope capped for darks?'
				else:
					title = 'Is scope uncapped for lights?'
				self.dialog = MDDialog(
					auto_dismiss=False,
					text=title,
					buttons=[
						MDFlatButton(text="DONE", 
							text_color=self.app.theme_cls.primary_color,
							on_press=partial(self.confirmed_fw_changed, name)),
						MDFlatButton(
							text="CANCEL", 
							text_color=self.app.theme_cls.primary_color,
							on_press=self.confirmed_fw_not_changed)
					],
				)
				self.dialog.open()

			else:
				toast('Cannot find filter {:}'.format(name))
				logger.warning('Cannot find filter {:} in current filterwheel'.format(name))
				if not_changed_action is not None:
					not_changed_action()
		else:
			# if we get here, we can go ahead
			self.change_filter(name)

	def confirmed_fw_changed(self, name, *args):
		self.dialog.dismiss()
		self.fw_changed(name)

	def confirmed_fw_not_changed(self, *args):
		self.dialog.dismiss()
		self.fw_not_changed()

	def change_filter(self, name, *args):
		try:
			self.device.select_position(
				position=self.filtermap()[name], 
				name=name, 
				success_action=partial(self.fw_changed, name),
				failure_action=self.fw_not_changed)
		except Exception as e:
			toast('problem moving EFW ({:})'.format(e))
			if self.not_changed_action is not None:
				self.not_changed_action()
			return

	def fw_changed(self, name, dt=None):
		# change has been done
		self.current_filter = name
		logger.debug('Filter changed to {:}'.format(name))
		if self.changed_action is not None:
			self.changed_action()

	def fw_not_changed(self):
		logger.debug('Filter not changed')
		if self.not_changed_action is not None:
			self.not_changed_action()

	def device_connected(self):
		# called by DeviceFamily when a device connects
		if self.device is not None:
			self.device.settings_have_changed()


class GenericFW(Device):

	family = StringProperty('FilterWheel')

	f1 = StringProperty('-')
	f2 = StringProperty('-')
	f3 = StringProperty('-')
	f4 = StringProperty('-')
	f5 = StringProperty('-')
	f6 = StringProperty('-')
	f7 = StringProperty('-')
	f8 = StringProperty('-')
	f9 = StringProperty('-')

	configurables = [
		('f1', {'name': 'position 1', 'options': _filter_types}),
		('f2', {'name': 'position 2', 'options': _filter_types}),
		('f3', {'name': 'position 3', 'options': _filter_types}),
		('f4', {'name': 'position 4', 'options': _filter_types}),
		('f5', {'name': 'position 5', 'options': _filter_types}),
		('f6', {'name': 'position 6', 'options': _filter_types}),
		('f7', {'name': 'position 7', 'options': _filter_types}),
		('f8', {'name': 'position 8', 'options': _filter_types}),
		('f9', {'name': 'position 9', 'options': _filter_types})
		]

	def settings_have_changed(self):
		
		# only transmit changes for connected devices
		if not self.connected:
			return
		
		# remove duplicates
		logger.debug('Checking for and removing duplicates')
		filts = set({})
		for pos in range(1, 10):
			fname = 'f{:}'.format(pos)
			f = getattr(self, fname)
			if f in filts:
				setattr(self, fname, '-')
			else:
				filts.add(f)
		Component.get('CaptureScript').filterwheel_changed()


class SingleFW(GenericFW):

	def connect(self):
		self.connected = True
		self.status = 'Single filter connected'

	def select_position(self, position=None, name=None, success_action=None, failure_action=None):
		if success_action is not None:
			success_action()


# class SimulatorFW(GenericFW):

# 	def select_position(self, position=None, name=None, success_action=None, failure_action=None):
# 		if success_action is not None:
# 			success_action()

# 	def connect(self):
# 		self.connected = True
# 		self.status = 'Filterwheel simulator active'


class ManualFW(GenericFW):

	def connect(self):
		self.connected = True
		self.status = 'Manual filterwheel'

	def select_position(self, position=None, name=None, success_action=None, failure_action=None):
		self.dialog = MDDialog(
			auto_dismiss=False,
			text='Change filter to {:} in position {:}'.format(name, position),
			buttons=[
				MDFlatButton(text="DONE", 
					text_color=self.app.theme_cls.primary_color,
					on_press=partial(self.post_dialog, success_action)),
				MDFlatButton(
					text="CANCEL", 
					text_color=self.app.theme_cls.primary_color,
					on_press=partial(self.post_dialog, failure_action))
			],
		)
		self.dialog.open()

	def post_dialog(self, action, *args):
		''' close dialog and perform action (i.e. success or failure to change)
		'''
		self.dialog.dismiss()
		if action is not None:
			action()

class SXFW(GenericFW):

	def connect(self):

		if self.connected:
			return

		self.connected = False
		logger.debug('importing HID')
		try:
			import hid
		except Exception as e:
			logger.warning('Cannot import HID ({:})'.format(e))
			self.status = 'Cannot import HID'
			return

		try:
			if hasattr(self, 'fw'):
				if self.fw:
					logger.debug('closing filterwheel')
					self.fw.close()
			else:
				self.fw = hid.device()
				logger.debug('got HID device')

		except Exception as e:
			logger.warning('Failed to get HID ({:})'.format(e))
			self.status = 'Failed to get HID device'
			return

		# note that if we open when already open, it fails
		try:
			logger.debug('opening SX EFW')
			self.fw.open(0x1278, 0x0920)
			self.connected = True
			self.status = 'SX filterwheel connected'
			logger.debug('successful')
		except Exception as e:
			logger.warning('fw.open failed ({:})'.format(e))
			self.status = 'fw.open failed'
			self.connected = False


	def select_position(self, position=None, name=None, success_action=None, failure_action=None):
		try:
			# move SX filterwheel
			logger.debug('Moving SX EFW to position {:}'.format(position))
			self.fw.write([position + 128, 0])
			# wait three seconds before informing controller it has been done
			logger.debug('success so setting up action {:}'.format(success_action))
			Clock.schedule_once(success_action, 3)
		except Exception as e:
			logger.debug('failed to select position ({:})'.format(e))
			# controller will handle this further
			if failure_action is not None:
				failure_action()

	# def on_close(self):
	#     if self.connected and self.efw:
	#         self.efw.close()


class ASCOMFW(GenericFW):

	driver = StringProperty(None)

	def disconnect(self):
		logger.debug('closing ASCOM filterwheel')
		self.fw.Connected = False

	def connect(self):

		if self.connected:
			return

		res = connect_to_ASCOM_device(device_type='FilterWheel', driver=self.driver)
		self.connected = res.get('connected', False)
		self.status = res['status']
		if self.connected:
			self.driver = res.get('driver', self.driver)
			self.fw = res['device']
		else:
			if 'exception' in res:
				self.status += ' ({:})'.format(res['exception'])

	def select_position(self, position=None, name=None, success_action=None, failure_action=None):
		try:
			# move filterwheel
			logger.debug('Moving ASCOM EFW to position {:}'.format(position))
			self.fw.Position = position
			# wait three seconds before informing controller it has been done
			logger.debug('success so setting up action {:}'.format(success_action))
			Clock.schedule_once(success_action, 3)
		except:
			# controller will handle this
			if failure_action is not None:
				failure_action()

