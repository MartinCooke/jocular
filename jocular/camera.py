''' Virtual and real camera classes, all subclasses of GenericCamera.
'''

import time
import array
import os
import glob
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from functools import partial
from skimage.transform import rescale, downscale_local_mean

import zwoasi as asi

from loguru import logger
from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.clock import Clock
from kivymd.toast.kivytoast import toast
from kivy.event import EventDispatcher

from jocular.component import Component
from jocular.devicemanager import Device, DeviceFamily
from jocular.utils import move_to_dir
from jocular.image import Image, ImageNotReadyException, is_fit

class Camera(Component, EventDispatcher, DeviceFamily):

	modes = { 
		'Watched dir': 'WatchedCamera', 
		'Simulator': 'SimulatorCamera',
		'ASCOM': 'ASCOMCamera',
		'SX (native)': 'SXCamera',
		'ASI (native)': 'ASICamera'
	}

	default_mode = 'Watched dir'
	family = 'Camera'

	def on_new_object(self, *args):
		logger.debug('-')
		if self.connected():
			self.device.on_new_object()

	def on_previous_object(self, *args):
		logger.debug('-')
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

	def on_close(self, *args):
		if self.connected():
			self.disconnect()	

#-------- Individual Camera modes here -------------------------------

class GenericCamera(Device):

	family = StringProperty('Camera')

	def on_new_object(self):
		self.last_capture = None

	def on_previous_object(self):
		self.last_capture = None

	def reset(self):
		self.last_capture = None

	def capture(self, **kwargs):
		return None

	def stop_capture(self):
		pass

	def get_image(self):
		if hasattr(self, 'last_capture'):
			return self.last_capture
		return None


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

	def capture(self, exposure=None, on_capture=None, on_failure=None,
		binning=None, internal_timing=False, return_image=False, is_bias=False):
		logger.info('Capturing in simulator expo {:}'.format(exposure))

		self.exposure = exposure
		if return_image:
			time.sleep(exposure)
			return self.get_camera_data()
			 
		self.capture_event = Clock.schedule_once(
			partial(self.check_exposure, on_capture), max(0.01, exposure))

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
				return im.get_image() 
			except Exception as e:
				print(e)
				pass
		# in the event of failure to get image, return noise
		return min(1, (self.exposure / 10)) * np.random.random((500, 500))


#-----------------


class ASICamera(GenericCamera):


	gain = NumericProperty(150)

	configurables = [
		('gain', {'name': 'gain setting', 'float': (1, 1000, 10),
				'help': ''})
	]


	def connect(self):

		if self.connected:
			return
			
		self.connected = False
		self.asicamera = None

		try:
			asipath = App.get_running_app().get_path('ASICamera2.dll')
			if not os.path.exists(asipath):
				self.status = 'Cannot find ASICamera2.dll in resources'
				return
		except Exception as e:
			self.status = 'asipath problem ({:})'.format(e)
			return

		try:
			asi.init(os.path.abspath(asipath))
		except Exception as e:
			self.status = 'asi.init ({:})'.format(e)
			return

		try:
			num_cameras = asi.get_num_cameras()
			if num_cameras == 0:
				self.status = 'no camera found'
				return
		except Exception as e:
			self.status = 'get_num_cameras ({:})'.format(e)
			return

		# get first camera found
		try:
			self.asicamera = asi.Camera(0)
		except Exception as e:
			self.status = 'assigning camera 0 ({:})'.format(e)
			return

		# if we want camera info we can get it using
		# camera_info = self._camera.get_camera_property()

		# set some properties: in future will be options
		try:
			self.asicamera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, 
				self.asicamera.get_controls()['BandWidth']['MinValue'])
			self.asicamera.disable_dark_subtract()
			self.asicamera.set_image_type(asi.ASI_IMG_RAW16)
			self.asicamera.set_control_value(asi.ASI_GAIN, 150)
		except Exception as e:
			self.status = 'setting values ({:})'.format(e)
			return

		whbi = self.asicamera.get_roi_format()
		self.status = 'ASI camera: {:} x {:}'.format(whbi[1], whbi[0])
		self.connected = True

	def capture(self, exposure=None, on_capture=None, on_failure=None,
		binning=None, internal_timing=False, return_image=False, is_bias=False):

		if is_bias:
			self.exposure = .001

		self.exposure = exposure
		self.on_failure = on_failure
		self.on_capture = on_capture

		# exposure is in microseconds
		self.asicamera.set_control_value(asi.ASI_EXPOSURE, int(self.exposure * 1e6))
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


