''' Native driver for Starlight Xpress cameras. Currently supports Lodestar
	only. Use zadig to install libusb driver on Windows.
'''

import time
import array
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from functools import partial

from loguru import logger
from kivy.properties import BooleanProperty
from kivy.clock import Clock

from jocular.cameras.genericcamera import GenericCamera
from jocular.utils import toast

SX_CLEAR_PIXELS = 1
SX_READ_PIXELS_DELAYED = 2
SX_READ_PIXELS = 3
SX_RESET = 6

# convert int formats
def convert_int(x, from_type='uint16', to_type='uint8'):
	return np.array([x], dtype=from_type).view(dtype=to_type)

class SXCamera(GenericCamera):

	lodestar = BooleanProperty(True)

	def connect(self):
		''' Connect to camera. Currently supports Lodestar only.
		'''

		if self.connected:
			return

		self.connected = False
		self.sxcamera = None

		try:
			import usb.core
			import usb.util
		except:
			self.status = 'no usb.core or usb.util'
			return

		# try to find Lodestar
		self.lodestar = False
		try:
			self.sxcamera = usb.core.find(idVendor=0x1278, idProduct=0x0507)
			if self.sxcamera is not None:
				self.lodestar = True
				logger.info('found Lodestar')
		except:
			pass

		if self.sxcamera is None:
			self.status = 'cannot find Lodestar'
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

		# used in capture; note h // 2 for interlaced; needs changing for ultrastar no doubt
		if self.lodestar:
			self.width, self.height = 752, 580
		else:
			self.width, self.height = 1392, 1040

		self.half_height = self.height // 2
		self.lswidth, self.mswidth = convert_int(self.width)
		self.lsheight, self.msheight = convert_int(self.half_height)

		self.status = 'SX Lodestar: {:} x {:} pixels'.format(
			self.width, self.height)

	def disconnect(self):
		if self.connected:
			self.connected = False
			self.status = 'disconnected'

	def stop_capture(self):
		# Cancel any pending reads
		if hasattr(self, 'capture_event'):
			if not self.internal_timing:  
				# don't cancel reading if using internal timing (causes crash on LS)
				self.capture_event.cancel()

	def clean_up(self):
		logger.debug('cleaning up')
		if hasattr(self, 'lodestar'):
			import usb.util
			usb.util.dispose_resources(self.sxcamera)
			logger.debug('Camera: disposed')

	def handle_failure(self, message, exception=None):
		toast('SX camera problem: {:}'.format(message))
		if exception is not None:
			logger.exception('Camera: handle_failure {:} ({:})'.format(message, exception))
		self.connected = False   # to ensure reconnect if that was the issue
		self.last_capture = None
		try:
			self.clean_up()
		except Exception as e:
			logger.exception('Camera: problem disposing {:}'.format(e))
		finally:
			if self.on_failure is not None:
				self.on_failure()

	def capture(self, exposure=None, on_capture=None, on_failure=None,
		binning=None, internal_timing=False, return_image=False, is_bias=False,
		is_faf=False):

		# is_faf not used in this version

		if is_bias:
			self.capture_bias(on_capture=on_capture, on_failure=on_failure)
			return

		logger.debug('Capturing from SX')
		# store these so they can be used without argument passing in futures etc
		self.on_capture = on_capture
		self.on_failure = on_failure
		self.exposure = exposure
		self.binning = binning
		self.internal_timing = internal_timing
		self.return_image = return_image
		self.last_capture = None

		# this in orig
		# self.connect()

		if not self.connected:
			toast('SX camera is not connected')
			# self.handle_failure('camera not connected')
			return

		try:
			if internal_timing:
				logger.debug('SX internally-timed exposure {:3f}'.format(exposure))
				# do internal_timed exposure
				self.start_internal_exposure()
				if return_image:
					time.sleep(exposure)
					return self.sxcamera_read()
				else:
					self.capture_event = Clock.schedule_once(
						self.read_internal_exposure, max(0.05, exposure)
					)
			else:
				# externally-timed
				logger.debug('SX external timed exposure {:3f}'.format(exposure))
				self.start_external_exposure()
				if return_image:
					time.sleep(exposure)
					return self.read_external_exposure()
				else:
					self.capture_event = Clock.schedule_once(
						self.read_external_exposure, max(0.05, self.exposure)
					)

		except Exception as e:
			self.handle_failure('capture', e)

	def capture_bias(self, on_capture=None, on_failure=None):
		# special case for bias as it needs even and odd for internally-timed exposure
		self.on_capture = on_capture
		self.on_failure = on_failure
		try:
			expo = 0.001
			self.exposure_command(rows='odd', exposure=expo)
			time.sleep(expo)
			odd_pixels = self.sxcamera.read(0x82, self.height * self.width, 10000)
			self.exposure_command(rows='even', exposure=expo)
			time.sleep(expo)
			even_pixels = self.sxcamera.read(0x82, self.height * self.width, 10000)
			pool = ThreadPoolExecutor(3)
			future = pool.submit(partial(self.deinterlace, odd_pixels, even_pixels))  # thread handles read
			future.add_done_callback(self.image_ready)  # when future is done, call image_ready
		except Exception as e:
			self.handle_failure('capture_bias', e)

	def exposure_command(self, rows='odd', exposure=None):
		# generate write command for sensor
		logger.debug('starting exposure')
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

	def start_internal_exposure(self):
		try:
			if self.lodestar:
				self.exposure_command(rows='odd', exposure=self.exposure)
		except Exception as e:
			self.handle_failure('start_internal_exposure', e)

	def start_external_exposure(self):
		try:
			self.sxcamera.ctrl_transfer(0x40, SX_RESET, 0, 0, 0)
			self.sxcamera.ctrl_transfer(0x40, SX_CLEAR_PIXELS, 0, 0, 0)
			logger.debug('started external exposure')
		except Exception as e:
			self.handle_failure('start_external_exposure', e)

	def read_internal_exposure(self, *args):
		logger.debug('reading internal exposure')
		try:
			pool = ThreadPoolExecutor(3)
			future = pool.submit(self.sxcamera_read)  # thread handles read
			future.add_done_callback(self.image_ready)  # when future is done, call image_ready
		except Exception as e:
			self.handle_failure('read_internal_exposure', e)

	def read_external_exposure(self, *args):
		''' read sensor at end of exposure time
		'''
		try:
			if self.lodestar:
				self.exposure_command(rows='odd')
				odds = self.sxcamera.read(0x82, self.height * self.width, timeout=10000)
				self.exposure_command(rows='even')
				evens = self.sxcamera.read(0x82, self.height * self.width, timeout=10000)
				self.last_capture = self.deinterlace(odds, evens)

			if self.on_capture is not None:
				self.on_capture()
		except Exception as e:
			self.handle_failure('read_external_exposure', e)

	def sxcamera_read(self):
		''' This is really the 'fast' read used for framing etc as it reads 
			odd rows and duplicates them; not convinced it is necessary any
			more because deinterlacing is fast; we can then get rid of the
			special case for bias above
		'''
		try:
			if self.lodestar:
				logger.debug('getting odd pixels')
				odd_pixels = self.sxcamera.read(0x82, self.height * self.width, 10000)
				return self.deinterlace(odd_pixels, odd_pixels)
		except Exception as e:
			self.handle_failure('sxcamera_read', e)

	def image_ready(self, future):
		self.last_capture = future.result()  # store image read from sensor
		logger.debug('im stats min {:.4f} max {:.4f} mean {:.4f}'.format(
			np.min(self.last_capture), np.max(self.last_capture), np.mean(self.last_capture)))
		if self.on_capture is not None:
			Clock.schedule_once(self.on_capture, 0)

	def get_capture_props(self):
		''' Any specific info for caller
		'''
		return {
			'camera': 'Lodestar X2',
			'pixel_width': 8.6,
			'pixel_height': 8.3
			}

	def get_pixel_height(self):
		return 8.3

	def deinterlace(self, odd8, even8):
		''' De-interlace Lodestar.
		'''

		logger.debug('deinterlacing')
		# convert uint8 arrays to uint16 and reshape
		odd = np.frombuffer(odd8, dtype='uint16').reshape(self.half_height, self.width)
		even = np.frombuffer(even8, dtype='uint16').reshape(self.half_height, self.width)

		# generate new array (full height)
		pix = np.zeros((self.height, self.width))

		# insert odd rows
		pix[::2, :] = odd

		# insert even rows and normalise to account for slight delay in reading
		pix[1::2, :] = even * (np.mean(odd) / np.mean(even))

		return pix / 2 ** 16



