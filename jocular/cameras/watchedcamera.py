''' Watched camera. Monitors a user-specified folder for new FITs images.
'''

import os
import numpy as np
from skimage.transform import rescale, downscale_local_mean

from loguru import logger
from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty
from kivy.clock import Clock

from jocular.component import Component
from jocular.utils import move_to_dir, toast
from jocular.image import Image, ImageNotReadyException, is_fit
from jocular.cameras.genericcamera import GenericCamera

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
			self.watched_dir is None
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
		if wdir is None or not os.path.exists(wdir):
			return []
		return [os.path.join(wdir, d) for d in os.listdir(wdir) if is_fit(d)]

	def watch(self, dt):
		''' Monitor watched directory.
		'''

		if self.watched_dir is None or not os.path.exists(self.watched_dir):
			return

		for path in self.get_possible_fits():
			s = None
			if self.capturing:

				try:
					s = Image(path, check_image_data=True)
				except ImageNotReadyException as e:
					# give it another chance on next event cycle
					# logger.debug('image not ready {:} ({:})'.format(path, e))
					pass
				except Exception as e:
					logger.exception('other issue {:} ({:})'.format(path, e))
					toast('Invalid fits file')
					move_to_dir(path, 'invalid')

				if s is not None:
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

		# add header info from sub into capture_props
		# note that this is just the essential info that
		# survives even after jocular has done its
		# processes
		capture_props = { p: getattr(sub, p) if hasattr(sub, p) else None 
			for p in ['gain', 'offset', 'camera', 'pixel_height', 'pixel_width', 'binning']}

		# if jocular has binned, changed pixel dims
		b = self.binning
		if b != 'no':
			binfac = int(b[0])
			if capture_props['pixel_height'] is not None:
				capture_props['pixel_height'] *= binfac
			if capture_props['pixel_width'] is not None:
				capture_props['pixel_width'] *= binfac


		capture_props['exposure'] = {
			'auto': sub.exposure,
			'from user': cs.get_exposure(),
		}[self.exposure]

		capture_props['filter'] = filt 
		if capture_props['filter'] is None:
			''' if from user, choose first filter in case of seq i.e. won't
				really work to use seq with watched
			'''
			capture_props['filter'] = {
				'auto': sub.filter,
				'from user': cs.get_filters()[0],
				'assume L': 'L'
			}[self.filt]

		capture_props['sub_type'] = sub_type
		if capture_props['sub_type'] is None:
			capture_props['sub_type'] = {
				'auto': sub.sub_type,
				'from user': cs.get_sub_type(),
				'assume light': 'light'
			}[self.sub_type]

		capture_props['temperature'] = {
			'auto': sub.temperature,
			'from user': Component.get('Session').temperature,
		}[self.temperature]

		# don't scale masters (check this!)
		if sub.is_master:
			capture_props['nsubs'] = sub.nsubs
			Component.get('Calibrator').save_master(
				data=im,
				capture_props=capture_props)

		else:
			# send image to ObjectIO to save
			# rescale to 16-bit int
			im *= (2**16)
			Component.get('ObjectIO').new_sub(
				data=im.astype(np.uint16),
				name='{:}_{:}'.format(capture_props['filter'], nm),
				capture_props=capture_props)

		# signal to interface the values being used
		cs.set_external_details(
			filt=capture_props['filter'],
			exposure=capture_props['exposure'],
			sub_type=capture_props['sub_type'])

	def bin(self, im):
		b = self.binning
		if b == 'no':
			return im
		binfac = int(b[0]) # i.e. 2 x 2 gives 2, etc
		if self.bin_method == 'interpolation':
			return rescale(im, 1 / binfac, anti_aliasing=True, mode='constant', 
				preserve_range=True, multichannel=False)
		return downscale_local_mean(im, (binfac, binfac))