class ASCOMCamera(GenericCamera):

	# configurables = {
	# 	'binning': {'options': ['None', '2 x 2', '3 x 3', '4 x 4'], 'help': 'some help text'},
	# 	'colour space': {'options': ['Mono', 'RGGB', 'GRGB', 'BGGR']},
	# 	'gain': {'range': (1, 1000), 'init': 150, 'int': True},
	# 	'cooling': {'range': (-40, 10), 'init': 0, 'int': True}
	# 	}

	driver = StringProperty(None)

	def on_close(self):
		# disconnect camera when closing Jocular
		if self.connected:
			logger.debug('closing ASCOM camera')
			self.camera.connected = False

	def connect(self):

		if self.connected:
			return
		
		self.connected = False
		self.camera = None

		if os.name != 'nt':
			self.status = 'Only works on Windows'
			return

		if self.driver is not None:
			# try to connect to the known driver
			try:
				self._connect(self.driver)
				return
			except Exception as e:
				self.status = 'Cannot connect to driver'
				logger.exception('Cannot connect to driver: ({:})'.format(e))

		# that didn't work, or driver is None, so choose
		try:
			import win32com.client
		except:
			self.status = 'Cannot import win30com.client; is ASCOM installed?'
			return

		try:
			chooser = win32com.client.Dispatch("ASCOM.Utilities.Chooser")
			chooser.DeviceType = 'Camera'
			self.driver = chooser.Choose(None)
		except Exception as e:
			self.status = 'Unable to choose driver'
			logger.exception('Unable to choose driver ({:})'.format(e))
			return

		# now try to connect to newly-chosen driver
		try:
			self._connect(self.driver)
			# need to fix this save
			# self.save()
		except Exception as e:
			self.status = 'Cannot connect: ({:})'.format(e)
			self.driver = None

	def _connect(self, driver):
		import win32com.client
		self.camera = win32com.client.Dispatch(driver)
		self.camera.Connected = True   # this is camera-specific prop (note upper case)
		logger.info('set connected on driver to True')
		self.connected = True    # note this is generic prop
		self.status = '{:}: {:} x {:}'.format(driver,
			self.camera.CameraXSize, self.camera.CameraYSize)

	def capture(self, exposure=None, on_capture=None, on_failure=None,
		binning=None, internal_timing=False, return_image=False, is_bias=False):

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
		im = np.array(self.camera.ImageArray)
		shape = [self.camera.CameraXSize, self.camera.CameraYSize]
		# needs to be transposed (to do)
		return im.reshape(shape) / 2 ** 16

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




''' ------------ SX cameras (just Lodestar for now)
'''

SX_CLEAR_PIXELS = 1
SX_READ_PIXELS_DELAYED = 2
SX_READ_PIXELS = 3
SX_RESET = 6

# convert int formats
def convert_int(x, from_type='uint16', to_type='uint8'):
	return np.array([x], dtype=from_type).view(dtype=to_type)


