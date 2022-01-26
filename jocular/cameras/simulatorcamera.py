import glob
import os
import time
from functools import partial
import numpy as np

from loguru import logger

from kivy.properties import StringProperty
from kivy.clock import Clock
from jocular.cameras.genericcamera import GenericCamera
from jocular.image import Image

#-------- Simulator Camera

class SimulatorCamera(GenericCamera):

	source = StringProperty('noise')

	configurables = [
		('source', {'name': 'How to generate', 'options': ['noise', 'capture'],
				'help': 'use noise or choose a random capture'})
	]

	def on_new_object(self):

		logger.info('Simulator on new object called')

		self.last_capture = None
		self.ims = None
		self.ROI = None

		''' choose capture directory at random
		'''
		if self.source == 'capture':
			sessions = glob.glob(os.path.join(self.app.get_path('captures'), '*'))
			if len(sessions) > 0:
				sesh = sessions[np.random.randint(len(sessions))]
				# choose within session
				dsos = glob.glob(os.path.join(sesh, '*'))
				if len(dsos) > 0:
					dso = dsos[np.random.randint(len(dsos))]
					# change this to work in path-independent way
					self.ims = glob.glob(dso+'/*.fit')
					if len(self.ims) == 0:
						self.ims = None
					else:
						logger.info('Using {:} for images'.format(self.ims))

	def connect(self):
		if self.source == 'capture':
			self.status = 'connected to captures'
		else:
			self.status = 'connected to random generator'
		self.connected = True
		self.on_new_object()

	def capture(self, exposure=None, on_capture=None, on_failure=None, is_faf=False,
		binning=None, return_image=False, is_bias=False):
		logger.info('Capturing in simulator expo {:}'.format(exposure))

		self.exposure = exposure
		if return_image:
			time.sleep(exposure)
			return self.get_camera_data()
			 
		self.capture_event = Clock.schedule_once(
			partial(self.check_exposure, on_capture), max(0.01, exposure))

	def get_capture_props(self):
		return {
			'camera': 'simulator'
		}

	def check_exposure(self, on_capture, dt):
		# if ready, get image, otherwise schedule a call in 200ms
		self.last_capture = self.get_camera_data()
		if on_capture is not None:
			Clock.schedule_once(on_capture, 0)

	def stop_capture(self):
		# Cancel any pending reads
		if hasattr(self, 'capture_event'):
			self.capture_event.cancel()

	def get_camera_data(self):
		if self.source == 'capture' and self.ims is not None:
			try:
				impath = self.ims[np.random.randint(len(self.ims))]
				logger.info('Serving fits image {:}'.format(impath))
				im = Image(impath)
				if self.ROI is None:
					return im.get_image() 
				xstart, width, ystart, height = self.ROI
				return im.get_image() [ystart: ystart + height, xstart: xstart + width]
			except Exception as e:
				logger.exception(e)
		# in the event of failure to get image, return noise
		return min(1, (self.exposure / 10)) * np.random.random((500, 500))

	def set_ROI(self, ROI):
		'''
		'''
		self.ROI = ROI


