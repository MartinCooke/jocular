''' Native driver for Starlight Xpress cameras. Currently supports Lodestar
	only. Use zadig to install libusb driver on Windows.

	to do:
		1. test on Windows using libusb directly accessible (via resources)
		2. implement Ultrastar code
		3. implement binning
		4. implement ROI for focusing?
'''

import time
import array
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import uuid

from loguru import logger
from kivy.properties import BooleanProperty, NumericProperty
from kivy.clock import Clock
from kivymd.toast.kivytoast import toast

from jocular.cameras.genericcamera import GenericCamera

SX_CLEAR_PIXELS = 1
SX_READ_PIXELS_DELAYED = 2
SX_READ_PIXELS = 3
SX_RESET = 6

# convert int formats
def convert_int(x, from_type='uint16', to_type='uint8'):
	return np.array([x], dtype=from_type).view(dtype=to_type)

class SXCamera(GenericCamera):

	configurables = [
		('internal_timing_threshold', {
			'name': 'use internal timing', 
			'float': (0, 2, .1),
			'help': 'use sensor timer for exposures shorter than this'}),
		('fast', {
			'name': 'fast mode', 
			'switch': '',
			'help': 'read odd rows and duplicate (only in focus/align/frame modes)'}),
	]

	fast = BooleanProperty(False)
	internal_timing_threshold = NumericProperty(1)

	sxcams = {
		'Lodestar': {'id': 0x0507, 'w': 752, 'h': 580, 'interlaced': True},
		'Ultrastar': {'id': 0x0525, 'w': 1392, 'h': 1040}
		}

	def connect(self):
		''' Connect to camera. Currently supports Lodestar only.
		'''

		if self.connected:
			return

		self.connected = False
		self.sxcamera = None
		self.model = None

		try:
			import usb.core
			import usb.util
		except:
			self.status = 'no usb.core or usb.util'
			return

		# find cam
		for nm, props in self.sxcams.items():
			cam = usb.core.find(idVendor=0x1278, idProduct=props['id'])
			if cam is not None:
				self.model = nm
				self.width = props['w']
				self.height = props['h']
				self.half_height = self.height // 2
				self.lswidth, self.mswidth = convert_int(self.width)
				self.lsheight, self.msheight = convert_int(self.half_height)
				self.interlaced = props.get('interlaced', False)
				self.sxcamera = cam
				logger.info('found {:}'.format(nm))
				break

		if self.sxcamera is None:
			self.status = 'cannot find any SX cameras'
			logger.info(self.status)
			return

		try:
			self.sxcamera.get_active_configuration()
		except Exception as e:
			logger.exception('problem getting active configuration ({:})'.format(e))
			self.status = 'cannot get active configuration'
			self.clean_up()
			return

		self.connected = True

		self.status = 'SX {:}: {:} x {:} pixels {:}'.format(
			self.model, self.width, self.height, '(interlaced)' if self.interlaced else '')

	def disconnect(self):
		''' Ensure any current exposure is stopped and dispose camera (important)
		'''
		if self.connected:
			self.stop_capture()
			self.clean_up()
			self.connected = False
			self.status = 'disconnected'
			logger.info('camera disconnected')

	def stop_capture(self):
		''' Called by capture when capture is stopped manually or as a result
			of any problem. Setting current_capture_id to None ensures that if
			the capture thread is sleeping, when it wakes up it will abort read
			of sensor
		'''
		self.current_capture_id = None

	def clean_up(self):
		''' On any problem, or camera disconnection, it is essential to
			dispose the camera resources otherwise we get permission 
			errors on trying to use device after reconnecting
		'''
		if hasattr(self, 'sxcamera'):
			import usb.util
			usb.util.dispose_resources(self.sxcamera)
			logger.debug('Camera: disposed')

	def handle_failure(self, message, exception=None):
		toast('SX camera problem: {:}'.format(message))
		if exception is not None:
			logger.exception('Camera: handle_failure {:} ({:})'.format(message, exception))
		self.connected = False   # to ensure reconnect if that was the issue
		self.last_capture = None
		self.stop_capture()
		try:
			self.clean_up()
		except Exception as e:
			logger.exception('Camera: problem disposing {:}'.format(e))
		finally:
			if self.params['on_failure'] is not None:
				self.params['on_failure']()

	@logger.catch()
	def capture(self, exposure=None, on_capture=None, on_failure=None, binning=None, 
		return_image=False, is_bias=False, is_faf=False):
		''' New version that is entirely 'futures' based for simplicity
		'''
		self.params = {
			'exposure': exposure,
			'on_capture': on_capture,
			'on_failure': on_failure,
			'binning': binning,
			'return_image': return_image,
			'is_faf': is_faf,
			'is_bias': is_bias}
		logger.debug('capture params {:}'.format(self.params))
		executor = ThreadPoolExecutor(max_workers=10)
		future = executor.submit(self._capture)
		future.add_done_callback(self.image_ready)
		logger.debug('set up future')

	def image_ready(self, future):
		im = future.result() # get
		if self.params['return_image']:
			return im
		self.last_capture = im
		logger.debug('im stats min {:.4f} max {:.4f}'.format(np.min(im), np.max(im)))
		if self.params['on_capture'] is not None:
			# not thread-safe to call it directly
			Clock.schedule_once(self.params['on_capture'], 0)

	@logger.catch()
	def _capture(self):
		''' Main capture routine
		'''

		''' give this capture an ID so we can compare it after sleep in case user
			has stopped capturing (in which case current_capture_id is set to None) or
			has started a new capture (in which case it is set to the new id)
		'''
		capture_id = uuid.uuid4()
		self.current_capture_id = capture_id

		timeout = 10000
		if self.params['is_bias']:
			''' special case for bias; we carry out 2 exact short exposures
			'''
			expo = 0.001
			self.exposure_command(rows='odd', exposure=expo)
			time.sleep(expo)
			odds = self.sxcamera.read(0x82, self.height * self.width, timeout)
			self.exposure_command(rows='even', exposure=expo)
			time.sleep(expo)
			evens = self.sxcamera.read(0x82, self.height * self.width, timeout)
			return self.interlace(odds, evens)

		# everything except bias
		expo = self.params['exposure']
		internal = expo < self.internal_timing_threshold
		logger.debug('SX exposure {:3f} (internal timing: {:})'.format(expo, internal))


		if internal:
			# tell camera to expose for required amount
			self.exposure_command(rows='odd', exposure=expo)
		else:
			# clear pixels to start exposure
			self.sxcamera.ctrl_transfer(0x40, SX_RESET, 0, 0, 0)
			self.sxcamera.ctrl_transfer(0x40, SX_CLEAR_PIXELS, 0, 0, 0)

		time.sleep(expo)

		''' if current_capture_id has changed since sleep, about
		'''
		if self.current_capture_id is None or self.current_capture_id != capture_id:
			logger.debug('capture id has changed so aborting capture of {:}'.format(capture_id))
			return

		if not internal:
			self.exposure_command(rows='odd')

		logger.trace('getting odd pixels')
		odds = self.sxcamera.read(0x82, self.height * self.width, timeout)

		# we can get a few more frames per second by copying even and odd
		if self.params['is_faf'] and self.fast:
			return self.interlace(odds, odds)

		# read even immediately (ie no new exposure)
		self.exposure_command(rows='even')
		logger.trace('getting even pixels')
		evens = self.sxcamera.read(0x82, self.height * self.width, timeout)
		return self.interlace(odds, evens)

	def interlace(self, odd8, even8):
		''' weave odd and even rows together and normalise to account for slight
			reading delays (de-zebra)
		'''
		# convert uint8 arrays to uint16 and reshape
		odd = np.frombuffer(odd8, dtype='uint16').reshape(self.half_height, self.width)
		even = np.frombuffer(even8, dtype='uint16').reshape(self.half_height, self.width)
		pix = np.zeros((self.height, self.width))
		pix[::2, :] = odd
		pix[1::2, :] = even * (np.mean(odd) / np.mean(even))
		return pix / 2 ** 16

	def exposure_command(self, rows='odd', exposure=None):
		''' build and execute command to expose the sensor; if exposure is provided,
			use internal timing
		'''

		try:
			rowcode = {'odd': 1, 'even': 2, 'all': 3}
			cmd = SX_READ_PIXELS if exposure is None else SX_READ_PIXELS_DELAYED
			params = array.array('B', [0x40, cmd, rowcode[rows], 0, 0, 0, 10, 0, 
				0, 0, 0, 0, self.lswidth, self.mswidth, self.lsheight, self.msheight, 1, 1])
			if exposure is not None:
				# add exposure details to command
				expo = int(exposure * 1000)  #  ms
				exp1, exp2, exp3, exp4 = convert_int(expo, from_type='uint32')
				params = params + array.array('B', [exp1, exp2, exp3, exp4])
			self.sxcamera.write(1, params, 1000)
		except Exception as e:
			self.handle_failure('exposure_command', e)