class SXCamera(GenericCamera):

	# configurables = {
	# 	'binning': {'options': ['None', '2 x 2', '3 x 3', '4 x 4']},
	# 	'colour space': {'options': ['Mono', 'RGGB', 'GRGB', 'BGGR']}
	# 	}

	def connect(self):
		''' Connect to Lodestar. For other SX cameras will need to change idProduct
			and check interface/endpoint details.
		'''

		if self.connected:
			return

		self.connected = False
		self.lodestar = None

		if os.name == 'nt':
			self.status = 'not yet supported on Windows'
			return

		try:
			import usb.core
			import usb.util
		except:
			self.status = 'no usb.core or usb.util'
			return

		try:
			self.lodestar = usb.core.find(idVendor=0x1278, idProduct=0x0507)
		except:
			self.status = 'cannot find Lodestar via usb.core.find'
			return

		if self.lodestar is None:
			self.status = 'cannot find Lodestar'
			return

		try:
			self.lodestar.get_active_configuration()
		except Exception as e:
			logger.exception('problem getting active configuration ({:})'.format(e))
			self.status = 'cannot get active configuration'
			self.clean_up()
			return

		self.connected = True

		# used in capture; note h // 2 for interlaced; needs changing for ultrastar no doubt
		self.width, self.height = 752, 580
		self.half_height = self.height // 2
		self.lswidth, self.mswidth = convert_int(self.width)
		self.lsheight, self.msheight = convert_int(self.half_height)

		self.status = 'SX Lodestar: 752 x 580 pixels'

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
			usb.util.dispose_resources(self.lodestar)
			logger.debug('Camera: disposed')

	def handle_failure(self, message='camera problem'):
		logger.error('Camera: handle_failure {:}'.format(message))
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
		binning=None, internal_timing=False, return_image=False, is_bias=False):

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
			self.handle_failure('camera not connected')
			return

		try:
			if internal_timing:
				logger.debug('SX internally-timed exposure {:3f}'.format(exposure))
				# do internal_timed exposure
				self.start_internal_exposure()
				if return_image:
					time.sleep(exposure)
					return self.lodestar_read()
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
			self.handle_failure('capture problem {:}'.format(e))

	def capture_bias(self, on_capture=None, on_failure=None):
		# special case for bias as it needs even and odd for internally-timed exposure
		self.on_capture = on_capture
		self.on_failure = on_failure
		try:
			expo = 0.001
			self.exposure_command(rows='odd', exposure=expo)
			time.sleep(expo)
			odd_pixels = self.lodestar.read(0x82, self.height * self.width, 10000)
			self.exposure_command(rows='even', exposure=expo)
			time.sleep(expo)
			even_pixels = self.lodestar.read(0x82, self.height * self.width, 10000)
			pool = ThreadPoolExecutor(3)
			future = pool.submit(partial(self.deinterlace, odd_pixels, even_pixels))  # thread handles read
			future.add_done_callback(self.image_ready)  # when future is done, call image_ready
		except Exception as e:
			self.handle_failure('problem in capture_bias {:}'.format(e))

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
			self.lodestar.write(1, params, 1000)
		except Exception as e:
			self.handle_failure('problem in exposure_command {:}'.format(e))

	def start_internal_exposure(self):
		try:
			self.exposure_command(rows='odd', exposure=self.exposure)
		except Exception as e:
			self.handle_failure('problem in start_internal_exposure {:}'.format(e))

	def start_external_exposure(self):
		try:
			self.lodestar.ctrl_transfer(0x40, SX_RESET, 0, 0, 0)
			self.lodestar.ctrl_transfer(0x40, SX_CLEAR_PIXELS, 0, 0, 0)
			logger.debug('started external exposure')
		except Exception as e:
			self.handle_failure('problem in start_external_exposure {:}'.format(e))

	def read_internal_exposure(self, *args):
		logger.debug('reading internal exposure')
		try:
			pool = ThreadPoolExecutor(3)
			future = pool.submit(self.lodestar_read)  # thread handles read
			future.add_done_callback(self.image_ready)  # when future is done, call image_ready
		except Exception as e:
			self.handle_failure('problem in read_internal_exposure {:}'.format(e))

	def read_external_exposure(self, *args):
		# Reads sensor at end of exposure time
		try:
			self.exposure_command(rows='odd')
			odds = self.lodestar.read(0x82, self.height * self.width, timeout=10000)
			self.exposure_command(rows='even')
			evens = self.lodestar.read(0x82, self.height * self.width, timeout=10000)

			# de-interlace to create final image
			self.last_capture = self.deinterlace(odds, evens)

			if self.on_capture is not None:
				self.on_capture()
		except Exception as e:
			self.handle_failure('problem in read_external_exposure {:}'.format(e))

	def lodestar_read(self):
		try:
			logger.debug('getting odd pixels')
			odd_pixels = self.lodestar.read(0x82, self.height * self.width, 10000)
			return self.deinterlace(odd_pixels, odd_pixels)
		except Exception as e:
			self.handle_failure('problem in lodestar_read {:}'.format(e))

	def image_ready(self, future):
		self.last_capture = future.result()  # store image read from sensor
		logger.debug('im stats min {:.4f} max {:.4f} mean {:.4f}'.format(
			np.min(self.last_capture), np.max(self.last_capture), np.mean(self.last_capture)))
		if self.on_capture is not None:
			Clock.schedule_once(self.on_capture, 0)

	def deinterlace(self, odd8, even8):
		'''De-interlaces Lodestar.'''

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

		# to test odd/even swap, uncomment above 2 lines and use these instead
		# pix[1::2, :] = odd
		# pix[::2, :] = even * (np.mean(odd) / np.mean(even))

		return pix / 2 ** 16




''' Watched camera: if controlled is set, only
	allows watched stuff through when user has pressed capture
'''


