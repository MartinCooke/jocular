''' Native suport for SX Lodestar camera. This only works reliably on the Mac
    at present.
'''

import time
import array
import os
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from functools import partial

from kivy.logger import Logger
from kivy.app import App
from kivy.properties import BooleanProperty
from kivy.clock import Clock

from jocular.component import Component

#  Lodestar (and other SX cameras) command set
SX_CLEAR_PIXELS = 1
SX_READ_PIXELS_DELAYED = 2
SX_READ_PIXELS = 3
SX_RESET = 6

# convert int formats
def convert_int(x, from_type='uint16', to_type='uint8'):
    return np.array([x], dtype=from_type).view(dtype=to_type)


class Camera(Component):

    camera_connected = BooleanProperty(False)

    def is_connected(self):
        return self.camera_connected

    def on_new_object(self):
        self.reset()

    def reset(self):
        self.connect()
        self.last_capture = None
        self.pause()

    def on_close(self):
        pass

    def pause(self):
        # Called by Capture when user pauses. We cancel any pending reads
        if hasattr(self, 'capture_event'):
            if (
                not self.internal_timing
            ):  # don't cancel reading if using internal timing (causes crash)
                self.capture_event.cancel()

    def clean_up(self):
        if hasattr(self, 'lodestar'):
            import usb.util

            usb.util.dispose_resources(self.lodestar)
            Logger.debug('Camera: disposed')

    def handle_failure(self, message='camera problem'):
        Logger.error('Camera: handle_failure {:}'.format(message))
        self.camera_connected = False  # to ensure reconnect if that was the issue
        self.last_capture = None
        try:
            self.clean_up()
        except Exception as e:
            Logger.warn('Camera: problem disposing {:}'.format(e))
            self.warn('disconnected?')
        finally:
            if self.on_failure is not None:
                self.on_failure()

    # generic capture routine
    def capture_sub(
        self,
        exposure=None,
        on_capture=None,
        on_failure=None,
        binning=None,
        internal_timing=False,
        return_image=False,
    ):

        # store these so they can be used without argument passing in futures etc
        self.on_capture = on_capture
        self.on_failure = on_failure
        self.exposure = exposure
        self.binning = binning
        self.internal_timing = internal_timing
        self.return_image = return_image
        self.last_capture = None

        # try to connect to camera (will handle if already connected)
        self.connect()

        if not self.camera_connected:
            self.handle_failure('camera not connected')
            return

        try:
            if internal_timing:
                # do internal_timed exposure
                self.start_internal_exposure()
                if return_image:
                    time.sleep(exposure)
                    return self.lodestar_read()
                else:
                    self.capture_event = Clock.schedule_once(
                        self.read_internal_exposure, max(0.1, exposure)
                    )
            else:
                # externally-timed
                self.start_external_exposure()
                if return_image:
                    time.sleep(exposure)
                    return self.read_external_exposure()
                else:
                    self.capture_event = Clock.schedule_once(
                        self.read_external_exposure, max(0.2, self.exposure)
                    )

        except Exception as e:
            self.handle_failure('capture problem {:}'.format(e))

    def capture_bias(self, on_capture=None, on_failure=None):
        # special case for bias as it needs even and odd for internally-timed exposure
        self.on_capture = on_capture
        self.on_failure = on_failure
        try:
            self.connect()
            expo = 0.001
            self.exposure_command(rows='odd', exposure=expo)
            time.sleep(expo)
            odd_pixels = self.lodestar.read(0x82, self.height * self.width, 10000)
            self.exposure_command(rows='even', exposure=expo)
            time.sleep(expo)
            even_pixels = self.lodestar.read(0x82, self.height * self.width, 10000)
            pool = ThreadPoolExecutor(3)
            future = pool.submit(
                partial(self.deinterlace, odd_pixels, even_pixels)
            )  # thread handles read
            future.add_done_callback(
                self.image_ready
            )  # when future is done, call image_ready
        except Exception as e:
            self.handle_failure('problem in capture_bias {:}'.format(e))

    def exposure_command(self, rows='odd', exposure=None):
        # generate write command for sensor
        try:
            rowcode = {'odd': 1, 'even': 2, 'all': 3}
            cmd = SX_READ_PIXELS if exposure is None else SX_READ_PIXELS_DELAYED
            params = array.array(
                'B',
                [
                    0x40, cmd, rowcode[rows], 0, 0, 0, 10, 0, 0, 0, 0, 0,
                    self.lswidth, self.mswidth, self.lsheight, self.msheight, 1, 1
                ],
            )
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
            Logger.trace('Camera: started external exposure')
        except Exception as e:
            self.handle_failure('problem in start_external_exposure {:}'.format(e))

    def read_internal_exposure(self, *args):
        try:
            pool = ThreadPoolExecutor(3)
            future = pool.submit(self.lodestar_read)  # thread handles read
            future.add_done_callback(
                self.image_ready
            )  # when future is done, call image_ready
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
            odd_pixels = self.lodestar.read(0x82, self.height * self.width, 10000)
            return self.deinterlace(odd_pixels, odd_pixels)
        except Exception as e:
            self.handle_failure('problem in lodestar_read {:}'.format(e))

    def image_ready(self, future):
        self.last_capture = future.result()  # store image read from sensor
        if self.on_capture is not None:
            Clock.schedule_once(self.on_capture, 0)

    def deinterlace(self, odd8, even8):
        '''De-interlaces Lodestar.'''

        # convert uint8 arrays to uint16 and reshape
        odd = np.frombuffer(odd8, dtype='uint16').reshape(self.half_height, self.width)
        even = np.frombuffer(even8, dtype='uint16').reshape(
            self.half_height, self.width
        )

        # generate new array (full height)
        pix = np.zeros((self.height, self.width))

        # insert odd rows
        pix[::2, :] = odd

        # insert even rows and normalise to account for slight delay in reading
        pix[1::2, :] = even * (np.mean(odd) / np.mean(even))

        return pix / 2 ** 16

    def connect(self):
        """Connect to Lodestar. For other cameras will need to change idProduct
        and check interface/endpoint details.
        """

        if self.camera_connected:
            return

        if os.name == 'nt':
            self.info('not supported')
            return

        # os.environ['PYUSB_DEBUG'] = 'debug'

        # try:
        #     import usb.backend.libusb0
        #     b = usb.backend.libusb0.get_backend()
        # except:
        #     self.warn('no usb.backend.libusb0')
        #     self.camera_connected = False
        #     return

        self.camera_connected = False

        try:
            import usb.core
        except:
            self.warn('no usb.core')
            return

        try:
            import usb.util
        except:
            self.warn('no usb.util')
            return

        self.lodestar = None
        try:
            self.lodestar = usb.core.find(idVendor=0x1278, idProduct=0x0507)
        except:
            self.warn('cannot find cam')

        #  next try libusb1
        if self.lodestar is None and os.name == 'nt':
            Logger.debug('Camera: looking for libusb on Windows')
            # try forcing backend (for windows)
            try:
                libusb_path = App.get_running_app().get_path('libusb')
                backend = usb.backend.libusb1.get_backend(
                    find_library=lambda x: libusb_path
                )
                self.lodestar = usb.core.find(
                    idVendor=0x1278, idProduct=0x0507, backend=backend
                )
            except:
                self.warn('cannot find w/ libusb1')

        if self.lodestar is None:
            self.info('not connected')
            return

        try:
            conf = self.lodestar.get_active_configuration()
        except Exception as e:
            Logger.warn('Camera: cannot get config ({:})'.format(e))
            self.warn('no config')
            self.clean_up()
            return

        # (might restrict this to Windows) try to claim interface
        # causes a crash on windows
        # interface = 0
        # if self.lodestar.is_kernel_driver_active(interface):
        #     Logger.debug('Camera: detaching and claiming interface')
        #     self.lodestar.detach_kernel_driver(interface)
        #     usb.util.claim_interface(self.lodestar, interface)

        # we don't use endpoint but for other cameras we will need code like this to
        #  find the endpoint (offline prior to implementation)

        # ep = camera[0].interfaces()[0].endpoints()[0]

        self.camera_connected = True
        self.info('SX Lodestar')

        # used in capture; note h // 2 for interlaced; needs changing for ultrastar no doubt
        self.width, self.height = 752, 580
        self.half_height = self.height // 2
        self.lswidth, self.mswidth = convert_int(self.width)
        self.lsheight, self.msheight = convert_int(self.half_height)
