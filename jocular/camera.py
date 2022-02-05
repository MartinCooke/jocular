''' Camera component. All work is done via camera subclasses.
'''

from kivy.event import EventDispatcher

from jocular.component import Component
from jocular.device import DeviceFamily

from jocular.cameras.watchedcamera import WatchedCamera
from jocular.cameras.sxcamera import SXCamera
from jocular.cameras.ultrastar import SXUltrastarCamera
# from jocular.cameras.ascomcamera import ASCOMCamera
from jocular.cameras.simulatorcamera import SimulatorCamera
from jocular.cameras.asicamera import ASICamera

class Camera(Component, EventDispatcher, DeviceFamily):

	modes = { 
		'Watched dir': 'WatchedCamera', 
		'Simulator': 'SimulatorCamera',
		#'ASCOM': 'ASCOMCamera',
		'ASI': 'ASICamera',
		'SX Lodestar': 'SXCamera',
		'SX Ultrastar': 'SXUltrastarCamera'
	}

	default_mode = 'Watched dir'
	family = 'Camera'

	def on_new_object(self, *args):
		if self.connected():
			self.device.on_new_object()

	def on_previous_object(self, *args):
		if self.connected():
			self.device.on_previous_object()

	def capture_sub(self, **kwargs):
		if self.connected():
			return self.device.capture(**kwargs)

	def stop_capture(self):
		if self.connected():
			self.device.stop_capture()

	def get_image(self):
		if self.connected():
			return self.device.get_image()

	def get_pixel_height(self):
		if self.connected():
			return self.device.get_pixel_height()

	def get_sensor_temperature(self):
		if self.connected():
			return self.device.get_sensor_temperature()


	def set_ROI(self, ROI):
		if self.connected():
			self.device.set_ROI(ROI)

	def get_capture_props(self):
		if self.connected():
			return self.device.get_capture_props()

	def on_close(self, *args):
		if self.connected():
			self.disconnect()	