class WatchedCamera(GenericCamera):


	configurables = [
		('watched_dir', {
			'name': 'Watched directory', 
			'filechooser': 'dironly',
			'help': 'Choose a location for Jocular to monitor'}),
		('save_originals', {
			'name': 'save originals?',
			'switch': '',
			'help': 'Keep FITs that arrive in watched dir?'}),
		('controllable', {
			'name': 'control using Jocular?', 
			'switch': '',
			'help': 'Only monitor when capture control is active'}),
		('binning', {
			'name': 'bin',
			'options': ['no', '2 x 2', '3 x 3', '4 x 4'],
			'help': 'bin images that arrive in the watched dir'
			}),
		('bin_method', {
			'name': 'bin method',
			'options': ['mean', 'interpolate'],
			'help': 'simple average or interpolation'
			}),
		('colour_space', {
			'name': 'colour space',
			'options': ['mono', 'GBRG', 'BGGR', 'GRBG', 'RGGB'],
			'help': 'how to interpret pixel matrix'
			}),
		('exposure', {
			'name': 'exposure',
			'options': ['auto', 'from user'],
			'help': 'how to get exposure (auto: FITs/filename)'
			}),
		('filt', {
			'name': 'filter',
			'options': ['auto', 'from user', 'assume L'],
			'help': 'how to get filter information (ignored when debayering)'
			}),
		('sub_type', {
			'name': 'sub type',
			'options': ['auto', 'from user', 'assume light'],
			'help': 'how to get sub type'
			})
	]

	watched_dir = StringProperty(None)
	save_originals = BooleanProperty(True)
	controllable = BooleanProperty(False)
	binning = StringProperty('no')
	colour_space = StringProperty('mono')
	bin_method = StringProperty('mean')
	exposure = StringProperty('auto')
	filt = StringProperty('auto')
	sub_type = StringProperty('auto')
	temperature = StringProperty('auto')

	capturing = BooleanProperty(False)

	def connect(self):

		self.connected = False

		# if no watched dir try to create in data_dir
		if self.watched_dir is None:
			data_dir = App.get_running_app().data_dir
			if data_dir is not None:
				path = os.path.join(data_dir, 'watched')
				if os.path.exists(path):
					self.watched_dir = path
				else:
					logger.debug('creating watched dir {:}'.format(path))
					try:
						os.mkdir(path)
						self.watched_dir = path
					except Exception as e:
						logger.exception('cannot create watched dir ({:})'.format(e))
						
		# if we reach here and watched dir still none, ask user to select
		if self.watched_dir is None:
			self.status = 'Please configure a watched directory'
			self.connected = False
			return

		# check if we can write to watched directory			
		try:
			with open(os.path.join(self.watched_dir, '.written'), 'w') as f:
				f.write('can write')
		except:
			self.status = 'Cannot write to {:}'.format(self.watched_dir)
			self.connected = False
			return

		# start watcher
		self.watching_event = Clock.schedule_interval(self.watch, .2)
		self.connected = True
		self.capturing = True  #  make this a setting
		self.status = 'Watching {:}'.format(self.watched_dir)

	def disconnect(self):
		if hasattr(self, 'watching_event'):
			self.watching_event.cancel()
			self.flush()
		self.status = 'stopped monitoring'
		self.connected = False

	def on_new_object(self):
		self.flush()
		self.capturing = not self.controllable

	def on_previous_object(self):
		self.capturing = False

	def capture(self, **kwargs):
		self.capturing = True 
		
	def stop_capture(self, **kwargs):
		if self.controllable: 
			self.capturing = False 

	def flush(self):
		# move any FITs to 'unused' folder in watcher
		for path in self.get_possible_fits():
			move_to_dir(path, 'unused')

	def on_controllable(self, *args):
		self.capturing = not self.controllable


	def get_possible_fits(self):
		wdir = self.watched_dir
		return [os.path.join(wdir, d) for d in os.listdir(wdir) if is_fit(d)]

		''' in this version we'll look only in the watched directory itself
			rather than messing around with ASILive's craziness
		'''
		# asipath = os.path.join(wdir, 'ASILive_AutoSave', 'SingleFrame')
		# if os.path.exists(asipath):
		# 	for sdir in os.listdir(asipath):
		# 		pth = os.path.join(asipath, sdir)
		# 		if os.path.isdir(pth):
		# 			fits += [os.path.join(pth, d) for d in os.listdir(pth)]
		#return [f for f in fits if is_fit(os.path.basename(f))]

	def watch(self, dt):
		''' Monitor watched directory.
		'''

		for path in self.get_possible_fits():
			if self.capturing:

				try:
					s = Image(path, check_image_data=True)
				except ImageNotReadyException as e:
					# give it another chance on next event cycle
					logger.debug('image not ready {:} ({:})'.format(path, e))
				except Exception as e:
					logger.exception('other issue {:} ({:})'.format(path, e))
					toast('Invalid fits file')
					move_to_dir(path, 'invalid')

				try:
					self.process_sub(s, path)
				except Exception as e:
					logger.exception('error processing sub ({:})'.format(e))
					toast('error processing sub')
					move_to_dir(path, 'invalid')
			else:				
				move_to_dir(path, 'unused')


	def process_sub(self, s, path):
		''' Apply user-specified colour space conversion and binning. Also 
			check if image has 3 separated RGB planes and generate 3 separate
			subs. 
		'''

		bn = os.path.basename(path)
		im = s.get_image()
		imshape = str(im.shape)
		imstats = 'mean {:.4f}. range {:.4f}-{:.4f}'.format(np.mean(im), np.min(im), np.max(im))

		# check if image has 3 separate (RGB) planes
		if im.ndim == 3:
			logger.debug('sub RGB {:} {:}'.format(imshape, imstats))
			if im.shape[0] == 3:  # 3 x X x Y
				for i, chan in enumerate(['R', 'G', 'B']):
					self.save_mono(s, self.bin(im[i, :, :]), bn, filt=chan, sub_type='light')
			elif im.shape[2] == 3:  # X x Y x 3
				for i, chan in enumerate(['R', 'G', 'B']):
					self.save_mono(s, self.bin(im[:, :, i]), bn, filt=chan, sub_type='light')
			else:
				# shouldn't happen as im nims/shape is checked in Image
				logger.error('cannot process 3D image')

		# don't debayer if mono
		elif self.colour_space == 'mono':
			logger.debug('sub mono {:} {:}'.format(imshape, imstats))
			self.save_mono(s, self.bin(im), bn)

		# don't debayer if master calibration frame
		elif s.is_master:
			logger.debug('master mono {:} {:}'.format(imshape, imstats))
			self.save_mono(s, self.bin(im), bn)

		# debayer
		else:
			logger.debug('sub OSC {:} {:}'.format(imshape, imstats))
			from colour_demosaicing import demosaicing_CFA_Bayer_bilinear
			rgb = demosaicing_CFA_Bayer_bilinear(im, pattern=self.colour_space)
			# rescale to original intensity range
			cfa_min, cfa_max = np.min(im), np.max(im)
			rgb_min, rgb_max = np.min(rgb), np.max(rgb)
			rgb = cfa_min + (cfa_max - cfa_min) * (rgb - rgb_min) / (rgb_max - rgb_min)
			for i, chan in enumerate(['R', 'G', 'B']):
				self.save_mono(s, self.bin(rgb[:, :, i]), bn, filt=chan, sub_type='light')
 
		if self.save_originals:
			Component.get('ObjectIO').save_original(path)
		else:
			Component.get('ObjectIO').delete_file(path)


	def save_mono(self, sub, im, nm, filt=None, sub_type=None):
		''' Save image, binning if required, constructing details from Image instance
		'''

		cs = Component.get('CaptureScript')

		exposure = {
			'auto': sub.exposure,
			'from user': cs.get_exposure(),
		}[self.exposure]

		if filt is None:
			''' if from user, choose first filter in case of seq i.e. won't
				really work to use seq with watched
			'''
			filt = {
				'auto': sub.filter,
				'from user': cs.get_filters()[0],
				'assume L': 'L'
			}[self.filt]

		if sub_type is None:
			sub_type = {
				'auto': sub.sub_type,
				'from user': cs.get_sub_type(),
				'assume light': 'light'
			}[self.sub_type]

		temperature = {
			'auto': sub.temperature,
			'from user': Component.get('Session').temperature,
		}[self.temperature]


		# don't scale masters (check this!)
		if sub.is_master:
			Component.get('Calibrator').save_master(
				data=im,
				exposure=exposure, 
				filt=filt, 
				temperature=temperature, 
				sub_type=sub_type,
				nsubs=sub.nsubs)

		else:
			# send image to ObjectIO to save
			# rescale to 16-bit int
			im *= (2**16)
			Component.get('ObjectIO').new_sub(
				data=im.astype(np.uint16),
				name='{:}_{:}'.format(filt, nm),
				exposure=exposure,
				filt=filt,
				temperature=temperature,
				sub_type=sub_type)

		# signal to interface the values being used
		cs.set_external_details(exposure=exposure, sub_type=sub_type, filt=filt)

	def bin(self, im):
		b = self.binning
		if b == 'no':
			return im
		binfac = int(b[0]) # i.e. 2 x 2 gives 2, etc
		if self.bin_method == 'interpolation':
			return rescale(im, 1 / binfac, anti_aliasing=True, mode='constant', 
				preserve_range=True, multichannel=False)
		return downscale_local_mean(im, (binfac, binfac))


