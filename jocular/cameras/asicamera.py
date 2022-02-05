''' see https://github.com/python-zwoasi/python-zwoasi/blob/master/zwoasi/__init__.py
'''

import time
import os
import numpy as np
import zwoasi as asi
from loguru import logger

from kivy.app import App
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.clock import Clock

from jocular.cameras.genericcamera import GenericCamera
from jocular.utils import toast


class ASICamera(GenericCamera):

	gain = NumericProperty(150)
	offset = NumericProperty(1)
	binning = StringProperty('1 x 1')
	use_min_bandwidth = BooleanProperty(True)
	polling_interval = NumericProperty(.2)  # in seconds
	#ROI = StringProperty('full')
	#square_sensor = BooleanProperty(True)

	configurables = [
		('gain', {'name': 'gain setting', 'float': (0, 1000, 10),
				'help': ''}),
		('offset', {'name': 'offset', 'float': (1, 240, 1),
				'help': ''}),
		('binning', {
			'name': 'bin', 
			'options': ['1 x 1', '2 x 2', '3 x 3'],
			'help': ''}),
		# ('ROI', {
		# 	'name': 'ROI',
		# 	'options': ['custom', 'full', 'three-quarters', 'two-thirds', 'half', 'third', 'quarter'],
		# 	'help': 'region of interest relative to full frame'
		# 	}),
		# ('square_sensor', {
		# 	'name': 'equalise aspect ratio',
		# 	'switch': '',
		# 	'help': 'make sensor width and height equal'
		# 	}),
		('polling_interval', {
			'name': 'polling interval', 
			'float': (.05, 1, .05),
			'help': 'how often to check for exposure'}),
		('use_min_bandwidth', {
			'name': 'minimise USB bandwidth',
			'switch': ''
			})
	]

	def _set_configurable(self, prop, vals):
		self.configurables = [(k, vals if k==prop else v) for k, v in self.configurables]

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
			if str(e).strip() == 'Library already initialized':
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

		# examine camera properties
		try:
			self.camera_props = self.asicamera.get_camera_property()
			for k, v in self.camera_props.items():
				logger.info('{:15s} {:}'.format(k, v))
		except Exception as e:
			self.status = 'error getting camera properties'
			logger.exception('error getting camera properties ({:})'.format(e))
			return

		# list camera controls
		try:
			self.camera_controls = self.asicamera.get_controls()
			for k, v in self.camera_controls.items():
				logger.info('{:15s} {:}'.format(k, v))
		except Exception as e:
			self.status = 'error getting camera controls'
			logger.exception('error getting camera controls ({:})'.format(e))
			return

		# get bin options
		try:
			binops = ['{:1d} x {:1d}'.format(b, b) for b in self.camera_props['SupportedBins']]
			self._set_configurable('binning', {
				'name': 'binning', 
				'options': binops})
		except Exception as e:
			logger.warning('cannot get bin options ({:})'.format(e))
			binops = ['1 x 1']

		# get gain options
		try:
			gainprops = self.camera_controls['Gain']
			ming, maxg = gainprops['MinValue'], gainprops['MaxValue']
			self._set_configurable('gain', {
				'name': 'gain setting', 
				'float': (ming, maxg, 10)})
		except Exception as e:
			self.status = 'cannot get gain options'
			logger.exception('cannot get gain options ({:})'.format(e))
			return

		# get offset options
		try:
			offsetprops = self.camera_controls['Offset']
			ming, maxg = offsetprops['MinValue'], offsetprops['MaxValue']
			self._set_configurable('offset', {
				'name': 'offset', 
				'float': (ming, maxg, 1)})
		except Exception as e:
			self.status = 'cannot get gain options'
			logger.exception('cannot get gain options ({:})'.format(e))
			return

		# set some properties
		try:
			if self.use_min_bandwidth:
				self.asicamera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, 
					self.camera_controls['BandWidth']['MinValue'])
			self.asicamera.disable_dark_subtract()
			self.asicamera.set_image_type(asi.ASI_IMG_RAW16)
		except Exception as e:
			self.status = 'error setting camera values'
			logger.exception('error setting camera values ({:})'.format(e))
			return

		try:
			# whbi = self.asicamera.get_roi_format()
			#if 'temperature' in self.camera_controls:
			temp = self.asicamera.get_control_value(asi.ASI_TEMPERATURE)[0]
			#else:
			#	temp = None
			self.status = '{:}: {:} x {:} {:}'.format(
				self.camera_props.get('Name', 'anon'),
				self.camera_props.get('MaxWidth', 0),
				self.camera_props.get('MaxHeight', 0),
				'' if temp is None else '{:.0f}C'.format(temp / 10))
				
			self.connected = True
			logger.info(self.status)
		except Exception as e:
			self.status = 'error getting camera sensor size'
			logger.exception('error getting camera sensor size ({:})'.format(e))

		# set initial ROI, binning etc
		self.on_gain()
		self.on_offset()
		self.set_ROI(ROI=None)


	def capture(self, exposure=None, on_capture=None, on_failure=None, is_faf=False,
		binning=None, return_image=False, is_bias=False):

		if is_bias:
			self.exposure = int(self.camera_controls['Exposure']['MinValue']) / 1e6
		else:
			self.exposure = exposure

		self.on_failure = on_failure
		self.on_capture = on_capture

		# cancel any existing exposure
		try:
			self.asicamera.stop_exposure()
		except Exception as e:
			toast('error stopping exposure')
			logger.exception('error stopping exposure ({:})'.format(e))

		# exposure is in microseconds (this is fast to set)
		try:
			self.asicamera.set_control_value(
				asi.ASI_EXPOSURE, int(self.exposure * 1e6))
			# logger.info('setting exposure to {:}'.format(self.exposure))
		except Exception as e:
			toast('camera issue while setting exposure')
			logger.exception('camera issue while setting exposure ({:})'.format(e))

		self.asicamera.start_exposure()

		if return_image:
			time.sleep(self.exposure)
			ready = False
			while not ready:
				time.sleep(self.polling_interval)
				ready = self.asicamera.get_exposure_status() != asi.ASI_EXP_WORKING
			if self.asicamera.get_exposure_status() != asi.ASI_EXP_SUCCESS:
				self.handle_failure('capture problem')
				return
			cd = self.get_camera_data()
			if cd is None:
				self.handle_failure('capture problem')
			return cd
			 
		self.capture_event = Clock.schedule_once(self.check_exposure, 
			max(self.polling_interval, self.exposure))


	def set_ROI(self, ROI=None):
		''' ROI has changed
		'''
		if not self.connected:
			return

		bins=int(self.binning[0])

		# if ROI is unclicked, use settings on interface
		if ROI is None:
			self.asicamera.set_roi(bins=bins)
			logger.trace('ROI changed: to full sensor, bin {:} '.format(bins))
			return

		# use ROI, which assumes binning already applied during framing
		start_x, width, start_y, height = ROI
		width = 8 * (width // 8)   # must be mult of 8
		height = 2 * (height // 2) # and of 2

		# note that width is a mult of 8 and height is mult of 2
		self.asicamera.set_roi(
			bins=bins,
			start_x=start_x,
			start_y=start_y,
			width=width,
			height=height)

		logger.trace('ROI changed: bins {:} start_x {:} start_y {:} width {:} height {:}'.format(
			bins, start_x, start_y, width, height))


	def on_binning(self, *args):
		''' If user changes binning then ROI is reset to None
			for the moment at least
		'''
		self.set_ROI(ROI=None)

		
	def on_gain(self, *args):
		if not self.connected:
			return
		try:
			self.asicamera.set_control_value(asi.ASI_GAIN, int(self.gain))
			logger.info('setting gain to {:.0f}'.format(self.gain))
		except Exception as e:
			toast('problem setting gain')
			logger.exception('problem setting gain ({:})'.format(e))

	def on_offset(self, *args):
		if not self.connected:
			return
		try:
			''' apparently offset is called brightness
			'''  
			self.asicamera.set_control_value(asi.ASI_BRIGHTNESS, int(self.offset))
			logger.info('setting offset to {:.0f}'.format(self.offset))
		except Exception as e:
			toast('problem setting offset')
			logger.exception('problem setting offset ({:})'.format(e))

	def get_camera_data(self):
		''' see capture method in
			https://github.com/stevemarple/python-zwoasi/blob/master/zwoasi/__init__.py
		'''

		# sometimes gets a timeout for reasons that are not clear
		try:
			data = self.asicamera.get_data_after_exposure(None)
			whbi = self.asicamera.get_roi_format()
			shape = [whbi[1], whbi[0]]
			img = np.frombuffer(data, dtype=np.uint16)
			return img.reshape(shape) / 2 ** 16
		except Exception as e:
			logger.warning('{:}'.format(e))
			return None


	def get_capture_props(self):
		''' return dict of props such as gain, ROI etc
			(these get converted to uppercase in FITs)
		'''
		start_x, start_y, width, height = self.asicamera.get_roi()
		return {
			'camera': self.camera_props.get('Name', 'anon'),
			'gain': self.gain,
			'offset': self.offset,
			'binning': int(self.binning[0]),
			#'ROI': self.ROI,
			#'equal_aspect': self.square_sensor,
			'temperature': self.get_sensor_temperature(),
			'ROI_x': start_x,
			'ROI_y': start_y,
			'ROI_w': width,
			'ROI_h': height,
			'pixel_width': self.camera_props['PixelSize'], # this before binning I think
			'pixel_height': self.camera_props['PixelSize']
			}

	def get_pixel_height(self):
		try:
			return self.camera_props['PixelSize'] * int(self.binning[0])
		except:
			return None

	def get_sensor_temperature(self):
		try:
			return self.asicamera.get_control_value(asi.ASI_TEMPERATURE)[0] / 10
		except Exception as e:
			return None

	def check_exposure(self, *arg):
		# if ready, get image, otherwise schedule next check 
		if self.asicamera.get_exposure_status() != asi.ASI_EXP_WORKING:
			self.last_capture = self.get_camera_data()
			if self.last_capture is not None:
				# got data, so schedule callback
				if self.on_capture is not None:
					Clock.schedule_once(self.on_capture, 0)
		else:
			self.capture_event = Clock.schedule_once(
				self.check_exposure, 
				self.polling_interval)

	def stop_capture(self):
		# Cancel any pending reads
		if hasattr(self, 'asicamera') and self.asicamera is not None:
			self.asicamera.stop_exposure()
		if hasattr(self, 'capture_event'):
			self.capture_event.cancel()

