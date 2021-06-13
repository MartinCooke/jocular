''' camera obeying ASCOM protocol (status: in development)
'''

import time
import numpy as np

from loguru import logger
from kivy.properties import StringProperty
from kivy.clock import Clock

from jocular.ascom import connect_to_ASCOM_device
from jocular.cameras.genericcamera import GenericCamera


class ASCOMCamera(GenericCamera):

	# configurables = {
	# 	'binning': {'options': ['None', '2 x 2', '3 x 3', '4 x 4'], 'help': 'some help text'},
	# 	'colour space': {'options': ['Mono', 'RGGB', 'GRGB', 'BGGR']},
	# 	'gain': {'range': (1, 1000), 'init': 150, 'int': True},
	# 	'cooling': {'range': (-40, 10), 'init': 0, 'int': True}
	# 	}

	driver = StringProperty(None)

	def on_close(self):
		self.disconnect()

	def disconnect(self):
		logger.debug('closing ASCOM camera')
		self.connected = False
		self.status = 'disconnected'
		self.camera.Connected = False  # closes ascom devic

	def connect(self):

		if self.connected:
			return

		res = connect_to_ASCOM_device(device_type='Camera', driver=self.driver)
		self.connected = res.get('connected', False)
		self.status = res['status']
		if self.connected:
			self.driver = res.get('driver', self.driver)
			self.camera = res['device']
			self.status += ': {:} x {:}'.format(
				self.camera.CameraXSize, self.camera.CameraYSize)

		else:
			if 'exception' in res:
				logger.exception('ascom connect problem ({:})'.format(res['exception']))


	def capture(self, exposure=None, on_capture=None, on_failure=None, is_faf=False,
		binning=None, return_image=False, is_bias=False):

		self.exposure = exposure
		self.on_failure = on_failure
		self.on_capture = on_capture

		if is_bias:
			self.exposure = .001
			openshutter = False
		else:
			openshutter = True

		self.camera.startExposure(self.exposure, openshutter) 

		if return_image:
			time.sleep(self.exposure)
			ready = False
			while not ready:
				time.sleep(.2)
				ready = self.camera.ImageReady
			return self.get_camera_data()

		self.capture_event = Clock.schedule_once(self.check_exposure, 
			max(0.2, self.exposure))

	def check_exposure(self, *arg):
		if self.camera.ImageReady:
			self.last_capture = self.get_camera_data()
			if self.on_capture is not None:
				Clock.schedule_once(self.on_capture, 0)
		else:
			self.capture_event = Clock.schedule_once(self.check_exposure, 0.2)

	def get_camera_data(self):
		# data is ready so get it, convert to correct size, and scale to range 0-1
		# assumes 16 bits for now
		im = np.array(self.camera.ImageArray).as_type(np.uint16) / 2**16
		return im.T

	def stop_capture(self):
		# Cancel any pending reads
		if hasattr(self, 'camera') and self.camera is not None:
			# occasionally objects to being aborted
			if self.camera.CanStopExposure:
				try:
					self.camera.StopExposure()
					logger.debug('stopped exposure')
				except Exception as e:
					logger.exception('unable to stop exposure ({:})'.format(e))
		if hasattr(self, 'capture_event'):
			self.capture_event.cancel()


