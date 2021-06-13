import time
import os
import numpy as np
import zwoasi as asi
from loguru import logger

from kivy.app import App
from kivy.properties import StringProperty, NumericProperty
from kivy.clock import Clock
#from kivymd.toast.kivytoast import toast
from jocular.oldtoast import toast

from jocular.cameras.genericcamera import GenericCamera

class ASICamera(GenericCamera):

	gain = NumericProperty(150)
	binning = StringProperty('no')

	configurables = [
		('gain', {'name': 'gain setting', 'float': (1, 1000, 10),
				'help': ''}),
		('binning', {
			'name': 'bin', 
			'options': ['no', '2 x 2', '3 x 3'],
			'help': ''})
	]

	def connect(self):

		if self.connected:
			return
			
		self.connected = False
		self.asicamera = None

		try:
			asipath = App.get_running_app().get_path('ASI')
			if not os.path.exists(asipath):
				self.status = 'Cannot find ASI library in resources'
				return
		except Exception as e:
			self.status = 'cannot find ASI library'
			logger.exception('asipath problem ({:})'.format(e))
			return

		try:
			asi.init(asipath)
		except asi.ZWO_Error as e:
			# we don't mind if it is already initialised but
			# we care about other errors
			if e == 'Library already initialized':
				pass
			else:
				self.status = 'cannot initialise camera'
				logger.exception('problem initialising ASI ({:})'.format(e))
				return
		except Exception as e:
			self.status = 'cannot initialise camera'
			logger.exception('problem initialising ASI ({:})'.format(e))
			return

		try:
			num_cameras = asi.get_num_cameras()
			if num_cameras == 0:
				self.status = 'no camera found'
				return
		except Exception as e:
			self.status = 'cannot get number of cameras'
			logger.exception('get_num_cameras ({:})'.format(e))
			return

		# get first camera found
		try:
			self.asicamera = asi.Camera(0)
		except Exception as e:
			self.status = 'error assigning camera 0'
			logger.exception('problem assigning camera 0 ({:})'.format(e))
			return

		# if we want camera info we can get it using
		# camera_info = self.asicamera.get_camera_property()

		# set some properties: in future will be options
		try:
			self.asicamera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, 
				self.asicamera.get_controls()['BandWidth']['MinValue'])
			self.asicamera.disable_dark_subtract()
			self.asicamera.set_image_type(asi.ASI_IMG_RAW16)
			self.asicamera.set_control_value(asi.ASI_GAIN, 150)
		except Exception as e:
			self.status = 'error setting camera values'
			logger.exception('error setting camera values ({:})'.format(e))
			return

		try:
			whbi = self.asicamera.get_roi_format()
			self.status = 'ASI camera: {:} x {:}'.format(whbi[1], whbi[0])
			self.connected = True
		except Exception as e:
			self.status = 'error getting camera sensor size'
			logger.exception('error getting camera sensor size ({:})'.format(e))


	def capture(self, exposure=None, on_capture=None, on_failure=None, is_faf=False,
		binning=None, return_image=False, is_bias=False):

		if is_bias:
			self.exposure = .001

		self.exposure = exposure
		self.on_failure = on_failure
		self.on_capture = on_capture

		# cancel any existing exposure
		try:
			self.asicamera.stop_exposure()
		except Exception as e:
			toast('error stopping exposure')
			logger.exception('error stopping exposure ({:})'.format(e))

		# set gain
		try:
			self.asicamera.set_control_value(asi.ASI_GAIN, self.gain)
		except Exception as e:
			toast('camera issue while setting gain')
			logger.exception('camera issue while setting gain ({:})'.format(e))

		# set binning
		if self.binning != 'no':
			try:
				self.asicamera.set_roi(bins=int(self.binning[0]))
			except ValueError as e:
				toast('camera issue while setting binning')
				logger.exception('illegal value for binning ({:})'.format(e))

		# exposure is in microseconds
		try:
			self.asicamera.set_control_value(asi.ASI_EXPOSURE, int(self.exposure * 1e6))
		except Exception as e:
			toast('camera issue while setting exposure')
			logger.exception('camera issue while setting exposure ({:})'.format(e))


		logger.debug('starting exposure')
		self.asicamera.start_exposure()

		if return_image:
			time.sleep(self.exposure)
			ready = False
			while not ready:
				time.sleep(.2)
				ready = self.asicamera.get_exposure_status() != asi.ASI_EXP_WORKING
			if self.asicamera.get_exposure_status() != asi.ASI_EXP_SUCCESS:
				self.handle_failure('capture problem')
				return
			return self.get_camera_data()
			 
		self.capture_event = Clock.schedule_once(self.check_exposure, 
			max(0.2, self.exposure))

	def get_camera_data(self):
		# from https://github.com/stevemarple/python-zwoasi/blob/master/zwoasi/__init__.py
		data = self.asicamera.get_data_after_exposure(None)
		whbi = self.asicamera.get_roi_format()
		shape = [whbi[1], whbi[0]]
		img = np.frombuffer(data, dtype=np.uint16)
		return img.reshape(shape) / 2 ** 16

	def check_exposure(self, *arg):
		# if ready, get image, otherwise schedule a call in 200ms
		if self.asicamera.get_exposure_status() != asi.ASI_EXP_WORKING:
			self.last_capture = self.get_camera_data()
			if self.on_capture is not None:
				Clock.schedule_once(self.on_capture, 0)
		else:
			self.capture_event = Clock.schedule_once(self.check_exposure, 0.2)

	def stop_capture(self):
		# Cancel any pending reads
		if hasattr(self, 'asicamera') and self.asicamera is not None:
			self.asicamera.stop_exposure()
		if hasattr(self, 'capture_event'):
			self.capture_event.cancel()

